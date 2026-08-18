"""
The netlist reader as a user reaches it.

`test_netlist.py` proves the parser is right about a file. This file proves a
person can actually get at it — that `helix-bom review board.net` dispatches to
the netlist reader, that the report says what a netlist can and cannot support,
and that the diagram gets written. Between those two things the module was
correct, tested, and unreachable, which is worth exactly nothing to somebody
who has a board to check.
"""

import json
import xml.etree.ElementTree as ET

import pytest

from helix_bom.cli import EXIT_FINDINGS, EXIT_OK, EXIT_UNREADABLE, main

CLEAN = "tests/fixtures/sensor_board.net"
DEFECTIVE = "tests/fixtures/dangling_board.net"
PRICED_CSV = "tests/fixtures/altium_with_pricing.csv"


# --------------------------------------------------------------------
# Which reader gets the file
# --------------------------------------------------------------------

def test_a_netlist_is_reviewed_as_a_netlist(capsys):
    assert main(["review", CLEAN]) == EXIT_OK
    assert "Netlist review" in capsys.readouterr().out


def test_a_bom_is_still_reviewed_as_a_bom(capsys):
    """The whole point of adding a second reader is that the first one keeps
    working. A dispatch bug here breaks every existing user to serve a new
    one."""
    assert main(["review", PRICED_CSV, "--budget", "100"]) == EXIT_OK
    assert "BOM review" in capsys.readouterr().out


def test_the_contents_decide_not_the_extension(tmp_path, capsys):
    """People rename exports, and `.net` is not unique to KiCad. Trusting the
    suffix means a CSV called `board.net` gets a parse error about
    parentheses, which tells the user nothing about what went wrong."""
    disguised_bom = tmp_path / "board.net"
    disguised_bom.write_text("Designator,Description,Qty\nR1,10k resistor,4\n")
    assert main(["review", str(disguised_bom)]) == EXIT_OK
    assert "BOM review" in capsys.readouterr().out

    disguised_netlist = tmp_path / "parts.csv"
    disguised_netlist.write_text(open(CLEAN, encoding="utf-8").read(), encoding="utf-8")
    assert main(["review", str(disguised_netlist)]) == EXIT_OK
    assert "Netlist review" in capsys.readouterr().out


def test_a_missing_netlist_exits_two():
    assert main(["review", "no_such_board.net"]) == EXIT_UNREADABLE


def test_a_broken_netlist_says_so_rather_than_half_reading_it(tmp_path, capsys):
    path = tmp_path / "truncated.net"
    path.write_text('(export (version "E") (components (comp (ref "U1")')
    assert main(["review", str(path)]) == EXIT_UNREADABLE
    assert "unbalanced parentheses" in capsys.readouterr().err


def test_a_sexp_file_that_is_not_a_netlist_says_what_to_export(tmp_path, capsys):
    path = tmp_path / "other.net"
    path.write_text('(kicad_pcb (version 20221018))')
    assert main(["review", str(path)]) == EXIT_UNREADABLE
    assert "File > Export > Netlist" in capsys.readouterr().err


# --------------------------------------------------------------------
# What the report claims
# --------------------------------------------------------------------

def test_every_printed_link_is_a_net_that_exists(capsys):
    """The reason netlist input was added. A drawn connection now corresponds
    to a net in the file, so this assertion is possible at all — against the
    BOM reader there was nothing to compare a link to."""
    main(["review", CLEAN])
    out = capsys.readouterr().out
    source = open(CLEAN, encoding="utf-8").read()

    body = out.split("Interconnect (")[1].split("Findings:")[0]
    link_lines = [line for line in body.splitlines() if "<->" in line]
    assert link_lines, "no links printed for a board that has them"
    for line in link_lines:
        for net_name in line.split("  ")[-1].split(", "):
            assert f'(name "{net_name.strip()}")' in source


def test_a_netlist_reports_all_five_checks_as_unrun(capsys):
    """A netlist supports none of the BOM checks. The dangerous version of
    this is the one that stays quiet about it — the exact failure SkippedCheck
    was created for, arriving through a new input format."""
    main(["review", CLEAN])
    out = capsys.readouterr().out

    assert "NOT CHECKED (5)" in out
    assert "These are not passes." in out
    for name in ("budget", "power budget", "physical fit",
                 "supply-chain lead time"):
        assert name in out


