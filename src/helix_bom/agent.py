"""
HELIX CORE — BOM Review Agent (first agent, per HELIX_DECISION_LOG.md D-014)

Scope, per AI_AGENT_FRAMEWORK.md: read-only analysis only. No consequential
actions. Every output is a written report for human review — nothing in
this agent sends, executes, or commits to anything on its own.

Two layers:
  1. Deterministic checks (budget, physical fit, power budget) — no LLM
     call required, fully testable offline with synthetic data.
  2. LLM synthesis (qualitative recommendations) — requires a real
     Anthropic (or configured) API key, supplied via environment variable
     at deploy time. NOT hardcoded here, NOT to be pasted into a chat
     conversation. This method is structurally complete but not exercised
     in sandbox testing until the owner supplies real credentials in their
     own deployment environment.
"""

from dataclasses import dataclass, field
from typing import Optional
import os

try:
    from dotenv import load_dotenv

    # Walk up from this file to find the repository root's .env, rather than
    # trusting the caller's working directory. The original code pinned the
    # lookup to this module's own folder, which was correct while the .env sat
    # beside it -- that placement was itself the fix for a real bug found by
    # field testing (D-023), where a bare load_dotenv() silently found nothing.
    # The rebuild moved the .env to the repository root, so the search has to
    # walk rather than pin; hardcoding "../.." would break again the next time
    # a module moves.
    #
    # encoding="utf-8-sig" transparently strips a UTF-8 BOM if present (common
    # when a .env is saved via Windows Notepad) and behaves identically to
    # plain utf-8 when there is none -- safe either way. That was a second real
    # bug (D-024), and it stays fixed here.
    _dir = os.path.dirname(os.path.abspath(__file__))
    while True:
        _candidate = os.path.join(_dir, ".env")
        if os.path.isfile(_candidate):
            load_dotenv(dotenv_path=_candidate, encoding="utf-8-sig")
            break
        _parent = os.path.dirname(_dir)
        if _parent == _dir:  # reached the filesystem root, no .env anywhere
            break
        _dir = _parent
except ImportError:
    pass  # python-dotenv not installed -- fall back to the real environment


@dataclass
class Component:
    name: str
    cost_usd: float  # unit cost -- total cost = cost_usd * quantity
    width_mm: float
    depth_mm: float
    height_mm: float
    power_draw_w: float  # per-unit draw -- total = power_draw_w * quantity
    category: str  # e.g. "compute", "power", "display", "connector"
    quantity: int = 1  # real BOMs list quantity per line item, not flat cost
    manufacturer: str = ""  # optional, e.g. "Texas Instruments" -- context for synthesis
    manufacturer_part_number: str = ""  # optional, e.g. "TPS61023DRLR"
    lead_time_days: int = 0  # 0 = not specified/in-stock; used by the new supply-chain check below


@dataclass
class DesignConstraints:
    budget_usd: float
    enclosure_width_mm: float
    enclosure_depth_mm: float
    enclosure_height_mm: float
    power_budget_w: float


@dataclass
class ReviewFinding:
    severity: str  # "info" | "warning" | "critical"
    message: str


@dataclass
class ReviewResult:
    findings: list = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_power_w: float = 0.0
    over_budget: bool = False
    over_power_budget: bool = False


