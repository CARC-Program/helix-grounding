"""
The CLI must not die on a console that cannot encode an em dash.

This is here because it actually happened, and it happened in the worst
possible place. `helix-bom demo` is the first command in the README — the one a
stranger runs before deciding whether the tool is worth more of their time —
and on a cp437 or cp850 console it raised UnicodeEncodeError and printed a
traceback instead of a report. Both are ordinary Windows console defaults.

Nothing in the code review would have found it. Every test ran under pytest's
captured UTF-8 streams, and every manual run happened on a UTF-8 terminal. It
took installing the published package and running it on a console configured
the way somebody else's machine is configured.

The fix transliterates rather than dropping: an em dash becomes "--", which
carries the meaning, instead of "?", which does not. These tests run the CLI as
a subprocess with PYTHONIOENCODING set, because that is the only way to
reproduce a real console — in-process capture replaces the stream and hides the
entire problem.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from helix_bom.cli import ASCII_FALLBACKS, _console_safe

REPO_ROOT = Path(__file__).parent.parent
LEGACY_ENCODINGS = ["cp437", "cp850", "ascii", "latin-1"]


def _run(args, encoding):
    return subprocess.run(
        [sys.executable, "-m", "helix_bom.cli", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        # Decode with the same codec the child was told to encode with.
        # Without this the parent decodes UTF-8 bytes as cp1252 and the test
        # fails on mojibake it introduced itself.
        encoding=encoding, errors="replace",
        env={**dict(__import__("os").environ),
             "PYTHONIOENCODING": encoding,
             "PYTHONPATH": str(REPO_ROOT / "src")},
    )


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_the_demo_does_not_crash_on_a_legacy_console(encoding):
    """The load-bearing one. If this fails, the first thing a new user sees is
    a stack trace."""
    result = _run(["demo"], encoding)
    assert "Traceback" not in result.stderr, result.stderr[:400]
    assert "UnicodeEncodeError" not in result.stderr
    assert "BOM review" in result.stdout


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_a_netlist_review_does_not_crash_on_a_legacy_console(encoding):
    result = _run(["review", "tests/fixtures/sensor_board.net"], encoding)
    assert "Traceback" not in result.stderr, result.stderr[:400]
    assert "Netlist review" in result.stdout


def test_the_em_dash_degrades_to_something_that_still_reads():
    """'--' carries the meaning of an em dash. '?' does not, and a report full
    of question marks reads as corrupted output rather than as a tool coping
    with an old terminal."""
    result = _run(["demo"], "cp437")
    assert "BOM review -- sample_bom.csv" in result.stdout
    assert "�" not in result.stdout
    assert "?" not in result.stdout.split("\n")[3]


def test_utf8_output_is_left_exactly_alone():
    """The fallback must not fire on a console that was fine. Punishing every
    modern terminal to accommodate an old one is the wrong trade."""
    result = _run(["demo"], "utf-8")
    assert "BOM review — sample_bom.csv" in result.stdout


@pytest.mark.parametrize("char", sorted(ASCII_FALLBACKS))
def test_every_declared_fallback_is_pure_ascii(char):
    """A fallback that is itself unencodable would move the crash rather than
    fix it."""
    ASCII_FALLBACKS[char].encode("ascii")


def test_json_output_stays_parseable_on_a_legacy_console():
    """Machine output is the whole of stdout or it is not machine output, and
    that rule does not get suspended because the terminal is old."""
    import json
    result = _run(["review", "tests/fixtures/altium_with_pricing.csv", "--json"], "cp437")
    assert "Traceback" not in result.stderr, result.stderr[:400]
    json.loads(result.stdout)


class _FakeStream:
    def __init__(self, encoding):
        self.encoding = encoding


def test_console_safe_handles_a_stream_with_no_encoding_attribute():
    """A redirected or wrapped stream can report None. Defaulting to UTF-8 is
    right, and crashing on a missing attribute would be absurd in the one
    function whose entire job is not crashing."""
    assert _console_safe("a — b", _FakeStream(None)) == "a — b"


def test_console_safe_survives_an_unknown_encoding_name():
    assert "--" in _console_safe("a — b", _FakeStream("not-a-real-codec"))
