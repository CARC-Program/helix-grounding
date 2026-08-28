"""
Tests for the checks that need nothing but the file.

These exist because `enrich` shipped in 0.2.0 doing nothing without a
distributor account: ten lines, zero checked, one message repeated ten times.
The feature was real and the gate was green and a stranger installing it got
no value at all, which is the outcome the whole first-user strategy depends on
avoiding.

The most important test in here is not one that proves a defect is caught. It
is `test_a_numeric_part_number_is_not_mistaken_for_a_value`, which proves a
*correct* line is left alone. This rule's first version called a real Wurth
part number "a value, not a part number" and marked it CRITICAL. A tool that
accuses correct work is worse than one that misses defects, because the second
is a nuisance and the first is a reason to stop using it.
"""

import pytest

from helix_bom.agent import Component
from helix_bom.structure import (
    check,
    expand_designators,
    looks_like_a_value,
)


def _part(mpn="RC0603FR-0710KL", designator="R1", quantity=1, name="a part"):
    return Component(name=name, cost_usd=0.0, width_mm=0, depth_mm=0, height_mm=0,
                     power_draw_w=0, category="", quantity=quantity,
                     manufacturer_part_number=mpn, designator=designator)


def _messages(components):
    return [f.message for f in check(components)]


# --------------------------------------------------------------------
# Values against part numbers
# --------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "10k", "100nF", "4.7uF", "1M", "22pF", "10R", "0.1uF", "100 nF", "2.2k", "1uH",
])
def test_a_component_value_is_recognised(text):
    assert looks_like_a_value(text)


@pytest.mark.parametrize("text", [
    "61300411121",          # Wurth -- the one this rule accused
    "0022232021",           # Molex
    "1-1234567-8",          # TE
    "RC0603FR-0710KL",      # Yageo
    "STM32F401RET6",
    "GRM188R71H104KA93D",
    "2N3904", "1N4148", "LM358",
    "0603",                 # a footprint, not a value and not a part
])
def test_a_numeric_part_number_is_not_mistaken_for_a_value(text):
    """The false positive that made this rule require a unit.

    Numeric part numbers are ordinary -- Wurth, Molex and TE all use them. A
    bare number is far more likely to be a part number than a value, so it is
    left alone. That costs the rule "10" for a ten-ohm resistor, which is the
    right way to be wrong.
    """
    assert not looks_like_a_value(text)


def test_a_value_in_the_part_number_column_is_critical():
    findings = check([_part(mpn="10k")])
    assert findings[0].severity == "critical"
    assert "value, not a part number" in findings[0].message


# --------------------------------------------------------------------
# Designators
# --------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("R1", ["R1"]),
    ("R1, R2, R3", ["R1", "R2", "R3"]),
    ("C1;C2;C3", ["C1", "C2", "C3"]),
    ("J1-J4", ["J1", "J2", "J3", "J4"]),
    ("R3..R5", ["R3", "R4", "R5"]),
    ("U1, U3-U5", ["U1", "U3", "U4", "U5"]),
    ("", []),
])
def test_designators_expand_including_ranges(text, expected):
    """Ranges are the reason this is not a comma count. A line reading "R3-R5"
    covers three parts, and counting commas would call every BOM that uses
    ranges a mismatch."""
    assert expand_designators(text) == expected


def test_a_runaway_range_is_left_alone_rather_than_expanded():
    """"R1-R99999" is a typo, not ninety-nine thousand resistors. Expanding it
    would hang the report rather than report the problem."""
    assert expand_designators("R1-R99999") == ["R1-R99999"]


def test_designators_that_do_not_match_the_quantity_are_caught():
    """One of the two numbers is wrong and the tool cannot say which. Both
    readings are expensive: order too few and the build stops; order by the
    designator count and the cost is wrong."""
    findings = check([_part(designator="R1, R2, R3", quantity=2)])
    assert any("3 designator(s) but a quantity of 2" in f.message for f in findings)


