"""
Sandbox test for BOMReviewAgent — SYNTHETIC DATA ONLY.

This is not a real client's BOM. It's a fabricated test case constructed
to exercise the deterministic checks in bom_review_agent.py, per
D-017's requirement that sandbox testing use synthetic/sample data, not
live client engagement. No network calls, no external communication.
"""

import sys
import os


from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_synthetic_bom():
    """A fabricated sample BOM, loosely modeled on a small IoT sensor
    device — deliberately includes a budget overage, a power overage, and
    a physical-fit conflict so all three deterministic checks exercise
    their failure paths, not just the pass path."""
    components = [
        Component("Compute module (SBC)", cost_usd=45.00, width_mm=65, depth_mm=30, height_mm=12, power_draw_w=3.5, category="compute"),
        Component("WiFi/BT radio module", cost_usd=8.50, width_mm=15, depth_mm=15, height_mm=3, power_draw_w=0.8, category="connectivity"),
        Component("Li-ion battery pack", cost_usd=12.00, width_mm=50, depth_mm=34, height_mm=8, power_draw_w=0.0, category="power"),
        Component("Custom sensor board", cost_usd=22.00, width_mm=40, depth_mm=25, height_mm=6, power_draw_w=1.2, category="sensor"),
        Component("Premium OLED display", cost_usd=38.00, width_mm=70, depth_mm=45, height_mm=5, power_draw_w=1.5, category="display"),
    ]
    constraints = DesignConstraints(
        budget_usd=100.00,       # components sum to $125.50 -> intentional overage
        enclosure_width_mm=68,   # display is 70mm wide -> intentional width conflict
        enclosure_depth_mm=50,
        enclosure_height_mm=25,  # stacked height = 34mm -> intentional overage
        power_budget_w=5.0,      # total draw = 7.0W -> intentional overage
    )
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_synthetic_bom()
    result = agent.review(components, constraints)

    print("=== HELIX BOM Review Agent — Sandbox Test (synthetic data) ===\n")
    print(f"Total BOM cost:  ${result.total_cost_usd:.2f}  (budget: ${constraints.budget_usd:.2f})")
    print(f"Total power draw: {result.total_power_w:.1f}W  (budget: {constraints.power_budget_w:.1f}W)")
    print(f"Over budget: {result.over_budget}   Over power budget: {result.over_power_budget}\n")
    print("Findings:")
    for f in result.findings:
        print(f"  [{f.severity.upper():8}] {f.message}")

    print("\nLLM synthesis layer:")
    print(" ", agent.synthesize_recommendations(result, components))

    # Basic pass/fail assertions for this sandbox run — confirms the
    # deterministic layer actually catches the three intentional problems
    # baked into the synthetic BOM above.
    assert result.over_budget is True, "Expected budget overage to be detected"
    assert result.over_power_budget is True, "Expected power overage to be detected"
    critical_count = sum(1 for f in result.findings if f.severity == "critical")
    assert critical_count >= 3, f"Expected >=3 critical findings, got {critical_count}"
    print("\n[SANDBOX TEST PASSED] All three intentional conflicts were detected correctly.")


if __name__ == "__main__":
    run()
