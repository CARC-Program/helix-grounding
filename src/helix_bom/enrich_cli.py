"""
`helix-bom enrich` — the command, kept apart from the engine.

Separate from `enrich.py` so the checking logic can be tested without argparse,
a filesystem or a terminal, and separate from `cli.py` because that module is
already the largest in the package and this adds a second file format, a cache
and two network adapters to it.

The command has three modes and they answer three different questions:

    --check-key   does my key work?          one part, one call, plain answer
    --offline     what does this look like?  invented data, loudly labelled
    (neither)     is my BOM orderable?       the real thing
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from .cli import err, out
from .distributors import LookupCache, OfflineDistributor, live_distributors
from .distributors.base import Outcome
from .enrich import enrich

EXIT_OK, EXIT_PROBLEMS, EXIT_UNUSABLE = 0, 1, 2

# A part that every distributor stocks, used only to prove a key works. Chosen
# because it is a jellybean part in a common package that will not go obsolete
# and quietly turn a working key into a failing test.
PROBE_PART = "GRM188R71H104KA93D"


def _distributors(args, environment=None):
    if args.offline:
        return [OfflineDistributor()]
    return live_distributors(environment)


def _cache(args):
    if args.clear_cache:
        return LookupCache(ttl_hours=args.cache_ttl or 12)
    if args.fresh:
        # Still writes, so the run after a --fresh run is fast again. Only
        # reading is suppressed, which is what "ignore cached prices" means.
        cache = LookupCache(ttl_hours=0.0)
        return cache
    return LookupCache(ttl_hours=args.cache_ttl) if args.cache_ttl \
        else LookupCache()


def _report_credentials(environment) -> None:
    """Say which credentials are present. Never say what they are.

    Printing a key into a terminal is how it ends up in a screenshot, a bug
    report, or a support email. Presence is all anyone needs to debug this.
    """
    names = ("MOUSER_API_KEY", "DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    out("credentials in the environment:")
    for name in names:
        value = environment.get(name)
        out(f"  {name:<24} {'set' if value else 'not set'}")
    if environment.get("DIGIKEY_SANDBOX"):
        out("  DIGIKEY_SANDBOX          set -- using Digi-Key's sandbox host")


def _check_key(args, environment) -> int:
    """Look one known part up and say exactly what happened.

    This exists because the adapters have never been run against the live APIs
    from this project. Somebody with a real key running this is the experiment
    that settles it, and the output is written so its result can be pasted into
    an issue without editing.
    """
    _report_credentials(environment)
    distributors = _distributors(args, environment)
    out(f"\nlooking up {PROBE_PART}\n")

    worst = EXIT_OK
    for distributor in distributors:
        capabilities = distributor.capabilities
        usable, why = distributor.usable()
        if not usable:
            out(f"  {capabilities.display_name:<20} skipped -- {why}")
            worst = max(worst, EXIT_UNUSABLE)
            continue
        result = distributor.lookup(PROBE_PART)
        if result.outcome is Outcome.MATCHED:
            record = result.record
            offer = record.best_offer
            out(f"  {capabilities.display_name:<20} MATCHED")
            out(f"    {record.manufacturer} {record.manufacturer_part_number}"
                f"  [{record.lifecycle.value}]")
            if offer:
                price = offer.unit_price_at(1)
                out(f"    stock {offer.stock}, "
                    f"{'no price' if price is None else f'{price} each at qty 1'}")
            out(f"    -> the adapter works against the live API. Please say so "
                f"in an issue so\n       `verified_against_live_api` can stop "
                f"saying False.")
        elif result.outcome is Outcome.NOT_CHECKED:
            out(f"  {capabilities.display_name:<20} NOT CHECKED -- {result.reason}")
            worst = max(worst, EXIT_UNUSABLE)
        else:
            # A reachable API that does not know a jellybean capacitor means
            # the request shape is wrong, not that the part is missing.
            out(f"  {capabilities.display_name:<20} {result.outcome.value.upper()}")
            out(f"    Reached the API, but it did not return this part. That "
                f"points at the request\n    shape rather than at the part. "
                f"Worth an issue.")
            worst = max(worst, EXIT_PROBLEMS)
    return worst


def _as_json(report) -> str:
    def money(value):
        return None if value is None else f"{value:.4f}"

    return json.dumps({
        "lines": [
            {
                "reference": line.reference,
                "quantity": getattr(line.component, "quantity", 1),
                "outcome": line.lookup.outcome.value,
                "reason": line.lookup.reason,
                "manufacturer_part_number":
                    line.lookup.record.manufacturer_part_number
                    if line.lookup.record else "",
                "manufacturer": line.lookup.record.manufacturer
                    if line.lookup.record else "",
                "lifecycle": line.lookup.record.lifecycle.value
                    if line.lookup.record else "unknown",
                "unit_price": money(line.unit_price),
                "extended_price": money(line.extended_price),
                "candidates": [c.manufacturer_part_number
                               for c in line.lookup.candidates],
                "findings": [{"severity": f.severity, "message": f.message,
                              "evidence": f.evidence} for f in line.findings],
            }
            for line in report.lines
        ],
        "checked": len(report.checked),
        "not_checked": len(report.not_checked),
        "reasons_not_checked": report.reasons_not_checked(),
        "complete": report.is_complete,
        "offline_data_used": report.offline_data_used,
        "unverified_adapters": report.unverified,
        "total_cost": money(report.total_cost),
        "stated_cost": money(report.stated_cost),
        "distributors": report.distributors,
    }, indent=2)


def run_enrich(args, environment=None) -> int:
    environment = environment if environment is not None else os.environ

    if args.clear_cache:
        removed = LookupCache().clear()
        out(f"cleared {removed} cached lookup(s)")
        return EXIT_OK

    if args.check_key:
        return _check_key(args, environment)

    if args.file is None:
        err("enrich needs a file, or --check-key, or --clear-cache.")
        return EXIT_UNUSABLE
    if not args.file.exists():
        err(f"no such file: {args.file}")
        return EXIT_UNUSABLE

    from .cli import _looks_like_netlist
    from .ingest import load_bom

    # `load_bom` raises rather than returning empty when it cannot find a
    # header, and letting that through gave a traceback where `review` gives a
    # sentence. Same failure, same treatment, and a pointer at the command
    # built for exactly this situation.
    try:
        if _looks_like_netlist(args.file):
            from .netlist import load_netlist
            components, _nets, ingest_report = load_netlist(args.file)
        else:
            components, ingest_report = load_bom(args.file)
    except FileNotFoundError:
        err(f"no such file: {args.file}")
        return EXIT_UNUSABLE
    except ValueError as exc:
        err(f"helix-bom: {exc}")
        err(f"Run `helix-bom diagnose {args.file}` to see how it was parsed.")
        return EXIT_UNUSABLE

    if not components:
        err(f"no component lines were read from {args.file.name}.")
        err("Run `helix-bom diagnose` on it to see how it was parsed.")
        return EXIT_UNUSABLE

    without_mpn = [c for c in components
                   if not (c.manufacturer_part_number or "").strip()]
    distributors = _distributors(args, environment)
    cache = None if args.fresh else _cache(args)

    report = enrich(components, distributors, cache=cache, compare=args.compare)

    if args.json:
        out(_as_json(report))
    else:
        out(report.describe())
        if without_mpn:
            # The commonest reason a BOM cannot be enriched, and the one the
            # archive says people are actually stuck on. Worth its own sentence
            # rather than being buried in the not-checked tally.
            out(f"\n{len(without_mpn)} of {len(components)} lines carry no "
                f"manufacturer part number at all.")
            out("  Nothing can be looked up for those, and no distributor can "
                "quote them either.")
            out("  This is the gap `enrich` exists for: a value and a footprint "
                "are not an orderable part.")
        if getattr(ingest_report, "missing_fields", None):
            out(f"\ncolumns the file did not have: "
                f"{', '.join(ingest_report.missing_fields)}")

    if args.strict and not report.is_complete:
        return EXIT_PROBLEMS
    if any(f.severity == "critical" for f in report.findings):
        return EXIT_PROBLEMS
    return EXIT_OK
