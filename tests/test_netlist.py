"""
Tests for reading a KiCad netlist.

The point of this module is that it turns a guess into a fact. A BOM-derived
interconnect diagram says "a compute part usually talks to a sensor over
I2C"; a netlist-derived one says "U1 pin 42 and U2 pin 4 are on the net named
I2C_SDA". These tests are mostly about protecting that distinction.
"""

import pytest

from helix_bom.netlist import (
    interconnect_from_nets,
    load_netlist,
    parse_sexp,
)

NETLIST = "tests/fixtures/sensor_board.net"


# --------------------------------------------------------------------
# The s-expression parser
# --------------------------------------------------------------------

def test_parses_nested_expressions():
    assert parse_sexp("(a (b c) (d (e f)))") == [["a", ["b", "c"], ["d", ["e", "f"]]]]


def test_quoted_strings_keep_their_spaces():
    """Component values and footprints contain spaces constantly. Splitting on
    whitespace would shred every one of them."""
    result = parse_sexp('(value "Resistor, 10k 1%")')

    assert result == [["value", "Resistor, 10k 1%"]]


def test_escaped_quotes_survive():
    assert parse_sexp(r'(value "2\" header")') == [["value", '2" header']]


@pytest.mark.parametrize("broken", ["(a b))", "((a b)", "(((", ")"])
def test_unbalanced_parentheses_are_refused(broken):
    """A truncated file should say so rather than silently yielding a partial
    netlist that looks complete."""
    with pytest.raises(ValueError, match="unbalanced"):
        parse_sexp(broken)


# --------------------------------------------------------------------
# Reading a real file
# --------------------------------------------------------------------

def test_components_and_nets_both_come_out():
    """A netlist carries the parts *and* the wiring, which is why accepting
    one means the customer has sent their BOM too."""
    components, nets, report = load_netlist(NETLIST)

    assert len(components) == 6
    assert len(nets) == 5
    assert report.tool == "Eeschema 8.0.4"


def test_part_numbers_are_read_from_schematic_properties():
    """The MPN in a netlist comes straight from the schematic, so it is
    usually more trustworthy than one retyped into a spreadsheet."""
    components, _, _ = load_netlist(NETLIST)
    mcu = next(c for c in components if "U1" in c.name)

    assert mcu.manufacturer_part_number == "STM32L476RGT6"
    assert mcu.manufacturer == "STMicroelectronics"


def test_components_are_the_same_type_the_csv_reader_produces():
    """Downstream code must not care which kind of file the parts came from."""
    from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints

    components, _, _ = load_netlist(NETLIST)

    assert all(isinstance(c, Component) for c in components)
    BOMReviewAgent().review(components, DesignConstraints(0, 0, 0, 0, 0))


def test_a_netlist_has_no_prices_and_says_so_rather_than_inventing_them():
    """Absent cost data must reach the agent as absent, so the budget check
    reports itself unrunnable instead of passing on a total of zero."""
    from helix_bom.agent import BOMReviewAgent, DesignConstraints

    components, _, _ = load_netlist(NETLIST)
    result = BOMReviewAgent().review(components, DesignConstraints(50, 0, 0, 0, 0))

    assert all(c.cost_usd == 0.0 for c in components)
    assert any(s.name == "budget" for s in result.skipped_checks)


def test_power_nets_are_identified():
    _, nets, report = load_netlist(NETLIST)
    by_name = {n.name: n for n in nets}

    assert by_name["GND"].is_power
    assert by_name["+3V3"].is_power
    assert not by_name["I2C_SDA"].is_power
    assert report.power_nets == 2 and report.signal_nets == 3


@pytest.mark.parametrize("name", ["GND", "AGND", "VSS", "VCC", "VDD", "+3V3",
                                  "+5V", "VBUS", "VBAT", "3V3"])
def test_common_power_net_names_are_recognised(name):
    from helix_bom.netlist import Net

    assert Net(code="1", name=name).is_power


@pytest.mark.parametrize("name", ["I2C_SDA", "SPI_MOSI", "USB_DP", "RESET",
                                  "Net-(U1-Pad3)"])
def test_signal_nets_are_not_mistaken_for_power(name):
    from helix_bom.netlist import Net

    assert not Net(code="1", name=name).is_power


def test_a_file_that_is_not_a_netlist_says_what_to_do(tmp_path):
    path = tmp_path / "notanetlist.net"
    path.write_text("(some other s-expression file)")

    with pytest.raises(ValueError, match="File > Export > Netlist"):
        load_netlist(path)


# --------------------------------------------------------------------
# Turning nets into a diagram
# --------------------------------------------------------------------

def test_every_link_corresponds_to_a_real_net():
    """The whole reason this exists. A BOM-derived sketch guesses that a
    compute part probably talks to a sensor; this asserts they do."""
    _, nets, _ = load_netlist(NETLIST)

    links = interconnect_from_nets(nets)
    pairs = {(a, b) for a, b, _ in links}

    assert ("U1", "U2") in pairs                      # MCU to sensor
    assert any("I2C_SDA" in names for _, _, names in links)


def test_power_nets_are_excluded_from_the_diagram():
    """GND touches nearly every part. Drawing it produces a hairball that
    communicates less than drawing nothing."""
    _, nets, _ = load_netlist(NETLIST)

    links = interconnect_from_nets(nets)

    assert not any("GND" in names or "+3V3" in names for _, _, names in links)


def test_links_are_ranked_by_how_many_nets_join_them():
    """Two parts sharing several nets are more strongly related than two
    sharing one, and a reader's eye should land on that first."""
    _, nets, _ = load_netlist(NETLIST)

    links = interconnect_from_nets(nets)

    assert links[0][:2] == ("U1", "U2")     # joined by both I2C lines
    assert len(links[0][2]) == 2


def test_the_edge_cap_is_honoured():
    """A large board can have thousands of pairs. An unbounded diagram is
    unreadable and slow to render."""
    from helix_bom.netlist import Net, Node

    nets = [Net(code=str(i), name=f"SIG{i}",
                nodes=[Node(ref=f"U{i}", pin="1"), Node(ref=f"U{i+1}", pin="1")])
            for i in range(200)]

    assert len(interconnect_from_nets(nets, max_edges=10)) == 10


def test_a_pin_wired_to_nothing_is_reported():
    """A single-node net is a connection somebody believed they had made."""
    from helix_bom.netlist import Net, Node

    nets = [Net(code="1", name="ORPHAN", nodes=[Node(ref="U1", pin="7")])]

    assert interconnect_from_nets(nets) == []       # nothing to draw
    assert len(nets[0].nodes) == 1                  # but it is still visible
