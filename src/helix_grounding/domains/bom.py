"""
BOM domain adapter — builds a GroundTruth from a bill of materials.

This is the reference adapter, and the pattern every other domain should
follow: the library core knows nothing about components or enclosures,
and this module knows nothing about regexes or tolerances. A new domain
is a new file here, not a change to the core.

What makes a domain adapter correct is completeness — every value the
prompt supplies to the model must be allowed here, or the model will be
punished for faithfully repeating what it was told. That failure mode is
worse than a missed fabrication because it is silent and it trains the
operator to distrust the validator.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from ..claims import ClaimKind
from ..truth import GroundTruth


@runtime_checkable
class ComponentLike(Protocol):
    """Structural type for a BOM line item.

    Deliberately structural: the adapter works with the existing Helix
    Component dataclass, a Pydantic model, or an ORM row, without any of
    them importing this library.
    """

    name: str
    cost_usd: float
    width_mm: float
    depth_mm: float
    height_mm: float
    power_draw_w: float
    quantity: int


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def ground_truth_for_bom(
    components: Iterable[ComponentLike],
    constraints: Any = None,
    alternatives: Iterable[Any] = (),
    allow_comparisons: bool = True,
) -> GroundTruth:
    """Build the set of values a BOM review is allowed to state.

    ``alternatives`` are looked-up substitute parts already supplied to
    the model. They must be allowed here or every sourcing suggestion the
    model correctly repeats will be flagged as invented.

    ``allow_comparisons`` permits pairwise differences between costs and
    lead times, because a review that names a cheaper part will state the
    gap. Turn it off for a stricter check when the prompt forbids the
    model from computing anything itself.
    """
    components = list(components)
    truth = GroundTruth()

    unit_costs = [float(c.cost_usd) for c in components]
    line_costs = [float(c.cost_usd) * int(c.quantity) for c in components]

    truth.allow_many(ClaimKind.CURRENCY, unit_costs)
    truth.allow_many(ClaimKind.CURRENCY, line_costs)
    truth.allow_total(ClaimKind.CURRENCY, line_costs)

    truth.allow_many(ClaimKind.QUANTITY, (int(c.quantity) for c in components))

    for component in components:
        truth.allow(ClaimKind.MEASUREMENT, component.width_mm, "mm")
        truth.allow(ClaimKind.MEASUREMENT, component.depth_mm, "mm")
        truth.allow(ClaimKind.MEASUREMENT, component.height_mm, "mm")
        truth.allow(ClaimKind.MEASUREMENT, component.power_draw_w, "W")
        truth.allow(
            ClaimKind.MEASUREMENT,
            float(component.power_draw_w) * int(component.quantity),
            "W",
        )

        lead_time = _attr(component, "lead_time_days", 0) or 0
        if lead_time:
            for unit in ("days", "day", "weeks", "week"):
                if unit.startswith("day"):
                    truth.allow(ClaimKind.MEASUREMENT, float(lead_time), unit)

        truth.allow_token(_attr(component, "manufacturer_part_number", "") or "")

    total_power = sum(
        float(c.power_draw_w) * int(c.quantity) for c in components
    )
    truth.allow(ClaimKind.MEASUREMENT, total_power, "W")

    if constraints is not None:
        budget = float(_attr(constraints, "budget_usd", 0.0))
        truth.allow(ClaimKind.CURRENCY, budget)
        total_cost = sum(line_costs)
        if total_cost > budget:
            truth.allow(ClaimKind.CURRENCY, total_cost - budget)

        for field_name, unit in (
            ("enclosure_width_mm", "mm"),
            ("enclosure_depth_mm", "mm"),
            ("enclosure_height_mm", "mm"),
            ("power_budget_w", "W"),
        ):
            value = _attr(constraints, field_name)
            if value is not None:
                truth.allow(ClaimKind.MEASUREMENT, float(value), unit)

        power_budget = _attr(constraints, "power_budget_w")
        if power_budget is not None and total_power > float(power_budget):
            truth.allow(
                ClaimKind.MEASUREMENT, total_power - float(power_budget), "W"
            )

    alternative_costs: list[float] = []
    alternative_leads: list[float] = []
    for alternative in alternatives:
        cost = float(_attr(alternative, "cost_usd", 0.0))
        truth.allow(ClaimKind.CURRENCY, cost)
        alternative_costs.append(cost)
        truth.allow_token(_attr(alternative, "manufacturer_part_number", "") or "")

        lead = _attr(alternative, "lead_time_days", None)
        if lead is not None:
            alternative_leads.append(float(lead))
            for unit in ("days", "day"):
                truth.allow(ClaimKind.MEASUREMENT, float(lead), unit)

    if allow_comparisons:
        # A review naming a substitute will state the price gap and the
        # lead-time gap. Allowing those differences explicitly is what
        # stopped legitimate comparisons being reported as fabrications.
        truth.allow_pairwise_differences(
            ClaimKind.CURRENCY, unit_costs + alternative_costs
        )
        component_leads = [
            float(_attr(c, "lead_time_days", 0) or 0) for c in components
        ]
        all_leads = [lead for lead in component_leads + alternative_leads if lead]
        for unit in ("days", "day"):
            truth.allow_pairwise_differences(ClaimKind.MEASUREMENT, all_leads, unit)

    return truth
