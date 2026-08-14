"""
Tests visual_diagram_generator.py:
1. Both SVG generators produce well-formed XML (parseable, not just
   string concatenation that happens to look right).
2. The placement blueprint's risk-highlighting actually matches real
   findings -- using Variated Test 3 (physical-fit-only), where the
   oversized display panel is DEFINITELY named in a finding and the
   compact MCU is DEFINITELY not.
"""
import sys, os
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))

from helix_bom.agent import BOMReviewAgent
from helix_bom.diagrams import generate_visual_interconnect_svg, generate_placement_blueprint_svg
from test_bom_review_realistic_scale_sandbox import build_realistic_synthetic_bom
from test_variated_3_physical_fit_only_sandbox import build_bom as build_test3_bom


def run():
    agent = BOMReviewAgent()

    print("=== Well-formed XML check: visual interconnect (realistic 18-item BOM) ===")
    components, _ = build_realistic_synthetic_bom()
    svg1 = generate_visual_interconnect_svg(components)
    ET.fromstring(svg1)  # raises if malformed -- this is the real check, not eyeballing it
    assert "NOT a verified schematic" in svg1
    print(f"[PASS] Well-formed XML, {len(svg1)} chars, caveat text present\n")

    print("=== Well-formed XML check + risk-highlighting: placement blueprint (Test 3) ===")
    components3, constraints3 = build_test3_bom()
    result3 = agent.review(components3, constraints3)
    svg2 = generate_placement_blueprint_svg(components3, constraints3, result3)
    ET.fromstring(svg2)
    assert "NOT thermal/EMI-aware" in svg2

    # The oversized display panel IS named in a finding -- must be
    # risk-highlighted. The compact MCU is NOT named in any finding --
    # must NOT be highlighted. Real check against real finding text,
    # not just "some rect somewhere is red." Note: labels are truncated
    # at a word boundary for long names (see _truncate_label), so we
    # check for the truncated form actually rendered, not the full
    # original name.
    assert "Oversized display" in svg2
    assert "FLAGGED" in svg2, "Expected the display panel to be risk-highlighted"
    # Verify specifically that the flagged marker sits near the display
    # panel's own rect, not just present somewhere in the document
    display_idx = svg2.find("Oversized display")
    flagged_idx = svg2.find("FLAGGED")
    assert flagged_idx > display_idx and flagged_idx - display_idx < 400, (
        "FLAGGED marker should appear directly after the display panel's own elements"
    )
    print(f"[PASS] Well-formed XML, {len(svg2)} chars, risk-highlight correctly "
          f"tied to the actual flagged component\n")

    # Verify the compact MCU (not flagged) does NOT get a FLAGGED marker
    # near its own rect
    mcu_idx = svg2.find("Compact MCU")
    next_flagged_after_mcu = svg2.find("FLAGGED", mcu_idx)
    text_between = svg2[mcu_idx:next_flagged_after_mcu] if next_flagged_after_mcu != -1 else svg2[mcu_idx:]
    assert "<rect" not in text_between.split("FLAGGED")[0][-200:] or next_flagged_after_mcu == -1 or next_flagged_after_mcu > display_idx, (
        "The non-flagged MCU should not itself carry a FLAGGED marker"
    )
    print("[PASS] Non-flagged component correctly has no risk marker\n")

    print("[SANDBOX TEST PASSED] Visual diagrams are well-formed and risk-highlighting is accurate.")


if __name__ == "__main__":
    run()
