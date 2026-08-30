"""
A single self-contained HTML file, written next to the BOM it describes.

Why HTML and not a desktop toolkit: the guarantee this tool sells is that the
BOM never leaves the machine, so anything with a server is disqualified before
it is designed. A file opened over ``file://`` keeps that literally true while
still giving tabs, filters, a diagram and colour -- and it costs no runtime
dependency, because producing it is string work.

Everything is inlined. No stylesheet, no script, no font and no image is
fetched from anywhere: a report that phoned out for a webfont would leak the
fact that a review happened, and on an air-gapped bench it would render wrong
as well. Opening this file with the network unplugged looks identical.

The whole document is built from ``html.escape``d values. A BOM is somebody
else's data -- a description field containing ``<script>`` is a plausible
accident and would otherwise execute in the reader's browser.
"""

from __future__ import annotations

import html
import platform
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

SEVERITY_LABEL = {"critical": "critical", "warning": "warning", "info": "note"}

# What to actually do about each finding. The terminal report says what is
# wrong; a reader looking at a list of problems still has to work out what the
# next move is, and spelling it out is the difference between a report and a
# task list.
ADVICE = (
    ("no manufacturer part number",
     "Add the manufacturer's part number. A value and a footprint are not an "
     "orderable part -- no distributor can quote this line as it stands."),
    ("the part number is a value",
     "Replace it with a specific part number. Parts that share a value differ "
     "in tolerance, package, voltage and power rating, and the assembler "
     "cannot choose for you."),
    ("the part number is a placeholder",
     "Fill this in. The line was never finished, and it will reach the "
     "assembler exactly as it is."),
    ("appears on",
     "A reference designator names one part on the board. Two lines claim "
     "this one, so one of them is wrong -- check it against the schematic."),
    ("the same part is on",
     "If this is one part used in several places, merge the lines. Left as "
     "it is, it gets ordered twice and the board is costed twice."),
    ("designator(s) but a quantity of",
     "One of the two numbers is wrong. Either designators are missing from "
     "the list or the quantity was typed by hand."),
    ("obsolete",
     "The distributor lists this part as obsolete. Find a replacement now "
     "rather than when the order is rejected."),
    ("out of stock",
     "Nothing is available to ship. Check a second distributor before "
     "committing this build to a date."),
    ("minimum order",
     "The distributor will not sell the quantity asked for. The real cost of "
     "this line is the minimum, not the quantity on the BOM."),
    ("price",
     "The price in the BOM is not the price at the quantity being bought. "
     "Re-cost the build before quoting it to anybody."),
)


