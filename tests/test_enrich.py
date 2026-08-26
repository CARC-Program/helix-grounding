"""
Tests for the enrichment engine and its command.

The engine's job is to say whether a BOM can actually be ordered. The thing that
makes it worth trusting is not the checks — those are arithmetic — but the
distinction it refuses to blur: **a part nobody stocks and a part nobody asked
about are different answers, and only one of them is the user's problem.**

Most of this file is about that distinction, because every version of this
project that got it wrong produced a confident report that was worse than
silence: a physical-fit check that passed on a BOM with no dimensions, a
detector that reported clean because it excluded the folder holding the problem,
and — while this module was being written — a six-part demo catalogue announcing
that STM32F401RET6 does not exist.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from helix_bom.agent import Component
from helix_bom.distributors import (
    Lifecycle,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
)
from helix_bom.distributors.base import Capabilities, Lookup
from helix_bom.enrich import EnrichmentReport, enrich

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def _component(mpn="BME280", quantity=1, cost=0.0, name="a part"):
    return Component(name=name, cost_usd=cost, width_mm=0, depth_mm=0,
                     height_mm=0, power_draw_w=0, category="", quantity=quantity,
                     manufacturer_part_number=mpn)


def _record(mpn="BME280", lifecycle=Lifecycle.ACTIVE, lifecycle_text="Active",
            stock=100, breaks=((1, "1.00"), (100, "0.50")), minimum=1,
            multiple=1, lead=None):
    return PartRecord(
        manufacturer_part_number=mpn, manufacturer="Someone",
        lifecycle=lifecycle, lifecycle_text=lifecycle_text,
        offers=(Offer(distributor="fake", distributor_part_number="F-1", url="",
                      stock=stock,
                      price_breaks=tuple(PriceBreak(q, Decimal(p))
                                         for q, p in breaks),
                      minimum_quantity=minimum, order_multiple=multiple,
                      lead_time_days=lead, fetched_at=NOW),))


class _Fake:
    """A distributor that answers however a test needs it to."""

    def __init__(self, answers=None, key="fake", live=True, verified=False,
                 usable=True, reason="usable"):
        self.answers = answers or {}
        self._key = key
        self._live = live
        self._verified = verified
        self._usable = usable
        self._reason = reason
        self.calls_made = 0
        self.asked = []

    @property
    def capabilities(self):
        return Capabilities(key=self._key, display_name=self._key,
                            terms_url="https://example.com/terms",
                            requires_api_key=False, live=self._live,
                            verified_against_live_api=self._verified)

    def usable(self, environment=None):
        return (self._usable, self._reason if not self._usable else "usable")

    def lookup(self, mpn):
        self.calls_made += 1
        self.asked.append(mpn)
        return self.answers.get(mpn.upper(), Lookup(query=mpn,
                                                    outcome=Outcome.NOT_FOUND))


def _matched(record):
    return Lookup(query=record.manufacturer_part_number, outcome=Outcome.MATCHED,
                  record=record)


def _run(components, distributor):
    return enrich(components, [distributor])


# --------------------------------------------------------------------
# Not found is not not checked
# --------------------------------------------------------------------

def test_a_line_with_no_part_number_is_not_checked_and_says_why():
    """The commonest case in a real BOM, and the gap the whole feature exists
    for: a value and a footprint are not an orderable part. Reporting it as
    "not found" would blame the user for something they did not do."""
    report = _run([_component(mpn="")], _Fake())
    line = report.lines[0]
    assert line.lookup.outcome is Outcome.NOT_CHECKED
    assert "no manufacturer part number" in line.lookup.reason
    assert not line.findings


def test_an_unusable_distributor_makes_every_line_not_checked_not_not_found():
    """Run with no API key, forty parts must not come back as forty critical
    findings saying they do not exist. Nothing was asked."""
    blocked = _Fake(usable=False, reason="MOUSER_API_KEY is not set")
    report = _run([_component("BME280"), _component("LM3914N")], blocked)
    assert len(report.not_checked) == 2
    assert not report.findings
    assert report.is_complete is False
    assert "MOUSER_API_KEY" in report.reasons_not_checked().popitem()[0]


def test_the_report_puts_the_not_checked_count_before_the_findings():
    """Ordering is the message. A reader who sees findings first assumes the
    run was complete."""
    blocked = _Fake(usable=False, reason="no key")
    text = _run([_component("BME280")], blocked).describe(now=NOW)
    assert "NOT CHECKED" in text
    assert text.index("NOT CHECKED") < len(text)
    assert "This is not a clean bill" in text


def test_a_complete_run_says_so_only_when_every_line_was_looked_up():
    good = _Fake({"BME280": _matched(_record())})
    assert _run([_component("BME280")], good).is_complete is True
    mixed = _run([_component("BME280"), _component(mpn="")], good)
    assert mixed.is_complete is False


def test_an_empty_bom_is_not_a_complete_run():
    assert enrich([], [_Fake()]).is_complete is False


# --------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------

def test_a_part_no_distributor_stocks_is_critical():
    report = _run([_component("NOSUCHPART")], _Fake())
    finding = report.findings[0]
    assert finding.severity == "critical"
    assert "no distributor asked has this part number" in finding.message


def test_an_obsolete_part_is_critical():
    """The finding that decides whether a board can be built at all."""
    record = _record(lifecycle=Lifecycle.OBSOLETE, lifecycle_text="Obsolete")
    report = _run([_component("BME280")],
                  _Fake({"BME280": _matched(record)}))
    assert any(f.severity == "critical" and "obsolete" in f.message
               for f in report.findings)


def test_an_nrnd_part_is_a_warning_not_a_blocker():
    """Buildable now, probably not next year. A critical here would train
    somebody to ignore criticals."""
    record = _record(lifecycle=Lifecycle.NRND,
                     lifecycle_text="Not Recommended for New Designs")
    findings = _run([_component("BME280")], _Fake({"BME280": _matched(record)})).findings
    assert [f.severity for f in findings if "new designs" in f.message] == ["warning"]


def test_stock_shorter_than_the_build_is_reported_with_both_numbers():
    record = _record(stock=40)
    report = _run([_component("BME280", quantity=100)],
                  _Fake({"BME280": _matched(record)}))
    finding = next(f for f in report.findings if "short" in f.message)
    assert "40 available, 100 needed" in finding.evidence


def test_no_stock_reports_the_lead_time():
    record = _record(stock=0, lead=365)
    report = _run([_component("BME280")], _Fake({"BME280": _matched(record)}))
    finding = next(f for f in report.findings if "out of stock" in f.message)
    assert "365 days" in finding.evidence


def test_unstated_stock_is_not_treated_as_zero():
    """None means the distributor did not say. Reporting that as "out of
    stock" invents a fact."""
    record = PartRecord(manufacturer_part_number="BME280",
                        offers=(Offer(distributor="f", distributor_part_number="",
                                      url="", stock=None, fetched_at=NOW),))
    report = _run([_component("BME280")], _Fake({"BME280": _matched(record)}))
    assert not any("stock" in f.message for f in report.findings)


