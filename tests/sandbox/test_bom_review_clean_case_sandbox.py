"""
Sandbox test — the case that's been missing so far: a BOM that actually
fits within budget, power, and physical constraints. Every prior test
used a deliberately broken BOM to verify problem detection; this one
verifies the agent doesn't raise false alarms on legitimately good work.
Synthetic data only, no real client.
"""

import sys
import os


from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_clean_synthetic_bom():
    """A fabricated BOM deliberately designed to fit comfortably within
    every constraint — the inverse of the broken test case."""
    components = [
        Component("Compute module (SBC)", cost_usd=35.00, width_mm=55, depth_mm=28, height_mm=10, power_draw_w=2.5, category="compute"),
        Component("WiFi/BT radio module", cost_usd=6.00, width_mm=12, depth_mm=12, height_mm=2, power_draw_w=0.5, category="connectivity"),
        Component("Li-ion battery pack", cost_usd=10.00, width_mm=40, depth_mm=28, height_mm=6, power_draw_w=0.0, category="power"),
        Component("Basic sensor board", cost_usd=15.00, width_mm=30, depth_mm=20, height_mm=4, power_draw_w=0.8, category="sensor"),
    ]
    constraints = DesignConstraints(
        budget_usd=100.00,        # components sum to $66.00 -- comfortably under
        enclosure_width_mm=68,    # widest component is 55mm -- fits
        enclosure_depth_mm=50,    # deepest is 28mm -- fits
        enclosure_height_mm=25,   # stacked height = 22mm -- fits
        power_budget_w=5.0,       # total draw = 3.8W -- fits
    )
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_clean_synthetic_bom()
    result = agent.review(components, constraints)

    print("=== HELIX BOM Review Agent — Sandbox Test (clean/passing synthetic BOM) ===\n")
    print(f"Total BOM cost:  ${result.total_cost_usd:.2f}  (budget: ${constraints.budget_usd:.2f})")
    print(f"Total power draw: {result.total_power_w:.1f}W  (budget: {constraints.power_budget_w:.1f}W)")
    print(f"Over budget: {result.over_budget}   Over power budget: {result.over_power_budget}\n")
    print("Findings:")
    for f in result.findings:
        print(f"  [{f.severity.upper():8}] {f.message}")

    # This is the actual point of this test: confirm NO false-positive
    # critical/warning findings on a genuinely clean BOM.
    assert result.over_budget is False, "False positive: flagged budget on a BOM that fits"
    assert result.over_power_budget is False, "False positive: flagged power on a BOM that fits"
    critical_or_warning = [f for f in result.findings if f.severity in ("critical", "warning")]
    assert len(critical_or_warning) == 0, f"False positive(s) found on a clean BOM: {critical_or_warning}"

    print("\nLLM synthesis layer:")
    synthesis = agent.synthesize_recommendations(result, components)
    print(" ", synthesis)

    print("\n[SANDBOX TEST PASSED] No false positives on a genuinely clean BOM.")


if __name__ == "__main__":
    run()
