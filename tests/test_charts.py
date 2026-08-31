"""
Tests for the drawn views.

The property that matters most here is not that a chart looks right -- it is
that a chart which cannot be drawn says so. An empty frame reads as "nothing
wrong" to somebody skimming, and this project's recurring failure is silence
being mistaken for a clean result. So every view is tested twice: once with
the data, and once without it.
"""

import xml.etree.ElementTree as ET

import pytest

from helix_bom.agent import Component
from helix_bom.charts import (cost_view, enclosure_view, lead_time_view,
                              risk_view)


def _part(name="Part", cost=1.0, quantity=1, lead=0, w=0.0, d=0.0, h=0.0,
          designator="U1", category="general"):
    return Component(name=name, cost_usd=cost, width_mm=w, depth_mm=d,
                     height_mm=h, power_draw_w=0.0, category=category,
                     quantity=quantity, designator=designator,
                     lead_time_days=lead)


def _wellformed(markup):
    ET.fromstring(markup)
    return True


# --------------------------------------------------------------------
# Refusing to draw
# --------------------------------------------------------------------

def test_a_view_with_no_data_gives_a_reason_not_an_empty_picture():
    """Each of these has to name the column it wanted. 'No data' on its own
    leaves the reader unable to fix it."""
    bare = [_part(cost=0.0)]

    for view, wanted in ((cost_view(bare), "price"),
                         (lead_time_view(bare), "lead-time"),
                         (enclosure_view(bare), "dimensions")):
        assert not view.available
        assert view.markup == ""
        assert wanted in view.reason


def test_risk_says_a_key_is_what_is_missing():
    class Report:
        lines = []

    view = risk_view(Report())

    assert not view.available
    assert "distributor API key" in view.reason


# --------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------

def test_cost_totals_extended_price_not_unit_price():
    """Four capacitors at 5c are 20c of the board, not 5c. Costing a BOM at
    unit price is the mistake the tool exists to catch, so its own chart must
    not make it."""
    view = cost_view([_part(cost=0.05, quantity=4, designator="C1"),
                      _part(cost=1.00, quantity=1, designator="U1")])

    assert view.available
    assert "$1.20 total" in view.markup
    assert _wellformed(view.markup)


def test_every_priced_line_gets_a_block():
    parts = [_part(cost=1.0, designator=f"R{n}") for n in range(6)]

    view = cost_view(parts)

    assert view.markup.count('class="cell"') == 6


def test_a_line_with_no_price_is_left_out_rather_than_drawn_as_zero():
    """A zero-area block is invisible, so a reader would never know the line
    was there. Better it is absent from a cost chart and present in the
    findings, which is where a missing price belongs."""
    view = cost_view([_part(cost=2.0, designator="U1"),
                      _part(cost=0.0, designator="U2")])

    assert view.markup.count('class="cell"') == 1
    assert "1 priced line(s)" in view.markup


# --------------------------------------------------------------------
# Lead time
# --------------------------------------------------------------------

def test_the_longest_lead_time_is_named_as_the_thing_that_gates_the_build():
    view = lead_time_view([_part(lead=7, designator="R1"),
                           _part(lead=126, designator="U1"),
                           _part(lead=21, designator="U2")])

    assert "gates the build" in view.markup
    assert "126 day(s) is the earliest" in view.markup
    assert _wellformed(view.markup)


def test_lines_with_no_stated_lead_time_are_not_drawn_as_zero_days():
    """Zero in this column means 'not stated', not 'available today'. Drawing
    it as a bar of length nothing asserts the second."""
    view = lead_time_view([_part(lead=0, designator="R1"),
                           _part(lead=30, designator="U1")])

    assert view.markup.count('class="cell"') == 1


# --------------------------------------------------------------------
# Enclosure
# --------------------------------------------------------------------

def test_the_footprint_reported_is_the_one_measured_not_the_limit_allowed():
    """A real bug: the packed width was reported as the envelope width, so a
    board using 58mm of a 60mm envelope was described as using all 60 -- and
    a part overflowing the shelf was counted as fitting."""
    parts = [_part(w=10, d=10, h=1, designator=f"U{n}") for n in range(3)]

    view = enclosure_view(parts, enclosure=(100.0, 50.0, 5.0))

    assert "Packed footprint 30 x 10 mm" in view.markup
    assert "Everything fits" in view.markup


def test_a_part_that_does_not_fit_is_flagged_and_the_verdict_changes():
    parts = [_part(w=10, d=10, h=9, designator="TALL")]

    view = enclosure_view(parts, enclosure=(50.0, 50.0, 4.0))

    assert "does not fit" in view.markup
    assert "Something does not fit" in view.markup


def test_without_an_envelope_it_draws_but_claims_no_verdict():
    """Dimensions without an envelope still answer 'how big is this', which is
    worth drawing. It must not imply a fit it was never given the box for."""
    view = enclosure_view([_part(w=10, d=10, h=2, designator="U1")])

    assert view.available
    assert "No envelope given" in view.markup
    assert "fits" not in view.markup


