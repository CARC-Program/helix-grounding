"""
Tests for the operations module.

The reason these matter more than their size suggests: `helix_ops` writes the
text a stranger reads first. Everything else in this repository fails
privately — a bad review is seen by one person who can be told. A launch post
that claims a version the package does not have fails in public, permanently,
to the audience the whole project has been built to reach.

So the load-bearing test here is `test_a_wrong_number_is_caught`. If the
grounding check ever silently stops checking, every other test in this file
passes and the feature is worse than not existing.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from helix_ops import campaign as campaign_module
from helix_ops import drafts
from helix_ops.campaign import Campaign
from helix_ops.cli import main
from helix_ops.facts import REPO_ROOT, gather, measure_tests

FACTS = gather()
MEASURED = replace(FACTS, tests_passing=255)


# --------------------------------------------------------------------
# Facts — every one of them is quotable in public
# --------------------------------------------------------------------

def test_the_version_comes_from_pyproject():
    declared = re.search(r'^version\s*=\s*"([^"]+)"',
                         (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                         re.MULTILINE).group(1)
    assert FACTS.version == declared


def test_the_library_version_matches_the_package_version():
    """These drifted apart once: the wheel shipped as 0.1.1 while
    `helix_grounding.__version__` still said 0.1.0, so anyone reading it
    programmatically got the wrong answer and had no way to know."""
    import helix_grounding
    assert helix_grounding.__version__ == FACTS.version


def test_the_declared_commands_match_the_actual_parser():
    """`COMMANDS` exists so a launch post can quote the CLI without reaching
    into argparse internals. That is only safe while the two agree."""
    from helix_bom.cli import COMMANDS, build_parser  # noqa: F401
    parser = build_parser()
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    subcommands = set(actions[0].choices)
    assert subcommands == set(COMMANDS)


def test_runtime_dependencies_excludes_the_optional_groups():
    """'Zero runtime dependencies' is the library's central claim. If this
    counted the `llm` extras it would report 3, and a reader checking the
    claim would find the sentence false."""
    assert FACTS.runtime_dependencies == 0


def test_an_unmeasured_test_count_is_none_not_a_guess():
    """The same rule the review agent follows about an unrun check, applied to
    the one number most likely to be quoted from memory."""
    assert gather(run_tests=False).tests_passing is None


def test_measuring_actually_runs_the_suite(tmp_path):
    probe = tmp_path / "test_probe.py"
    probe.write_text("def test_one(): assert True\ndef test_two(): assert True\n")
    assert measure_tests(REPO_ROOT, [str(probe), "-p", "no:cacheprovider"]) == 2


def test_a_failing_suite_refuses_to_produce_a_number(tmp_path):
    """Nothing should be posted about a project whose tests are failing, and
    the way to guarantee that is to make the number unavailable rather than
    to rely on remembering."""
    probe = tmp_path / "test_broken.py"
    probe.write_text("def test_one(): assert False\n")
    with pytest.raises(RuntimeError, match="did not pass"):
        measure_tests(REPO_ROOT, [str(probe), "-p", "no:cacheprovider"])


# --------------------------------------------------------------------
# Drafts
# --------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(drafts.BY_KEY))
def test_every_draft_renders_and_is_grounded(key):
    text = drafts.render(key, MEASURED)
    assert text.strip()
    report = drafts.verify(text, MEASURED)
    assert report.is_grounded, report.summary()


@pytest.mark.parametrize("key", sorted(drafts.BY_KEY))
def test_no_draft_hardcodes_the_version_or_install_command(key):
    """A stored number is a number that goes stale silently."""
    text = drafts.render(key, MEASURED)
    if MEASURED.version in text:
        assert MEASURED.package in text
    assert "pip install helix-grounding" in text or "install" not in text.lower()


def test_a_draft_that_states_a_test_count_refuses_without_a_measurement():
    with pytest.raises(drafts.DraftError, match="not run"):
        drafts.render("show_hn", FACTS)


def test_a_wrong_number_is_caught():
    """The load-bearing test. Corrupt exactly one figure and the check must
    reject the post; if this ever passes vacuously, the whole module is
    theatre."""
    text = drafts.render("show_hn", MEASURED).replace("255 tests", "300 tests")
    report = drafts.verify(text, MEASURED)
    assert not report.is_grounded
    assert any(claim.value == 300 for claim in report.ungrounded)


def test_the_check_is_not_vacuous():
    """A grounding report of '0 ungrounded' over 0 extracted claims is true
    and meaningless. At least one real draft has to produce real claims, or
    the reassurance above is measuring nothing."""
    report = drafts.verify(drafts.render("show_hn", MEASURED), MEASURED)
    assert report.checked_count >= 5


@pytest.mark.parametrize("text,expected", [
    ("net U1 and Pad7 on R3", []),          # digits inside identifiers
    ("0.94 faithfulness", []),              # both halves of a decimal
    ("version 0.1.1 shipped", []),          # a version string
    ("255 tests pass", [255.0]),            # the case that matters
    ("0 runtime dependencies", [0.0]),
])
def test_the_count_extractor_reads_only_bare_integers(text, expected):
    found = [claim.value for claim in drafts.CountExtractor().extract(text)]
    assert found == expected


def test_a_fabricated_currency_amount_is_caught():
    """The stock extractor's job, confirmed to still be wired in after the
    custom one was added alongside it."""
    text = drafts.render("show_hn", MEASURED).replace("$3.20", "$9.99")
    assert not drafts.verify(text, MEASURED).is_grounded


# --------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return tmp_path / "campaign.json"


def test_a_campaign_round_trips(store):
    original = Campaign()
    original.mark_prerequisite("repo_public")
    original.mark_posted("reddit_pcb", "https://example.com/post", on="2026-08-20")
    original.record_response("reddit_pcb", "bug", "misread a semicolon file",
                             ran_it=True, on="2026-08-21")
    original.save(store)

    loaded = Campaign.load(store)
    assert loaded.prerequisites["repo_public"] is True
    assert loaded.posts["reddit_pcb"].url == "https://example.com/post"
    assert loaded.strangers_who_ran_it == 1
    assert len(loaded.open_bugs()) == 1


def test_prerequisites_block_every_channel(store):
    assert "Not ready to post" in Campaign().next_action()


def _ready() -> Campaign:
    campaign = Campaign()
    for key in campaign_module.PREREQUISITES:
        campaign.mark_prerequisite(key)
    return campaign


def test_one_channel_at_a_time(store):
    """FIRST_USERS.md: post in one place, fix what it finds, then post again.
    Five posts in a day is a spam pattern. Holding that as a rule in a
    document means nobody is held to it."""
    campaign = _ready()
    campaign.mark_posted("reddit_pcb", "https://example.com/1", on="2026-08-20")
    campaign.record_response("reddit_pcb", "bug", "misread a file",
                             ran_it=True, on="2026-08-21")

    assert "Fix the bug" in campaign.next_action()
    assert "Show HN" not in campaign.next_action()

    campaign.resolve("reddit_pcb", 0, "fixed in 0.1.2 with a test")
    assert "Show HN" in campaign.next_action()


def test_show_hn_is_announced_as_one_shot():
    campaign = _ready()
    campaign.mark_posted("reddit_pcb", "https://example.com/1", on="2026-08-20")
    assert "one-shot" in campaign.next_action()


def test_a_response_to_an_unposted_channel_is_refused():
    """A record of feedback on a post that was never made is a record of
    something that did not happen, and this file is the project's memory."""
    with pytest.raises(ValueError, match="not posted yet"):
        _ready().record_response("show_hn", "bug", "x", ran_it=True)


