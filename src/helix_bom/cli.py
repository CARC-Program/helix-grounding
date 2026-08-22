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
from .diagrams import generate_netlist_interconnect_svg
from .ingest import load_bom
from .netlist import connectivity_findings, interconnect_from_nets, load_netlist

# The public list of subcommands. Declared here rather than read back out of
# argparse internals, because helix_ops quotes it in launch posts and a
# private attribute is not something a published claim should rest on. A test
# fails if this and the parser ever disagree.
COMMANDS = ("demo", "diagnose", "review")

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SAMPLE_BOM = Path(__file__).parent / "examples" / "sample_bom.csv"
EXIT_OK, EXIT_FINDINGS, EXIT_UNREADABLE = 0, 1, 2

# Characters this project writes in prose that an older Windows console cannot
# encode. cp437 and cp850 are still ordinary console defaults, and on both of
# them `helix-bom demo` -- the first command in the README, the one a stranger
# runs before anything else -- died with UnicodeEncodeError before printing a
# single finding. Found by running the published package on a non-UTF-8
# console rather than by reading the code, which would never have shown it.
ASCII_FALLBACKS = {
    "\u2014": "--",     # em dash
    "\u2013": "-",      # en dash
    "\u00b0": " deg",   # degree sign
    "\u20ac": "EUR",    # euro sign
    "\u00a3": "GBP",    # pound sign
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
}


def _console_safe(text: str, stream) -> str:
    """Return ``text`` in a form ``stream`` can actually encode.

    Transliterates rather than dropping, because "--" carries the meaning of an
    em dash and "?" does not. Anything still unencodable after that becomes a
    replacement character: a mangled character is a cosmetic problem, and a
    traceback where the report should be is not.

    On a UTF-8 console this does nothing at all -- the fast path is a single
    successful encode.
    """
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        pass
    except LookupError:
        # The stream names a codec Python does not have. Transliterating is
        # still worth doing; round-tripping through the missing codec is not,
        # and trying it a second time was how the first version of this
        # function raised the very error it exists to prevent.
        return _transliterate(text)

    text = _transliterate(text)
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except LookupError:  # pragma: no cover - unreachable, kept as a backstop
        return text


def _transliterate(text: str) -> str:
    for char, plain in ASCII_FALLBACKS.items():
        text = text.replace(char, plain)
    return text


def out(text: str = "") -> None:
    print(_console_safe(str(text), sys.stdout))


def err(text: str = "") -> None:
    print(_console_safe(str(text), sys.stderr), file=sys.stderr)

# The Component fields a KiCad netlist actually supplies. Everything else --
# price, dimensions, power draw, category, lead time -- is absent from the
# format, not zero in this particular file. Handing the agent this set is what
# makes it report those checks as unrun instead of silently passing them.
NETLIST_FIELDS = frozenset({
    "name", "quantity", "manufacturer", "manufacturer_part_number",
})


def _looks_like_netlist(path: Path) -> bool:
    """Decide by content, falling back to the extension.

    The extension alone is not enough: people rename exports, and `.net` is
    also used by other tools. The first meaningful token of a KiCad netlist is
    always `(export`, so read for that. If the file cannot be read as text at
    all, defer to the suffix and let the real loader produce the error, which
    will be a better one than anything guessed at here.
    """
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:400].lstrip()
    except OSError:
        return path.suffix.lower() == ".net"
    return head.startswith("(export") or (
        path.suffix.lower() == ".net" and head.startswith("(")
    )


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