def test_the_drawing_disclaims_placement_every_time():
    """The one sentence that must never be dropped. A picture of boxes on a
    board reads as a layout suggestion unless it says otherwise, and neither
    a BOM nor a netlist knows where anything goes."""
    view = enclosure_view([_part(w=5, d=5, h=1)], enclosure=(50.0, 50.0, 10.0))

    assert "Position carries no claim" in view.markup


# --------------------------------------------------------------------
# Shared properties
# --------------------------------------------------------------------

@pytest.mark.parametrize("build", [
    lambda: cost_view([_part(cost=1.0)]),
    lambda: lead_time_view([_part(lead=10)]),
    lambda: enclosure_view([_part(w=5, d=5, h=2)], enclosure=(50.0, 50.0, 9.0)),
])
def test_every_drawing_is_well_formed_xml(build):
    """A malformed SVG renders as nothing at all in a browser, and nothing at
    all is indistinguishable from a clean result."""
    assert _wellformed(build().markup)


@pytest.mark.parametrize("build", [
    lambda parts: cost_view(parts),
    lambda parts: lead_time_view(parts),
    lambda parts: enclosure_view(parts, enclosure=(90.0, 90.0, 9.0)),
])
def test_a_part_name_cannot_break_out_of_the_drawing(build):
    """Same reason the page escapes: this text comes from somebody's file."""
    parts = [_part(name="<script>alert(1)</script>", cost=1.0, lead=5,
                   w=5, d=5, h=2, designator="<img src=x onerror=alert(2)>")]

    markup = build(parts).markup

    assert "<script>alert(1)</script>" not in markup
    assert "<img src=x" not in markup
    assert _wellformed(markup)


def test_no_view_reaches_the_network_for_anything():
    """The report's guarantee is only as good as the pieces inside it.

    Checked by looking for the constructs that actually fetch, not for the
    string "http": every SVG carries `xmlns="http://www.w3.org/2000/svg"`,
    which is a namespace name and is never dereferenced by anything. A test
    banning the substring would fail on correct code and teach whoever hit it
    to delete the check.
    """
    parts = [_part(cost=1.0, lead=5, w=5, d=5, h=2)]

    for view in (cost_view(parts), lead_time_view(parts),
                 enclosure_view(parts, enclosure=(50.0, 50.0, 9.0))):
        assert "href" not in view.markup            # covers xlink:href too
        assert "<image" not in view.markup
        assert "url(" not in view.markup            # CSS fetch inside a fill
        assert "@import" not in view.markup


# --------------------------------------------------------------------
# Caps, and the checking they must not quietly stop doing
# --------------------------------------------------------------------

def test_the_cost_treemap_groups_a_long_tail_but_keeps_the_total_honest():
    """Five hundred blocks smaller than a cursor is a slow page nobody can
    click. Grouping them is fine; changing the total is not."""
    from helix_bom.charts import COST_BLOCKS

    parts = ([_part(cost=100.0, designator="BIG")]
             + [_part(cost=1.0, designator=f"R{n}") for n in range(200)])

    view = cost_view(parts)

    assert view.markup.count('class="cell"') <= COST_BLOCKS + 1
    assert "$300.00 total" in view.markup            # 100 + 200 x 1
    assert "201 priced line(s)" in view.markup
    assert "grouped into one block" in view.markup


def test_a_part_beyond_the_drawing_cap_still_fails_the_fit_verdict():
    """The bug this cap could have introduced, and the reason it did not.

    Only the first FIT_BOXES parts are drawn. If the verdict were computed
    from the drawn ones, a board would be reported as fitting because the
    part that does not fit happened to sort past the cap. The verdict is
    computed over every part, and this proves it: the offending part is
    narrow, so it sorts last by width, well beyond anything drawn.
    """
    from helix_bom.charts import FIT_BOXES

    parts = [_part(w=10, d=1, h=1, designator=f"OK{n}")
             for n in range(FIT_BOXES + 20)]
    parts.append(_part(w=0.5, d=0.5, h=99, designator="TOWER"))

    view = enclosure_view(parts, enclosure=(500.0, 500.0, 5.0))

    assert "Something does not fit" in view.markup
    assert "counted in the verdict but not drawn" in view.markup


def test_the_fit_note_says_how_many_were_left_undrawn():
    """Silence about an omission is the failure mode. If 40 parts are not on
    the drawing, the drawing has to say so."""
    from helix_bom.charts import FIT_BOXES

    parts = [_part(w=2, d=2, h=1, designator=f"C{n}")
             for n in range(FIT_BOXES + 40)]

    view = enclosure_view(parts, enclosure=(400.0, 400.0, 10.0))

    assert "40 smaller part(s) are counted in the verdict but not drawn" \
        in view.markup
