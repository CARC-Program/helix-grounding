"""
Command-line entry point: ``helix-bom review my_bom.csv --budget 50``.

A CLI rather than a web upload, for a specific reason: the people this is for
already have a terminal open next to their EDA tool, and a file on disk is the
artifact they already have. A web form would ask them to do more work than the
tool saves.

What this prints is chosen to survive being pasted into an email, because that
is what somebody does with a review they want a second opinion on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import BOMReviewAgent, DesignConstraints
from .ingest import load_bom

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
EXIT_OK, EXIT_FINDINGS, EXIT_UNREADABLE = 0, 1, 2


def _parse_enclosure(text: str) -> tuple[float, float, float]:
    """Accept 100x80x25, 100X80X25, or 100*80*25 — people type all three."""
    parts = [p for p in text.replace("X", "x").replace("*", "x").split("x") if p]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"expected WIDTHxDEPTHxHEIGHT in mm, e.g. 100x80x25 (got {text!r})"
        )
    try:
        width, depth, height = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"enclosure dimensions must be numbers in mm (got {text!r})"
        )
    return width, depth, height


def _render(components, report, result, constraints, show_all_columns: bool) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"BOM review — {report.source}")
    add("=" * 60)
    add("")

    # --- what was read -------------------------------------------------
    add(f"Read {report.rows_used} line item(s), "
        f"{sum(c.quantity for c in components)} part(s) total.")
    if report.header_row > 1:
        add(f"  Header found on line {report.header_row} "
            f"({report.header_row - 1} preamble line(s) skipped).")
    if report.rows_skipped_dnp:
        add(f"  {report.rows_skipped_dnp} row(s) excluded as do-not-populate.")
    add("")

    add("Columns used:")
    for field_name, source in report.mapped.items():
        note = report.ambiguous.get(source)
        add(f"  {source:<28} -> {field_name}" + (f"   [!] {note}" if note else ""))
    if show_all_columns and report.unmapped_headers:
        add("")
        add("Columns ignored (no matching field):")
        for header in report.unmapped_headers:
            add(f"  {header}")
    add("")

    if report.problems:
        add(f"Cells that could not be read ({len(report.problems)}):")
        for problem in report.problems[:10]:
            add(f"  {problem}")
        if len(report.problems) > 10:
            add(f"  ...and {len(report.problems) - 10} more.")
        add("")

    # --- totals --------------------------------------------------------
    if any(c.cost_usd for c in components):
        add(f"BOM total: ${result.total_cost_usd:,.2f}"
            + (f"  (budget ${constraints.budget_usd:,.2f})"
               if constraints.budget_usd else ""))
    if any(c.power_draw_w for c in components):
        add(f"Power draw: {result.total_power_w:.1f}W"
            + (f"  (budget {constraints.power_budget_w:.1f}W)"
               if constraints.power_budget_w else ""))
    add("")

    # --- findings ------------------------------------------------------
    add("Findings:")
    for finding in sorted(result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9)):
        add(f"  [{finding.severity.upper()}] {finding.message}")
    add("")

    # --- what did not run ----------------------------------------------
    # Deliberately last and unmissable. A reader who stops before this point
    # has the wrong impression of how much was checked, so it is never
    # collapsed into a count or hidden behind a flag.
    if result.skipped_checks:
        add(f"NOT CHECKED ({len(result.skipped_checks)}):")
        for skipped in result.skipped_checks:
            add(f"  {skipped.name}")
            add(f"      {skipped.reason}")
        add("")
        add("  These are not passes. Supply the missing columns to check them.")
    else:
        add("All checks ran against the submitted data.")

    return "\n".join(lines)


def _as_dict(components, report, result) -> dict:
    return {
        "source": report.source,
        "ingest": {
            "header_row": report.header_row,
            "delimiter": report.delimiter,
            "rows_used": report.rows_used,
            "rows_skipped_dnp": report.rows_skipped_dnp,
            "columns_mapped": report.mapped,
            "columns_ambiguous": report.ambiguous,
            "columns_ignored": report.unmapped_headers,
            "fields_missing": report.missing_fields,
            "problems": [
                {"row": p.row, "column": p.column, "value": p.value, "problem": p.problem}
                for p in report.problems
            ],
        },
        "totals": {
            "line_items": len(components),
            "parts": sum(c.quantity for c in components),
            "cost_usd": round(result.total_cost_usd, 2),
            "power_w": round(result.total_power_w, 3),
        },
        "over_budget": result.over_budget,
        "over_power_budget": result.over_power_budget,
        "complete": result.is_complete,
        "findings": [{"severity": f.severity, "message": f.message} for f in result.findings],
        "skipped_checks": [{"name": s.name, "reason": s.reason} for s in result.skipped_checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="helix-bom",
        description="Review a bill of materials for budget, power, fit and "
                    "supply-chain risk. Reports what it could not check as "
                    "clearly as what it could.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="review a BOM CSV file")
    review.add_argument("file", type=Path, help="BOM export (CSV, from KiCad, Altium, or a spreadsheet)")
    review.add_argument("--budget", type=float, default=0.0, metavar="USD",
                        help="cost budget for the whole BOM")
    review.add_argument("--enclosure", type=_parse_enclosure, metavar="WxDxH",
                        help="enclosure envelope in mm, e.g. 100x80x25")
    review.add_argument("--power", type=float, default=0.0, metavar="WATTS",
                        help="power budget in watts")
    review.add_argument("--json", action="store_true", help="emit JSON instead of text")
    review.add_argument("--show-ignored-columns", action="store_true",
                        help="list columns that matched no known field")
    review.add_argument("--strict", action="store_true",
                        help="exit non-zero if any check could not run")

    args = parser.parse_args(argv)

    try:
        components, report = load_bom(args.file)
    except FileNotFoundError:
        print(f"helix-bom: no such file: {args.file}", file=sys.stderr)
        return EXIT_UNREADABLE
    except ValueError as exc:
        print(f"helix-bom: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if not components:
        print(f"helix-bom: {report.source} has a header but no data rows.", file=sys.stderr)
        return EXIT_UNREADABLE

    width, depth, height = args.enclosure or (0.0, 0.0, 0.0)
    constraints = DesignConstraints(
        budget_usd=args.budget,
        enclosure_width_mm=width,
        enclosure_depth_mm=depth,
        enclosure_height_mm=height,
        power_budget_w=args.power,
    )
    # The ingest report knows which columns the file actually had, which
    # is better information than the agent can infer from the values.
    result = BOMReviewAgent().review(
        components, constraints, available_fields=set(report.mapped)
    )

    if args.json:
        print(json.dumps(_as_dict(components, report, result), indent=2))
    else:
        print(_render(components, report, result, constraints, args.show_ignored_columns))

    if any(f.severity == "critical" for f in result.findings):
        return EXIT_FINDINGS
    if args.strict and not result.is_complete:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
