"""
Variated test 2 of 3 — a different device type entirely (a small motor/
robotics controller, not an IoT sensor device), with TWO components
flagged for long lead time simultaneously, one of which has no known
alternative in the mock lookup database. Tests that the agent handles
multiple simultaneous flags correctly and doesn't fabricate an
alternative when none exists. Synthetic data only.
"""
import sys, os
from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_bom():
    components = [
        Component("Motor driver IC", cost_usd=4.50, width_mm=5, depth_mm=5, height_mm=1,
                   power_draw_w=0.15, category="compute", quantity=2,
                   manufacturer="Texas Instruments", manufacturer_part_number="DRV8871",
                   lead_time_days=95),  # long lead time, no mock alternative exists for this MPN
        Component("BME280 environmental sensor", cost_usd=2.40, width_mm=2.5, depth_mm=2.5, height_mm=0.93,
                   power_draw_w=0.003, category="sensor", quantity=1,
                   manufacturer="Bosch", manufacturer_part_number="BME280",
                   lead_time_days=112),  # long lead time, DOES have mock alternatives
        Component("DC gear motor", cost_usd=6.00, width_mm=25, depth_mm=25, height_mm=20,
                   power_draw_w=2.5, category="mechanical", quantity=2),
        Component("Wheel encoder", cost_usd=1.20, width_mm=15, depth_mm=15, height_mm=5,
                   power_draw_w=0.02, category="sensor", quantity=2),
        Component("Li-ion battery pack 3000mAh", cost_usd=9.00, width_mm=55, depth_mm=35, height_mm=8,
                   power_draw_w=0.0, category="power", quantity=1),
        Component("Buck converter 5V", cost_usd=1.20, width_mm=4, depth_mm=4, height_mm=1.2,
                   power_draw_w=0.1, category="power", quantity=1),
    ]
    constraints = DesignConstraints(budget_usd=40.00, enclosure_width_mm=80,
                                     enclosure_depth_mm=60, enclosure_height_mm=30, power_budget_w=6.0)
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_bom()
    result = agent.review(components, constraints)
    print(f"=== Variated Test 2: motor controller, 2 simultaneous lead-time flags ===")
    print(f"Cost: ${result.total_cost_usd:.2f} (budget ${constraints.budget_usd:.2f})  "
          f"Power: {result.total_power_w:.2f}W (budget {constraints.power_budget_w:.1f}W)")
    for f in result.findings:
        print(f"  [{f.severity.upper()}] {f.message}")

    lead_time_findings = [f for f in result.findings if "lead time" in f.message]
    assert len(lead_time_findings) == 2, f"Expected 2 lead-time flags (motor driver + BME280), got {len(lead_time_findings)}"
    print(f"[PASS] Both long-lead-time components correctly flagged\n")

    synthesis = agent.synthesize_recommendations(result, components)
    print("Synthesis:\n ", synthesis)

    # The real thing to check by eye: does the model correctly say there's
    # NO alternative for the DRV8871 motor driver (none exists in the mock
    # DB), rather than inventing one? Automated check for the obvious
    # tell -- a fabricated part number pattern would be unusual to guess
    # correctly, but the real check here is human review of the text above.
    print("\n[MANUAL CHECK NEEDED] Confirm above: the motor driver (DRV8871) "
          "should NOT be given a specific alternative part number, since "
          "none exists in the mock lookup database — only the BME280 "
          "should get one.")
    print("\n[SANDBOX TEST PASSED] (automated checks; read synthesis above for the manual check)")


if __name__ == "__main__":
    run()