def _advice(message: str) -> str:
    lowered = (message or "").lower()
    for needle, text in ADVICE:
        if needle in lowered:
            return text
    return ""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _money(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"${value:.2f}"
    return f"${float(value):.2f}"


def _attr(component, name, default=""):
    return getattr(component, name, default) or default


# --------------------------------------------------------------------
# Style. Written out rather than minified so that somebody who opens the
# file in an editor can read and change it.
# --------------------------------------------------------------------

STYLE = """
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #14161a;
  --muted: #5c6570;
  --line: #e2e6ea;
  --critical: #b4232b;
  --critical-bg: #fdf2f2;
  --warning: #8a5a00;
  --warning-bg: #fdf8ec;
  --info: #2b5f8a;
  --info-bg: #f0f5fa;
  --ok: #1f7a4d;
  --accent: #1b3a5c;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171b;
    --panel: #1c2026;
    --ink: #e7eaee;
    --muted: #9aa5b1;
    --line: #2c323a;
    --critical: #ff8189;
    --critical-bg: #2a1b1d;
    --warning: #e5b567;
    --warning-bg: #2a2419;
    --info: #7fb2dd;
    --info-bg: #1a2530;
    --ok: #6fce9f;
    --accent: #cfe0f0;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 32px 20px 72px; }
header.top { margin-bottom: 22px; }
h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
h1 .file { color: var(--muted); font-weight: 400; }
.sub { color: var(--muted); font-size: 13.5px; margin: 0; }

.banner {
  margin: 18px 0 0; padding: 13px 16px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--warning-bg);
  border-left: 4px solid var(--warning); font-size: 14px;
}
.banner.clean { background: var(--info-bg); border-left-color: var(--ok); }
.banner strong { display: block; margin-bottom: 2px; }

.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 6px; }
.tile {
  flex: 1 1 130px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 13px 15px;
}
.tile .n { font-size: 25px; font-weight: 600; line-height: 1.1; }
.tile .k { font-size: 12px; color: var(--muted); text-transform: uppercase;
           letter-spacing: 0.06em; margin-top: 3px; }
.tile.critical .n { color: var(--critical); }
.tile.warning .n { color: var(--warning); }

nav.tabs {
  display: flex; flex-wrap: wrap; gap: 4px; margin: 26px 0 0;
  border-bottom: 1px solid var(--line);
}
nav.tabs button {
  appearance: none; border: 0; background: none; cursor: pointer;
  font: inherit; font-size: 14px; color: var(--muted);
  padding: 9px 14px; border-bottom: 2px solid transparent; margin-bottom: -1px;
}
nav.tabs button:hover { color: var(--ink); }
nav.tabs button[aria-selected="true"] {
  color: var(--ink); border-bottom-color: var(--accent); font-weight: 600;
}
section.panel { display: none; padding-top: 20px; }
section.panel.active { display: block; }

.filters { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 16px; }
.filters button {
  appearance: none; cursor: pointer; font: inherit; font-size: 13px;
  padding: 5px 12px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--panel); color: var(--muted);
}
.filters button[aria-pressed="true"] {
  border-color: var(--accent); color: var(--ink); font-weight: 600;
}

.finding {
  background: var(--panel); border: 1px solid var(--line);
  border-left: 4px solid var(--line); border-radius: 8px;
  padding: 13px 16px; margin-bottom: 10px;
}
.finding.critical { border-left-color: var(--critical); }
.finding.warning  { border-left-color: var(--warning); }
.finding.info     { border-left-color: var(--info); }
.finding .head { display: flex; flex-wrap: wrap; gap: 9px; align-items: baseline; }
.tag {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em;
  font-weight: 700; padding: 2px 8px; border-radius: 4px;
}
.finding.critical .tag { color: var(--critical); background: var(--critical-bg); }
.finding.warning  .tag { color: var(--warning);  background: var(--warning-bg); }
.finding.info     .tag { color: var(--info);     background: var(--info-bg); }
.ref { font-weight: 650; font-family: ui-monospace, SFMono-Regular, Menlo,
       Consolas, monospace; }
.msg { flex: 1 1 auto; }
.evidence { color: var(--muted); font-size: 13.5px; margin-top: 6px; }
.next { font-size: 13.5px; margin-top: 9px; padding-top: 9px;
        border-top: 1px dashed var(--line); }
.next b { font-weight: 650; }

table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px;
          background: var(--panel); }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line);
         white-space: nowrap; }
th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
     color: var(--muted); font-weight: 600; }
tr:last-child td { border-bottom: 0; }
td.mono, th.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas,
                   monospace; }
td.wrap-cell { white-space: normal; min-width: 220px; }
.pill { font-size: 11.5px; padding: 2px 8px; border-radius: 999px;
        background: var(--info-bg); color: var(--info); }
.pill.no { background: var(--warning-bg); color: var(--warning); }
.pill.yes { background: var(--info-bg); color: var(--ok); }

.reason { background: var(--panel); border: 1px solid var(--line);
          border-radius: 8px; padding: 12px 15px; margin-bottom: 9px; }
.reason .n { font-weight: 650; }
.kv { display: grid; grid-template-columns: 190px 1fr; gap: 5px 16px;
      font-size: 14px; }
.kv dt { color: var(--muted); }
.kv dd { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas,
         monospace; }
h2 { font-size: 15px; margin: 26px 0 11px; }
h2:first-child { margin-top: 0; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0; }
.diagram { background: var(--panel); border: 1px solid var(--line);
           border-radius: 8px; padding: 16px; overflow-x: auto; }
.diagram svg { max-width: 100%; height: auto; display: block; }
footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line);
         color: var(--muted); font-size: 12.5px; }
footer code { font-size: 12px; }
"""

SCRIPT = """
(function () {
  var tabs = document.querySelectorAll('nav.tabs button');
  function show(name) {
    tabs.forEach(function (t) {
      t.setAttribute('aria-selected', String(t.dataset.tab === name));
    });
    document.querySelectorAll('section.panel').forEach(function (p) {
      p.classList.toggle('active', p.id === 'tab-' + name);
    });
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () { show(t.dataset.tab); });
  });

  var filters = document.querySelectorAll('.filters button');
  filters.forEach(function (b) {
    b.addEventListener('click', function () {
      filters.forEach(function (o) {
        o.setAttribute('aria-pressed', String(o === b));
      });
      var want = b.dataset.sev;
      document.querySelectorAll('.finding').forEach(function (f) {
        f.style.display = (want === 'all' || f.classList.contains(want))
          ? '' : 'none';
      });
    });
  });
})();
"""


# --------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------

def _findings_panel(findings) -> str:
    if not findings:
        return ('<p class="empty">No findings. Read the "Not checked" tab '
                'before treating that as a clean bill of health.</p>')

    counts = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    buttons = ['<button data-sev="all" aria-pressed="true">'
               f'All {len(findings)}</button>']
    for severity in ("critical", "warning", "info"):
        if counts.get(severity):
            buttons.append(
                f'<button data-sev="{severity}" aria-pressed="false">'
                f'{SEVERITY_LABEL[severity]} {counts[severity]}</button>')

    rows = []
    for f in sorted(findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 9),
                                             x.reference)):
        severity = f.severity if f.severity in SEVERITY_ORDER else "info"
        advice = _advice(f.message)
        rows.append(
            f'<div class="finding {severity}">'
            f'<div class="head">'
            f'<span class="tag">{_esc(SEVERITY_LABEL[severity])}</span>'
            f'<span class="ref">{_esc(f.reference)}</span>'
            f'<span class="msg">{_esc(f.message)}</span>'
            f'</div>'
            + (f'<div class="evidence">{_esc(f.evidence)}</div>'
               if f.evidence else "")
            + (f'<div class="next"><b>What to do:</b> {_esc(advice)}</div>'
               if advice else "")
            + '</div>')

    return (f'<div class="filters">{"".join(buttons)}</div>'
            + "".join(rows))


