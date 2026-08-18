"""
Write the diagrams to real .svg files and open them, so they can be looked at
rather than only validated as well-formed XML.

The distinction matters here more than usual. This project has twice shipped a
diagram that parsed perfectly and showed nothing — a placement blueprint that
clipped its own contents past the canvas edge (D-043), and an interconnect
sketch that drew twelve rectangles of size 0x0 on a real BOM export. Both
passed every structural check that existed at the time. Somebody has to look.

Run it:  python scripts/export_diagrams.py [--no-open] [--out DIR]

Files land in scripts/diagram_output/ unless --out says otherwise.
"""

import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints  # noqa: E402
from helix_bom.diagrams import (                                          # noqa: E402
    generate_netlist_interconnect_svg,
    generate_placement_blueprint_svg,
)
from helix_bom.netlist import interconnect_from_nets, load_netlist        # noqa: E402

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "diagram_output"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def interconnect_from_a_real_netlist() -> tuple[str, str]:
    """The diagram that makes a checkable claim.

    Every line corresponds to a net in the file, so the output can be compared
    against the schematic and found wrong. The category-based sketch it
    replaced could not be checked against anything — it described what usually
    connects to what.
    """
    _, nets, report = load_netlist(FIXTURES / "sensor_board.net")
    links = interconnect_from_nets(nets)
    print(f"Interconnect from {report.source}: {len(links)} link(s) "
          f"across {report.signal_nets} signal net(s).")
    return ("interconnect_from_netlist.svg",
            generate_netlist_interconnect_svg(links, source=report.source))


def placement_blueprint() -> tuple[str, str]:
    """The blueprint, drawn from data that actually carries dimensions.

    Hand-built on purpose, and worth stating why: no BOM export carries
    millimetres, so on a real file this diagram has nothing to draw. That
    measurement is what prompted netlist input in the first place. Real
    placement lives in a board file (.kicad_pcb), and reading one is not built.
    """
    components = [
        Component("ESP32-S3 module", 3.20, 25.5, 18.0, 3.1, 0.24, "compute"),
        Component("OLED display 2.4in", 8.90, 61.0, 45.0, 4.2, 0.09, "display"),
        Component("LiPo cell 2000mAh", 6.40, 60.0, 35.0, 6.5, 0.0, "power"),
        Component("USB-C receptacle", 0.55, 9.0, 7.4, 3.2, 0.0, "connector"),
        Component("IMU breakout", 4.10, 20.0, 20.0, 2.0, 0.01, "sensor"),
    ]
    constraints = DesignConstraints(
        budget_usd=30.0,
        enclosure_width_mm=70.0, enclosure_depth_mm=50.0, enclosure_height_mm=12.0,
        power_budget_w=1.0,
    )
    result = BOMReviewAgent().review(components, constraints)
    flagged = [f for f in result.findings if f.severity != "info"]
    print(f"Placement blueprint: {len(components)} parts, "
          f"{len(flagged)} finding(s) driving a red outline.")
    return ("placement_blueprint.svg",
            generate_placement_blueprint_svg(components, constraints, result))


GENERATORS = (interconnect_from_a_real_netlist, placement_blueprint)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    output_dir = DEFAULT_OUTPUT_DIR
    if "--out" in argv:
        output_dir = Path(argv[argv.index("--out") + 1])
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for generate in GENERATORS:
        name, svg = generate()
        path = output_dir / name
        path.write_text(svg, encoding="utf-8")
        print(f"  saved  {path}")
        written.append(path)

    if "--no-open" in argv:
        print(f"\nNot opening a browser. Files are in {output_dir}")
        return 0

    print("\nOpening both in your default browser...")
    for path in written:
        webbrowser.open(path.resolve().as_uri())
    print(f"If nothing opened, the files are in {output_dir} — "
          f"double-click either one.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
