"""
Variated test 1 of 3 — over budget, comfortably within power budget.
Prior tests either failed both or neither; this isolates one failure
mode from the other to confirm they're independently detected, not
coincidentally correlated. Synthetic data only.
"""
import sys, os
from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_bom():
    components = [
        Component("High-end MCU module", cost_usd=18.00, width_mm=20, depth_mm=20, height_mm=2,
                   power_draw_w=0.4, category="compute", quantity=1,
                   manufacturer="STMicroelectronics", manufacturer_part_number="STM32H743"),
        Component("Premium display module", cost_usd=22.00, width_mm=40, depth_mm=30, height_mm=3,
                   power_draw_w=0.3, category="display", quantity=1),
        Component("Battery pack", cost_usd=8.00, width_mm=30, depth_mm=20, height_mm=5,
                   power_draw_w=0.0, category="power", quantity=1),
        Component("Misc passives", cost_usd=0.03, width_mm=1, depth_mm=1, height_mm=0.5,
                   power_draw_w=0.0, category="passive", quantity=15),
    ]
    constraints = DesignConstraints(budget_usd=30.00, enclosure_width_mm=50,
                                     enclosure_depth_mm=35, enclosure_height_mm=10, power_budget_w=2.0)
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_bom()
    result = agent.review(components, constraints)
    print(f"=== Variated Test 1: over budget, under power ===")
    print(f"Cost: ${result.total_cost_usd:.2f} (budget ${constraints.budget_usd:.2f})  "
          f"Power: {result.total_power_w:.2f}W (budget {constraints.power_budget_w:.1f}W)")
    for f in result.findings:
        print(f"  [{f.severity.upper()}] {f.message}")

    assert result.over_budget is True, "Expected over-budget to be flagged"
    assert result.over_power_budget is False, "Expected power to be within budget"
    print("[PASS] Cost and power failure modes correctly detected independently\n")

    synthesis = agent.synthesize_recommendations(result, components)
    print("Synthesis:\n ", synthesis)
    print("\n[SANDBOX TEST PASSED]")


if __name__ == "__main__":
    run()