def test_the_remedy_offered_is_one_a_netlist_user_can_act_on(capsys):
    """'Add a price column' is impossible advice for a format with no columns.
    A report that is accurate about what happened and wrong about what to do
    next still sends the reader somewhere useless."""
    main(["review", CLEAN])
    out = capsys.readouterr().out
    assert "no export option adds them" in out
    assert "review` on your BOM CSV as well" in out


def test_strict_mode_fails_a_netlist(capsys):
    """Nothing could be checked, so a build gate must not go green."""
    assert main(["review", CLEAN]) == EXIT_OK
    assert main(["review", CLEAN, "--strict"]) == EXIT_FINDINGS


# --------------------------------------------------------------------
# Defects only a netlist can show
# --------------------------------------------------------------------

def test_a_named_net_with_one_connection_is_flagged(capsys):
    """The finding that justifies reading netlists at all. On a schematic
    printout a label that connected to nothing is drawn exactly like one that
    did, so this is invisible to the eye and trivial to a parser."""
    main(["review", DEFECTIVE])
    out = capsys.readouterr().out
    assert "SENSOR_INT" in out
    assert "typed but never joined anything" in out


@pytest.mark.parametrize("auto_name", [
    "unconnected-(U1-Pad7)",   # KiCad 7/8
    "Net-(R3-Pad1)",           # KiCad 6
    "N$12",                    # older exports
])
def test_kicad_named_single_node_nets_are_not_flagged(auto_name, capsys):
    """An unconnected pin that KiCad named itself is normal, often deliberate,
    and already reported by KiCad. Flagging it here would bury the one finding
    that matters under a list of ones that do not."""
    main(["review", DEFECTIVE])
    out = capsys.readouterr().out
    assert auto_name not in out


def test_a_component_on_no_net_is_flagged(capsys):
    main(["review", DEFECTIVE])
    out = capsys.readouterr().out
    assert "U3" in out
    assert "on no net at all" in out


def test_mounting_holes_are_reported_as_deliberate_not_as_a_defect(capsys):
    """H1 and H2 are unconnected because that is what a mounting hole is.
    Warning about them trains the reader to skim the section that exists to
    be read."""
    main(["review", DEFECTIVE])
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "H1, H2" in l)
    assert line.strip().startswith("[INFO]")
    assert "deliberate" in line


# --------------------------------------------------------------------
# The diagram
# --------------------------------------------------------------------

def test_the_diagram_is_written_and_is_well_formed(tmp_path, capsys):
    out_path = tmp_path / "board.svg"
    assert main(["review", CLEAN, "--diagram", str(out_path)]) == EXIT_OK
    assert out_path.exists()
    ET.fromstring(out_path.read_text(encoding="utf-8"))
    assert "written to" in capsys.readouterr().err


def test_the_diagram_notice_goes_to_stderr_so_json_stays_parseable(tmp_path, capsys):
    """Machine output is the whole of stdout or it is not machine output —
    the rule the demo banner already had to learn."""
    out_path = tmp_path / "board.svg"
    main(["review", CLEAN, "--diagram", str(out_path), "--json"])
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert "written to" in captured.err


def test_a_bom_cannot_produce_a_diagram_and_says_why(tmp_path, capsys):
    """The measurement that started this work: drawn from a BOM, the diagram
    was an error string and an empty canvas. Refusing is more useful than
    shipping that, and the message names the file that would work."""
    out_path = tmp_path / "nope.svg"
    assert main(["review", PRICED_CSV, "--diagram", str(out_path)]) == EXIT_UNREADABLE
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "--diagram needs a netlist" in err
    assert "File > Export > Netlist" in err


def test_every_box_in_the_diagram_is_a_reference_from_the_file(tmp_path):
    out_path = tmp_path / "board.svg"
    main(["review", CLEAN, "--diagram", str(out_path)])
    root = ET.fromstring(out_path.read_text(encoding="utf-8"))
    source = open(CLEAN, encoding="utf-8").read()

    labels = [el.text for el in root.iter("{http://www.w3.org/2000/svg}text")]
    refs = [t for t in labels if t and len(t) <= 4 and t[0].isupper() and t[-1].isdigit()]
    assert refs, "no component boxes drawn"
    for ref in refs:
        assert f'(ref "{ref}")' in source


