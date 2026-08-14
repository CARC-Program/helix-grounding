"""
Regression tests for two bugs found while auditing the diagram generator.

Both were invisible to the existing suite because every fixture used clean
ASCII component names that happened not to collide. That is the general
lesson: test data chosen for readability tests the happy path twice.
"""

import xml.etree.ElementTree as ET

import pytest

from helix_bom.diagrams import (
    generate_placement_blueprint_svg,
    generate_visual_interconnect_svg,
)


class Component:
    def __init__(self, name, category, width_mm=10.0, depth_mm=10.0):
        self.name = name
        self.category = category
        self.width_mm = width_mm
        self.depth_mm = depth_mm


class Constraints:
    enclosure_width_mm = 100.0
    enclosure_depth_mm = 80.0


class Finding:
    def __init__(self, message):
        self.message = message


class Review:
    def __init__(self, *messages):
        self.findings = [Finding(m) for m in messages]


# --------------------------------------------------------------------
# BUG: component names were interpolated into SVG without XML escaping
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "AT&T cellular module",
    "Resistor <100R>",
    'Connector "keyed"',
    "Divider >50% duty",
])
def test_special_characters_produce_valid_xml(name):
    """A BOM is client-submitted data. An ampersand or angle bracket in a
    part name produced malformed XML that no viewer would render — and a
    name containing a closing tag could inject markup into a diagram the
    client opens in a browser."""
    components = [
        Component("MCU board", "compute"),
        Component(name, "sensor"),
    ]

    svg = generate_visual_interconnect_svg(components)

    root = ET.fromstring(svg)  # raises ParseError if the escaping is wrong

    # The parser round-trips the escapes back to the original characters, so
    # the name must survive intact in a text node — proving it was escaped on
    # the way out rather than stripped or mangled.
    rendered = " ".join(node.text or "" for node in root.iter())
    assert name[:40] in rendered


def test_special_characters_in_placement_blueprint_produce_valid_xml():
    components = [Component("Sensor <A&B>", "sensor", 20.0, 20.0)]

    svg = generate_placement_blueprint_svg(components, Constraints())

    ET.fromstring(svg)


def test_escaping_does_not_mangle_ordinary_names():
    components = [Component("STM32 MCU board", "compute")]

    svg = generate_visual_interconnect_svg(components)

    assert "STM32 MCU board" in svg


# --------------------------------------------------------------------
# BUG: substring matching flagged the wrong component
# --------------------------------------------------------------------

def test_shorter_component_name_is_not_flagged_by_a_longer_ones_finding():
    """A component called 'Battery' matched a finding about the 'Battery
    Pack 5000mAh' and got a red risk outline it had not earned — the client
    sees a flagged box on a part with no finding against it."""
    components = [
        Component("Battery", "power", 20.0, 20.0),
        Component("Battery Pack 5000mAh", "power", 30.0, 30.0),
    ]
    review = Review("Battery Pack 5000mAh has a stated lead time of 120 days.")

    svg = generate_placement_blueprint_svg(components, Constraints(), review)

    # Exactly one component should carry the [FLAGGED] marker.
    assert svg.count("[FLAGGED]") == 1


def test_the_correctly_named_component_is_still_flagged():
    """The fix must not suppress genuine flags."""
    components = [Component("Oversized display panel", "display", 200.0, 20.0)]
    review = Review(
        "Oversized display panel (200.0mm wide) exceeds enclosure width (100.0mm)."
    )

    svg = generate_placement_blueprint_svg(components, Constraints(), review)

    assert "[FLAGGED]" in svg


def test_unrelated_components_are_never_flagged():
    components = [
        Component("MCU board", "compute", 20.0, 20.0),
        Component("LiPo cell", "power", 30.0, 30.0),
    ]
    review = Review("MCU board has a stated lead time of 120 days.")

    svg = generate_placement_blueprint_svg(components, Constraints(), review)

    assert svg.count("[FLAGGED]") == 1