def test_a_reel_only_part_bought_in_threes_is_flagged():
    """Three needed, minimum three thousand. The BOM total is wrong by a factor
    of a thousand and nothing else in the tool would notice."""
    record = _record(breaks=((3000, "0.05"),), minimum=3000, stock=9000)
    report = _run([_component("BME280", quantity=3)],
                  _Fake({"BME280": _matched(record)}))
    finding = next(f for f in report.findings if "minimum" in f.message)
    assert "minimum is 3000" in finding.evidence


def test_a_quantity_that_is_not_a_whole_pack_is_a_note_not_a_warning():
    record = _record(multiple=10, breaks=((1, "0.10"),))
    report = _run([_component("BME280", quantity=25)],
                  _Fake({"BME280": _matched(record)}))
    assert [f.severity for f in report.findings if "multiple" in f.message] == ["info"]


def test_near_matches_are_never_promoted_to_a_match():
    """The failure this would cause is a production order for the wrong reel."""
    candidate = _record(mpn="TPS61023DRLR")
    answer = Lookup(query="TPS61023DRLT", outcome=Outcome.CANDIDATES,
                    candidates=(candidate,))
    report = _run([_component("TPS61023DRLT")],
                  _Fake({"TPS61023DRLT": answer}))
    line = report.lines[0]
    assert line.lookup.record is None
    assert line.unit_price is None
    finding = next(f for f in report.findings if "no exact match" in f.message)
    assert "TPS61023DRLR" in finding.evidence