def _not_checked_panel(report) -> str:
    reasons = report.reasons_not_checked() if hasattr(
        report, "reasons_not_checked") else {}
    if not reasons:
        return ('<p class="empty">Every line was looked up.</p>')

    blocks = [
        '<div class="banner"><strong>These are not passes.</strong>'
        'A line that could not be checked is a line nobody has verified. '
        'The tool reports them so that silence is never mistaken for a '
        'clean result.</div>'
    ]
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        blocks.append(f'<div class="reason"><span class="n">{count} '
                      f'line(s)</span> &mdash; {_esc(reason)}</div>')
    return "".join(blocks)


def _lines_panel(report) -> str:
    if not report.lines:
        return '<p class="empty">No lines were read.</p>'

    rows = []
    for line in report.lines:
        component = line.component
        checked = line.was_checked
        outcome = getattr(line.lookup.outcome, "value", "")
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(_attr(component, "designator"))}</td>'
            f'<td class="wrap-cell">{_esc(_attr(component, "name"))}</td>'
            f'<td>{_esc(_attr(component, "quantity", 1))}</td>'
            f'<td class="mono">'
            f'{_esc(_attr(component, "manufacturer_part_number"))}</td>'
            f'<td>{_esc(_attr(component, "manufacturer"))}</td>'
            f'<td><span class="pill {"yes" if checked else "no"}">'
            f'{_esc(outcome)}</span></td>'
            f'<td class="mono">{_esc(_money(line.unit_price))}</td>'
            f'<td class="mono">{_esc(_money(line.extended_price))}</td>'
            "</tr>")

    return (
        '<div class="scroll"><table><thead><tr>'
        "<th>Designator</th><th>Description</th><th>Qty</th>"
        "<th>Part number</th><th>Manufacturer</th><th>Looked up</th>"
        "<th>Unit</th><th>Extended</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def _file_panel(ingest, source: Path) -> str:
    if ingest is None:
        return '<p class="empty">No parse detail available.</p>'

    def row(key, value):
        return f"<dt>{_esc(key)}</dt><dd>{_esc(value)}</dd>"

    detail = [
        row("file", source.name),
        row("size", f'{getattr(ingest, "size_bytes", 0)} bytes'),
        row("encoding", getattr(ingest, "encoding", "")),
        row("delimiter", repr(getattr(ingest, "delimiter", ""))),
        row("header row", f'line {getattr(ingest, "header_row", 1)} of '
                          f'{getattr(ingest, "total_rows", 0)}'),
        row("data rows", getattr(ingest, "rows_read", 0)),
        row("decimal separator", getattr(ingest, "decimal_separator", ".")),
    ]

    mapped = getattr(ingest, "mapped", {}) or {}
    unmapped = getattr(ingest, "unmapped_headers", []) or []
    missing = getattr(ingest, "missing_fields", []) or []

    parts = [f'<h2>How the file was read</h2><dl class="kv">'
             f'{"".join(detail)}</dl>']

    if mapped:
        rows = "".join(f'<tr><td class="mono">{_esc(head)}</td>'
                       f'<td class="mono">{_esc(field)}</td></tr>'
                       for head, field in mapped.items())
        parts.append('<h2>Columns matched</h2><div class="scroll"><table>'
                     "<thead><tr><th>Heading in your file</th>"
                     "<th>Understood as</th></tr></thead><tbody>"
                     f"{rows}</tbody></table></div>")

    if unmapped:
        parts.append("<h2>Columns ignored</h2><p>"
                     + ", ".join(f"<code>{_esc(h)}</code>" for h in unmapped)
                     + "</p>")

    if missing:
        parts.append(
            "<h2>Columns the file did not have</h2>"
            '<p class="empty">Checks needing these could not run: '
            + ", ".join(f"<code>{_esc(m)}</code>" for m in missing) + "</p>")

    return "".join(parts)


# --------------------------------------------------------------------
# The document
# --------------------------------------------------------------------

def build_html(report, ingest=None, source=None, diagram_svg: str = "",
               version: str = "") -> str:
    """The whole report as one string. No I/O, so it is trivial to test."""
    source = Path(source) if source else Path("bill of materials")
    findings = list(report.findings)
    criticals = sum(1 for f in findings if f.severity == "critical")
    warnings = sum(1 for f in findings if f.severity == "warning")
    not_checked = len(report.not_checked)
    total = len(report.lines)

    if not report.is_complete:
        banner = (
            '<div class="banner"><strong>This is not a clean bill of '
            f'health.</strong>{not_checked} of {total} line(s) could not be '
            "checked. See the <em>Not checked</em> tab for what each one "
            "needed.</div>")
    elif findings:
        banner = ('<div class="banner"><strong>Every line was checked.</strong>'
                  f"{len(findings)} finding(s) below.</div>")
    else:
        banner = ('<div class="banner clean"><strong>Every line was checked '
                  "and nothing was found.</strong>Compare the column mapping "
                  "in the <em>File</em> tab against what you expected.</div>")

    tabs = [("findings", f"Findings ({len(findings)})"),
            ("notchecked", f"Not checked ({not_checked})"),
            ("lines", f"Lines ({total})")]
    panels = [("findings", _findings_panel(findings)),
              ("notchecked", _not_checked_panel(report)),
              ("lines", _lines_panel(report))]
    if diagram_svg:
        tabs.append(("routing", "Routing"))
        panels.append(("routing",
                       '<h2>Interconnect</h2><p class="empty">Every line is a '
                       "net that exists between named pins, read from the "
                       "file. Power and ground nets are left out because they "
                       'touch nearly everything.</p>'
                       f'<div class="diagram">{diagram_svg}</div>'))
    tabs.append(("file", "File"))
    panels.append(("file", _file_panel(ingest, source)))

    nav = "".join(
        f'<button data-tab="{key}" aria-selected="{"true" if i == 0 else "false"}">'
        f"{_esc(label)}</button>"
        for i, (key, label) in enumerate(tabs))
    body = "".join(
        f'<section class="panel{" active" if i == 0 else ""}" id="tab-{key}">'
        f"{content}</section>"
        for i, (key, content) in enumerate(panels))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BOM review &mdash; {_esc(source.name)}</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>BOM review <span class="file">&mdash; {_esc(source.name)}</span></h1>
  <p class="sub">Generated {_esc(generated)} on this machine. Nothing was
  uploaded and nothing was sent.</p>
  {banner}
  <div class="tiles">
    <div class="tile"><div class="n">{total}</div><div class="k">lines</div></div>
    <div class="tile critical"><div class="n">{criticals}</div>
      <div class="k">critical</div></div>
    <div class="tile warning"><div class="n">{warnings}</div>
      <div class="k">warnings</div></div>
    <div class="tile"><div class="n">{not_checked}</div>
      <div class="k">not checked</div></div>
  </div>
</header>
<nav class="tabs">{nav}</nav>
{body}
<footer>
  helix-grounding {_esc(version or "")} &middot; python
  {_esc(platform.python_version())} &middot; {_esc(platform.system())}<br>
  This file is self-contained: no stylesheet, script, font or image is loaded
  from anywhere. It renders identically with the network unplugged.
</footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def write_html(report, destination, ingest=None, source=None,
               diagram_svg: str = "", version: str = "") -> Path:
    """Write the report and return where it landed."""
    destination = Path(destination)
    destination.write_text(
        build_html(report, ingest=ingest, source=source,
                   diagram_svg=diagram_svg, version=version),
        encoding="utf-8")
    return destination


def default_destination(source) -> Path:
    """Beside the BOM, named after it.

    Not in the current working directory: somebody reviewing
    ``~/designs/rev-c/bom.csv`` from their home folder should find the report
    with the design, not wherever the shell happened to be.
    """
    source = Path(source)
    return source.with_name(f"{source.stem}_review.html")


def open_in_browser(path) -> bool:
    """Best effort. Returns whether the browser was actually launched.

    Never raises: a report that was written successfully must not look like a
    failure because the machine has no desktop session -- which is exactly the
    case on the CI runners and over SSH.
    """
    import webbrowser
    try:
        return webbrowser.open(Path(path).resolve().as_uri())
    except Exception:                                    # noqa: BLE001
        return False


__all__ = ["build_html", "write_html", "default_destination",
           "open_in_browser"]
