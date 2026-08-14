"""
Variated test 3 of 3 — physical fit conflict as the ONLY issue; cost and
power both comfortably within budget. Isolates the width/depth check
independent of the other failure modes, similar in spirit to Variated
Test 1 but for a different check entirely. Synthetic data only.
"""
import sys, os
from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_bom():
    components = [
        Component("Compact MCU", cost_usd=3.00, width_mm=12, depth_mm=12, height_mm=1.5,
                   power_draw_w=0.2, category="compute", quantity=1),
        Component("Oversized display panel", cost_usd=5.00, width_mm=85, depth_mm=50, height_mm=4,
                   power_draw_w=0.5, category="display", quantity=1),  # deliberately too wide
        Component("Coin cell battery", cost_usd=0.50, width_mm=20, depth_mm=20, height_mm=3.2,
                   power_draw_w=0.0, category="power", quantity=1),
    ]
    constraints = DesignConstraints(budget_usd=20.00, enclosure_width_mm=60,
                                     enclosure_depth_mm=45, enclosure_height_mm=10, power_budget_w=1.0)
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_bom()
    result = agent.review(components, constraints)
    print(f"=== Variated Test 3: physical fit conflict only ===")
    print(f"Cost: ${result.total_cost_usd:.2f} (budget ${constraints.budget_usd:.2f})  "
          f"Power: {result.total_power_w:.2f}W (budget {constraints.power_budget_w:.1f}W)")
    for f in result.findings:
        print(f"  [{f.severity.upper()}] {f.message}")

    assert result.over_budget is False
    assert result.over_power_budget is False
    width_findings = [f for f in result.findings if "width" in f.message]
    assert len(width_findings) == 1, f"Expected exactly 1 width-conflict finding, got {len(width_findings)}"
    print("[PASS] Physical-fit conflict correctly isolated from cost/power (both fine)\n")

    synthesis = agent.synthesize_recommendations(result, components)
    print("Synthesis:\n ", synthesis)
    print("\n[SANDBOX TEST PASSED]")


if __name__ == "__main__":
    run()
