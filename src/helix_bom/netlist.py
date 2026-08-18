"""
Read a KiCad netlist: the file that actually knows how the board is wired.

A BOM is a shopping list. It says which parts and how many, and it is silent
on how any of them connect — that information lives in the schematic, and a
netlist is the schematic's connectivity exported in a form a program can read.

This is why an interconnect diagram drawn from a BOM alone can only ever be a
*suggestion* based on what categories of part usually talk to each other.
Given a netlist, the same diagram stops being a guess: every line drawn
corresponds to a net that exists, between pins that are named.

A netlist also carries the component list, so a customer who sends one has
sent their BOM too — usually a better BOM than their CSV export, because it
comes straight from the schematic rather than through a spreadsheet.

Format: KiCad's ``.net`` is s-expressions. This module parses the subset that
matters (``components`` and ``nets``) and ignores the rest rather than
failing on fields it was not expecting, because netlist exporters add fields
between versions and refusing an unknown one would break on every upgrade.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .agent import Component

# Nets present on nearly every board that connect nearly everything. Drawing
# them turns a diagram into a hairball where every part links to every other
# part, which communicates less than drawing nothing. Excluded from the
# diagram, still reported in the counts.
POWER_NET_PATTERNS = (
    r"^gnd$", r"^agnd$", r"^dgnd$", r"^pgnd$", r"^earth$", r"^vss[a-z]*$",
    r"^\+?\d+v\d*$", r"^vcc[a-z]*$", r"^vdd[a-z]*$", r"^vbus$", r"^vin$",
    r"^\+?v?bat[t]?$", r"^vref[a-z]*$",
)
_POWER_NET = re.compile("|".join(POWER_NET_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class Node:
    """One pin on one component, as a net sees it."""

    ref: str          # e.g. "U1"
    pin: str          # e.g. "42" — a string, because pins are "A6" and "B12" too
    function: str = ""  # e.g. "SDA", when the symbol names its pins


@dataclass
class Net:
    """One electrical connection between two or more pins."""

    code: str
    name: str
    nodes: list = field(default_factory=list)

    @property
    def is_power(self) -> bool:
        return bool(_POWER_NET.match(self.name.strip()))

    @property
    def refs(self) -> set:
        return {node.ref for node in self.nodes}


@dataclass
class NetlistReport:
    """What the file contained, in the same spirit as IngestReport: state the
    assumptions rather than making them quietly."""

    source: str = ""
    tool: str = ""
    schematic: str = ""
    components: int = 0
    nets: int = 0
    power_nets: int = 0
    signal_nets: int = 0
    unconnected: list = field(default_factory=list)
    single_node_nets: list = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.components} component(s), {self.nets} net(s) "
                f"({self.signal_nets} signal, {self.power_nets} power) "
                f"from {self.source}")


def _tokenize(text: str):
    """Split s-expression source into parens, quoted strings, and atoms."""
    token = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
    for match in token.finditer(text):
        yield match.group(0)


def parse_sexp(text: str):
    """Parse s-expressions into nested lists.

    Written by hand rather than pulled in as a dependency: the library's whole
    argument is that it needs nothing installed, and this is forty lines.
    """
    stack: list = [[]]
    for tok in _tokenize(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            if len(stack) == 1:
                raise ValueError("unbalanced parentheses: too many ')'")
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise ValueError("unbalanced parentheses: unclosed '('")
    return stack[0]


def _children(node, key: str):
    """Every sub-list of ``node`` whose head is ``key``."""
    return [item for item in node
            if isinstance(item, list) and item and item[0] == key]


def _value(node, key: str, default: str = "") -> str:
    """The single value of ``(key value)``, or a default."""
    found = _children(node, key)
    if found and len(found[0]) > 1 and isinstance(found[0][1], str):
        return found[0][1]
    return default


def load_netlist(path) -> tuple[list, list, NetlistReport]:
    """Read a KiCad netlist into components, nets, and a report.

    Returns ``Component`` objects of the same type the CSV reader produces, so
    everything downstream is unchanged — the checks, the grounding adapter and
    the CLI do not need to know which kind of file the parts came from.

    Prices are absent: a netlist carries no cost data. That is not a failure,
    it is the shape of the file, and the budget check will correctly report
    itself as unrunnable rather than inventing zeroes.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    try:
        tree = parse_sexp(text)
    except ValueError as exc:
        raise ValueError(f"{path.name}: not a readable netlist ({exc})") from exc

    export = next((item for item in tree
                   if isinstance(item, list) and item and item[0] == "export"), None)
    if export is None:
        raise ValueError(
            f"{path.name}: no (export ...) block — this does not look like a "
            f"KiCad netlist. Export one from Eeschema with File > Export > Netlist."
        )

    report = NetlistReport(source=path.name)
    design = _children(export, "design")
    if design:
        report.schematic = _value(design[0], "source")
        report.tool = _value(design[0], "tool")

    # --- components -------------------------------------------------
    components: list[Component] = []
    for block in _children(export, "components"):
        for comp in _children(block, "comp"):
            ref = _value(comp, "ref")
            value = _value(comp, "value")
            properties = {_value(prop, "name"): _value(prop, "value")
                          for prop in _children(comp, "property")}
            # KiCad 6+ writes named properties; older files put the part
            # number in a field. Check both rather than assuming a version.
            mpn = (properties.get("MPN") or properties.get("Mpn")
                   or properties.get("Manufacturer Part Number") or "")
            components.append(Component(
                name=f"{value} ({ref})" if value else ref,
                cost_usd=0.0,
                width_mm=0.0, depth_mm=0.0, height_mm=0.0,
                power_draw_w=0.0,
                category="",
                quantity=1,
                manufacturer=properties.get("Manufacturer", ""),
                manufacturer_part_number=mpn,
                lead_time_days=0,
            ))
    report.components = len(components)

    # --- nets -------------------------------------------------------
    nets: list[Net] = []
    for block in _children(export, "nets"):
        for raw in _children(block, "net"):
            net = Net(code=_value(raw, "code"), name=_value(raw, "name"))
            for node in _children(raw, "node"):
                net.nodes.append(Node(
                    ref=_value(node, "ref"),
                    pin=_value(node, "pin"),
                    function=_value(node, "pinfunction"),
                ))
            nets.append(net)

    report.nets = len(nets)
    report.power_nets = sum(1 for n in nets if n.is_power)
    report.signal_nets = report.nets - report.power_nets

    # A net with one node is a pin wired to nothing. That is a real schematic
    # defect and worth surfacing -- it usually means a connection someone
    # believed they had made.
    report.single_node_nets = [n.name for n in nets if len(n.nodes) == 1]

    connected = {ref for net in nets for ref in net.refs}
    all_refs = {c.name.split("(")[-1].rstrip(")") for c in components}
    report.unconnected = sorted(all_refs - connected)

    return components, nets, report


