"""
HELIX CORE — Visual diagram generation (D-041/D-042).

Real SVG output, not ASCII text — for Standard (visual interconnect) and
Senior (top-down placement blueprint with risk-highlighting) tiers.

Same honesty rules as generate_interconnect_diagram() in
bom_review_agent.py: these are suggested sketches derived from category
tags and submitted dimensions, not verified schematics or EDA-grade
placement. Every diagram states this in its own rendered text, not just
in code comments, so the caveat travels with the artifact itself.
"""

# A small, fixed palette -- not client-configurable yet, kept simple and
# legible rather than decorative.
CATEGORY_COLORS = {
    "compute": "#4A90D9",
    "power": "#E8A33D",
    "sensor": "#5CB85C",
    "display": "#9B59B6",
    "connectivity": "#1ABC9C",
    "connector": "#95A5A6",
    "passive": "#BDC3C7",
    "pcb": "#7F8C8D",
    "mechanical": "#D35400",
}
RISK_COLOR = "#D9534F"  # used only to outline components tied to a real finding


def _xml(text) -> str:
    """Escape text before it goes into an SVG node.

    Component names come from client-submitted data. Without escaping, a part
    called "Resistor <100R>" or "AT&T module" produces malformed XML that no
    viewer will render, and a name containing a closing tag could inject
    arbitrary markup into a diagram the client opens in a browser. Every test
    so far used clean ASCII names, which is exactly why this went unnoticed.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_visual_interconnect_svg(components: list) -> str:
    """Standard tier — real SVG version of the ASCII interconnect
    diagram: a compute hub with category groups connected by labeled
    lines. Same "typical, not verified" caveat as the text version,
    rendered directly in the image, not just documented elsewhere."""
    by_category: dict = {}
    for c in components:
        by_category.setdefault(c.category, []).append(c)

    compute = by_category.get("compute", [])
    if not compute:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="80">'
            '<text x="10" y="40" font-family="sans-serif" font-size="14" fill="#D9534F">'
            "No 'compute' category component found -- cannot anchor a diagram "
            "without a central controller/MCU.</text></svg>"
        )

    hub_name = compute[0].name
    protocol_by_category = {
        "sensor": "I2C/SPI", "display": "SPI/I2C", "connectivity": "UART/SPI",
        "connector": "GPIO", "power": "Power rail",
    }
    connected = [cat for cat in by_category if cat != "compute" and cat in protocol_by_category]

    width, height = 700, 140 + 70 * len(connected)
    hub_x, hub_y, hub_w, hub_h = 260, 20, 180, 50

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#FAFAFA"/>',
        f'<text x="10" y="18" font-family="sans-serif" font-size="11" fill="#888">'
        f'Suggested interconnect diagram -- category-based, NOT a verified schematic. '
        f'Confirm pin assignment against real datasheets.</text>',
        f'<rect x="{hub_x}" y="{hub_y}" width="{hub_w}" height="{hub_h}" rx="6" '
        f'fill="{CATEGORY_COLORS["compute"]}" stroke="#333" stroke-width="1.5"/>',
        f'<text x="{hub_x + hub_w/2}" y="{hub_y + hub_h/2 + 5}" font-family="sans-serif" '
        f'font-size="13" fill="white" text-anchor="middle">{_xml(hub_name[:24])}</text>',
    ]

    y = hub_y + hub_h + 40
    for cat in connected:
        parts = by_category[cat]
        proto = protocol_by_category[cat]
        color = CATEGORY_COLORS.get(cat, "#999")
        names = ", ".join(p.name for p in parts[:2])
        if len(parts) > 2:
            names += f" +{len(parts) - 2} more"
        box_x, box_w = 80, 300
        svg.append(f'<line x1="{hub_x + hub_w/2}" y1="{hub_y + hub_h}" '
                   f'x2="{box_x + box_w/2}" y2="{y}" stroke="#666" stroke-width="1.5"/>')
        svg.append(f'<text x="{(hub_x + hub_w/2 + box_x + box_w/2)/2}" y="{(hub_y+hub_h+y)/2}" '
                   f'font-family="sans-serif" font-size="10" fill="#333">{proto}</text>')
        svg.append(f'<rect x="{box_x}" y="{y}" width="{box_w}" height="40" rx="5" '
                   f'fill="{color}" stroke="#333" stroke-width="1"/>')
        svg.append(f'<text x="{box_x + box_w/2}" y="{y + 25}" font-family="sans-serif" '
                   f'font-size="11" fill="white" text-anchor="middle">'
                   f'{_xml(cat)}: {_xml(names[:40])}</text>')
        y += 70

    svg.append("</svg>")
    return "\n".join(svg)


def _truncate_label(name: str, max_len: int = 20) -> str:
    """Truncates at a word boundary where possible -- cutting mid-word
    (e.g. 'Oversized disp...') looks unprofessional on a client-facing
    diagram and was caught during testing, not assumed fine because the
    code ran without error."""
    if len(name) <= max_len:
        return name
    truncated = name[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.5:  # only break at a space if it's not too early
        truncated = truncated[:last_space]
    return truncated + "..."


def generate_placement_blueprint_svg(components: list, constraints, review_result=None) -> str:
    """Senior tier — top-down placement sketch using REAL submitted
    width/depth per component, simple shelf-packing (not real EDA/thermal
    placement -- stated plainly in the render itself). Components tied to
    a real finding (physical-fit conflict, long lead time) are outlined in
    red as a risk-highlight, using actual finding data, not decoration.
    """
    scale = 3.0  # px per mm, keeps a typical enclosure readable
    margin = 30
    enc_w = constraints.enclosure_width_mm * scale
    enc_h = constraints.enclosure_depth_mm * scale

    # Identify which specific components are tied to a real finding, by
    # name match against the finding text -- only components genuinely
    # named in a finding get the risk outline, not a blanket "some risk
    # exists somewhere" flag.
    # Real bug fixed here: a plain substring test flags the wrong part. A
    # component called "Battery" matches a finding about the "Battery Pack
    # 5000mAh", so the blueprint outlines a component that has no finding
    # against it -- and the client is looking at a red box on the wrong part.
    # Findings name components by their full name, so when several names match
    # the same finding, only the longest is the one actually being discussed;
    # any name contained inside another match is a false positive.
    risky_names = set()
    if review_result:
        for f in review_result.findings:
            matched = [c.name for c in components if c.name in f.message]
            for name in matched:
                if any(name != other and name in other for other in matched):
                    continue  # shadowed by a longer name in this same finding
                risky_names.add(name)

    # Simple shelf-packing: sort widest-first, pack left-to-right, wrap
    # to a new shelf when the current row is full. A real placement tool
    # would consider thermal/EMI/routing -- this doesn't, and says so.
    sorted_components = sorted(components, key=lambda c: -c.width_mm)
    shelves = []
    current_shelf, current_x, shelf_h = [], 0, 0
    max_x_used = 0  # tracks the true rightmost extent, including any
                     # component that overflows past the enclosure width --
                     # needed so an oversized part is never clipped out of
                     # the canvas (caught by visually inspecting output,
                     # not just checking well-formed XML -- see D-043)
    for c in sorted_components:
        w = c.width_mm * scale
        d = c.depth_mm * scale
        if current_x + w > enc_w and current_shelf:
            shelves.append((current_shelf, shelf_h))
            current_shelf, current_x, shelf_h = [], 0, 0
        current_shelf.append((c, current_x, d, w))
        current_x += w
        max_x_used = max(max_x_used, current_x)
        shelf_h = max(shelf_h, d)
    if current_shelf:
        shelves.append((current_shelf, shelf_h))

    total_h = sum(h for _, h in shelves) + margin * 2
    svg_h = max(total_h, enc_h) + 60
    # Canvas width must fit the wider of: the enclosure itself, or the
    # widest actual row of components -- an oversized component that
    # overflows the enclosure must still be fully visible, not clipped,
    # since seeing the overflow IS the point of flagging it.
    svg_w = max(enc_w, max_x_used) + margin * 2

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.0f}" height="{svg_h:.0f}" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">',
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="#FAFAFA"/>',
        f'<text x="10" y="16" font-family="sans-serif" font-size="11" fill="#888">'
        f'Suggested top-down placement -- simple size-based packing, NOT thermal/EMI-aware '
        f'EDA placement. Components outlined red are tied to a specific finding below.</text>',
        f'<rect x="{margin}" y="30" width="{enc_w:.0f}" height="{enc_h:.0f}" fill="none" '
        f'stroke="#333" stroke-width="2" stroke-dasharray="4,2"/>',
        f'<text x="{margin}" y="{30 + enc_h + 15:.0f}" font-family="sans-serif" font-size="10" '
        f'fill="#666">Enclosure envelope: {constraints.enclosure_width_mm:.0f}mm x '
        f'{constraints.enclosure_depth_mm:.0f}mm</text>',
    ]

    y_cursor = 30
    for shelf, shelf_h in shelves:
        for c, x_offset, d, w in shelf:
            color = CATEGORY_COLORS.get(c.category, "#999")
            is_risky = c.name in risky_names
            stroke = RISK_COLOR if is_risky else "#333"
            stroke_w = 3 if is_risky else 1
            svg.append(f'<rect x="{margin + x_offset:.0f}" y="{y_cursor:.0f}" '
                       f'width="{w:.0f}" height="{d:.0f}" fill="{color}" '
                       f'stroke="{stroke}" stroke-width="{stroke_w}"/>')
            label = _truncate_label(c.name)
            svg.append(f'<text x="{margin + x_offset + w/2:.0f}" y="{y_cursor + d/2:.0f}" '
                       f'font-family="sans-serif" font-size="8" fill="white" '
                       f'text-anchor="middle">{_xml(label)}</text>')
            if is_risky:
                svg.append(f'<text x="{margin + x_offset + w/2:.0f}" y="{y_cursor + d/2 + 10:.0f}" '
                           f'font-family="sans-serif" font-size="7" fill="white" '
                           f'text-anchor="middle">[FLAGGED]</text>')
        y_cursor += shelf_h

    svg.append("</svg>")
    return "\n".join(svg)
