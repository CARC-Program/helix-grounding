"""
Tests for the HTML report and the windowed entry point.

Two of these are the reason this file exists rather than being folded into the
CLI tests. A BOM is somebody else's data being rendered into a document that a
browser will execute, so escaping is a security property and is tested as one.
And the report is the visible form of the promise that nothing leaves the
machine -- a single fetched webfont would break that quietly, in a way no
reader could see, so the document is checked for anything that loads.
"""

from pathlib import Path

import pytest

from helix_bom.cli import main
from helix_bom.enrich import enrich
from helix_bom.ingest import load_bom
from helix_bom.report import (build_html, default_destination, open_in_browser,
                              write_html)

FIXTURE = str(Path(__file__).parent.parent / "src" / "helix_bom" / "examples"
              / "enrich_demo.csv")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Never touch the real cache, and never let a developer's distributor key
    turn a offline unit test into a live request."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for name in ("MOUSER_API_KEY", "DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


def _report(path=FIXTURE):
    components, ingest = load_bom(path)
    return enrich(components, []), ingest


# --------------------------------------------------------------------
# The document
# --------------------------------------------------------------------

def test_every_finding_reaches_the_page():
    report, ingest = _report()
    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert html.count('class="finding ') == len(report.findings)
    for finding in report.findings:
        assert finding.reference in html or finding.message in html


def test_a_finding_carries_what_to_do_about_it():
    """The terminal says what is wrong. A reader looking at a list still has
    to work out the next move, and the report is where that belongs."""
    report, ingest = _report()

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert "What to do:" in html
    assert "no distributor can quote this line" in html


def test_an_incomplete_review_says_so_before_anything_else():
    """The failure this project keeps guarding against: silence read as a
    clean bill of health. With no distributors nothing can be looked up, so
    the banner has to say that at the top rather than in a tab."""
    report, ingest = _report()
    assert not report.is_complete

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert "not a clean bill of health" in html
    assert "These are not passes." in html


def test_the_routing_tab_appears_only_with_a_diagram():
    report, ingest = _report()

    without = build_html(report, ingest=ingest, source=Path(FIXTURE))
    with_svg = build_html(report, ingest=ingest, source=Path(FIXTURE),
                          diagram_svg="<svg><circle r='1'/></svg>")

    assert 'data-tab="routing"' not in without
    assert 'data-tab="routing"' in with_svg
    assert "<circle r='1'/>" in with_svg


# --------------------------------------------------------------------
# The promise the report is the visible form of
# --------------------------------------------------------------------

def test_nothing_in_the_page_loads_from_anywhere(tmp_path):
    """No stylesheet, script, font, image or frame may be fetched.

    A report that pulled a webfont would tell a third party that a review
    happened and when, and would render wrong on a bench with no network --
    while still looking correct on the machine of whoever added it.
    """
    import re

    report, ingest = _report()
    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    for tag in re.findall(r"<(?:script|link|img|iframe|object|embed)[^>]*>",
                          html, re.IGNORECASE):
        assert "src=" not in tag.lower(), tag
        assert "href=" not in tag.lower(), tag

    assert "@import" not in html


def test_bom_content_cannot_put_script_in_the_report(tmp_path):
    """A description field is somebody else's text. Rendered unescaped it
    executes in the reader's browser, and a BOM exported from a tool that
    allows angle brackets is a plausible accident rather than an attack."""
    evil = tmp_path / "evil.csv"
    evil.write_text(
        "Designator,Description,Quantity,Manufacturer,"
        "Manufacturer Part Number,Unit Price\n"
        'U1,"<script>alert(1)</script>",1,ACME,'
        '"<img src=x onerror=alert(2)>",1.00\n',
        encoding="utf-8")
    report, ingest = _report(str(evil))

    html = build_html(report, ingest=ingest, source=evil)

    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(2)>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # Exactly one script element, and it is the report's own.
    assert html.count("<script") == 1


# --------------------------------------------------------------------
# Where it goes
# --------------------------------------------------------------------

def test_the_report_lands_beside_the_bom_not_in_the_shell_directory(tmp_path):
    """Somebody reviewing ~/designs/rev-c/bom.csv from their home folder
    should find the report with the design."""
    source = tmp_path / "designs" / "rev-c" / "bom.csv"
    source.parent.mkdir(parents=True)

    destination = default_destination(source)

    assert destination.parent == source.parent
    assert destination.name == "bom_review.html"


def test_opening_a_browser_never_raises(monkeypatch, tmp_path):
    """No desktop session is the normal case on CI and over SSH. A written
    report must not look like a failure because nothing could display it."""
    import webbrowser

    def explode(*args, **kwargs):
        raise RuntimeError("no display")

    monkeypatch.setattr(webbrowser, "open", explode)
    target = tmp_path / "r.html"
    target.write_text("<html></html>", encoding="utf-8")

    assert open_in_browser(target) is False


