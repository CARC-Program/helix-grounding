"""
Pictures drawn from data the file actually contains.

Every view here is generated as inline SVG or plain markup. No charting
library, no runtime dependency, and nothing fetched -- the report's guarantee
that it loads nothing from anywhere is a property of this module too, not just
of the page that embeds it.

The rule each view obeys: **when the data is not there, say so rather than
draw something.** A cost treemap of a BOM with no prices would be a picture of
nothing, and an empty chart reads as "no problems" to somebody skimming. So
each builder returns a ``View`` that is either a drawing or a sentence naming
the column that was missing, and the report renders whichever it got.

What is deliberately absent: anything showing where parts sit on the board. A
BOM has no coordinates and a netlist has no coordinates, so a board render
from either would be an invention. Positions come from a placement file, and
until one is read, no view here claims to know them.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

# Chosen to stay distinguishable in greyscale and to survive the common forms
# of colour blindness -- a risk chart that reads as one flat colour to eight
# percent of engineers is a chart that failed.
PALETTE = ("#2C6395", "#3E8A6E", "#B4762B", "#8A5A9E", "#4A7A9B",
           "#996B4F", "#5E7A3E", "#A34F5E")
INK = "#2B3038"
MUTED = "#6B7480"
GRID = "#DFE3E8"
PAPER = "#FAFAFA"
DANGER = "#B4232B"
WARN = "#B4762B"

# Caps on how much is drawn. Chosen so a real board stays interactive: past
# these counts a block is smaller than a cursor and the page gets heavy for
# nothing anybody can see or click.
COST_BLOCKS = 40
FIT_BOXES = 120


class _Rest:
    """Stands in for the aggregated tail of a treemap."""

    def __init__(self, count: int):
        self.count = count
        self.designator = f"{count} smaller lines"
        self.name = "everything else, grouped"
        self.category = ""
        self.quantity = 1


@dataclass(frozen=True)
class View:
    """A drawing, or the reason there is not one."""

    markup: str = ""
    reason: str = ""

    @property
    def available(self) -> bool:
        return bool(self.markup)


def _x(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _num(value, default=0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(result) or math.isinf(result) else result


def _ref(component) -> str:
    return (getattr(component, "designator", "")
            or getattr(component, "manufacturer_part_number", "")
            or getattr(component, "name", "") or "?")


def _svg(width: float, height: float, body: str, title: str = "",
         note: str = "") -> str:
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'role="img">'
            f'<rect width="{width:.0f}" height="{height:.0f}" fill="{PAPER}"/>')
    if title:
        head += (f'<text x="14" y="22" font-family="sans-serif" font-size="13" '
                 f'fill="{INK}">{_x(title)}</text>')
    if note:
        head += (f'<text x="14" y="{height - 12:.0f}" font-family="sans-serif" '
                 f'font-size="10" fill="{MUTED}">{_x(note)}</text>')
    return head + body + "</svg>"


# --------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------

def _split_treemap(items, x, y, w, h, out):
    """Recursive binary treemap.

    Split the sorted run in half by value, give each half the share of the
    rectangle its total deserves, and recurse across the longer axis. Not the
    squarified algorithm, which packs slightly tighter; this one is a dozen
    lines, has no pathological case, and the aspect ratios stay readable, which
    is the whole requirement.
    """
    if not items:
        return
    if len(items) == 1:
        out.append((items[0], x, y, w, h))
        return

    total = sum(value for value, _ in items)
    if total <= 0:
        return
    running, cut = 0.0, 1
    for index, (value, _) in enumerate(items):
        if running + value > total / 2 and index > 0:
            cut = index
            break
        running += value
        cut = index + 1

    first, second = items[:cut], items[cut:]
    share = sum(value for value, _ in first) / total
    if w >= h:
        _split_treemap(first, x, y, w * share, h, out)
        _split_treemap(second, x + w * share, y, w * (1 - share), h, out)
    else:
        _split_treemap(first, x, y, w, h * share, out)
        _split_treemap(second, x, y + h * share, w, h * (1 - share), out)


def cost_view(components) -> View:
    """Where the money goes, by extended cost."""
    priced = []
    for component in components:
        unit = _num(getattr(component, "cost_usd", 0.0))
        quantity = max(1, int(_num(getattr(component, "quantity", 1), 1)))
        if unit > 0:
            priced.append((unit * quantity, component))

    if not priced:
        return View(reason="no unit prices in this file, so there is no cost "
                           "to break down. A BOM export can carry a price "
                           "column; a netlist never does.")

    priced.sort(key=lambda pair: -pair[0])
    total = sum(value for value, _ in priced)

    # A block too small to see is a block nobody can click, and five hundred
    # of them is a slow page for no gain. The tail is aggregated into one
    # honest block so the areas still sum to the real total.
    tail = []
    if len(priced) > COST_BLOCKS:
        tail = priced[COST_BLOCKS:]
        priced = priced[:COST_BLOCKS]
        rest = sum(value for value, _ in tail)
        if rest > 0:
            priced.append((rest, _Rest(len(tail))))

    width, height = 900.0, 430.0
    top, pad = 54.0, 14.0
    boxes = []
    _split_treemap(priced, pad, top, width - 2 * pad, height - top - 34, boxes)

    categories = {}
    body = []
    for (value, component), bx, by, bw, bh in boxes:
        category = (getattr(component, "category", "") or "").strip() or "-"
        if category not in categories:
            categories[category] = PALETTE[len(categories) % len(PALETTE)]
        colour = categories[category]
        share = value / total * 100
        reference = _ref(component)
        name = getattr(component, "name", "") or ""
        body.append(
            f'<g class="cell" data-ref="{_x(reference)}">'
            f'<title>{_x(reference)} — {_x(name)} — ${value:,.2f} '
            f'({share:.1f}%)</title>'
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{max(bw - 2, 0):.1f}" '
            f'height="{max(bh - 2, 0):.1f}" fill="{colour}" rx="2"/>')
        if bw > 66 and bh > 30:
            body.append(
                f'<text x="{bx + 8:.1f}" y="{by + 19:.1f}" '
                f'font-family="sans-serif" font-size="11" fill="white" '
                f'font-weight="600">{_x(reference[:16])}</text>')
        if bw > 66 and bh > 46:
            body.append(
                f'<text x="{bx + 8:.1f}" y="{by + 34:.1f}" '
                f'font-family="sans-serif" font-size="10" fill="white" '
                f'fill-opacity="0.85">${value:,.2f} · {share:.0f}%</text>')
        body.append("</g>")

    shown = len(priced) - (1 if tail else 0)
    note = (f"{shown + len(tail)} priced line(s), ${total:,.2f} total. Area is "
            f"extended cost: unit price times quantity."
            + (f"  The {len(tail)} smallest are grouped into one block; the "
               f"areas still sum to the real total." if tail else ""))
    return View(markup=_svg(width, height, "".join(body),
                            title="Where the money goes", note=note))


# --------------------------------------------------------------------
# Lead time
# --------------------------------------------------------------------

def lead_time_view(components, limit: int = 18) -> View:
    """Which part gates the build.

    The longest lead time is the date the whole board is ready, however cheap
    and available everything else is. That single fact is worth a picture,
    because it is the one a spreadsheet hides in a column nobody sorts.
    """
    waits = [(int(_num(getattr(component, "lead_time_days", 0))), component)
             for component in components]
    waits = [(days, component) for days, component in waits if days > 0]

    if not waits:
        return View(reason="no lead-time figures in this file. These usually "
                           "come from a distributor rather than the EDA tool, "
                           "so a key fills them in.")

    waits.sort(key=lambda pair: -pair[0])
    shown = waits[:limit]
    longest = shown[0][0]

    row, top = 26.0, 58.0
    width = 900.0
    height = top + row * len(shown) + 44
    label_w, right_pad = 190.0, 90.0
    track = width - label_w - right_pad

    body = []
    for index, (days, component) in enumerate(shown):
        y = top + index * row
        critical = days == longest
        bar = track * (days / longest)
        colour = DANGER if critical else (WARN if days >= longest * 0.6
                                          else PALETTE[0])
        reference = _ref(component)
        body.append(
            f'<g class="cell" data-ref="{_x(reference)}">'
            f'<title>{_x(reference)} — {days} day(s)</title>'
            f'<text x="14" y="{y + 13:.1f}" font-family="sans-serif" '
            f'font-size="11" fill="{INK}">{_x(reference[:26])}</text>'
            f'<rect x="{label_w:.0f}" y="{y + 3:.1f}" width="{bar:.1f}" '
            f'height="16" fill="{colour}" rx="2"/>'
            f'<text x="{label_w + bar + 8:.1f}" y="{y + 15:.1f}" '
            f'font-family="sans-serif" font-size="10" fill="{MUTED}">'
            f'{days} d{" — gates the build" if critical else ""}</text>'
            f'</g>')

    body.append(f'<line x1="{label_w:.0f}" y1="{top - 6:.0f}" '
                f'x2="{label_w:.0f}" y2="{top + row * len(shown):.0f}" '
                f'stroke="{GRID}"/>')

    omitted = len(waits) - len(shown)
    note = (f"{longest} day(s) is the earliest this build can be complete. "
            + (f"{omitted} shorter line(s) not shown." if omitted else ""))
    return View(markup=_svg(width, height, "".join(body),
                            title="What gates the build", note=note))


# --------------------------------------------------------------------
# Supply risk
# --------------------------------------------------------------------

def risk_view(report) -> View:
    """Lifecycle, stock and minimum order, per line that was actually checked.

    Rendered as a table rather than a drawing on purpose: the useful operation
    is sorting and comparing exact numbers, and a scatter plot of four points
    would be decoration standing in front of the figures.
    """
    checked = [line for line in getattr(report, "lines", []) if line.was_checked]
    if not checked:
        return View(reason="no line was looked up, so there is nothing to "
                           "rate. Set a distributor API key and these fill "
                           "in: lifecycle, stock against your build quantity, "
                           "minimum order quantity and price at that quantity.")

    rows = []
    for line in checked:
        record = getattr(line.lookup, "record", None)
        lifecycle = getattr(getattr(record, "lifecycle", None), "value",
                            "unknown")
        offer = getattr(record, "best_offer", None) if record else None
        stock = getattr(offer, "stock", None) if offer else None
        minimum = getattr(offer, "minimum_quantity", None) if offer else None
        quantity = int(_num(getattr(line.component, "quantity", 1), 1))
        # The check the whole paid tier turns on: what a unit actually costs
        # at the quantity being bought, not at one.
        at_quantity = (offer.unit_price_at(quantity)
                       if offer and hasattr(offer, "unit_price_at") else None)

        # Matches Lifecycle's own values rather than a guess at them.
        bad_life = str(lifecycle).lower() in (
            "obsolete", "not recommended for new designs")
        short = stock is not None and stock < quantity
        over_min = minimum is not None and minimum > quantity

        rows.append(
            "<tr>"
            f'<td class="mono">{_x(_ref(line.component))}</td>'
            f'<td class="mono">{_x(getattr(line.component, "manufacturer_part_number", ""))}</td>'
            f'<td class="{"bad" if bad_life else ""}">{_x(lifecycle)}</td>'
            f'<td class="mono {"bad" if short else ""}">'
            f'{_x("?" if stock is None else f"{stock:,}")}</td>'
            f'<td class="mono">{_x(quantity)}</td>'
            f'<td class="mono {"warn" if over_min else ""}">'
            f'{_x("-" if minimum is None else minimum)}</td>'
            f'<td class="mono">'
            f'{_x("-" if at_quantity is None else f"${at_quantity:.4f}")}</td>'
            "</tr>")

    return View(markup=(
        '<div class="scroll"><table class="risk"><thead><tr>'
        "<th>Line</th><th>Part number</th><th>Lifecycle</th>"
        "<th>In stock</th><th>You need</th><th>Min order</th>"
        "<th>Unit @ qty</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"))


# --------------------------------------------------------------------
# Enclosure fit
# --------------------------------------------------------------------

def _iso(x: float, y: float, z: float, scale: float):
    """Flat isometric: 30 degrees, no perspective.

    No perspective on purpose. A vanishing point would make two parts of the
    same height read as different sizes depending where they sit, and the only
    question this drawing answers is whether things fit.
    """
    cos30, sin30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    return ((x - y) * cos30 * scale, ((x + y) * sin30 - z) * scale)


def _cuboid(x, y, z, w, d, h, scale, ox, oy, colour, outline) -> str:
    """One box, three visible faces, drawn back to front."""
    def point(px, py, pz):
        sx, sy = _iso(px, py, pz, scale)
        return f"{sx + ox:.1f},{sy + oy:.1f}"

    top = " ".join([point(x, y, z + h), point(x + w, y, z + h),
                    point(x + w, y + d, z + h), point(x, y + d, z + h)])
    left = " ".join([point(x, y + d, z + h), point(x + w, y + d, z + h),
                     point(x + w, y + d, z), point(x, y + d, z)])
    right = " ".join([point(x + w, y, z + h), point(x + w, y + d, z + h),
                      point(x + w, y + d, z), point(x + w, y, z)])
    return (f'<polygon points="{left}" fill="{colour}" fill-opacity="0.72" '
            f'stroke="{outline}" stroke-width="0.8"/>'
            f'<polygon points="{right}" fill="{colour}" fill-opacity="0.88" '
            f'stroke="{outline}" stroke-width="0.8"/>'
            f'<polygon points="{top}" fill="{colour}" stroke="{outline}" '
            f'stroke-width="0.8"/>')


def enclosure_view(components, enclosure=None) -> View:
    """Component volumes packed into the enclosure, in isometric.

    Emphatically not a placement. Where a part is drawn carries no claim at
    all -- the packing is widest-first shelves, and a real tool would weigh
    thermal, EMI and routing. What the drawing does answer is the question the
    numbers answer: does this add up to something that fits.
    """
    sized = [c for c in components
             if _num(getattr(c, "width_mm", 0)) > 0
             and _num(getattr(c, "depth_mm", 0)) > 0]
    if not sized:
        return View(reason="no component dimensions in this file. Standard "
                           "EDA exports carry footprints, not millimetres, so "
                           "enclosure fit cannot be checked from this file "
                           "alone -- the columns have to be supplied.")

    enc_w, enc_d, enc_h = (enclosure if enclosure else (0.0, 0.0, 0.0))
    span = enc_w if enc_w > 0 else max(
        60.0, sum(_num(getattr(c, "width_mm", 0)) for c in sized) ** 0.5 * 3)

    # Widest-first shelf packing, the same approach the placement blueprint
    # uses, kept identical so two drawings of one BOM never disagree.
    placed, cursor_x, cursor_y, shelf_d, used_w = [], 0.0, 0.0, 0.0, 0.0
    for component in sorted(sized, key=lambda c: -_num(getattr(c, "width_mm", 0))):
        w = _num(getattr(component, "width_mm", 0))
        d = _num(getattr(component, "depth_mm", 0))
        h = max(_num(getattr(component, "height_mm", 0)), 0.6)
        if cursor_x + w > span and placed:
            cursor_x, cursor_y, shelf_d = 0.0, cursor_y + shelf_d, 0.0
        placed.append((component, cursor_x, cursor_y, w, d, h))
        cursor_x += w
        shelf_d = max(shelf_d, d)
        # The true rightmost extent, which is not the shelf limit: a part
        # wider than the envelope overflows past it and still has to be
        # counted, or the drawing clips it and the note calls it a fit.
        used_w = max(used_w, cursor_x)
    used_d = cursor_y + shelf_d
    tallest = max(h for *_, h in placed)

    # Drawn boxes are capped; the fit verdict below is computed over every
    # part regardless, because a report that stopped checking at part 120
    # would call a board that does not fit a board that does.
    drawn = placed[:FIT_BOXES]
    omitted_boxes = len(placed) - len(drawn)

    scale = min(6.0, max(1.6, 620.0 / max(span + used_d, 1.0)))
    width, height = 900.0, 470.0
    ox, oy = width / 2, 120.0

    body = []
    if enc_w > 0 and enc_d > 0:
        body.append(_cuboid(0, 0, 0, enc_w, enc_d, max(enc_h, 0.5), scale,
                            ox, oy, "#FFFFFF", "#98A2AE")
                    .replace('fill-opacity="0.72"', 'fill-opacity="0.10"')
                    .replace('fill-opacity="0.88"', 'fill-opacity="0.16"'))

    # Back to front, so nearer boxes overdraw the ones behind them.
    for component, px, py, w, d, h in sorted(drawn,
                                            key=lambda item: item[1] + item[2]):
        too_tall = enc_h > 0 and h > enc_h
        too_wide = enc_w > 0 and px + w > enc_w
        too_deep = enc_d > 0 and py + d > enc_d
        bad = too_tall or too_wide or too_deep
        colour = DANGER if bad else PALETTE[hash(_ref(component)) % len(PALETTE)]
        body.append(f'<g class="cell" data-ref="{_x(_ref(component))}">'
                    f'<title>{_x(_ref(component))} — {w:g} x {d:g} x {h:g} mm'
                    f'{" — does not fit" if bad else ""}</title>'
                    + _cuboid(px, py, 0, w, d, h, scale, ox, oy, colour,
                              "#33404E")
                    + "</g>")

    if enc_w > 0:
        fits = (used_d <= enc_d and used_w <= enc_w and tallest <= enc_h)
        verdict = ("Everything fits the stated envelope."
                   if fits else "Something does not fit -- shown in red.")
        note = (f"Envelope {enc_w:g} x {enc_d:g} x {enc_h:g} mm. "
                f"Packed footprint {used_w:g} x {used_d:g} mm, tallest part "
                f"{tallest:g} mm. {verdict}")
    else:
        note = (f"{len(placed)} part(s) with dimensions, tallest {tallest:g} "
                f"mm. No envelope given: pass --enclosure WxDxH to check fit.")
    if omitted_boxes:
        note += (f"  {omitted_boxes} smaller part(s) are counted in the "
                 f"verdict but not drawn.")

    return View(markup=_svg(width, height, "".join(body),
                            title="Volume, not placement", note=note + "  "
                            "Position carries no claim; packing is widest-first."))


__all__ = ["View", "cost_view", "lead_time_view", "risk_view",
           "enclosure_view"]