def _render_netlist(components, nets, report, result, links, constraints) -> str:
    """Report a netlist review.

    Deliberately not the same renderer as the CSV path. A netlist has no
    header row, no delimiter and no column mapping, so reusing that report
    would mean printing fields that do not exist for this kind of file --
    which is the same class of dishonesty as reporting an unrun check as a
    pass, just quieter.
    """
    lines: list[str] = []
    add = lines.append

    add(f"Netlist review — {report.source}")
    add("=" * 60)
    add("")

    add(f"Read {report.components} component(s) from the schematic.")
    if report.tool:
        add(f"  Exported by      {report.tool}")
    if report.schematic:
        add(f"  Schematic        {report.schematic}")
    add(f"  Nets             {report.nets} "
        f"({report.signal_nets} signal, {report.power_nets} power/ground)")
    add("")

    # --- the interconnect ----------------------------------------------
    if links:
        add(f"Interconnect ({len(links)} link(s), read from the file — not inferred):")
        for ref_a, ref_b, names in links:
            add(f"  {ref_a} <-> {ref_b:<8}  {', '.join(names)}")
        add("")
    else:
        add("Interconnect: no signal net joins two components in this file.")
        add("")

    if any(c.cost_usd for c in components):
        add(f"Total: ${result.total_cost_usd:,.2f}"
            + (f"  (budget ${constraints.budget_usd:,.2f})"
               if constraints.budget_usd else ""))
        add("")

    add("Findings:")
    for finding in sorted(result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9)):
        add(f"  [{finding.severity.upper()}] {finding.message}")
    add("")

    # Same rule as the CSV report: last, and never collapsed into a count.
    # The reason differs though -- a missing column can be supplied, whereas a
    # netlist structurally does not carry prices, so the remedy is a different
    # file rather than a better export.
    if result.skipped_checks:
        add(f"NOT CHECKED ({len(result.skipped_checks)}):")
        for skipped in result.skipped_checks:
            add(f"  {skipped.name}")
            add(f"      {skipped.reason}")
        add("")
        add("  These are not passes. A netlist carries connectivity, not cost,")
        add("  size, power or category — no export option adds them. Run")
        add("  `helix-bom review` on your BOM CSV as well to check those.")
    else:
        add("All checks ran against the submitted data.")

    return "\n".join(lines)


def _as_dict_netlist(components, nets, report, result, links) -> dict:
    return {
        "source": report.source,
        "kind": "netlist",
        "netlist": {
            "tool": report.tool,
            "schematic": report.schematic,
            "components": report.components,
            "nets": report.nets,
            "signal_nets": report.signal_nets,
            "power_nets": report.power_nets,
            "unconnected": report.unconnected,
            "single_node_nets": report.single_node_nets,
        },
        "interconnect": [
            {"a": a, "b": b, "nets": names} for a, b, names in links
        ],
        "totals": {
            "line_items": len(components),
            "parts": sum(c.quantity for c in components),
        },
        "complete": result.is_complete,
        "findings": [{"severity": f.severity, "message": f.message} for f in result.findings],
        "skipped_checks": [{"name": s.name, "reason": s.reason} for s in result.skipped_checks],
    }


