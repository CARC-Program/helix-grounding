"""
The diagnostic report must be safe to paste in public.

That is the entire reason it exists. The ask in FIRST_USERS.md is "try to
break it and tell me what happened" — but a bill of materials names a
company's suppliers, exposes its costs, and describes its design. Nobody can
attach the file that broke the parser.

So the report carries structure and no contents. This file is what makes that
claim checkable, using a fixture whose every value is distinctive enough that
a leak cannot hide.
"""

import pytest

from helix_bom.cli import _describe_value, main

# Every value here is unusual on purpose: if any of them appears in the
# diagnostic output, a real part number or price would have too.
CONFIDENTIAL = {
    "part_name": "Zzyzx flux capacitor rev7",
    "mpn": "QQ-9931-SECRET",
    "manufacturer": "Umbrella Aerospace",
    "price": "1337.42",
    "quantity": "8675309",
    "designator": "U404",
}


@pytest.fixture
def sensitive_bom(tmp_path):
    path = tmp_path / "confidential.csv"
    path.write_text(
        "Designator,Description,Quantity,Manufacturer,MPN,Unit Price\n"
        f"{CONFIDENTIAL['designator']},{CONFIDENTIAL['part_name']},"
        f"{CONFIDENTIAL['quantity']},{CONFIDENTIAL['manufacturer']},"
        f"{CONFIDENTIAL['mpn']},{CONFIDENTIAL['price']}\n"
    )
    return path


def test_no_component_data_reaches_the_diagnostic(sensitive_bom, capsys):
    """The load-bearing test. If this fails, the feature is worse than not
    existing — it would invite people to publish their own data believing a
    promise that turned out to be false."""
    main(["diagnose", str(sensitive_bom)])
    out = capsys.readouterr().out

    for label, value in CONFIDENTIAL.items():
        assert value not in out, f"{label} leaked into the diagnostic: {value!r}"


def test_unreadable_cells_are_described_by_shape_not_content(tmp_path, capsys):
    """A cell that failed to parse is the most likely thing to be a supplier
    code or a negotiated price — precisely what must not be republished."""
    path = tmp_path / "messy.csv"
    path.write_text(
        "Description,Qty,Unit Price\n"
        "Widget,1,CONFIDENTIAL-RATE-X99\n"
    )

    main(["diagnose", str(path)])
    out = capsys.readouterr().out

    assert "CONFIDENTIAL-RATE-X99" not in out
    assert "21 chars" in out            # the shape, which is what debugs it
    assert "Unit Price" in out          # the column, which is not sensitive


def test_the_report_still_says_enough_to_debug_a_parsing_bug(sensitive_bom, capsys):
    """Redaction that removes the useful part is just a blank page."""
    main(["diagnose", str(sensitive_bom)])
    out = capsys.readouterr().out

    assert "encoding" in out
    assert "delimiter" in out
    assert "header row" in out
    assert "MPN" in out                       # heading, not the part number
    assert "manufacturer_part_number" in out  # what it mapped to
    assert "decimal separator" in out


def test_headings_are_included_and_the_caveat_is_stated(sensitive_bom, capsys):
    """Headings have to be included — the parser matches on them, so a bug
    report without them is undebuggable. A heading could still name a
    project, so the report says to edit it rather than pretending the risk
    is zero."""
    main(["diagnose", str(sensitive_bom)])
    out = capsys.readouterr().out

    assert "headers found" in out
    assert "edit it before posting" in out


def test_diagnose_exits_zero_even_when_the_review_would_not(capsys):
    """Running a diagnostic is not a build step, and a non-zero exit would
    make it look like the diagnostic itself failed."""
    assert main(["diagnose", "tests/fixtures/altium_with_pricing.csv"]) == 0


@pytest.mark.parametrize("value,expected", [
    ("", "empty"),
    ("ask supplier", "12 chars, letters"),
    ("$1,234.56", "9 chars, digits, comma, dot, currency symbol"),
    ("(50)", "4 chars, digits, bracket"),
    ("12%", "3 chars, digits, percent"),
])
def test_value_shapes_describe_without_repeating(value, expected):
    assert _describe_value(value) == expected
