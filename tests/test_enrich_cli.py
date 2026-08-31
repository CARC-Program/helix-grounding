"""
Tests for `helix-bom enrich` as a command.

Every test here runs against the offline catalogue or a stub, never the network.
Two of them are about secrets rather than behaviour: an API key that reaches
stdout ends up in a screenshot or a pasted bug report, and the command that
exists to help somebody debug their credentials is the likeliest place for that
to happen.
"""

import json
from pathlib import Path

import pytest

from helix_bom.cli import COMMANDS, build_parser, main
from helix_bom.enrich_cli import EXIT_OK, EXIT_PROBLEMS, EXIT_UNUSABLE, run_enrich

DEMO = str(Path(__file__).parent.parent / "src" / "helix_bom" / "examples"
           / "enrich_demo.csv")
SAMPLE = str(Path(__file__).parent.parent / "src" / "helix_bom" / "examples"
             / "sample_bom.csv")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Never touch the real user cache from a test, and never let one test's
    cached answers decide another's result."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_SECRET", raising=False)


def _args(**kw):
    defaults = dict(file=None, offline=True, compare=False, fresh=False,
                    cache_ttl=None, clear_cache=False, check_key=False,
                    json=False, strict=False)
    defaults.update(kw)
    return type("Args", (), defaults)()


# --------------------------------------------------------------------
# The command exists and is advertised
# --------------------------------------------------------------------

def test_enrich_is_in_the_public_command_list():
    """helix_ops quotes COMMANDS in launch posts. A command that works but is
    not listed does not exist as far as anybody reading is concerned."""
    assert "enrich" in COMMANDS
    actions = [a for a in build_parser()._actions if hasattr(a, "choices")
               and a.choices]
    assert "enrich" in set(actions[0].choices)


# --------------------------------------------------------------------
# Running it
# --------------------------------------------------------------------

def test_the_demo_file_shows_every_check_firing(capsys):
    """The bundled example is built so one run demonstrates the whole feature:
    an obsolete part, an NRND part sold only by the reel, a near-match that is
    not a match, a price that is wrong at the quantity, and a line with no part
    number at all."""
    code = main(["enrich", "--offline", DEMO])
    text = capsys.readouterr().out
    assert code == EXIT_PROBLEMS          # the obsolete part is critical
    assert "the part is obsolete" in text
    assert "not recommended for new designs" in text
    assert "below the minimum order quantity" in text
    assert "no exact match" in text
    assert "the BOM price is under" in text
    assert "carry no part number of any kind" in text


def test_offline_output_leads_with_the_warning_that_it_is_invented(capsys):
    main(["enrich", "--offline", DEMO])
    assert capsys.readouterr().out.lstrip().startswith("!! OFFLINE DEMONSTRATION DATA")


def test_a_real_bom_against_the_demo_catalogue_reports_not_checked(capsys):
    """The bug this catches: six invented parts announcing that STM32F401RET6
    does not exist. Every line the catalogue does not hold must come back as
    "not looked up", never as a critical finding."""
    main(["enrich", "--offline", SAMPLE])
    text = capsys.readouterr().out
    assert "NOT CHECKED" in text
    assert "no distributor asked has this part number" not in text


def test_json_output_is_the_whole_of_stdout(capsys):
    """Machine output is the whole of stdout or it is not machine output --
    the same rule the demo banner had to learn."""
    main(["enrich", "--offline", "--json", DEMO])
    payload = json.loads(capsys.readouterr().out)
    assert payload["offline_data_used"] is True
    assert payload["complete"] is False
    assert len(payload["lines"]) == 7
    assert any(line["lifecycle"] == "obsolete" for line in payload["lines"])


def test_strict_fails_when_a_line_could_not_be_checked(capsys):
    assert run_enrich(_args(file=Path(SAMPLE), strict=True)) == EXIT_PROBLEMS


def test_a_clean_bom_exits_zero(capsys, tmp_path):
    good = tmp_path / "good.csv"
    good.write_text(
        "Designator;Description;Quantity;Manufacturer Part Number;Unit Price\n"
        "C1;cap;1;GRM188R71H104KA93D;$0.22\n", encoding="utf-8")
    assert main(["enrich", "--offline", str(good)]) == EXIT_OK
    assert "Nothing wrong found" in capsys.readouterr().out


def test_a_missing_file_exits_two(capsys):
    assert main(["enrich", "--offline", "nope.csv"]) == EXIT_UNUSABLE
    assert "no such file" in capsys.readouterr().err


def test_no_file_and_no_action_says_what_to_do(capsys):
    assert run_enrich(_args()) == EXIT_UNUSABLE
    assert "--check-key" in capsys.readouterr().err


def test_an_unparseable_file_points_at_diagnose(capsys, tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("nothing at all\n", encoding="utf-8")
    assert run_enrich(_args(file=empty)) == EXIT_UNUSABLE
    assert "diagnose" in capsys.readouterr().err


# --------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------

def test_a_second_run_is_served_from_the_cache(capsys):
    main(["enrich", "--offline", DEMO])
    capsys.readouterr()
    main(["enrich", "--offline", DEMO])
    assert "from cache" in capsys.readouterr().out


def test_clear_cache_empties_it_and_says_how_many(capsys):
    main(["enrich", "--offline", DEMO])
    capsys.readouterr()
    assert main(["enrich", "--offline", "--clear-cache"]) == EXIT_OK
    assert "cleared" in capsys.readouterr().out


# --------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------

def test_check_key_reports_presence_and_never_the_value(capsys):
    """The command most likely to have its output pasted into a bug report."""
    environment = {"MOUSER_API_KEY": "SUPERSECRET123",
                   "DIGIKEY_CLIENT_ID": "CLIENTID456"}
    run_enrich(_args(check_key=True, offline=True), environment=environment)
    text = capsys.readouterr().out
    assert "MOUSER_API_KEY" in text and "set" in text
    assert "SUPERSECRET123" not in text
    assert "CLIENTID456" not in text


def test_check_key_with_nothing_configured_says_which_to_set(capsys):
    code = run_enrich(_args(check_key=True, offline=False), environment={})
    text = capsys.readouterr().out
    assert code == EXIT_UNUSABLE
    assert "MOUSER_API_KEY" in text
    assert "not set" in text


def test_check_key_offline_proves_the_probe_part_is_in_the_catalogue(capsys):
    """If the probe part is ever removed from the demo catalogue, --check-key
    --offline silently stops proving anything. This is the tripwire."""
    code = run_enrich(_args(check_key=True, offline=True), environment={})
    text = capsys.readouterr().out
    assert code == EXIT_OK
    assert "MATCHED" in text


def test_the_demo_is_useful_with_no_key_at_all(capsys):
    """What a stranger sees. 0.2.0 gave them ten lines of "not checked" and
    nothing else -- a headline feature behind a door most people will not open,
    in a project whose first-user strategy is that a stranger installs it and
    reports a bug.

    Structural checks need no key, no network and no account, so this must
    produce real findings."""
    code = main(["enrich", DEMO])          # no --offline, no credentials
    text = capsys.readouterr().out
    assert code == EXIT_PROBLEMS           # the missing part number is critical
    assert "no manufacturer part number" in text
    assert "designator(s) but a quantity of" in text
    assert "finding(s):" in text


def test_a_run_with_no_key_never_claims_the_parts_were_checked(capsys):
    """The other half. Useful findings must not be mistaken for a clean bill on
    the parts themselves."""
    main(["enrich", DEMO])
    text = capsys.readouterr().out
    assert "NOT CHECKED" in text
    assert "no distributor asked has this part number" not in text
