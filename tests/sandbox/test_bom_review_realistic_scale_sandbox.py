"""
Sandbox test — a realistically-scaled synthetic BOM (18 line items, real
quantities, manufacturers, part numbers, one genuine long-lead-time part)
closer to what an actual client would submit in the field, rather than
the minimal 4-5 item BOMs used in earlier tests. Still entirely
fabricated/synthetic data, no real client.

Modeled loosely on a small battery-powered IoT sensor device -- MCU,
power management, sensors, connectors, and the passive components
(resistors/capacitors) a real board actually needs, which every prior
test omitted entirely.
"""

import sys
import os


from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints


def build_realistic_synthetic_bom():
    components = [
        # Core compute
        Component("ESP32-S3 MCU module", cost_usd=3.20, width_mm=18, depth_mm=25.5, height_mm=3.1,
                   power_draw_w=0.5, category="compute", quantity=1,
                   manufacturer="Espressif", manufacturer_part_number="ESP32-S3-WROOM-1"),
        # Power management
        Component("Li-Po charge/protect IC", cost_usd=0.85, width_mm=3, depth_mm=3, height_mm=0.9,
                   power_draw_w=0.02, category="power", quantity=1,
                   manufacturer="Texas Instruments", manufacturer_part_number="BQ24075RGTR"),
        Component("Buck converter 3.3V", cost_usd=1.10, width_mm=3, depth_mm=3, height_mm=1.0,
                   power_draw_w=0.05, category="power", quantity=1,
                   manufacturer="Texas Instruments", manufacturer_part_number="TPS62203DGKR"),
        Component("Li-Po battery pack 2000mAh", cost_usd=6.50, width_mm=50, depth_mm=34, height_mm=6,
                   power_draw_w=0.0, category="power", quantity=1,
                   manufacturer="Generic", manufacturer_part_number="LP503450"),
        # Sensors
        Component("BME280 environmental sensor", cost_usd=2.40, width_mm=2.5, depth_mm=2.5, height_mm=0.93,
                   power_draw_w=0.003, category="sensor", quantity=1,
                   manufacturer="Bosch", manufacturer_part_number="BME280",
                   lead_time_days=112),  # deliberately the long-lead-time part this test should catch
        Component("PIR motion sensor", cost_usd=1.80, width_mm=10, depth_mm=10, height_mm=8,
                   power_draw_w=0.065, category="sensor", quantity=1,
                   manufacturer="Generic", manufacturer_part_number="AM312"),
        # Connectivity/antenna
        Component("2.4GHz PCB antenna", cost_usd=0.40, width_mm=15, depth_mm=6, height_mm=0.2,
                   power_draw_w=0.0, category="connectivity", quantity=1),
        # Connectors
        Component("USB-C connector", cost_usd=0.35, width_mm=9, depth_mm=7.5, height_mm=3.2,
                   power_draw_w=0.0, category="connector", quantity=1,
                   manufacturer="GCT", manufacturer_part_number="USB4110"),
        Component("JST battery connector", cost_usd=0.12, width_mm=6, depth_mm=4, height_mm=3,
                   power_draw_w=0.0, category="connector", quantity=1),
        # Passives -- the category every prior test omitted entirely
        Component("0.1uF ceramic decoupling capacitor", cost_usd=0.02, width_mm=1.6, depth_mm=0.8, height_mm=0.8,
                   power_draw_w=0.0, category="passive", quantity=8),
        Component("10uF tantalum capacitor", cost_usd=0.15, width_mm=3.2, depth_mm=1.6, height_mm=1.6,
                   power_draw_w=0.0, category="passive", quantity=3),
        Component("10k ohm resistor", cost_usd=0.01, width_mm=1.0, depth_mm=0.5, height_mm=0.4,
                   power_draw_w=0.0, category="passive", quantity=6),
        Component("Status LED", cost_usd=0.05, width_mm=1.6, depth_mm=0.8, height_mm=0.6,
                   power_draw_w=0.02, category="passive", quantity=2),
        Component("LED current-limit resistor", cost_usd=0.01, width_mm=1.0, depth_mm=0.5, height_mm=0.4,
                   power_draw_w=0.0, category="passive", quantity=2),
        # Board + mechanical
        Component("4-layer PCB (custom)", cost_usd=4.50, width_mm=45, depth_mm=30, height_mm=1.6,
                   power_draw_w=0.0, category="pcb", quantity=1),
        Component("Enclosure screws M2x6", cost_usd=0.03, width_mm=2, depth_mm=2, height_mm=6,
                   power_draw_w=0.0, category="mechanical", quantity=4),
        Component("Push button (reset)", cost_usd=0.08, width_mm=6, depth_mm=6, height_mm=3.5,
                   power_draw_w=0.0, category="mechanical", quantity=1),
        Component("Push button (user)", cost_usd=0.08, width_mm=6, depth_mm=6, height_mm=3.5,
                   power_draw_w=0.0, category="mechanical", quantity=1),
    ]
    constraints = DesignConstraints(
        budget_usd=35.00,
        enclosure_width_mm=60,
        enclosure_depth_mm=45,
        enclosure_height_mm=15,
        power_budget_w=1.0,
    )
    return components, constraints


