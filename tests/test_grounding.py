"""
Tests for helix_grounding.

Two jobs. First, prove the extraction did not lose anything: the exact
fabricated text captured from a real field session must still be caught.
Second, prove the bugs found during extraction are actually fixed — each
of those tests names the specific defect it covers, because a test whose
purpose you cannot reconstruct in six months is a test you will delete.
"""

import pytest

from helix_grounding import ClaimKind, GroundTruth, Verifier
from helix_grounding.domains.bom import ground_truth_for_bom


# --------------------------------------------------------------------
# Test doubles — mirror the shape of the real BOM types without
# importing them, so the library stays independent of the agent.
# --------------------------------------------------------------------

class Component:
    def __init__(self, name, cost_usd, width_mm, depth_mm, height_mm,
                 power_draw_w, quantity=1, manufacturer_part_number="",
                 lead_time_days=0):
        self.name = name
        self.cost_usd = cost_usd
        self.width_mm = width_mm
        self.depth_mm = depth_mm
        self.height_mm = height_mm
        self.power_draw_w = power_draw_w
        self.quantity = quantity
        self.manufacturer_part_number = manufacturer_part_number
        self.lead_time_days = lead_time_days


class Constraints:
    def __init__(self, budget_usd, enclosure_width_mm, enclosure_depth_mm,
                 enclosure_height_mm, power_budget_w):
        self.budget_usd = budget_usd
        self.enclosure_width_mm = enclosure_width_mm
        self.enclosure_depth_mm = enclosure_depth_mm
        self.enclosure_height_mm = enclosure_height_mm
        self.power_budget_w = power_budget_w


class Alternative:
    def __init__(self, manufacturer_part_number, cost_usd, lead_time_days):
        self.manufacturer_part_number = manufacturer_part_number
        self.cost_usd = cost_usd
        self.lead_time_days = lead_time_days


@pytest.fixture
def bom():
    """The over-budget scenario from the original variated test 1."""
    components = [
        Component("High-end MCU module", 18.00, 25, 25, 5, 1.2,
                  manufacturer_part_number="STM32F401RE"),
        Component("Premium Display module", 22.00, 60, 40, 6, 0.8),
        Component("LiPo battery pack", 8.45, 50, 34, 10, 0.0),
    ]
    constraints = Constraints(30.00, 100, 80, 25, 5.0)
    return components, constraints


@pytest.fixture
def verifier():
    return Verifier()


# --------------------------------------------------------------------
# Regression — the original catches must survive the refactor
# --------------------------------------------------------------------

def test_catches_the_real_fabrication_from_the_field_session(bom, verifier):
    """The exact text a local model produced during a real run. It
    invented a $36.00 total for a component that costs $18.00."""
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    text = (
        "After reviewing your build against its budget of $30.00 with an "
        "identified overspend of $18.45, the High-end MCU module costing a "
        "total of $36.00 should be addressed first."
    )
    report = verifier.verify(text, truth)

    assert not report.is_grounded
    assert 36.0 in [c.value for c in report.ungrounded]


def test_genuinely_correct_text_produces_no_false_positives(bom, verifier):
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    text = (
        "Your BOM totals $48.45 against a $30.00 budget, an overage of "
        "$18.45. The High-end MCU module is $18.00 and the Premium Display "
        "module is $22.00. Total draw is 2.0 W against a 5.0 W budget."
    )
    report = verifier.verify(text, truth)

    assert report.is_grounded, report.summary()


# --------------------------------------------------------------------
# Fixed bugs — each names the defect it covers
# --------------------------------------------------------------------

def test_thousands_separator_parses_as_one_number(verifier):
    """BUG: the original pattern was r'\\$(\\d+\\.?\\d*)', which read
    '$1,250.00' as the number 1. Any realistic BOM over $1,000 had its
    total silently misparsed, then reported as a fabrication because 1
    was not in the allowed set."""
    truth = GroundTruth().allow(ClaimKind.CURRENCY, 1250.00)

    report = verifier.verify("The total is $1,250.00 for this build.", truth)

    assert report.is_grounded, report.summary()
    assert [c.value for c in report.grounded] == [1250.00]


