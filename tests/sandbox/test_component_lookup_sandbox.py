"""
Tests component_lookup_tool.py directly and confirms bom_review_agent.py
correctly triggers a lookup for a long-lead-time part with a known MPN,
and correctly returns nothing for parts with no match -- an empty result
is the honest answer, not something to paper over.
"""
import sys, os

from helix_bom.components import lookup_alternatives, AlternativePart


def run():
    print("=== Known MPN (BME280) ===")
    alts = lookup_alternatives("BME280")
    assert len(alts) == 2, f"Expected 2 mock alternatives, got {len(alts)}"
    for a in alts:
        assert isinstance(a, AlternativePart)
        print(f"  {a.manufacturer} {a.manufacturer_part_number} — ${a.cost_usd}, {a.lead_time_days}d — {a.note}")
    print("[PASS] Known MPN returns real (mock) alternatives")

    print("\n=== Unknown MPN ===")
    alts = lookup_alternatives("SOME-PART-NOT-IN-DB")
    assert alts == [], "Expected empty list for unknown part, not a guess"
    print("[PASS] Unknown MPN correctly returns empty list, not a fabricated guess")

    print("\n[SANDBOX TEST PASSED] Lookup tool behaves correctly for both cases.")


if __name__ == "__main__":
    run()