# --------------------------------------------------------------------
# Through the command line
# --------------------------------------------------------------------

def test_html_writes_a_report_without_changing_the_verdict(tmp_path, capsys):
    """The exit code is the review's answer. Asking for a prettier rendering
    of it must not change what it says."""
    destination = tmp_path / "report.html"

    with_html = main(["enrich", FIXTURE, "--html", str(destination),
                      "--no-open"])
    capsys.readouterr()
    without_html = main(["enrich", FIXTURE])

    assert with_html == without_html
    assert destination.exists()
    assert "<!doctype html>" in destination.read_text(encoding="utf-8")


def test_html_with_no_path_lands_beside_the_bom(tmp_path, capsys):
    bom = tmp_path / "board.csv"
    bom.write_text(Path(FIXTURE).read_text(encoding="utf-8"), encoding="utf-8")

    main(["enrich", str(bom), "--html", "--no-open"])

    assert (tmp_path / "board_review.html").exists()
    assert "Report:" in capsys.readouterr().out


def test_a_report_that_cannot_be_written_does_not_hide_the_findings(
        tmp_path, capsys):
    """The review already ran. A read-only directory is a reason to print a
    line, not to report a clean BOM."""
    unwritable = tmp_path / "no-such-directory" / "report.html"

    code = main(["enrich", FIXTURE, "--html", str(unwritable), "--no-open"])
    captured = capsys.readouterr()

    assert code == main(["enrich", FIXTURE])
    assert "could not write" in captured.err
    assert "no manufacturer part number" in captured.out


# --------------------------------------------------------------------
# The windowed entry point
# --------------------------------------------------------------------

def test_a_path_on_the_command_line_skips_the_picker():
    """This is what makes dragging a BOM onto the icon work, so it is checked
    before any dialog code runs."""
    from helix_bom.desktop import choose_file

    assert choose_file([FIXTURE]) == Path(FIXTURE)
    assert choose_file(["does-not-exist.csv"]) is None


def test_the_window_and_the_command_line_produce_the_same_report(tmp_path):
    """Two implementations that drift is worse than one plain window. The
    desktop path must be the same review, not a second copy of it."""
    from helix_bom.desktop import review

    bom = tmp_path / "board.csv"
    bom.write_text(Path(FIXTURE).read_text(encoding="utf-8"), encoding="utf-8")

    destination = review(bom)
    report, ingest = _report(str(bom))

    assert destination == tmp_path / "board_review.html"
    written = destination.read_text(encoding="utf-8")
    assert written.count('class="finding ') == len(report.findings)


def test_an_unreadable_file_says_so_rather_than_raising(tmp_path):
    from helix_bom.desktop import review

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        review(empty)


# --------------------------------------------------------------------
# The drawn views, as they appear in the page
# --------------------------------------------------------------------

def test_the_report_carries_a_tab_for_every_view():
    report, ingest = _report()

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    for tab in ("cost", "lead", "risk", "fit", "findings", "lines", "file"):
        assert f'data-tab="{tab}"' in html


def test_a_view_that_cannot_be_drawn_says_so_in_the_page():
    """Not an empty frame. The enrich demo has no dimensions and no key, so
    two of the four must be visibly absent with a reason attached."""
    report, ingest = _report()

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert "Not drawn, and that is not a pass." in html
    assert "no component dimensions in this file" in html
    assert "distributor API key" in html


def test_the_cost_view_is_drawn_because_the_demo_has_prices():
    report, ingest = _report()

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert "Where the money goes" in html
    assert "Area is extended cost" in html


def test_one_part_can_be_lit_up_across_every_view():
    """Cross-highlighting is the whole reason the views are in one page rather
    than four files. Every element that represents a part carries the same
    key, and the match is exact -- a substring test once outlined the wrong
    component because one name contained another."""
    report, ingest = _report()

    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    assert "data-ref=" in html
    # Exactness is the property, not any particular line of script. A Map
    # keyed by the reference matches by equality; a substring search would
    # not, and once outlined the wrong component because "Battery" is inside
    # "Battery Pack 5000mAh". These forbid the substring forms outright.
    assert ".includes(" not in html
    assert ".indexOf(" not in html
    assert ".startsWith(" not in html
    assert "byRef" in html                            # the indexed exact lookup


def test_the_views_do_not_break_the_promise_the_page_makes():
    """Adding pictures must not add a fetch. Same check as the page-level one,
    run again now that three SVGs are embedded in it."""
    import re

    report, ingest = _report()
    html = build_html(report, ingest=ingest, source=Path(FIXTURE))

    for tag in re.findall(r"<(?:script|link|img|iframe|object|embed|image)[^>]*>",
                          html, re.IGNORECASE):
        assert "src=" not in tag.lower(), tag
        assert "href=" not in tag.lower(), tag
