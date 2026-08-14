"""
Tests for reading a BOM the way it actually arrives.

Every fixture here is shaped like a real export, because the gap between
hand-built Component objects and a stranger's file is exactly where this
tool was unusable.
"""

import pytest

from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints
from helix_bom.ingest import _parse_money, load_bom

FIXTURES = "tests/fixtures"


# --------------------------------------------------------------------
# Real export shapes
# --------------------------------------------------------------------

def test_kicad_preamble_is_skipped():
    """KiCad writes four lines of tool metadata before the header. Assuming
    row 1 is the header fails on every KiCad file ever exported."""
    components, report = load_bom(f"{FIXTURES}/kicad_grouped.csv")

    assert report.header_row == 6
    assert len(components) == 5
    assert report.mapped["quantity"] == "Qnty"


def test_kicad_description_is_preferred_over_value_as_the_name():
    """A KiCad row has Value='10k' and Description='Resistor, 10k 1%'. The
    description is the one a human reading a report can act on."""
    components, _ = load_bom(f"{FIXTURES}/kicad_grouped.csv")

    assert components[0].name == "Resistor, 10k 1%"


def test_semicolon_delimited_files_are_detected():
    """Excel writes semicolons in locales where the comma is a decimal
    point. A comma-only reader sees one giant column."""
    components, report = load_bom(f"{FIXTURES}/altium_with_pricing.csv")

    assert report.delimiter == ";"
    assert len(components) == 5


def test_do_not_populate_rows_are_excluded():
    """A DNP part is not fitted, so it costs nothing and occupies no space.
    Counting it inflates every total on the report."""
    components, report = load_bom(f"{FIXTURES}/altium_with_pricing.csv")

    assert report.rows_skipped_dnp == 1
    assert not any("not fitted" in c.name for c in components)


def test_dnp_rows_are_subtracted_exactly_once():
    """BUG: rows_used decremented rows_read *and* subtracted the DNP count,
    so a file with one DNP row reported one fewer line item than it had.
    Caught by reading the output, not by a failing test."""
    components, report = load_bom(f"{FIXTURES}/altium_with_pricing.csv")

    assert report.rows_used == len(components) == 5


def test_lead_times_and_part_numbers_survive_the_round_trip():
    components, _ = load_bom(f"{FIXTURES}/altium_with_pricing.csv")
    mcu = next(c for c in components if "MCU" in c.name)

    assert mcu.manufacturer_part_number == "STM32F401RET6"
    assert mcu.lead_time_days == 120
    assert mcu.cost_usd == pytest.approx(8.42)


# --------------------------------------------------------------------
# Numbers, as different continents write them
# --------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("$1.23", 1.23),
    ("1.23", 1.23),
    ("$1,234.56", 1234.56),      # thousands
    ("1,000", 1000.0),           # thousands, no decimals
    ("USD 8.42", 8.42),
    ("(2.50)", -2.50),           # accounting-style negative
    ("", 0.0),
])
def test_money_parses_us_convention(raw, expected):
    assert _parse_money(raw, ".") == pytest.approx(expected)


@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 1234.56),       # thousands
    ("12,50", 12.50),
    ("0,08", 0.08),
    ("€4,10", 4.10),
    ("1.000", 1000.0),           # thousands, no decimals
])
def test_money_parses_european_convention(raw, expected):
    assert _parse_money(raw, ",") == pytest.approx(expected)


@pytest.mark.parametrize("samples,expected", [
    (["$1,234.56", "12.50"], "."),
    (["1.234,56", "12,50"], ","),
    (["1.000", "2.000", "0,08"], ","),
    (["1,000", "2,000"], "."),
    (["10", "20", "30"], "."),          # no evidence either way: US default
    (["1.234,56", "1,000"], ","),       # the decisive form outvotes the weak one
])
def test_the_number_convention_is_decided_per_file(samples, expected):
    """Read cell by cell, "1.000" is both one and one thousand and nothing
    resolves it. The rest of the file resolves it."""
    from helix_bom.ingest import detect_decimal_separator

    assert detect_decimal_separator(samples) == expected


def test_european_spreadsheet_reads_correctly_end_to_end():
    components, _ = load_bom(f"{FIXTURES}/spreadsheet_european.csv")
    widget, bracket, screw = components

    assert widget.quantity == 1000 and widget.cost_usd == pytest.approx(1234.56)
    assert bracket.quantity == 10 and bracket.cost_usd == pytest.approx(12.50)
    assert screw.quantity == 2000 and screw.cost_usd == pytest.approx(0.08)


# --------------------------------------------------------------------
# Messy input stays legible
# --------------------------------------------------------------------

def test_unreadable_cells_are_reported_not_guessed(tmp_path):
    """A price of 'ask supplier' is not zero. Coercing it silently produces
    a confident total from a file the tool half-understood."""
    path = tmp_path / "messy.csv"
    path.write_text(
        "Description,Qty,Unit Price\n"
        "Widget,2,$4.00\n"
        "Mystery part,1,ask supplier\n"
    )

    components, report = load_bom(path)

    assert len(report.problems) == 1
    problem = report.problems[0]
    assert problem.row == 3                      # as the spreadsheet numbers it
    assert problem.value == "ask supplier"
    assert components[1].cost_usd == 0.0


