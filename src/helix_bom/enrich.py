"""
Checking a bill of materials against somebody who actually sells the parts.

This is the check the archive said was missing. `docs/DEMAND_EVIDENCE.md` reads
twenty answers to eight questions about getting a usable BOM out of a CAD tool;
the accepted answer to "can I order components from a BOM?" is *yes, vendor
import works fine — as long as you have a manufacturer part number in there*.
Ordering is solved. Arriving at it with part numbers that are real, current, and
priced at the quantity actually being bought is not.

Seven things get checked per line, and each one is a way a BOM that looks
finished turns out not to be:

    the part does not exist            a typo, or an internal number nobody else knows
    the part is obsolete               the board cannot be built from this design
    the part is NRND                   it can be built once, and not again
    stock is short of the build        or there is none, and a lead time instead
    the quantity is below the minimum  you need three; they sell a reel of three thousand
    the price is not the price         costed at one-off, buying at a hundred, or the reverse
    only near matches came back        a suffix apart is a different reel, tape or grade

The rule that governs all of them is the one this project keeps relearning: **a
check that could not run is reported, never passed.** Every line that was not
looked up — no key, no network, spent quota — is counted separately and named,
because a report listing forty parts as "not found" when nothing was ever asked
is worse than no report. That is the same failure as the physical-fit check that
passed silently on a BOM with no dimensions in it, and it gets the same
treatment here.

Nothing in this module invents a part number, and nothing substitutes one. Near
matches are shown to a person to choose from. A tool that quietly swaps
TPS61023DRLR for TPS61023DRLT has not helped anybody; it has moved the mistake
somewhere harder to find.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from . import structure
from .distributors.base import Lifecycle, Lookup, Outcome

# A stated price is called wrong when it is off by this much *and* the money
# involved is worth mentioning. Without the second test every 0.4-cent resistor
# line becomes a finding and the report is unreadable; without the first, a
# thousand-piece reel priced at the one-off rate slips through.
PRICE_TOLERANCE = 0.15
PRICE_MINIMUM_DIFFERENCE = Decimal("0.50")

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    severity: str
    reference: str
    message: str
    evidence: str = ""

    def line(self) -> str:
        tag = {"critical": "CRITICAL", "warning": "warning ", "info": "note    "}
        text = f"  [{tag.get(self.severity, self.severity)}] {self.reference}: {self.message}"
        return text + (f"\n              {self.evidence}" if self.evidence else "")


@dataclass
class LineResult:
    """One BOM line, and what the distributor said about it."""

    component: object
    lookup: Lookup
    unit_price: Decimal | None = None
    extended_price: Decimal | None = None
    findings: list = field(default_factory=list)

    @property
    def reference(self) -> str:
        return (getattr(self.component, "manufacturer_part_number", "")
                or getattr(self.component, "name", "") or "?")

    @property
    def was_checked(self) -> bool:
        return self.lookup.outcome is not Outcome.NOT_CHECKED


@dataclass
class EnrichmentReport:
    lines: list = field(default_factory=list)
    structural: list = field(default_factory=list)
    distributors: list = field(default_factory=list)
    unverified: list = field(default_factory=list)
    offline_data_used: bool = False
    cache_hits: int = 0
    calls_made: int = 0

    # ---------------------------------------------------------------- counts
    @property
    def checked(self) -> list:
        return [line for line in self.lines if line.was_checked]

    @property
    def not_checked(self) -> list:
        return [line for line in self.lines if not line.was_checked]

    @property
    def findings(self) -> list:
        found = [f for line in self.lines for f in line.findings]
        found.extend(Finding(f.severity, f.reference, f.message, f.evidence)
                     for f in self.structural)
        found.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.reference))
        return found

    @property
    def is_complete(self) -> bool:
        """True only when every line was actually looked up.

        A caller showing this to somebody else must say so when it is False.
        """
        return bool(self.lines) and not self.not_checked

    @property
    def total_cost(self) -> Decimal:
        return sum((line.extended_price for line in self.lines
                    if line.extended_price is not None), Decimal("0"))

    @property
    def stated_cost(self) -> Decimal:
        total = Decimal("0")
        for line in self.lines:
            stated = getattr(line.component, "cost_usd", 0) or 0
            quantity = getattr(line.component, "quantity", 1) or 1
            total += Decimal(str(stated)) * Decimal(quantity)
        return total

    @property
    def priced_lines(self) -> list:
        return [line for line in self.lines if line.extended_price is not None]

    def reasons_not_checked(self) -> dict:
        counts = {}
        for line in self.not_checked:
            reason = line.lookup.reason or "no reason given"
            counts[reason] = counts.get(reason, 0) + 1
        return counts

    # --------------------------------------------------------------- report
    def describe(self, now=None) -> str:
        now = now or datetime.now(timezone.utc)
        out = []

        if self.offline_data_used:
            out.append("!! OFFLINE DEMONSTRATION DATA -- these prices and stock "
                       "levels are made up.\n   Nothing here came from a "
                       "distributor. Do not quote it.\n")

        out.append(f"{len(self.lines)} lines, {len(self.checked)} looked up, "
                   f"{len(self.not_checked)} not looked up")
        if self.distributors:
            out.append(f"  asked: {', '.join(self.distributors)}"
                       f"  ({self.calls_made} calls, {self.cache_hits} from cache)")

        if self.unverified:
            out.append(f"\n  NOTE: the adapter for {', '.join(self.unverified)} has "
                       f"never been run against the live API from this project.\n"
                       f"  Its request and response handling is written from the "
                       f"published specification and tested\n  against recorded "
                       f"fixtures. The first person to use it with a real key is "
                       f"testing it.")

        if self.not_checked:
            # Loud, and before the findings. Forty "not found" lines that were
            # never asked about is the single most misleading thing this report
            # could print.
            out.append(f"\n{len(self.not_checked)} of {len(self.lines)} lines were "
                       f"NOT CHECKED. This is not a clean bill:")
            for reason, count in sorted(self.reasons_not_checked().items(),
                                        key=lambda kv: -kv[1]):
                out.append(f"    {count:>4} x {reason}")

        findings = self.findings
        if findings:
            out.append(f"\n{len(findings)} finding(s):")
            out.extend(f.line() for f in findings)
        else:
            # Said with its scope attached. "Nothing wrong" after a structural
            # pass is a much smaller claim than "nothing wrong" after a
            # distributor confirmed every part, and the two must not read alike.
            scope = f"{len(self.lines)} line(s) checked for structure"
            if self.checked:
                scope += f", {len(self.checked)} looked up at a distributor"
            out.append(f"\nNothing wrong found: {scope}.")

        priced = self.priced_lines
        if priced:
            ages = [line.lookup.record.best_offer.age_hours(now)
                    for line in priced
                    if line.lookup.record and line.lookup.record.best_offer]
            out.append(f"\ncost of the {len(priced)} priced line(s): "
                       f"{self.total_cost:.2f} at the quantities in the file")
            if len(priced) < len(self.lines):
                out.append(f"  ({len(self.lines) - len(priced)} line(s) carry no "
                           f"price, so this is a floor, not a total)")
            if ages:
                oldest = max(ages)
                out.append(f"  prices fetched " + (
                    "just now" if oldest < 1 else f"up to {oldest:.0f} hours ago"))
        return "\n".join(out)


# --------------------------------------------------------------------
# The checks. One function each, so a new one is a small addition and an
# existing one can be read on its own.
# --------------------------------------------------------------------

def _quantity(component) -> int:
    try:
        return max(int(getattr(component, "quantity", 1) or 1), 1)
    except (TypeError, ValueError):
        return 1


def _check_found(line) -> list:
    outcome = line.lookup.outcome
    if outcome is Outcome.NOT_FOUND:
        return [Finding("critical", line.reference,
                        "no distributor asked has this part number",
                        "A typo, an internal part number, or a part nobody "
                        "stocks. It cannot be ordered as written.")]
    if outcome is Outcome.CANDIDATES:
        names = ", ".join(c.manufacturer_part_number
                          for c in line.lookup.candidates[:4])
        return [Finding("warning", line.reference,
                        "no exact match; near matches only",
                        f"Found: {names}. A suffix apart is usually a different "
                        f"reel, tape or temperature grade -- pick one deliberately.")]
    return []


def _check_lifecycle(line) -> list:
    record = line.lookup.record
    if not record:
        return []
    if record.lifecycle is Lifecycle.OBSOLETE:
        return [Finding("critical", line.reference,
                        "the part is obsolete",
                        f"Distributor says: {record.lifecycle_text!r}. "
                        f"This design cannot be built from it.")]
    if record.lifecycle is Lifecycle.NRND:
        return [Finding("warning", line.reference,
                        "not recommended for new designs",
                        f"Distributor says: {record.lifecycle_text!r}. "
                        f"Buildable now, probably not next year.")]
    return []


def _check_stock(line) -> list:
    record = line.lookup.record
    offer = record.best_offer if record else None
    if not offer or offer.stock is None:
        return []
    needed = _quantity(line.component)
    if offer.stock == 0:
        lead = (f" Lead time {offer.lead_time_days} days."
                if offer.lead_time_days else " No lead time given.")
        return [Finding("warning", line.reference, "out of stock", lead.strip())]
    if offer.stock < needed:
        return [Finding("warning", line.reference,
                        f"stock is short of the build",
                        f"{offer.stock} available, {needed} needed.")]
    return []


def _check_minimum(line) -> list:
    record = line.lookup.record
    offer = record.best_offer if record else None
    if not offer:
        return []
    needed = _quantity(line.component)
    if offer.minimum_quantity > needed:
        return [Finding("warning", line.reference,
                        "below the minimum order quantity",
                        f"{needed} needed, minimum is {offer.minimum_quantity}. "
                        f"The line will cost more than the BOM says.")]
    if offer.order_multiple > 1 and needed % offer.order_multiple:
        return [Finding("info", line.reference,
                        "quantity is not a whole multiple of the pack size",
                        f"{needed} needed, sold in {offer.order_multiple}s.")]
    return []


def _check_price(line) -> list:
    """The BOM's own price against what the part costs at the BOM's quantity.

    This is the check that catches the two commonest costing mistakes at once,
    and they run in opposite directions: a BOM costed from the one-off price
    over-states a production run, and one costed from the reel price
    under-states a prototype.
    """
    if line.unit_price is None:
        return []
    stated_raw = getattr(line.component, "cost_usd", None)
    if not stated_raw:
        return []
    stated = Decimal(str(stated_raw))
    actual = line.unit_price
    if actual <= 0:
        return []
    quantity = Decimal(_quantity(line.component))
    difference = abs(stated - actual)
    if (difference / actual) <= Decimal(str(PRICE_TOLERANCE)):
        return []
    if difference * quantity < PRICE_MINIMUM_DIFFERENCE:
        return []
    direction = "over" if stated > actual else "under"
    return [Finding("warning", line.reference,
                    f"the BOM price is {direction} by "
                    f"{(difference / actual):.0%} at this quantity",
                    f"BOM says {stated:.4f} each; at {quantity} the price is "
                    f"{actual:.4f} each "
                    f"({difference * quantity:.2f} across the line).")]


CHECKS = (_check_found, _check_lifecycle, _check_stock, _check_minimum, _check_price)


# --------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------

def enrich(components, distributors, cache=None, compare: bool = False,
           on_progress=None) -> EnrichmentReport:
    """Look every component up and check what comes back.

    ``compare`` asks every distributor about every part instead of stopping at
    the first exact match. It gives a cheaper price and costs proportionally
    more calls, which matters against a thousand-a-day limit and a
    two-hundred-line BOM.
    """
    report = EnrichmentReport()
    # First, and always. These need no key, no network and no account, and
    # 0.2.0 shipped without them -- so a run with no credentials produced ten
    # lines of "not checked" and nothing else.
    report.structural = structure.check(components)
    usable = []
    for distributor in distributors:
        capabilities = distributor.capabilities
        ok, why = distributor.usable()
        if not ok:
            report.unverified = report.unverified   # unchanged; recorded per line
            continue
        usable.append(distributor)
        report.distributors.append(capabilities.display_name)
        if capabilities.live and not capabilities.verified_against_live_api:
            report.unverified.append(capabilities.display_name)
        if not capabilities.live:
            report.offline_data_used = True

    blocked_reasons = [d.usable()[1] for d in distributors if not d.usable()[0]]

    for component in components:
        mpn = getattr(component, "manufacturer_part_number", "") or ""
        line = LineResult(component=component,
                          lookup=Lookup(query=mpn, outcome=Outcome.NOT_CHECKED,
                                        reason=_no_lookup_reason(mpn, usable,
                                                                 blocked_reasons)))
        if mpn.strip() and usable:
            line.lookup = _best_lookup(mpn, usable, cache, compare, report)
        _price(line)
        for check in CHECKS:
            line.findings.extend(check(line))
        report.lines.append(line)
        if on_progress:
            on_progress(line, report)

    if cache is not None:
        report.cache_hits = cache.hits
        cache.save()
    report.calls_made = sum(getattr(d, "calls_made", 0) for d in usable)
    return report


def _no_lookup_reason(mpn: str, usable, blocked_reasons) -> str:
    if not mpn.strip():
        return ("the BOM line carries no manufacturer part number "
                "-- nothing to look up")
    if not usable:
        return blocked_reasons[0] if blocked_reasons else "no distributor configured"
    return "not looked up"


def _best_lookup(mpn, distributors, cache, compare, report) -> Lookup:
    """Ask distributors until something matches, or ask all of them.

    A NOT_CHECKED from one distributor never ends the search -- a dead network
    at one is not an answer about the part -- but if every distributor returns
    NOT_CHECKED, that is what the line gets, with the first reason attached.
    """
    matches, misses, unchecked = [], [], []
    for distributor in distributors:
        key = distributor.capabilities.key
        result = cache.get(key, mpn) if cache is not None else None
        if result is None:
            result = distributor.lookup(mpn)
            if cache is not None:
                cache.put(key, mpn, result)
        if result.outcome is Outcome.MATCHED:
            matches.append(result)
            if not compare:
                break
        elif result.outcome is Outcome.NOT_CHECKED:
            unchecked.append(result)
        else:
            misses.append(result)

    if matches:
        return _cheapest(matches) if len(matches) > 1 else matches[0]
    for result in misses:                 # a real answer beats a non-answer
        if result.outcome is Outcome.CANDIDATES:
            return result
    if misses:
        return misses[0]
    return unchecked[0] if unchecked else Lookup(
        query=mpn, outcome=Outcome.NOT_CHECKED, reason="no distributor answered")


def _cheapest(matches) -> Lookup:
    """Merge equal matches from several distributors, cheapest offer first."""
    primary = matches[0]
    offers = [offer for m in matches if m.record for offer in m.record.offers]
    offers.sort(key=lambda o: (o.unit_price_at(1) is None, o.unit_price_at(1) or 0))
    merged = primary.record
    if merged is not None:
        merged = type(merged)(
            manufacturer_part_number=merged.manufacturer_part_number,
            manufacturer=merged.manufacturer,
            description=merged.description,
            lifecycle=merged.lifecycle,
            lifecycle_text=merged.lifecycle_text,
            datasheet_url=merged.datasheet_url,
            package=merged.package,
            offers=tuple(offers),
        )
    return Lookup(query=primary.query, outcome=primary.outcome, record=merged,
                  candidates=primary.candidates, reason=primary.reason)


def _price(line) -> None:
    record = line.lookup.record
    if not record or not record.offers:
        return
    quantity = _quantity(line.component)
    priced = [(offer, offer.unit_price_at(quantity)) for offer in record.offers]
    priced = [(offer, price) for offer, price in priced if price is not None]
    if not priced:
        return
    offer, unit = min(priced, key=lambda pair: pair[1])
    line.unit_price = unit
    line.extended_price = unit * Decimal(quantity)
