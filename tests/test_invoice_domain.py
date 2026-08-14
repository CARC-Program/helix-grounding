"""
Tests for the invoice domain adapter and the date support it forced.

The point of a second domain is to find out whether the core generalises or
whether it was quietly shaped around the first one. The last section tests
that directly.
"""

import datetime

import pytest

from helix_grounding import ClaimKind, DateExtractor, GroundTruth, Verifier
from helix_grounding.domains.invoice import ground_truth_for_invoice


class Line:
    def __init__(self, description, quantity, unit_price, sku=""):
        self.description = description
        self.quantity = quantity
        self.unit_price = unit_price
        self.sku = sku


class Invoice:
    def __init__(self, **kw):
        self.number = kw.get("number", "INV-2026-0412")
        self.lines = kw.get("lines", [])
        self.tax_rate = kw.get("tax_rate", 0.0)
        self.discount_rate = kw.get("discount_rate", 0.0)
        self.issue_date = kw.get("issue_date")
        self.due_date = kw.get("due_date")
        self.payment_terms_days = kw.get("payment_terms_days")
        self.amount_paid = kw.get("amount_paid")


@pytest.fixture
def invoice():
    """$1,000 of goods, 10% off, 8.25% tax on what's left.

    subtotal  1000.00
    discount  -100.00  (10%)
    taxable    900.00
    tax        +74.25  (8.25%)
    total      974.25
    """
    return Invoice(
        number="INV-2026-0412",
        lines=[
            Line("Widget A", 10, 40.00, sku="WGT-A"),
            Line("Widget B", 4, 150.00, sku="WGT-B"),
        ],
        discount_rate=10.0,
        tax_rate=8.25,
        issue_date=datetime.date(2026, 8, 16),
        due_date=datetime.date(2026, 9, 15),
        payment_terms_days=30,
    )


@pytest.fixture
def verifier():
    return Verifier()


# --------------------------------------------------------------------
# The derivation chain — the thing BOM never exercised
# --------------------------------------------------------------------

def test_every_step_of_the_chain_is_allowed(invoice, verifier):
    """A summary quotes the working, not just the answer. A ground truth
    holding only the total would report every correct intermediate figure as
    a fabrication."""
    truth = ground_truth_for_invoice(invoice)

    text = (
        "Invoice INV-2026-0412: subtotal $1,000.00, less a 10% discount of "
        "$100.00, leaves $900.00 taxable. Tax at 8.25% adds $74.25, for a "
        "total of $974.25 due 2026-09-15 on 30 day terms."
    )
    report = verifier.verify(text, truth)

    assert report.is_grounded, report.summary()


def test_a_wrong_total_is_caught(invoice, verifier):
    truth = ground_truth_for_invoice(invoice)

    report = verifier.verify("The total due is $1,074.25.", truth)

    assert not report.is_grounded
    assert 1074.25 in [c.value for c in report.ungrounded]


def test_a_plausible_but_wrong_tax_amount_is_caught(invoice, verifier):
    """$82.50 is 8.25% of the *subtotal* rather than the discounted base —
    exactly the arithmetic slip a model makes, and one that reads as correct
    to a human skimming the summary."""
    truth = ground_truth_for_invoice(invoice)

    report = verifier.verify("Tax at 8.25% comes to $82.50.", truth)

    assert not report.is_grounded
    assert 82.50 in [c.value for c in report.ungrounded]


def test_rounding_matches_the_printed_invoice(verifier):
    """If the adapter allows an unrounded figure while the invoice prints the
    rounded one, the model repeats the printed value and gets flagged for
    being right."""
    inv = Invoice(lines=[Line("Odd", 3, 33.333)], tax_rate=0.0)
    truth = ground_truth_for_invoice(inv)

    report = verifier.verify("The line comes to $100.00.", truth)

    assert report.is_grounded, report.summary()


def test_remaining_balance_is_allowed(verifier):
    inv = Invoice(lines=[Line("Widget", 1, 500.00)], tax_rate=0.0, amount_paid=200.00)
    truth = ground_truth_for_invoice(inv)

    report = verifier.verify("You have paid $200.00; $300.00 remains.", truth)

    assert report.is_grounded, report.summary()


# --------------------------------------------------------------------
# Dates — invisible to the library before this domain existed
# --------------------------------------------------------------------

def test_a_fabricated_due_date_is_caught(invoice, verifier):
    """Before ClaimKind.DATE this text produced no date claim at all, so an
    invented due date passed through silently. That is the single most
    valuable thing the invoice domain surfaced."""
    truth = ground_truth_for_invoice(invoice)

    report = verifier.verify("Payment is due 2026-10-01.", truth)

    assert not report.is_grounded
    assert "2026-10-01" in [c.value for c in report.ungrounded]


def test_the_real_due_date_passes_in_any_format(invoice, verifier):
    """The invoice says 2026-09-15; a summary may write that a dozen ways."""
    truth = ground_truth_for_invoice(invoice)

    for written in ("2026-09-15", "09/15/2026", "September 15, 2026", "15 Sept 2026"):
        report = verifier.verify(f"Due {written}.", truth)
        assert report.is_grounded, f"{written}: {report.summary()}"