class BOMReviewAgent:
    """Deterministic component-selection review — no LLM call in this class."""

    def review(self, components: list, constraints: DesignConstraints) -> ReviewResult:
        result = ReviewResult()

        # Real gap fixed here: a line item's true cost/power contribution
        # is unit_value * quantity, not just the unit value. Every prior
        # test used quantity=1 for everything, which masked this -- a
        # real BOM with, say, 20x of a $0.05 resistor was silently being
        # totaled as $0.05, not $1.00.
        result.total_cost_usd = sum(c.cost_usd * c.quantity for c in components)
        result.total_power_w = sum(c.power_draw_w * c.quantity for c in components)

        # Budget check
        if result.total_cost_usd > constraints.budget_usd:
            result.over_budget = True
            overage = result.total_cost_usd - constraints.budget_usd
            result.findings.append(ReviewFinding(
                "critical",
                f"BOM total (${result.total_cost_usd:.2f}) exceeds stated "
                f"budget (${constraints.budget_usd:.2f}) by ${overage:.2f}."
            ))

        # Power budget check
        if result.total_power_w > constraints.power_budget_w:
            result.over_power_budget = True
            overage_w = result.total_power_w - constraints.power_budget_w
            result.findings.append(ReviewFinding(
                "critical",
                f"Total power draw ({result.total_power_w:.1f}W) exceeds "
                f"stated power budget ({constraints.power_budget_w:.1f}W) "
                f"by {overage_w:.1f}W."
            ))

        # Physical fit check — same stack-up logic used on HELIX's own
        # enclosure (MK1_MECHANICAL_DESIGN.md, MK1_ENCLOSURE_DESIGN.md):
        # sum component footprints against enclosure envelope, don't just
        # check the single largest part. Note: physical dimensions are
        # per-unit regardless of quantity (quantity affects cost/power
        # totals, not footprint -- 20 resistors on a PCB don't stack
        # vertically the way this simplified check models placement).
        widest_component = max(components, key=lambda c: c.width_mm, default=None)
        deepest_component = max(components, key=lambda c: c.depth_mm, default=None)

        if widest_component and widest_component.width_mm > constraints.enclosure_width_mm:
            result.findings.append(ReviewFinding(
                "critical",
                f"{widest_component.name} ({widest_component.width_mm:.1f}mm wide) exceeds "
                f"enclosure width ({constraints.enclosure_width_mm:.1f}mm)."
            ))
        if deepest_component and deepest_component.depth_mm > constraints.enclosure_depth_mm:
            result.findings.append(ReviewFinding(
                "critical",
                f"{deepest_component.name} ({deepest_component.depth_mm:.1f}mm deep) exceeds "
                f"enclosure depth ({constraints.enclosure_depth_mm:.1f}mm)."
            ))
        # Height check — NOT a sum of all component heights. Summing every
        # line item (including tiny passives) as if they all stack
        # vertically was a reasonable proxy for 4-5 "major component" BOMs
        # (battery, display, compute board -- things that plausibly do
        # occupy separate layers), but produces false alarms at realistic
        # scale, where most parts mount flat, side-by-side, on the same
        # PCB layer. Caught via realistic-scale testing (D-033), not
        # theory. Using tallest single component as the honest proxy
        # instead -- true multi-layer stack analysis would need a
        # board-layer/mounting-side field this BOM format doesn't carry,
        # and pretending otherwise would be false precision.
        tallest_component = max(components, key=lambda c: c.height_mm, default=None)
        if tallest_component and tallest_component.height_mm > constraints.enclosure_height_mm:
            result.findings.append(ReviewFinding(
                "warning",
                f"Tallest single component ({tallest_component.name}, "
                f"{tallest_component.height_mm:.1f}mm) exceeds stated enclosure "
                f"height ({constraints.enclosure_height_mm:.1f}mm). Note: this "
                f"checks the single tallest part, not a full multi-layer stack "
                f"— confirming how components actually share PCB layers "
                f"requires board-layer data not present in this BOM format."
            ))

        # Missing-category sanity check
        categories_present = {c.category for c in components}
        expected = {"compute", "power"}
        missing = expected - categories_present
        for m in missing:
            result.findings.append(ReviewFinding(
                "warning",
                f"No component tagged category '{m}' found in the submitted "
                f"BOM — confirm this is intentional (e.g. power handled "
                f"off-BOM by an external supply)."
            ))

        # New: supply-chain lead-time risk check. A real, common reason a
        # hardware build slips schedule -- a part with a 90+ day lead
        # time can silently become the critical path on the whole build.
        LEAD_TIME_WARNING_DAYS = 90
        long_lead_parts = [c for c in components if c.lead_time_days >= LEAD_TIME_WARNING_DAYS]
        for c in long_lead_parts:
            result.findings.append(ReviewFinding(
                "warning",
                f"{c.name} has a stated lead time of {c.lead_time_days} days — "
                f"this is a real supply-chain risk that can silently become "
                f"the critical path for the whole build. Consider a "
                f"second-source alternative if one exists."
            ))

        if not result.findings:
            result.findings.append(ReviewFinding(
                "info", "No critical issues found in deterministic checks."
            ))

        return result

    def generate_interconnect_diagram(self, components: list) -> str:
        """
        High-level block/interconnect diagram based on component
        categories — NOT a verified schematic. This is the honestly-
        scoped version of "diagram/layout" capability: a flat BOM has no
        netlist, no pin assignments, no confirmed protocol per connection.
        What it does have is category tags, which support a reasonable
        *typical* interconnect suggestion (a compute module usually talks
        to sensors over I2C/SPI, to connectivity modules over UART/SPI,
        etc.) -- useful as a starting sketch, explicitly not a substitute
        for checking real datasheets and actually assigning pins.
        """
        by_category: dict = {}
        for c in components:
            by_category.setdefault(c.category, []).append(c)

        compute = by_category.get("compute", [])
        if not compute:
            return (
                "[No 'compute' category component found — cannot anchor an "
                "interconnect diagram without a central controller/MCU.]"
            )
        hub = compute[0].name
        box_width = max(len(hub) + 2, 19)

        # Typical protocol suggestions by category -- a reasonable
        # starting guess, not a verified connection. Stated as such in
        # the output itself, not just in this comment.
        protocol_by_category = {
            "sensor": "I2C/SPI (typical)",
            "display": "SPI/I2C (typical)",
            "connectivity": "UART/SPI (typical)",
            "connector": "direct/GPIO (typical)",
            "power": "voltage rail (typical)",
        }

        lines = [
            "=== SUGGESTED HIGH-LEVEL INTERCONNECT DIAGRAM ===",
            "(Based on component categories only -- NOT a verified schematic.",
            " Confirm actual protocol and pin assignment against real",
            " datasheets before wiring anything.)",
            "",
            f"                    +{'-' * box_width}+",
            f"                    | {hub:<{box_width - 1}}|  <- hub",
            f"                    +{'-' * box_width}+",
        ]
        connected_categories = [cat for cat in by_category if cat != "compute" and cat in protocol_by_category]
        for cat in connected_categories:
            parts = by_category[cat]
            proto = protocol_by_category[cat]
            names = ", ".join(p.name for p in parts[:3])
            if len(parts) > 3:
                names += f", +{len(parts) - 3} more"
            lines.append(f"                             | --[{proto}]--> {cat}: {names}")

        uncategorized = [cat for cat in by_category if cat != "compute" and cat not in protocol_by_category]
        if uncategorized:
            lines.append("")
            lines.append("Supporting/structural components (not shown as connections):")
            for cat in uncategorized:
                names = ", ".join(p.name for p in by_category[cat])
                lines.append(f"  - {cat}: {names}")

        return "\n".join(lines)

    def check_full_grounding(self, synthesis_text: str, components: list, constraints: DesignConstraints) -> dict:
        """
        Hard validation layer, run after every synthesis call, no soft
        warnings. Checks four categories of claim against ground truth:
        dollar amounts, dimensions, part numbers, and quantities. Returns
        a dict of {category: [ungrounded values found]} -- an empty dict
        means the text is fully grounded and safe to deliver. A non-empty
        dict must block delivery; see synthesize_recommendations_validated
        for the reject/regenerate flow this feeds.
        """
        import re

        issues = {}

        # --- Dollar amounts ---
        valid_dollars = set()
        for c in components:
            valid_dollars.add(round(c.cost_usd, 2))
            valid_dollars.add(round(c.cost_usd * c.quantity, 2))
        valid_dollars.add(round(constraints.budget_usd, 2))
        total_cost = sum(c.cost_usd * c.quantity for c in components)
        valid_dollars.add(round(total_cost, 2))
        if total_cost > constraints.budget_usd:
            valid_dollars.add(round(total_cost - constraints.budget_usd, 2))

        from helix_bom.components import lookup_alternatives
        known_mpns = set()
        for c in components:
            if c.manufacturer_part_number:
                known_mpns.add(c.manufacturer_part_number.upper())
                for a in lookup_alternatives(c.manufacturer_part_number):
                    known_mpns.add(a.manufacturer_part_number.upper())
                    valid_dollars.add(round(a.cost_usd, 2))
                    valid_dollars.add(round(abs(a.cost_usd - c.cost_usd), 2))

        found_dollars = re.findall(r"\$(\d+\.?\d*)", synthesis_text)
        bad_dollars = [round(float(f), 2) for f in found_dollars
                       if not any(abs(round(float(f), 2) - v) < 0.015 for v in valid_dollars)]
        if bad_dollars:
            issues["dollar_amounts"] = bad_dollars

        # --- Dimensions (e.g. "85mm", "50 mm") ---
        valid_dims = set()
        for c in components:
            valid_dims.update([round(c.width_mm, 1), round(c.depth_mm, 1), round(c.height_mm, 1)])
        valid_dims.update([round(constraints.enclosure_width_mm, 1),
                            round(constraints.enclosure_depth_mm, 1),
                            round(constraints.enclosure_height_mm, 1)])
        found_dims = re.findall(r"(\d+\.?\d*)\s*mm", synthesis_text)
        bad_dims = [round(float(f), 1) for f in found_dims
                    if not any(abs(round(float(f), 1) - v) < 0.15 for v in valid_dims)]
        if bad_dims:
            issues["dimensions_mm"] = bad_dims

        # --- Part numbers (alphanumeric tokens that look like MPNs) ---
        found_mpn_like = re.findall(r"\b[A-Z]{2,}[A-Z0-9\-]{2,}\d[A-Z0-9\-]*\b", synthesis_text)
        bad_mpns = [m for m in found_mpn_like if m.upper() not in known_mpns]
        if bad_mpns:
            issues["part_numbers"] = bad_mpns

        # --- Quantities (conservative: only clear multiplier patterns
        # like "x5" or "5 units", since bare numbers are too ambiguous to
        # check reliably without false positives) ---
        valid_quantities = {c.quantity for c in components}
        found_qty = re.findall(r"\bx\s?(\d+)\b|\b(\d+)\s*units?\b", synthesis_text, re.IGNORECASE)
        flat_qty = [int(a or b) for a, b in found_qty]
        bad_qty = [q for q in flat_qty if q not in valid_quantities]
        if bad_qty:
            issues["quantities"] = bad_qty

        return issues

    def synthesize_recommendations_validated(self, review_result: ReviewResult, components: list,
                                              constraints: DesignConstraints, max_retries: int = 2) -> dict:
        """
        The actual reject/regenerate flow. Never returns unvalidated text.
        On each failed attempt, the specific fabricated values are fed
        back into the retry prompt as an explicit correction, not just a
        blind resample. After max_retries failures, returns a safe
        fallback (deterministic findings only, no narrative) rather than
        ever delivering unvalidated content to a client.

        Returns: {"text": str, "validated": bool, "rejected_attempts": list}
        rejected_attempts logs exactly what was invented on each failed
        try, per the audit requirement -- nothing is silently discarded.
        """
        rejected_attempts = []
        correction_note = ""

        for attempt in range(max_retries + 1):
            text = self.synthesize_recommendations(review_result, components, correction_note)
            issues = self.check_full_grounding(text, components, constraints)

            if not issues:
                return {"text": text, "validated": True, "rejected_attempts": rejected_attempts}

            rejected_attempts.append({"attempt": attempt + 1, "text": text, "issues": issues})
            # Build a corrective note for the next attempt, naming the
            # exact fabricated values so the retry isn't just a blind
            # re-roll of the same failure.
            bad_values = []
            for category, values in issues.items():
                bad_values.extend(f"{v} ({category})" for v in values)
            correction_note = (
                f"\n\nYOUR PREVIOUS ATTEMPT INCLUDED FABRICATED VALUES NOT IN "
                f"THE DATA: {', '.join(str(v) for v in bad_values)}. Do not "
                f"repeat these or any other invented numbers. Only state "
                f"values that appear explicitly in the component list above."
            )

        # All retries exhausted, still ungrounded -- safe fallback, never
        # deliver unvalidated narrative text.
        fallback = (
            "[AUTOMATED SYNTHESIS FAILED GROUNDING VALIDATION after "
            f"{max_retries + 1} attempts -- narrative recommendation withheld "
            "pending human review. The deterministic findings above are "
            "independently verified and safe to rely on regardless of this "
            "failure.]"
        )
        return {"text": fallback, "validated": False, "rejected_attempts": rejected_attempts}

    def synthesize_recommendations(self, review_result: ReviewResult, components: list,
                                    correction_note: str = "") -> str:
        """
        Qualitative synthesis layer. Uses the backend-agnostic LLMClient
        (llm_client.py) per D-026 -- defaults to local Ollama (no API key,
        no subscription), falls back to hosted Anthropic only if
        HELIX_LLM_BACKEND=hosted is explicitly set.
        """
        from helix_llm.client import get_default_client

        findings_text = "\n".join(f"- [{f.severity}] {f.message}" for f in review_result.findings)
        components_text = "\n".join(
            f"- {c.name} x{c.quantity} (${c.cost_usd:.2f} each = ${c.cost_usd * c.quantity:.2f}, "
            f"{c.width_mm}x{c.depth_mm}x{c.height_mm}mm, {c.power_draw_w}W each, "
            f"category={c.category}"
            + (f", mfr={c.manufacturer}" if c.manufacturer else "")
            + (f", mpn={c.manufacturer_part_number}" if c.manufacturer_part_number else "")
            + (f", lead_time={c.lead_time_days}d" if c.lead_time_days else "")
            + ")"
            for c in components
        )

        # Ground any long-lead-time recommendation in an actual looked-up
        # alternative instead of letting the model invent one -- see
        # component_lookup_tool.py. MOCK data for now; same interface a
        # real distributor API integration would fill.
        #
        # IMPORTANT (D-036): the cheaper/pricier comparison and the
        # component-to-alternative pairing are computed HERE, in Python,
        # not left for the LLM to work out. A real field test caught the
        # model getting this backwards -- calling a $3.10 alternative
        # "cheaper" than a $2.40 original, and separately fabricating a
        # lead-time issue on an unrelated component by conflating two
        # different parts' numbers in one unstructured paragraph. Small
        # models (and honestly, LLMs in general) are unreliable at doing
        # arithmetic comparisons and multi-entity bookkeeping in free text
        # -- that's exactly the kind of task this project has pushed into
        # deterministic code from the start (D-033's quantity-math fix was
        # the same lesson). The model is now only asked to phrase an
        # already-correct comparison, not compute one.
        from helix_bom.components import lookup_alternatives
        alternatives_text = ""
        for c in components:
            if c.lead_time_days >= 90 and c.manufacturer_part_number:
                alts = lookup_alternatives(c.manufacturer_part_number)
                if alts:
                    alternatives_text += (
                        f"\nFor {c.name} ({c.manufacturer_part_number}, "
                        f"${c.cost_usd:.2f} each, {c.lead_time_days}-day lead time) "
                        f"— and ONLY for this component, not any other part in the "
                        f"BOM — these looked-up alternatives exist:\n"
                    )
                    for a in alts:
                        delta = a.cost_usd - c.cost_usd
                        if delta > 0:
                            price_label = f"${delta:.2f} MORE expensive than the original"
                        elif delta < 0:
                            price_label = f"${abs(delta):.2f} CHEAPER than the original"
                        else:
                            price_label = "the same price as the original"

                        lead_delta = c.lead_time_days - a.lead_time_days
                        if lead_delta > 0:
                            lead_label = f"{lead_delta} days FASTER than the original"
                        elif lead_delta < 0:
                            lead_label = f"{abs(lead_delta)} days SLOWER than the original"
                        else:
                            lead_label = "the same lead time as the original"

                        alternatives_text += (
                            f"  - {a.manufacturer} {a.manufacturer_part_number}: "
                            f"${a.cost_usd:.2f} ({price_label}), "
                            f"{a.lead_time_days}-day lead time ({lead_label}). {a.note}\n"
                        )

        prompt = (
            "You are writing a component review for a small hardware "
            "maker/startup client. Write in a natural, professional tone "
            "as a knowledgeable engineer would — not stiff or overly "
            "formal, no boilerplate phrases like 'per our guidelines.' "
            "You are an external consultant advising the client on THEIR "
            "project — always say 'your build,' 'your timeline,' 'your "
            "BOM'; never 'our build,' 'our timeline,' or 'we/us' as if "
            "you were on their team.\n\n"
            "Deterministic checks already found the following issues:\n\n"
            f"{findings_text}\n\n"
            f"Full component list submitted:\n{components_text}\n\n"
            + (f"{alternatives_text}\n"
               "IMPORTANT: the price and lead-time comparisons above are "
               "already correctly computed for you — restate them as given, "
               "do not recompute or re-judge which is cheaper. Each "
               "alternative listed is only a substitute for the ONE "
               "component named directly above it — never apply an "
               "alternative, its price, or its lead time to any other "
               "component in the BOM. Do not invent or guess at any other "
               "specific part numbers, specs, or features not given to "
               "you explicitly, and do not claim a finding exists for a "
               "component unless it's listed in the findings above.\n\n"
               if alternatives_text else
               "No verified alternative parts were looked up for any "
               "flagged component. Do not invent or guess at specific "
               "replacement part numbers or specs you were not given.\n\n")
            + "Note: components with category='power' (e.g. battery packs) "
            "are power SOURCES, not consumers — 0W listed for them is "
            "correct and expected, not an anomaly. Do not flag a "
            "power-category component's power_draw_w as unusual or "
            "missing data.\n\n"
            "Write a short (150-250 word) recommendation for the client: "
            "what to change first, in priority order, and roughly why. "
            "Do not invent numbers not present above. Do not promise "
            "specific cost savings you haven't been given data for."
        )
        client = get_default_client()
        return client.generate(prompt + correction_note, max_tokens=800)