# --------------------------------------------------------------------
# Price
# --------------------------------------------------------------------

def test_the_line_is_priced_at_the_quantity_being_bought():
    report = _run([_component("BME280", quantity=100)],
                  _Fake({"BME280": _matched(_record())}))
    line = report.lines[0]
    assert line.unit_price == Decimal("0.50")
    assert line.extended_price == Decimal("50.00")


def test_a_bom_costed_at_the_one_off_price_is_caught():
    """One of the two commonest costing mistakes. The BOM says a dollar each
    because somebody read the single-unit price; at a hundred it is fifty
    cents, and the build costs half what the spreadsheet claims."""
    report = _run([_component("BME280", quantity=100, cost=1.00)],
                  _Fake({"BME280": _matched(_record())}))
    finding = next(f for f in report.findings if "BOM price" in f.message)
    assert "over by" in finding.message
    assert "50.00" in finding.evidence


def test_a_bom_costed_at_the_reel_price_is_caught_too():
    """The same mistake in the other direction, which is the expensive one:
    the prototype costs three times the estimate."""
    report = _run([_component("BME280", quantity=1, cost=0.50)],
                  _Fake({"BME280": _matched(_record(breaks=((1, "1.50"),)))}))
    finding = next(f for f in report.findings if "BOM price" in f.message)
    assert "under by" in finding.message


def test_a_price_that_is_close_enough_is_not_a_finding():
    """Currency drift and rounding are not errors. A report that flags every
    line is a report nobody reads."""
    report = _run([_component("BME280", quantity=1, cost=1.05)],
                  _Fake({"BME280": _matched(_record())}))
    assert not [f for f in report.findings if "BOM price" in f.message]


def test_a_tiny_absolute_difference_is_not_worth_saying():
    """A 0.4-cent resistor priced at 0.5 cents is 25% out and nobody cares.
    Without this the report is unreadable on any real BOM."""
    report = _run([_component("R1", quantity=2, cost=0.004)],
                  _Fake({"R1": _matched(_record(mpn="R1", breaks=((1, "0.005"),)))}))
    assert not [f for f in report.findings if "BOM price" in f.message]


def test_an_unpriced_line_is_left_out_of_the_total_and_the_total_says_so():
    """A floor presented as a total is the same lie as a partial check
    presented as a clean bill."""
    priced = _matched(_record(mpn="A"))
    report = enrich([_component("A"), _component("B")],
                    [_Fake({"A": priced})])
    assert report.total_cost == Decimal("1.00")
    assert "floor, not a total" in report.describe(now=NOW)


# --------------------------------------------------------------------
# Several distributors
# --------------------------------------------------------------------

def test_the_search_stops_at_the_first_match_by_default():
    """A thousand calls a day against a two-hundred-line BOM is the constraint
    that makes this the default."""
    first = _Fake({"BME280": _matched(_record())}, key="first")
    second = _Fake({"BME280": _matched(_record())}, key="second")
    enrich([_component("BME280")], [first, second])
    assert first.calls_made == 1
    assert second.calls_made == 0


def test_compare_asks_everybody_and_keeps_the_cheaper_offer():
    dear = _matched(_record(breaks=((1, "2.00"),)))
    cheap = _matched(_record(breaks=((1, "0.75"),)))
    report = enrich([_component("BME280")],
                    [_Fake({"BME280": dear}, key="dear"),
                     _Fake({"BME280": cheap}, key="cheap")],
                    compare=True)
    assert report.lines[0].unit_price == Decimal("0.75")