def run():
    agent = BOMReviewAgent()
    components, constraints = build_realistic_synthetic_bom()
    result = agent.review(components, constraints)

    print(f"=== HELIX BOM Review Agent — Realistic-scale test ({len(components)} line items) ===\n")
    print(f"Total BOM cost:  ${result.total_cost_usd:.2f}  (budget: ${constraints.budget_usd:.2f})")
    print(f"Total power draw: {result.total_power_w:.3f}W  (budget: {constraints.power_budget_w:.1f}W)")
    print(f"Over budget: {result.over_budget}   Over power budget: {result.over_power_budget}\n")
    print("Findings:")
    for f in result.findings:
        print(f"  [{f.severity.upper():8}] {f.message}")

    # Verify quantity is actually being multiplied through correctly --
    # this is the real bug this recalibration fixes. Hand-computed check:
    expected_cost = sum(c.cost_usd * c.quantity for c in components)
    expected_power = sum(c.power_draw_w * c.quantity for c in components)
    assert abs(result.total_cost_usd - expected_cost) < 0.001, "Quantity not correctly multiplied into cost total"
    assert abs(result.total_power_w - expected_power) < 0.001, "Quantity not correctly multiplied into power total"
    print(f"\n[PASS] Quantity correctly multiplied into totals (hand-verified: ${expected_cost:.2f}, {expected_power:.3f}W)")

    # This BOM's tallest single component (battery, 6mm) fits within the
    # 15mm enclosure height -- correctly should NOT trigger a height
    # warning now, whereas the old naive sum-of-all-18-heights logic
    # incorrectly did. This is the actual fix verification.
    height_findings = [f for f in result.findings if "enclosure height" in f.message]
    assert len(height_findings) == 0, (
        f"Expected no false height warning (tallest part is 6mm, fits in 15mm enclosure), "
        f"but got: {height_findings}"
    )
    print("[PASS] No false height alarm — tallest single component correctly fits, "
          "unlike the old sum-all-heights logic which falsely flagged this BOM")

    # Verify the long-lead-time part is actually caught
    lead_time_findings = [f for f in result.findings if "lead time" in f.message]
    assert len(lead_time_findings) == 1, "Expected the 112-day BME280 lead time to be flagged"
    print(f"[PASS] Long lead-time part correctly flagged: {lead_time_findings[0].message}")

    print("\nLLM synthesis layer:")
    synthesis = agent.synthesize_recommendations(result, components)
    print(" ", synthesis)

    print(f"\n[SANDBOX TEST PASSED] {len(components)}-line-item BOM handled correctly, "
          f"quantity math verified, supply-chain risk correctly caught.")


if __name__ == "__main__":
    run()
