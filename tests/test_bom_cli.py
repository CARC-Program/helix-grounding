"""
Tests for the command-line surface.

Exit codes get their own tests because a CLI that always exits 0 cannot be
used in a build, and a build gate is the most likely second use of this tool
after a human reads the output once.
"""

import json

import pytest

from helix_bom.cli import EXIT_FINDINGS, EXIT_OK, EXIT_UNREADABLE, main

PRICED = "tests/fixtures/altium_with_pricing.csv"
UNPRICED = "tests/fixtures/kicad_grouped.csv"


# --------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------

def test_a_budget_overrun_exits_nonzero():
    """The BOM totals $13.81 against a $10 budget."""
    assert main(["review", PRICED, "--budget", "10"]) == EXIT_FINDINGS


def test_a_bom_within_budget_exits_zero():
    assert main(["review", PRICED, "--budget", "100"]) == EXIT_OK


def test_an_unreadable_file_exits_two_not_one(tmp_path):
    """Distinguishing 'I found problems' from 'I could not read this' is the
    difference between a build failing for the right reason and the wrong
    one."""
    path = tmp_path / "readme.csv"
    path.write_text("just some prose\nnothing tabular here\n")

    assert main(["review", str(path)]) == EXIT_UNREADABLE


def test_a_missing_file_exits_two():
    assert main(["review", "definitely_not_here.csv"]) == EXIT_UNREADABLE


def test_strict_mode_fails_when_checks_could_not_run():
    """Without --strict an unpriced BOM exits 0: nothing was found wrong.
    With it, 'I could not check' is itself a failure — which is what you
    want gating a build."""
    assert main(["review", UNPRICED]) == EXIT_OK
    assert main(["review", UNPRICED, "--strict"]) == EXIT_FINDINGS


# --------------------------------------------------------------------
# What the human sees
# --------------------------------------------------------------------

def test_skipped_checks_are_stated_not_implied(capsys):
    main(["review", UNPRICED, "--budget", "50"])
    out = capsys.readouterr().out

    assert "NOT CHECKED" in out
    assert "These are not passes" in out


def test_the_preamble_skip_is_disclosed(capsys):
    """If the tool silently starts reading at line 6, the user should be
    told — that is a guess that could have gone wrong."""
    main(["review", UNPRICED])
    out = capsys.readouterr().out

    assert "Header found on line 6" in out
    assert "preamble line(s) skipped" in out


def test_column_mapping_is_shown_so_a_wrong_guess_is_visible(capsys):
    main(["review", PRICED, "--budget", "100"])
    out = capsys.readouterr().out

    assert "Unit Price" in out and "cost_usd" in out
    assert "Manufacturer Part Number" in out


def test_excluded_dnp_rows_are_disclosed(capsys):
    main(["review", PRICED, "--budget", "100"])
    out = capsys.readouterr().out

    assert "1 row(s) excluded as do-not-populate" in out


def test_ambiguous_column_matches_are_flagged_to_the_user(tmp_path, capsys):
    path = tmp_path / "ambiguous.csv"
    path.write_text("Part,Qty,Cost\nWidget,2,4.00\n")

    main(["review", str(path), "--budget", "100"])
    out = capsys.readouterr().out

    assert "[!]" in out
    assert "line total" in out


# --------------------------------------------------------------------
# JSON, for the machine reading this instead of a person
# --------------------------------------------------------------------

def test_json_output_is_valid_and_carries_the_skipped_checks(capsys):
    main(["review", UNPRICED, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["complete"] is False
    assert {s["name"] for s in payload["skipped_checks"]} >= {"budget", "physical fit"}
    assert payload["ingest"]["header_row"] == 6


def test_json_totals_match_the_file(capsys):
    main(["review", PRICED, "--budget", "10", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["totals"]["line_items"] == 5
    assert payload["totals"]["parts"] == 8
    assert payload["totals"]["cost_usd"] == pytest.approx(13.81)
    assert payload["over_budget"] is True


def test_json_records_every_unreadable_cell(tmp_path, capsys):
    path = tmp_path / "messy.csv"
    path.write_text("Description,Qty,Unit Price\nWidget,2,$4.00\nOdd,1,call us\n")

    main(["review", str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["ingest"]["problems"]) == 1
    assert payload["ingest"]["problems"][0]["value"] == "call us"


# --------------------------------------------------------------------
# Argument handling
# --------------------------------------------------------------------

@pytest.mark.parametrize("text", ["100x80x25", "100X80X25", "100*80*25"])
def test_enclosure_accepts_the_separators_people_actually_type(text):
    from helix_bom.cli import _parse_enclosure

    assert _parse_enclosure(text) == (100.0, 80.0, 25.0)


@pytest.mark.parametrize("bad", ["100x80", "100", "axbxc", ""])
def test_a_malformed_enclosure_is_rejected_with_an_example(bad):
    import argparse

    from helix_bom.cli import _parse_enclosure

    with pytest.raises(argparse.ArgumentTypeError, match="100x80x25|numbers in mm"):
        _parse_enclosure(bad)


def test_a_header_only_file_is_not_a_silent_empty_review(tmp_path, capsys):
    path = tmp_path / "headeronly.csv"
    path.write_text("Description,Qty,Unit Price\n")

    code = main(["review", str(path)])

    assert code == EXIT_UNREADABLE
    assert "no data rows" in capsys.readouterr().err


# --------------------------------------------------------------------
# The demo — first thing a new user runs
# --------------------------------------------------------------------

def test_demo_runs_with_no_arguments_at_all(capsys):
    """The gap between `pip install` and understanding what this does has to
    be one command with no homework. Somebody who has to go and find a CSV
    before seeing any output is somebody who closes the terminal."""
    code = main(["demo"])
    out = capsys.readouterr().out

    assert code == EXIT_FINDINGS          # the sample is deliberately over budget
    assert "BOM total: $15.08" in out
    assert "NOT CHECKED" in out


def test_demo_shows_all_three_outcomes_at_once(capsys):
    """A sample that only demonstrates success teaches nothing. This one has
    a finding, a supply-chain warning, and checks that cannot run."""
    main(["demo"])
    out = capsys.readouterr().out

    assert "[CRITICAL]" in out
    assert "lead time of 126 days" in out
    assert "physical fit" in out


def test_demo_points_the_user_at_their_own_file(capsys):
    main(["demo"])

    assert "your own BOM" in capsys.readouterr().out


def test_demo_supports_json_too(capsys):
    main(["demo", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["totals"]["line_items"] == 10
    assert payload["over_budget"] is True


def test_the_bundled_sample_actually_ships_inside_the_package():
    """A demo that depends on a file outside the installed package works on
    the developer's machine and nowhere else."""
    from helix_bom.cli import SAMPLE_BOM

    assert SAMPLE_BOM.is_file()
    assert "helix_bom" in SAMPLE_BOM.parts