def test_word_form_currency_is_checked(verifier):
    """BUG: only '$'-prefixed amounts were extracted, so a model writing
    '36 dollars' or '36 USD' bypassed the safety net completely. This was
    a hole in the guarantee, not a cosmetic gap."""
    truth = GroundTruth().allow(ClaimKind.CURRENCY, 18.00)

    report = verifier.verify("The module costs 36 dollars in total.", truth)

    assert not report.is_grounded
    assert 36.0 in [c.value for c in report.ungrounded]


@pytest.mark.parametrize("token", ["RS485", "DDR4", "USB3", "I2C", "IP67", "MHz"])
def test_known_standards_are_not_flagged_as_part_numbers(token, verifier):
    """BUG: the identifier pattern matched any uppercase-then-digit token,
    so mentioning RS485 or DDR4 was reported as an invented part number.
    That burned every retry and delivered the safe fallback on a report
    that was correct — a false positive is more damaging here than a
    false negative."""
    truth = GroundTruth().allow_token("STM32F401RE")

    report = verifier.verify(f"The board uses a {token} interface.", truth)

    assert report.is_grounded, f"{token} was wrongly flagged: {report.summary()}"


def test_genuine_fabricated_part_number_is_still_caught(verifier):
    """The vocabulary must not become a blanket amnesty."""
    truth = GroundTruth().allow_token("STM32F401RE")

    report = verifier.verify("Consider swapping in the ATMEGA328P instead.", truth)

    assert not report.is_grounded
    assert "ATMEGA328P" in [c.value for c in report.ungrounded]


def test_digits_inside_an_identifier_are_not_read_as_measurements(verifier):
    """BUG, found by the parametrised test above: with no left boundary,
    the measurement pattern read the '2C' inside 'I2C' as 2 degrees
    Celsius and reported it ungrounded. 'AT24C256' would have become
    24 degrees. Fixed by refusing a match that starts immediately after
    an uppercase letter or digit, plus dropping bare C/K as units."""
    truth = GroundTruth().allow(ClaimKind.MEASUREMENT, 40.0, "mm")

    for text in ("Uses an I2C bus.", "The AT24C256 EEPROM.", "A DDR4 module."):
        report = verifier.verify(text, truth)
        assert not [c for c in report.ungrounded
                    if c.kind is ClaimKind.MEASUREMENT], f"false measurement in: {text}"


def test_compact_dimension_strings_still_extract(verifier):
    """The boundary fix must not break '60x40x6mm', which is how
    dimensions are actually written in BOM prose."""
    truth = GroundTruth().allow_many(ClaimKind.MEASUREMENT, [60.0, 40.0, 6.0], "mm")

    report = verifier.verify("The display is 60x40x6mm overall.", truth)

    assert report.is_grounded, report.summary()
    assert 6.0 in [c.value for c in report.grounded]


def test_units_do_not_cross_validate(verifier):
    """BUG: all 'mm' figures went into one pool and power into another,
    but nothing tied a number to its unit. A model could state a value in
    the wrong unit and pass because the bare number existed somewhere."""
    truth = GroundTruth()
    truth.allow(ClaimKind.MEASUREMENT, 100.0, "mm")

    ok = verifier.verify("The enclosure is 100 mm wide.", truth)
    bad = verifier.verify("The board draws 100 W under load.", truth)

    assert ok.is_grounded
    assert not bad.is_grounded, "100W should not validate against 100mm"


def test_legitimate_price_comparison_is_not_flagged(bom, verifier):
    """BUG: a review naming a cheaper substitute states the gap between
    the two prices. That difference was never in the allowed set, so
    every correct sourcing comparison was reported as invented. This was
    the largest single source of false positives."""
    components, constraints = bom
    alternatives = [Alternative("STM32F411RE", 15.50, 21)]
    truth = ground_truth_for_bom(components, constraints, alternatives=alternatives)

    text = (
        "The STM32F411RE at $15.50 is $2.50 cheaper than your current "
        "STM32F401RE at $18.00."
    )
    report = verifier.verify(text, truth)

    assert report.is_grounded, report.summary()


def test_empty_ground_truth_raises_instead_of_condemning_everything(verifier):
    """BUG: an unpopulated ground truth marked every claim ungrounded and
    looked like catastrophic fabrication, when it actually meant the
    caller forgot a step. Failing loudly beats a confidently wrong
    verdict."""
    with pytest.raises(ValueError, match="empty"):
        verifier.verify("The total is $40.00.", GroundTruth())


