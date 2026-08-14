"""
Generates real .svg files from the same synthetic BOMs used in testing,
and opens each one in your default web browser so you can actually see
them rendered -- not just validated as well-formed XML in a terminal.

Run from the TESTING folder:
    python3 export_and_view_diagrams.py

Files are written to a new "diagram_output" folder next to this script.
"""
import sys
import os
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AI_CODE"))

from bom_review_agent import BOMReviewAgent
from visual_diagram_generator import generate_visual_interconnect_svg, generate_placement_blueprint_svg
from test_bom_review_realistic_scale_sandbox import build_realistic_synthetic_bom
from test_variated_3_physical_fit_only_sandbox import build_bom as build_test3_bom


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "diagram_output")
    os.makedirs(output_dir, exist_ok=True)

    agent = BOMReviewAgent()

    # 1. Visual interconnect diagram -- the realistic 18-item BOM
    print("Generating visual interconnect diagram (18-item realistic BOM)...")
    components, _ = build_realistic_synthetic_bom()
    interconnect_svg = generate_visual_interconnect_svg(components)
    interconnect_path = os.path.join(output_dir, "interconnect_diagram.svg")
    with open(interconnect_path, "w", encoding="utf-8") as f:
        f.write(interconnect_svg)
    print(f"  Saved: {interconnect_path}")

    # 2. Placement blueprint with risk-highlighting -- Test 3 (has a
    # genuine flagged component: the oversized display panel)
    print("Generating placement blueprint (Variated Test 3, with risk-highlighting)...")
    components3, constraints3 = build_test3_bom()
    result3 = agent.review(components3, constraints3)
    blueprint_svg = generate_placement_blueprint_svg(components3, constraints3, result3)
    blueprint_path = os.path.join(output_dir, "placement_blueprint.svg")
    with open(blueprint_path, "w", encoding="utf-8") as f:
        f.write(blueprint_svg)
    print(f"  Saved: {blueprint_path}")

    # Open both in the default browser. webbrowser needs an absolute
    # file:// URL, not a bare path, to work reliably on Windows.
    print("\nOpening both in your default browser...")
    webbrowser.open("file://" + os.path.abspath(interconnect_path))
    webbrowser.open("file://" + os.path.abspath(blueprint_path))

    print("\nDone. If a browser window didn't open automatically, the files "
          f"are sitting in:\n  {os.path.abspath(output_dir)}\n"
          "Double-click either .svg file to open it manually.")


if __name__ == "__main__":
    run()
