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
SAMPLE_BOM = Path(__file__).parent / "examples" / "sample_bom.csv"
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
    if report.rows_skipped_totals:
        add(f"  {report.rows_skipped_totals} summary/total row(s) excluded.")
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


def _describe_value(value: str) -> str:
    """Describe a cell's shape without repeating its contents.

    A diagnostic is useless if nobody dares run it. The whole point of the
    report is that it can be pasted into a public bug tracker, and a cell that
    failed to parse may be a part number, a supplier code or a price -- the
    exact things a company will not publish. Its *shape* is what debugs the
    parser anyway: length, whether it held digits, whether separators were
    present. The content adds nothing a maintainer needs.
    """
    if not value:
        return "empty"
    kinds = []
    if any(c.isdigit() for c in value):
        kinds.append("digits")
    if any(c.isalpha() for c in value):
        kinds.append("letters")
    for symbol, name in ((",", "comma"), (".", "dot"), ("$", "currency symbol"),
                         ("€", "currency symbol"), ("£", "currency symbol"),
                         ("%", "percent"), ("(", "bracket")):
        if symbol in value and name not in kinds:
            kinds.append(name)
    return f"{len(value)} chars, " + (", ".join(kinds) if kinds else "no digits or letters")


def _render_diagnostic(report, result, components) -> str:
    """A bug report a company can paste in public.

    Structure only: what the file looked like and what the parser made of it.
    No part numbers, no prices, no quantities, no descriptions.
    """
    import platform
    import sys as _sys

    lines: list[str] = []
    add = lines.append

    add("helix-bom diagnostic report")
    add("=" * 60)
    add("")
    add("Safe to paste into a public bug report. Contains no component data —")
    add("no part numbers, prices, quantities or descriptions. Column *headings*")
    add("are included because the parser matches on them; if a heading itself")
    add("names something confidential, edit it before posting.")
    add("")

    try:
        from importlib.metadata import version
        installed = version("helix-grounding")
    except Exception:
        installed = "unknown (running from source?)"

    add(f"helix-grounding   {installed}")
    add(f"python            {_sys.version.split()[0]}")
    add(f"platform          {platform.system()} {platform.machine()}")
    add("")

    add("file")
    add(f"  size            {report.size_bytes:,} bytes")
    add(f"  encoding        {report.encoding}")
    add(f"  delimiter       {report.delimiter!r}")
    add(f"  header row      line {report.header_row} of {report.total_rows}")
    add(f"  data rows       {report.rows_read} read, {report.rows_used} used")
    if report.rows_skipped_dnp:
        add(f"  excluded        {report.rows_skipped_dnp} do-not-populate")
    if report.rows_skipped_totals:
        add(f"  excluded        {report.rows_skipped_totals} summary rows")
    add(f"  number format   decimal separator {report.decimal_separator!r}")
    add("")

    add(f"headers found ({len(report.headers)})")
    for index, heading in enumerate(report.headers, start=1):
        add(f"  {index:>2}  {heading}")
    add("")

    add(f"columns matched ({len(report.mapped)})")
    for field_name, source in report.mapped.items():
        flag = "  [ambiguous]" if source in report.ambiguous else ""
        add(f"  {source:<28} -> {field_name}{flag}")
    if report.unmapped_headers:
        add("")
        add(f"columns ignored ({len(report.unmapped_headers)})")
        for heading in report.unmapped_headers:
            add(f"  {heading}")
    add("")

    ran = BOMReviewAgent.TOTAL_CHECKS - len(result.skipped_checks)
    add(f"checks that could run   {ran} of {BOMReviewAgent.TOTAL_CHECKS}")
    for skipped in result.skipped_checks:
        add(f"  skipped  {skipped.name}")
    add("")

    if report.problems:
        add(f"cells that could not be read ({len(report.problems)})")
        for problem in report.problems[:20]:
            add(f"  row {problem.row}, column {problem.column!r}: "
                f"{_describe_value(problem.value)}")
        if len(report.problems) > 20:
            add(f"  ...and {len(report.problems) - 20} more")
    else:
        add("cells that could not be read   none")
    add("")

    add("What did it get wrong? Describe the expected result below —")
    add("a corrected total, the right column mapping, whatever it missed.")

    return "\n".join(lines)


def _as_dict(components, report, result) -> dict:
    return {
        "source": report.source,
        "ingest": {
            "header_row": report.header_row,
            "delimiter": report.delimiter,
            "rows_used": report.rows_used,
            "rows_skipped_dnp": report.rows_skipped_dnp,
            "rows_skipped_totals": report.rows_skipped_totals,
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

    # `demo` exists because of where people give up. Installing succeeds, and
    # then the tool asks for a file they have to go and find -- so the first
    # thing they see is a prompt for homework rather than output. A bundled
    # sample means the gap between installing and understanding what this does
    # is one command with no arguments.
    demo = sub.add_parser(
        "demo", help="review a bundled example BOM (no file needed)")
    demo.add_argument("--json", action="store_true", help="emit JSON instead of text")
    demo.add_argument("--show-ignored-columns", action="store_true",
                      help="list columns that matched no known field")
    demo.add_argument("--strict", action="store_true",
                      help="exit non-zero if any check could not run")

    # `diagnose` exists so a bug report is possible at all. The ask in
    # FIRST_USERS.md is "try to break it and tell me" -- but a BOM is
    # commercially sensitive, so nobody can attach the file that broke it.
    # This prints the structure and none of the contents.
    diagnose = sub.add_parser(
        "diagnose",
        help="print a shareable report about how a file was parsed "
             "(no component data)")
    diagnose.add_argument("file", type=Path, help="the BOM that was read wrongly")

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

    if args.command == "diagnose":
        args.budget, args.power, args.enclosure = 0.0, 0.0, None
        args.json = args.strict = args.show_ignored_columns = False

    if args.command == "demo":
        # Constraints chosen so the sample shows all three outcomes at once:
        # a budget it breaches, checks that pass, and checks that cannot run
        # because a real EDA export carries no dimensions or power figures.
        args.file = SAMPLE_BOM
        args.budget, args.power, args.enclosure = 12.00, 0.0, None
        if not args.json:
            # Human-facing only. Printed ahead of --json output it would sit
            # above the document and make it unparseable -- a caught bug, and
            # the general rule it came from: machine output is the whole of
            # stdout or it is not machine output.
            print(f"Reviewing the bundled example: {SAMPLE_BOM.name}")
            print("Run `helix-bom review <your file>.csv` against your own BOM.\n")

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

    if args.command == "diagnose":
        print(_render_diagnostic(report, result, components))
        return EXIT_OK
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