def test_power_nets_never_reach_the_diagram(tmp_path):
    """Excluded because they touch nearly every part. A diagram where
    everything connects to everything shows less than one that shows
    nothing."""
    out_path = tmp_path / "board.svg"
    main(["review", CLEAN, "--diagram", str(out_path)])
    svg = out_path.read_text(encoding="utf-8")
    assert "GND" not in svg
    assert "+3V3" not in svg


def test_nothing_is_drawn_outside_the_canvas(tmp_path):
    """D-043's lesson, applied to a new renderer: confirming well-formed XML
    would not have caught the clipping bug either. The extents get checked."""
    out_path = tmp_path / "board.svg"
    main(["review", CLEAN, "--diagram", str(out_path)])
    root = ET.fromstring(out_path.read_text(encoding="utf-8"))
    width, height = float(root.get("width")), float(root.get("height"))

    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "rect" and el.get("x") is not None:
            x, y = float(el.get("x")), float(el.get("y"))
            assert 0 <= x and x + float(el.get("width")) <= width
            assert 0 <= y and y + float(el.get("height")) <= height
        elif tag == "line":
            for point in ("1", "2"):
                assert 0 <= float(el.get("x" + point)) <= width
                assert 0 <= float(el.get("y" + point)) <= height


def test_a_board_with_no_signal_links_says_so_rather_than_drawing_nothing(tmp_path):
    """A blank image reads as 'nothing is connected', which is a claim about
    the board. The claim being made is about the file."""
    path = tmp_path / "power_only.net"
    path.write_text(
        '(export (version "E")'
        '  (components (comp (ref "C1") (value "100nF")))'
        '  (nets (net (code "1") (name "GND")'
        '    (node (ref "C1") (pin "2")))))'
    )
    out_path = tmp_path / "power_only.svg"
    main(["review", str(path), "--diagram", str(out_path)])
    svg = out_path.read_text(encoding="utf-8")
    ET.fromstring(svg)
    assert "no signal net joins two components" in svg.lower()


# --------------------------------------------------------------------
# JSON and the diagnostic
# --------------------------------------------------------------------

def test_json_output_names_the_kind_of_file_it_read(capsys):
    """A caller pointed at a directory of mixed exports needs to know which
    reader produced the record, because the fields differ."""
    main(["review", CLEAN, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "netlist"
    assert payload["netlist"]["signal_nets"] == 3
    assert payload["interconnect"]
    assert payload["complete"] is False


def test_the_netlist_diagnostic_leaks_no_design_data(tmp_path, capsys):
    """Stricter than the CSV diagnostic, and it has to be. A CSV's headings
    are printed because the parser matches on them and a heading is rarely
    secret. A netlist's equivalents are net names and part values — which are
    the design itself, and no rule can tell `I2C_SDA` from
    `MOTOR_KILL_INTERLOCK`."""
    secrets = {
        "net": "MOTOR_KILL_INTERLOCK",
        "value": "Zzyzx flux capacitor rev7",
        "mpn": "QQ-9931-SECRET",
        "schematic": "/home/dev/unannounced-product/secret.kicad_sch",
    }
    path = tmp_path / "confidential.net"
    path.write_text(
        f'(export (version "E")'
        f'  (design (source "{secrets["schematic"]}") (tool "Eeschema 8.0.4"))'
        f'  (components'
        f'    (comp (ref "U1") (value "{secrets["value"]}")'
        f'      (property (name "MPN") (value "{secrets["mpn"]}")))'
        f'    (comp (ref "U2") (value "MCU")))'
        f'  (nets (net (code "1") (name "{secrets["net"]}")'
        f'    (node (ref "U1") (pin "1")) (node (ref "U2") (pin "2")))))'
    )

    assert main(["diagnose", str(path)]) == EXIT_OK
    out = capsys.readouterr().out
    for label, value in secrets.items():
        assert value not in out, f"{label} leaked into the diagnostic: {value!r}"


def test_the_netlist_diagnostic_still_says_enough_to_debug(capsys):
    """Redaction that removes the useful part is just a blank page."""
    main(["diagnose", DEFECTIVE])
    out = capsys.readouterr().out
    assert "KiCad netlist" in out
    assert "Eeschema 8.0.4" in out       # the exporter, not the design
    assert "components      6" in out
    assert "single-node" in out
    assert "checks that could run   0 of 5" in out