def test_one_distributor_being_unreachable_does_not_end_the_search():
    """A dead network at one distributor is not an answer about the part."""
    dead = _Fake({"BME280": Lookup(query="BME280", outcome=Outcome.NOT_CHECKED,
                                   reason="could not reach")}, key="dead")
    alive = _Fake({"BME280": _matched(_record())}, key="alive")
    report = enrich([_component("BME280")], [dead, alive])
    assert report.lines[0].lookup.outcome is Outcome.MATCHED


def test_a_real_answer_beats_a_non_answer():
    dead = _Fake({"X": Lookup(query="X", outcome=Outcome.NOT_CHECKED,
                              reason="timeout")}, key="dead")
    knows = _Fake({}, key="knows")          # answers NOT_FOUND
    report = enrich([_component("X")], [dead, knows])
    assert report.lines[0].lookup.outcome is Outcome.NOT_FOUND


def test_every_distributor_failing_leaves_the_line_not_checked_with_a_reason():
    dead = _Fake({"X": Lookup(query="X", outcome=Outcome.NOT_CHECKED,
                              reason="timeout")}, key="dead")
    report = enrich([_component("X")], [dead])
    assert report.lines[0].lookup.outcome is Outcome.NOT_CHECKED
    assert report.lines[0].lookup.reason == "timeout"


# --------------------------------------------------------------------
# What the report admits about itself
# --------------------------------------------------------------------

def test_offline_data_is_announced_at_the_very_top():
    """Plausible prices attached to real part numbers are what somebody quotes
    by accident. The banner is the only thing standing between the demo and a
    purchase order."""
    text = _run([_component("BME280")],
                _Fake({"BME280": _matched(_record())}, live=False)).describe(now=NOW)
    assert text.startswith("!! OFFLINE DEMONSTRATION DATA")
    assert "Do not quote it" in text


def test_an_unverified_adapter_is_named_in_the_report():
    """The Mouser and Digi-Key adapters have never run against the live APIs
    from this project. A reader deserves to know that the first person to use
    one is testing it."""
    text = _run([_component("BME280")],
                _Fake({"BME280": _matched(_record())}, key="Mouser",
                      live=True, verified=False)).describe(now=NOW)
    assert "never been run against the live API" in text


def test_a_verified_adapter_is_not_flagged():
    text = _run([_component("BME280")],
                _Fake({"BME280": _matched(_record())}, verified=True)).describe(now=NOW)
    assert "never been run" not in text


def test_the_report_says_how_old_its_prices_are():
    """A cached price presented as current is worse than no price."""
    report = _run([_component("BME280")], _Fake({"BME280": _matched(_record())}))
    fresh = report.describe(now=NOW)
    stale = report.describe(now=NOW + timedelta(hours=9))
    assert "just now" in fresh
    assert "9 hours ago" in stale


def test_findings_are_ordered_worst_first():
    answers = {
        "A": _matched(_record(mpn="A", lifecycle=Lifecycle.OBSOLETE,
                              lifecycle_text="Obsolete")),
        "B": _matched(_record(mpn="B", stock=0)),
    }
    report = enrich([_component("A"), _component("B")], [_Fake(answers)])
    severities = [f.severity for f in report.findings]
    assert severities == sorted(severities, key=lambda s: {"critical": 0,
                                                           "warning": 1,
                                                           "info": 2}[s])


def test_a_clean_run_says_what_it_actually_checked():
    """"Nothing wrong found" is only meaningful with a count beside it."""
    text = _run([_component("BME280")],
                _Fake({"BME280": _matched(_record())})).describe(now=NOW)
    assert "Nothing wrong found in the 1 lines that were checked" in text


def test_an_empty_report_describes_itself_without_crashing():
    assert "0 lines" in EnrichmentReport().describe(now=NOW)