def test_only_people_who_ran_it_count_towards_the_milestone():
    """Upvotes, views and encouraging comments are proxies. ROADMAP.md closes
    a milestone on a real person doing something they did not do before."""
    campaign = _ready()
    campaign.mark_posted("reddit_pcb", "https://example.com/1", on="2026-08-20")
    campaign.record_response("reddit_pcb", "question", "nice idea, what about Eagle?",
                             ran_it=False, on="2026-08-21")
    campaign.record_response("reddit_pcb", "ran_nothing_found", "ran clean",
                             ran_it=True, on="2026-08-21")
    assert campaign.strangers_who_ran_it == 1


def test_three_feature_requests_are_marked_as_a_signal():
    campaign = _ready()
    campaign.mark_posted("reddit_pcb", "https://example.com/1", on="2026-08-20")
    for _ in range(3):
        campaign.record_response("reddit_pcb", "feature", "support Eagle exports",
                                 ran_it=False, on="2026-08-21")
    assert campaign.feature_requests()["support Eagle exports"] == 3
    assert "three is a signal" in campaign.milestone_status()


def test_a_channel_added_later_appears_in_an_older_record(store):
    """The store is JSON on disk and outlives the code that wrote it. A new
    channel that does not appear in a loaded file is a channel invisible to
    every report."""
    store.write_text(json.dumps({"prerequisites": {}, "posts": {}}), encoding="utf-8")
    loaded = Campaign.load(store)
    assert set(loaded.posts) == set(drafts.BY_KEY)


# --------------------------------------------------------------------
# The console
# --------------------------------------------------------------------

def test_facts_command_runs(capsys):
    assert main(["facts"]) == 0
    assert "helix-grounding" in capsys.readouterr().out


def test_draft_command_refuses_an_unmeasured_test_count(capsys):
    assert main(["draft", "show_hn"]) == 1
    assert "not run" in capsys.readouterr().err


def test_check_command_rejects_a_tampered_draft(tmp_path, capsys):
    path = tmp_path / "post.md"
    path.write_text(drafts.render("reddit_pcb", FACTS).replace("--budget 50",
                                                               "--budget 9999"),
                    encoding="utf-8")
    assert main(["check", str(path)]) == 1
    assert "UNGROUNDED" in capsys.readouterr().err


def test_status_reports_position_and_one_next_action(store, capsys):
    assert main(["--store", str(store), "status"]) == 0
    out = capsys.readouterr().out
    assert "strangers who ran it" in out
    assert out.count("next:") == 1


def test_ops_and_api_stay_out_of_the_published_wheel():
    """`helix_ops` runs this business, not the user's board. Nobody installing
    a verification library should receive a launch tracker, and nobody should
    receive an undeployed API skeleton either. Checked against the config
    rather than by building, so it runs in the normal suite."""
    packages = re.search(r'\[tool\.hatch\.build\.targets\.wheel\].*?packages\s*=\s*\[(.*?)\]',
                         (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                         re.DOTALL).group(1)
    assert "helix_ops" not in packages
    assert "helix_api" not in packages
    assert "helix_grounding" in packages