def test_matching_designators_and_quantity_are_silent():
    assert not check([_part(designator="R1, R2, R3", quantity=3)])


def test_a_range_counts_as_its_expansion_against_the_quantity():
    assert not check([_part(designator="J1-J4", quantity=4)])


def test_the_same_designator_on_two_lines_is_critical():
    """A reference designates one part on the board. Two lines claiming R3 means
    one of them is wrong, and no distributor or assembly house catches it."""
    findings = check([
        _part(designator="R1, R2, R3", quantity=3, name="10k"),
        _part(designator="R3, R4", quantity=2, name="4k7", mpn="RC0603FR-074K7L"),
    ])
    duplicate = [f for f in findings if "appears on 2 lines" in f.message]
    assert duplicate and duplicate[0].severity == "critical"
    assert duplicate[0].reference == "R3"


def test_a_line_with_no_designator_does_not_produce_a_quantity_finding():
    """A netlist always has references; a spreadsheet often does not. Absence
    is not a mismatch."""
    assert not check([_part(designator="", quantity=5)])


# --------------------------------------------------------------------
# Missing and placeholder part numbers
# --------------------------------------------------------------------

def test_no_part_number_at_all_is_critical():
    """The commonest defect in the archive: not a wrong part number, no part
    number. `docs/DEMAND_EVIDENCE.md` has the evidence."""
    findings = check([_part(mpn="")])
    assert findings[0].severity == "critical"
    assert "no manufacturer part number" in findings[0].message


@pytest.mark.parametrize("text", ["TBD", "tbd", "TODO", "N/A", "???", "XXX", "-"])
def test_a_placeholder_part_number_is_critical(text):
    findings = check([_part(mpn=text)])
    assert any("placeholder" in f.message for f in findings)
    assert findings[0].severity == "critical"


def test_a_real_part_number_produces_nothing():
    """The baseline. Without it, a rule that always fires looks rigorous."""
    assert check([_part()]) == []


# --------------------------------------------------------------------
# Across lines
# --------------------------------------------------------------------

def test_the_same_part_on_two_lines_is_reported_with_the_total():
    """Two lines, one part: ordered twice and costed twice."""
    findings = check([
        _part(mpn="STM32F401RET6", designator="U1", name="MCU"),
        _part(mpn="STM32F401RET6", designator="U2", name="MCU again"),
    ])
    repeated = [f for f in findings if "separate lines" in f.message]
    assert repeated and repeated[0].severity == "warning"
    assert "2 will be ordered" in repeated[0].evidence


def test_part_numbers_are_compared_without_regard_to_case():
    findings = check([_part(mpn="stm32f401ret6", designator="U1"),
                      _part(mpn="STM32F401RET6", designator="U2")])
    assert any("separate lines" in f.message for f in findings)


def test_lines_with_no_part_number_are_not_counted_as_duplicates_of_each_other():
    """Three lines missing an MPN is three missing MPNs, not a duplicate."""
    findings = check([_part(mpn="", designator="C1"), _part(mpn="", designator="C2")])
    assert not [f for f in findings if "separate lines" in f.message]
    assert len([f for f in findings if "no manufacturer part number" in f.message]) == 2


# --------------------------------------------------------------------
# Shape of the output
# --------------------------------------------------------------------

def test_findings_come_out_worst_first():
    findings = check([
        _part(mpn="", designator="C1"),                       # critical
        _part(designator="R1, R2", quantity=1),               # warning
    ])
    ranks = {"critical": 0, "warning": 1, "info": 2}
    assert [ranks[f.severity] for f in findings] == \
        sorted(ranks[f.severity] for f in findings)


def test_every_finding_names_something_and_explains_itself():
    findings = check([_part(mpn=""), _part(mpn="10k", designator="R9")])
    assert findings
    for finding in findings:
        assert finding.reference and finding.reference != "?"
        assert finding.message and finding.evidence


def test_an_empty_bom_produces_nothing():
    assert check([]) == []
