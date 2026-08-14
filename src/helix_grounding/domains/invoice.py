"""
Invoice domain adapter — the second domain, and the one that tested whether
the core actually generalises.

BOM review is sums and comparisons. An invoice is a *chain*: line totals feed
a subtotal, the subtotal feeds a discount, what's left feeds a tax, and tax
feeds the total. Every intermediate figure is something a model will state in
prose, and every one of them is a number a model can get wrong in a way that
costs somebody money.

Two things this exposed, both now fixed in the core rather than worked around
here:

  * A due date produced no claim at all. Dates were invisible to the library,
    so a model could invent one and nothing noticed. ``ClaimKind.DATE`` and
    ``DateExtractor`` exist because of this file.
  * ``GroundTruth`` stored exact-match tokens in a single untyped set, which
    only worked while identifiers were the sole exact-match kind. It is now
    keyed by kind.

Nothing else needed changing, which is the result the exercise was after.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from ..claims import ClaimKind
from ..truth import GroundTruth


@runtime_checkable
class InvoiceLineLike(Protocol):
    """Structural type for one line on an invoice."""

    description: str
    quantity: float
    unit_price: float


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _money(value: float) -> float:
    """Round to cents the way an invoice does.

    This matters more than it looks. If the adapter allows an unrounded
    89.13749999 while the invoice prints $89.14, the model faithfully repeats
    the printed figure and gets flagged for it. Rounding here is what keeps
    the check aligned with the document a human is actually holding.
    """
    return round(value + 1e-9, 2)


def ground_truth_for_invoice(
    invoice: Any,
    lines: Iterable[InvoiceLineLike] | None = None,
    allow_line_arithmetic: bool = True,
) -> GroundTruth:
    """Build the set of values an invoice summary is allowed to state.

    ``invoice`` supplies the header: ``number``, ``tax_rate`` and
    ``discount_rate`` as percentages, ``issue_date`` / ``due_date`` as ISO
    strings or ``date`` objects, ``payment_terms_days``, and ``currency``.
    Every field is optional — a partial invoice yields a partial ground truth
    rather than an error.

    ``lines`` defaults to ``invoice.lines``. Pass it explicitly when the
    caller holds them separately.

    ``allow_line_arithmetic`` permits per-line totals and the differences a
    summary states when comparing lines. Turn it off for a stricter check
    where the prompt forbids the model from computing anything itself.
    """
    if lines is None:
        lines = _attr(invoice, "lines", []) or []
    lines = list(lines)

    truth = GroundTruth()

    # --- line level -------------------------------------------------
    unit_prices = [float(line.unit_price) for line in lines]
    line_totals = [_money(float(line.unit_price) * float(line.quantity)) for line in lines]

    truth.allow_many(ClaimKind.CURRENCY, unit_prices)
    truth.allow_many(ClaimKind.QUANTITY, (float(line.quantity) for line in lines))
    if allow_line_arithmetic:
        truth.allow_many(ClaimKind.CURRENCY, line_totals)

    for line in lines:
        truth.allow_token(_attr(line, "sku", "") or "")

    # --- the derivation chain ---------------------------------------
    # Each step is allowed explicitly, because a summary quotes the steps and
    # not just the final figure. A ground truth holding only the total would
    # report every correct intermediate line as a fabrication.
    subtotal = _money(sum(line_totals))
    truth.allow(ClaimKind.CURRENCY, subtotal)

    discount_rate = float(_attr(invoice, "discount_rate", 0.0) or 0.0)
    discount_amount = _money(subtotal * discount_rate / 100.0)
    if discount_rate:
        truth.allow(ClaimKind.PERCENTAGE, discount_rate)
        truth.allow(ClaimKind.CURRENCY, discount_amount)

    taxable_base = _money(subtotal - discount_amount)
    truth.allow(ClaimKind.CURRENCY, taxable_base)

    tax_rate = float(_attr(invoice, "tax_rate", 0.0) or 0.0)
    tax_amount = _money(taxable_base * tax_rate / 100.0)
    if tax_rate:
        truth.allow(ClaimKind.PERCENTAGE, tax_rate)
        truth.allow(ClaimKind.CURRENCY, tax_amount)

    total = _money(taxable_base + tax_amount)
    truth.allow(ClaimKind.CURRENCY, total)

    # An explicit total on the invoice wins over the computed one. They should
    # agree; when they don't, the invoice is the document the customer holds,
    # and disagreeing with it is the caller's problem to notice -- not a
    # reason for this adapter to silently prefer its own arithmetic.
    stated_total = _attr(invoice, "total", None)
    if stated_total is not None:
        truth.allow(ClaimKind.CURRENCY, _money(float(stated_total)))

    # Amounts already paid, and what remains.
    amount_paid = _attr(invoice, "amount_paid", None)
    if amount_paid is not None:
        truth.allow(ClaimKind.CURRENCY, _money(float(amount_paid)))
        truth.allow(ClaimKind.CURRENCY, _money(total - float(amount_paid)))

    # --- identifiers, dates, terms ----------------------------------
    truth.allow_token(_attr(invoice, "number", "") or "")
    truth.allow_token(_attr(invoice, "purchase_order", "") or "")
    truth.allow_token(_attr(invoice, "account_number", "") or "")

    truth.allow_date(_attr(invoice, "issue_date", None))
    truth.allow_date(_attr(invoice, "due_date", None))
    truth.allow_date(_attr(invoice, "paid_date", None))

    terms_days = _attr(invoice, "payment_terms_days", None)
    if terms_days is not None:
        for unit in ("days", "day"):
            truth.allow(ClaimKind.MEASUREMENT, float(terms_days), unit)

    if allow_line_arithmetic:
        # A summary comparing two lines states the gap between them.
        truth.allow_pairwise_differences(ClaimKind.CURRENCY, line_totals)

    return truth