@pytest.mark.parametrize("text,expected", [
    ("2026-09-15", "2026-09-15"),
    ("09/15/2026", "2026-09-15"),
    ("15/09/2026", "2026-09-15"),   # unambiguous: 15 cannot be a month
    ("September 15, 2026", "2026-09-15"),
    ("15 September 2026", "2026-09-15"),
    ("1st March 2026", "2026-03-01"),
])
def test_date_formats_normalise_to_iso(text, expected):
    claims = DateExtractor().extract(f"dated {text} exactly")

    assert [c.value for c in claims] == [expected]


@pytest.mark.parametrize("bad", ["2026-02-31", "2026-13-01", "2026-02-29"])
def test_impossible_dates_are_rejected_not_normalised(bad):
    """A fabricated 2026-02-31 must not quietly become a real day. 2026 is
    not a leap year, so the 29th is impossible too."""
    assert DateExtractor().extract(f"due {bad}") == []


def test_ambiguous_numeric_dates_follow_the_configured_convention():
    """03/04/2026 is March 4th in the US and April 3rd nearly everywhere
    else. No parser resolves that — the caller picks."""
    assert DateExtractor().extract("03/04/2026")[0].value == "2026-03-04"
    assert DateExtractor(day_first=True).extract("03/04/2026")[0].value == "2026-04-03"


def test_a_date_is_reported_once_not_per_matching_pattern():
    claims = DateExtractor().extract("Issued September 15, 2026 and shipped.")

    assert len(claims) == 1


def test_dates_are_exact_not_approximate():
    """Numeric kinds compare with a tolerance. A day either is or is not the
    due date — one day out is wrong, not nearly right."""
    truth = GroundTruth().allow_date("2026-09-15")

    assert truth.permits(ClaimKind.DATE, "2026-09-15")
    assert not truth.permits(ClaimKind.DATE, "2026-09-16")


def test_allow_date_accepts_date_objects_and_strings():
    """Callers hold real date objects; making them stringify first is the
    kind of friction that gets an adapter written wrong."""
    truth = GroundTruth().allow_date(datetime.date(2026, 9, 15))

    assert truth.permits(ClaimKind.DATE, "2026-09-15")


def test_identifier_and_date_tokens_do_not_collide():
    """Both are exact-match kinds sharing one storage mechanism. A date must
    not satisfy an identifier claim, or vice versa."""
    truth = GroundTruth().allow_token("INV-2026-0412").allow_date("2026-09-15")

    assert not truth.permits(ClaimKind.IDENTIFIER, "2026-09-15")
    assert not truth.permits(ClaimKind.DATE, "INV-2026-0412")


# --------------------------------------------------------------------
# Did the abstraction actually hold?
# --------------------------------------------------------------------

CORE_MODULES = ["claims", "extractors", "truth", "verifier"]


def _executable_source(module: str) -> str:
    """A module's code with docstrings and comments removed.

    The first version of this test grepped raw source for domain words and
    failed on prose: MeasurementExtractor explained itself using a width and
    a height, and the date parser calls a day a "component" of a date. Both
    matched a naive blacklist; neither is coupling. Stripping to executable
    code is what actually tests the claim — a domain word surviving here
    means real coupling, not an illustrative sentence.
    """
    import ast
    import importlib
    import inspect

    tree = ast.parse(inspect.getsource(importlib.import_module(f"helix_grounding.{module}")))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)  # drop the docstring
    return ast.unparse(tree)


@pytest.mark.parametrize("module", CORE_MODULES)
def test_no_domain_concept_appears_in_core_code(module):
    """The whole claim of this library is that the core is domain-agnostic.
    If a domain concept reaches executable code, adding the third vertical
    means editing the verifier — and the claim is false.

    DEFAULT_KNOWN_VOCABULARY is the deliberate exception: it is public,
    extensible data whose hardware flavour is documented, not logic.
    """
    code = _executable_source(module).lower()
    if module == "extractors":
        code = code.split("default_known_vocabulary")[0] + code.split("})")[-1]

    for word in ("component", "enclosure", "invoice", "budget", "supplier"):
        assert word not in code, f"{module}.py couples to '{word}' in executable code"


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_never_imports_a_domain(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(f"helix_grounding.{module}"))

    assert "domains" not in source


def test_adding_a_domain_touched_no_domain_specific_core_logic():
    """The invoice adapter forced two core changes — ClaimKind.DATE and
    per-kind token storage. Both are general capabilities usable by any
    domain, which is the difference between extending a library and
    special-casing one."""
    from helix_grounding import TOKEN_KINDS
    from helix_grounding.domains.bom import ground_truth_for_bom

    # The BOM domain can use the date support the invoice domain forced,
    # without a line of invoice code being involved.
    truth = ground_truth_for_bom([]).allow_date("2026-09-15")

    assert truth.permits(ClaimKind.DATE, "2026-09-15")
    assert ClaimKind.DATE in TOKEN_KINDS


def test_both_domains_produce_a_working_ground_truth_from_the_same_core(invoice):
    """The end-to-end version of the same claim: one Verifier, two domains,
    no domain-specific configuration."""
    from helix_grounding.domains.bom import ground_truth_for_bom

    class Component:
        name, cost_usd, quantity = "MCU", 18.00, 1
        width_mm = depth_mm = height_mm = 10.0
        power_draw_w = 1.0
        manufacturer_part_number = "STM32F401RE"

    verifier = Verifier()

    bom_report = verifier.verify("The MCU is $18.00.", ground_truth_for_bom([Component()]))
    inv_report = verifier.verify("The total is $974.25.", ground_truth_for_invoice(invoice))

    assert bom_report.is_grounded, bom_report.summary()
    assert inv_report.is_grounded, inv_report.summary()