def _render_diagnostic_netlist(report, result, links) -> str:
    """The netlist equivalent of the CSV diagnostic: structure, no contents.

    Stricter than it first appears. On a CSV the column *headings* are printed,
    because the parser matches on them and a heading is rarely secret. A
    netlist has no headings -- its equivalents are net names and part values,
    and those are the design. `I2C_SDA` is harmless; `MOTOR_KILL_INTERLOCK`
    and a part number are not, and no rule can tell them apart. So counts and
    shapes go in the report and names stay out of it, reference designators
    aside, which say nothing beyond `there is a fourth resistor`.
    """
    import platform
    import sys as _sys

    lines: list[str] = []
    add = lines.append

    add("helix-bom diagnostic report (netlist)")
    add("=" * 60)
    add("")
    add("Safe to paste into a public bug report. Contains no net names, no part")
    add("values and no part numbers — a netlist is the design itself, so only")
    add("structure is reported here.")
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
    add(f"  format          KiCad netlist (s-expression)")
    add(f"  exported by     {report.tool or 'not stated in the file'}")
    add(f"  components      {report.components}")
    add(f"  nets            {report.nets} "
        f"({report.signal_nets} signal, {report.power_nets} power/ground)")
    add(f"  single-node     {len(report.single_node_nets)}")
    add(f"  unconnected     {len(report.unconnected)} component(s)")
    add(f"  links drawn     {len(links)}")
    add("")

    ran = BOMReviewAgent.TOTAL_CHECKS - len(result.skipped_checks)
    add(f"checks that could run   {ran} of {BOMReviewAgent.TOTAL_CHECKS}")
    for skipped in result.skipped_checks:
        add(f"  skipped  {skipped.name}")
    add("")
    add("What did it get wrong? Describe the expected result below —")
    add("the component count, a link it missed, a net it read as power.")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """The argument surface, separated from running it.

    Split out so a test can compare the parser's real subcommands against
    the public COMMANDS list. helix_ops quotes that list in launch posts,
    and a published claim should not rest on the two staying in step by
    memory.
    """
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
    diagnose.add_argument("file", type=Path,
                          help="the BOM or netlist that was read wrongly")

    review = sub.add_parser(
        "review", help="review a BOM CSV file or a KiCad netlist")
    review.add_argument(
        "file", type=Path,
        help="a BOM export (CSV from KiCad, Altium or a spreadsheet), or a "
             "KiCad .net netlist")
    review.add_argument("--budget", type=float, default=0.0, metavar="USD",
                        help="cost budget for the whole BOM")
    review.add_argument("--enclosure", type=_parse_enclosure, metavar="WxDxH",
                        help="enclosure envelope in mm, e.g. 100x80x25")
    review.add_argument("--power", type=float, default=0.0, metavar="WATTS",
                        help="power budget in watts")
    review.add_argument("--json", action="store_true", help="emit JSON instead of text")
    review.add_argument("--show-ignored-columns", action="store_true",
                        help="list columns that matched no known field")
    # Netlist input only, and deliberately not ignored on a CSV. A BOM does
    # not carry connectivity, so a diagram drawn from one is a guess about
    # what usually connects to what -- which is the thing this stopped
    # shipping.
    review.add_argument("--diagram", type=Path, metavar="OUT.svg",
                        help="write an SVG interconnect diagram (needs a "
                             "netlist; a BOM carries no connectivity)")
    review.add_argument("--strict", action="store_true",
                        help="exit non-zero if any check could not run")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "diagnose":
        args.budget, args.power, args.enclosure = 0.0, 0.0, None
        args.json = args.strict = args.show_ignored_columns = False
        args.diagram = None

    if args.command == "demo":
        # Constraints chosen so the sample shows all three outcomes at once:
        # a budget it breaches, checks that pass, and checks that cannot run
        # because a real EDA export carries no dimensions or power figures.
        args.file = SAMPLE_BOM
        args.budget, args.power, args.enclosure = 12.00, 0.0, None
        args.diagram = None
        if not args.json:
            # Human-facing only. Printed ahead of --json output it would sit
            # above the document and make it unparseable -- a caught bug, and
            # the general rule it came from: machine output is the whole of
            # stdout or it is not machine output.
            out(f"Reviewing the bundled example: {SAMPLE_BOM.name}")
            out("Run `helix-bom review <your file>.csv` against your own BOM.\n")

    # Which kind of file this is decides everything downstream. It is read
    # from the contents rather than trusted from the extension, because both
    # formats get renamed, and the cost of guessing wrong is a confusing
    # error about a header row in a file that never had one.
    is_netlist = _looks_like_netlist(args.file)
    nets: list = []
    links: list = []

    try:
        if is_netlist:
            components, nets, report = load_netlist(args.file)
            links = interconnect_from_nets(nets)
        else:
            components, report = load_bom(args.file)
    except FileNotFoundError:
        err(f"helix-bom: no such file: {args.file}")
        return EXIT_UNREADABLE
    except ValueError as exc:
        err(f"helix-bom: {exc}")
        return EXIT_UNREADABLE

    if not components:
        detail = ("parsed, but lists no parts -- no (components ...) block"
                  if is_netlist else "has a header but no data rows")
        err(f"helix-bom: {report.source} {detail}.")
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
    # is better information than the agent can infer from the values. For a
    # netlist the answer is fixed by the format itself: connectivity and
    # part identity, nothing priced or measured.
    result = BOMReviewAgent().review(
        components, constraints,
        available_fields=NETLIST_FIELDS if is_netlist else set(report.mapped),
    )
    if is_netlist:
        # Checks a BOM cannot express, so they live with the netlist reader
        # rather than in an agent that reviews shopping lists.
        result.findings.extend(connectivity_findings(components, nets, report))

    if args.diagram:
        if not is_netlist:
            err("helix-bom: --diagram needs a netlist. A BOM lists parts and "
                "quantities; how they connect is in the schematic. Export one "
                "from Eeschema with File > Export > Netlist.")
            return EXIT_UNREADABLE
        try:
            args.diagram.write_text(
                generate_netlist_interconnect_svg(links, source=report.source),
                encoding="utf-8")
        except OSError as exc:
            err(f"helix-bom: could not write {args.diagram}: {exc}")
            return EXIT_UNREADABLE
        # stderr on purpose: --json output has to be the whole of stdout or
        # it is not machine output. Same rule the demo banner is bound by.
        err(f"Interconnect diagram written to {args.diagram}")

    if args.command == "diagnose":
        out(_render_diagnostic_netlist(report, result, links) if is_netlist
            else _render_diagnostic(report, result, components))
        return EXIT_OK
    if args.json:
        out(json.dumps(
            _as_dict_netlist(components, nets, report, result, links) if is_netlist
            else _as_dict(components, report, result), indent=2))
    elif is_netlist:
        out(_render_netlist(components, nets, report, result, links, constraints))
    else:
        out(_render(components, report, result, constraints, args.show_ignored_columns))

    if any(f.severity == "critical" for f in result.findings):
        return EXIT_FINDINGS
    if args.strict and not result.is_complete:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