def interconnect_from_nets(nets: list, max_edges: int = 60) -> list:
    """Reduce nets to component-to-component links, ready to draw.

    Returns ``(ref_a, ref_b, [net names])`` tuples. Unlike the category-based
    sketch this replaces, every link here is a connection that exists in the
    schematic — so the resulting diagram is a statement of fact rather than a
    guess about what usually talks to what.

    Power and ground are excluded: they touch nearly every part, and a diagram
    where everything connects to everything shows less than one that shows
    nothing.
    """
    links: dict[tuple, list] = {}
    for net in nets:
        if net.is_power:
            continue
        refs = sorted(net.refs)
        for index, first in enumerate(refs):
            for second in refs[index + 1:]:
                links.setdefault((first, second), []).append(net.name)

    ranked = sorted(links.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [(a, b, names) for (a, b), names in ranked[:max_edges]]


# KiCad invents a name for every net the designer did not label. The exact
# spelling has changed across versions, so all three are matched rather than
# whichever one this machine's KiCad happens to emit.
_AUTO_NAMED = re.compile(r"^(net-\(|unconnected-\(|n\$\d+$)", re.IGNORECASE)

# References that are legitimately connected to nothing. A mounting hole with
# no net is a mounting hole; flagging it teaches the reader to skim the
# section, which costs more than the finding is worth.
_UNCONNECTED_BY_DESIGN = re.compile(r"^(H|MH|FID|TP|LOGO|MK)\d+$", re.IGNORECASE)


def connectivity_findings(components: list, nets: list, report: NetlistReport) -> list:
    """Defects a netlist can prove and a BOM cannot even see.

    None of the five BOM checks can run on a netlist — it carries no prices,
    no dimensions, no power figures and no categories, and the agent says so
    rather than passing them silently. What it does carry is connectivity, and
    connectivity has its own failure modes.

    Returns ``ReviewFinding`` objects, the same type the BOM checks produce, so
    the caller merges them into one list rather than presenting two kinds of
    result.
    """
    from .agent import ReviewFinding

    findings = []

    # --- a label that landed nowhere ---------------------------------
    # A single-node net means one pin carries a net all to itself. When KiCad
    # named that net, it is simply an unconnected pin, which KiCad already
    # reports and which is often intentional. When a *person* named it, they
    # typed a label expecting it to join something — and it did not. That is
    # the interesting case, and it is invisible on a schematic printout
    # because the label is drawn exactly as it would be if it had connected.
    dangling = [net for net in nets
                if len(net.nodes) == 1 and not _AUTO_NAMED.match(net.name.strip())]
    for net in sorted(dangling, key=lambda n: n.name):
        node = net.nodes[0]
        where = f"{node.ref} pin {node.pin}" + (f" ({node.function})" if node.function else "")
        findings.append(ReviewFinding(
            "warning",
            f"Net '{net.name}' reaches only {where}. A named net with one "
            f"connection is a label that was typed but never joined anything."
        ))

    # --- a part wired to nothing at all ------------------------------
    orphans = [ref for ref in report.unconnected
               if not _UNCONNECTED_BY_DESIGN.match(ref)]
    by_design = [ref for ref in report.unconnected if ref not in orphans]
    if orphans:
        findings.append(ReviewFinding(
            "warning",
            f"{len(orphans)} component(s) appear in the schematic on no net at "
            f"all: {', '.join(orphans)}. Either they are placed and unwired, or "
            f"their pins are unconnected by intent."
        ))
    if by_design:
        findings.append(ReviewFinding(
            "info",
            f"{len(by_design)} component(s) unconnected, which their reference "
            f"designators suggest is deliberate — mounting holes, fiducials or "
            f"test points: {', '.join(by_design)}."
        ))

    # --- what was read, stated rather than assumed -------------------
    findings.append(ReviewFinding(
        "info",
        f"{report.signal_nets} signal net(s) and {report.power_nets} power/ground "
        f"net(s) read from {report.source}. Power nets are excluded from the "
        f"interconnect diagram because they touch nearly every part."
    ))
    return findings