def test_skipped_kinds_are_recorded_not_silently_passed(verifier):
    """A kind the caller cannot check must be visible in the report.
    'We verified this' must never quietly mean 'we verified some of
    this'."""
    truth = GroundTruth().allow(ClaimKind.CURRENCY, 40.00).skip(ClaimKind.PERCENTAGE)

    report = verifier.verify("Costs $40.00, about 30% over target.", truth)

    assert report.is_grounded
    assert ClaimKind.PERCENTAGE in report.skipped_kinds


# --------------------------------------------------------------------
# Correction notes and the retry loop
# --------------------------------------------------------------------

def test_correction_note_quotes_surrounding_context(bom, verifier):
    """Naming a bare number tells the model what is wrong but not where.
    Quoting the sentence measurably improves the odds the retry fixes the
    right claim."""
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    report = verifier.verify("The display module costs a total of $99.00.", truth)
    note = report.correction_note()

    assert "$99.00" in note
    assert "display module" in note


def test_retry_loop_accepts_a_corrected_second_attempt(bom, verifier):
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    calls = []

    def generate(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return "The MCU costs a total of $36.00."
        return "The MCU costs $18.00 and the BOM totals $48.45."

    outcome = verifier.generate_validated(generate, "base prompt", truth)

    assert outcome.validated
    assert outcome.attempts == 2
    assert len(outcome.rejected) == 1
    assert "$36.00" in calls[1], "the retry prompt must name what was invented"


def test_exhausted_retries_never_deliver_ungrounded_text(bom, verifier):
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    outcome = verifier.generate_validated(
        lambda prompt: "The MCU costs a total of $999.00.",
        "base prompt",
        truth,
        max_attempts=3,
    )

    assert not outcome.validated
    assert outcome.attempts == 3
    assert "999" not in outcome.text
    assert len(outcome.rejected) == 3


def test_rejections_are_reported_to_the_audit_hook(bom, verifier):
    """A caught fabrication is the evidence the safety net works.
    Discarding it destroys the only proof."""
    components, constraints = bom
    truth = ground_truth_for_bom(components, constraints)

    logged = []
    verifier.generate_validated(
        lambda prompt: "The MCU costs a total of $999.00.",
        "base prompt",
        truth,
        max_attempts=2,
        on_reject=logged.append,
    )

    assert len(logged) == 2
    assert all("999" in r.summary() for r in logged)


def test_overlapping_claims_are_reported_once(verifier):
    """A currency match and a quantity match can cover the same span;
    the correction note should name the problem once, not twice."""
    truth = GroundTruth().allow(ClaimKind.CURRENCY, 10.00)

    report = verifier.verify("That is $55.00 over.", truth)

    assert len(report.ungrounded) == 1


# --------------------------------------------------------------------
# Identifiers in the source data's own prose
# --------------------------------------------------------------------

def test_a_part_named_in_the_bom_is_grounded_even_if_it_is_not_the_full_mpn(verifier):
    """A BOM line called "ESP32-S3 module" with part number ESP32-S3-WROOM-1
    makes "the ESP32-S3 module" a faithful description, not an invention.
    Harvesting identifiers from the MPN field alone flagged it — noise on
    ordinary correct English, found while reproducing D-036."""
    class C:
        name = "ESP32-S3 module"
        cost_usd, quantity = 3.20, 1
        width_mm = depth_mm = height_mm = 10.0
        power_draw_w = 0.24
        manufacturer_part_number = "ESP32-S3-WROOM-1"

    truth = ground_truth_for_bom([C()])

    assert verifier.verify("The ESP32-S3 module draws little power.", truth).is_grounded


def test_harvesting_names_does_not_ground_an_unrelated_part(verifier):
    """The fix must not become a blanket amnesty for anything that looks
    like a part number."""
    class C:
        name = "ESP32-S3 module"
        cost_usd, quantity = 3.20, 1
        width_mm = depth_mm = height_mm = 10.0
        power_draw_w = 0.24
        manufacturer_part_number = "ESP32-S3-WROOM-1"

    truth = ground_truth_for_bom([C()])

    report = verifier.verify("Swap in the ATMEGA328P instead.", truth)
    assert not report.is_grounded
    assert "ATMEGA328P" in [c.value for c in report.ungrounded]