def test_ambiguous_columns_are_flagged(tmp_path):
    """'Cost' might be a unit price or a line total. Matching it is right;
    doing so silently is not."""
    path = tmp_path / "ambiguous.csv"
    path.write_text("Part,Qty,Cost\nWidget,2,4.00\n")

    _, report = load_bom(path)

    assert "Cost" in report.ambiguous
    assert "line total" in report.ambiguous["Cost"]


def test_blank_rows_are_ignored_not_counted(tmp_path):
    path = tmp_path / "gaps.csv"
    path.write_text("Part,Qty,Price\nA,1,1.00\n\n\nB,2,2.00\n")

    components, report = load_bom(path)

    assert len(components) == 2
    assert report.rows_used == 2


def test_missing_quantity_defaults_to_one(tmp_path):
    path = tmp_path / "noqty.csv"
    path.write_text("Description,Unit Price\nWidget,4.00\n")

    components, _ = load_bom(path)

    assert components[0].quantity == 1


def test_a_file_that_is_not_a_bom_says_so(tmp_path):
    """Guessing at a file that has no header is worse than refusing it."""
    path = tmp_path / "readme.csv"
    path.write_text("hello world\nthis is not a bom\n")

    with pytest.raises(ValueError, match="no header row found"):
        load_bom(path)


def test_a_bom_with_no_name_column_says_which_columns_would_work(tmp_path):
    path = tmp_path / "anonymous.csv"
    path.write_text("Qty,Unit Price\n2,4.00\n")

    with pytest.raises(ValueError, match="Description, Comment, Value"):
        load_bom(path)


def test_excel_byte_order_mark_does_not_corrupt_the_first_header(tmp_path):
    """Excel prefixes a UTF-8 BOM. Read as plain utf-8 the first header
    becomes '﻿Description' and matches nothing."""
    path = tmp_path / "excel.csv"
    path.write_bytes("Description,Qty,Unit Price\nWidget,2,4.00\n".encode("utf-8-sig"))

    components, report = load_bom(path)

    assert report.mapped["name"] == "Description"
    assert components[0].name == "Widget"


# --------------------------------------------------------------------
# The dangerous case: a check that did not run must not look like a pass
# --------------------------------------------------------------------

def test_a_real_export_reports_what_it_could_not_check():
    """A KiCad export has no prices, dimensions, power or lead times. Before
    this, the physical and power checks compared zeros, found nothing, and
    stayed quiet — so the report read as a clean bill of health."""
    components, _ = load_bom(f"{FIXTURES}/kicad_grouped.csv")

    result = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )

    assert not result.is_complete
    skipped = {s.name for s in result.skipped_checks}
    assert {"budget", "physical fit", "power budget"} <= skipped


def test_the_headline_finding_never_reads_as_clean_when_checks_were_skipped():
    components, _ = load_bom(f"{FIXTURES}/kicad_grouped.csv")

    result = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )
    headline = result.findings[0]

    assert headline.severity == "warning"
    assert "not a clean bill of health" in headline.message


def test_a_complete_bom_says_every_check_ran():
    """The fix must not cry wolf on data that genuinely supports every
    check."""
    components = [
        Component("MCU", 8.42, 10, 10, 1.6, 0.5, "compute", 1,
                  manufacturer_part_number="STM32F401RET6", lead_time_days=14),
        Component("LiPo cell", 4.00, 50, 34, 10, 0.0, "power", 1, lead_time_days=7),
    ]

    result = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )

    assert result.is_complete
    assert result.findings[0].message.startswith("No issues found. Every check ran")


def test_a_fully_in_stock_bom_is_not_reported_as_unchecked():
    """`lead_time_days=0` means "in stock", not "unknown". Inferring
    availability from all-zeros warned that lead time went unchecked on a BOM
    where every part was in stock — a false positive, and false positives here
    train the reader to skim past the section that exists to be read."""
    components = [
        Component("MCU", 8.42, 10, 10, 1.6, 0.5, "compute", 1, lead_time_days=0),
        Component("LiPo cell", 4.00, 50, 34, 10, 0.0, "power", 1, lead_time_days=0),
    ]

    result = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )

    assert result.is_complete
    assert not any(s.name == "supply-chain lead time" for s in result.skipped_checks)


def test_the_file_column_set_beats_inference_when_it_is_available():
    """A price column of all zeros is a priced BOM of free samples, not an
    unpriced one. Only the file's headers can tell those apart, so the ingest
    layer's answer wins over the agent's guess."""
    components = [Component("Free sample", 0.0, 10, 10, 2, 0.1, "misc", 1)]
    fields = {"name", "cost_usd", "quantity", "width_mm", "category",
              "power_draw_w", "lead_time_days"}

    inferred = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )
    told = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0),
        available_fields=fields,
    )

    assert any(s.name == "budget" for s in inferred.skipped_checks)
    assert not any(s.name == "budget" for s in told.skipped_checks)


def test_physical_fit_still_fires_when_dimensions_are_present():
    """Gating checks on data availability must not disable them."""
    components = [Component("Oversized panel", 5.00, 200, 20, 3, 0.1, "display", 1,
                            lead_time_days=5)]

    result = BOMReviewAgent().review(
        components, DesignConstraints(50.0, 100.0, 80.0, 25.0, 5.0)
    )

    assert any("exceeds enclosure width" in f.message for f in result.findings)
