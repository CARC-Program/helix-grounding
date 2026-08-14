"""
Tests generate_interconnect_diagram() -- confirms it correctly anchors on
the compute component, groups by category, and handles the no-compute
edge case without crashing.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from helix_bom.agent import BOMReviewAgent, Component
from test_bom_review_realistic_scale_sandbox import build_realistic_synthetic_bom


def run():
    agent = BOMReviewAgent()

    print("=== Realistic 18-item BOM ===")
    components, _ = build_realistic_synthetic_bom()
    diagram = agent.generate_interconnect_diagram(components)
    print(diagram)
    assert "ESP32-S3 MCU module" in diagram, "Expected the hub name to appear uncut"
    assert "sensor:" in diagram and "power:" in diagram
    assert "NOT a verified schematic" in diagram, "Honesty caveat must always be present"
    print("[PASS] Diagram correctly anchors on compute hub and groups by category\n")

    print("=== Edge case: no compute component at all ===")
    no_compute = [Component("Random passive", cost_usd=0.01, width_mm=1, depth_mm=1, height_mm=1,
                             power_draw_w=0.0, category="passive")]
    result = agent.generate_interconnect_diagram(no_compute)
    print(result)
    assert "No 'compute' category component found" in result
    print("[PASS] No-compute edge case handled without crashing\n")

    print("[SANDBOX TEST PASSED]")


if __name__ == "__main__":
    run()
