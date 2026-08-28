"""
Tests for the local agent.

Two things need proving and they pull in opposite directions.

The forbidden actions must be **impossible to register**, not merely refused at
run time -- the same structural move as `OpportunitySource` having no write
method. A policy in a docstring is a policy somebody edits at two in the
morning; a constructor that raises is not.

And the guard must not accuse correct work. Its first real use rejected the
task "release gate", which reads the working tree and sends nothing anywhere,
because "release" was in the outward list. That is the same fault as the value
detector calling a real Wurth part number a value, and it matters more here: a
guard that blocks legitimate tasks gets weakened by whoever hits it next, and
then it blocks nothing.
"""

from datetime import datetime, timezone

import pytest

from helix_auto.briefing import Action, Briefing, build
from helix_auto.levels import (
    FORBIDDEN,
    OUTWARD,
    Forbidden,
    Level,
    Task,
    describe_boundaries,
)
from helix_auto.signals import Confidence, Signal
from helix_auto.tasks import REGISTERED

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------
# What cannot be built
# --------------------------------------------------------------------

@pytest.mark.parametrize("name,description", [
    ("like recent posts", "like posts that mention BOM tools"),
    ("dislike competitors", "dislike rival announcements"),
    ("upvote our thread", "upvote the announcement"),
    ("downvote criticism", "downvote negative comments"),
    ("follow engineers", "follow accounts that post about PCBs"),
    ("unfollow inactive", "unfollow accounts that did not follow back"),
    ("make accounts", "create account on each forum"),
    ("signup sweep", "signup for every hardware forum"),
    ("bulk dm", "message every hardware engineer found"),
    ("mass message", "mass message the subreddit members"),
    ("repost weekly", "repost the announcement every week"),
    ("solve captcha", "captcha solving for signup"),
    ("bypass limits", "bypass the posting rate limit"),
    ("evade throttle", "evade the rate limit with delays"),
    ("scrape reddit", "scrape posts without using the API"),
    ("sock puppet", "operate a sock puppet account"),
    ("astroturf launch", "astroturf the launch discussion"),
])
def test_a_forbidden_task_cannot_be_constructed(name, description):
    """Refused at construction, on the machine of whoever wrote it, rather
    than at three in the morning on somebody's account."""
    with pytest.raises(Forbidden):
        Task(name=name, description=description, level=Level.APPROVE)


def test_the_refusal_says_which_word_and_why():
    """A refusal without a reason gets worked around. One with a reason gets
    understood, and the reason here is rarely ethics -- it is that the account
    gets banned from the only distribution this project has."""
    with pytest.raises(Forbidden, match="upvote"):
        Task(name="upvote", description="upvote the post", level=Level.APPROVE)
    try:
        Task(name="follow all", description="follow everyone", level=Level.APPROVE)
    except Forbidden as exc:
        assert "ban" in str(exc)


def test_raising_the_level_does_not_unlock_a_forbidden_action():
    """The gate is the action, not the permission. There is no level at which
    automated voting becomes acceptable, so every level must refuse it."""
    for level in (Level.AUTOMATIC, Level.NOTIFY, Level.APPROVE):
        with pytest.raises(Forbidden):
            Task(name="upvote posts", description="upvote", level=level)


# --------------------------------------------------------------------
# What cannot run unattended
# --------------------------------------------------------------------

@pytest.mark.parametrize("name,description", [
    ("publish to pypi", "publish the built artifacts"),
    ("post announcement", "post the draft to the forum"),
    ("reply to comments", "reply to everyone in the thread"),
    ("send emails", "send the announcement by email"),
    ("pay for ads", "pay the advertising invoice"),
])
def test_an_outward_task_cannot_be_automatic(name, description):
    """The "never silently upgrade" rule, enforced where the level is chosen.

    Anything reaching a person who did not ask for it waits for a human, every
    time -- not once at setup.
    """
    with pytest.raises(Forbidden, match="AUTOMATIC"):
        Task(name=name, description=description, level=Level.AUTOMATIC)
    # ... and the same task is fine when it waits for somebody.
    assert Task(name=name, description=description, level=Level.APPROVE)


def test_a_read_only_task_is_not_mistaken_for_an_outward_one():
    """The false positive that made this list shorter.

    "release gate" reads the working tree, the history and the built artifacts
    and sends nothing anywhere. The guard rejected it because "release" was in
    the outward list -- catching the check along with the thing checked. The
    alternative was renaming the task to get past the guard, which teaches the
    next person to word around it rather than fix it.
    """
    assert Task(name="release gate",
                description="Run every pre-flight check over the working tree, "
                            "the history and the built artifacts.",
                level=Level.AUTOMATIC)
    assert "release" not in OUTWARD


def test_publishing_is_still_caught_after_that_narrowing():
    """The other half. Narrowing the list must not have opened the door."""
    with pytest.raises(Forbidden):
        Task(name="ship it", description="publish the release to PyPI",
             level=Level.AUTOMATIC)
    with pytest.raises(Forbidden):
        Task(name="ship it", description="upload the wheel",
             level=Level.AUTOMATIC)


def test_needs_a_person_is_true_for_everything_above_automatic():
    read = Task(name="count things", description="count local things",
                level=Level.AUTOMATIC)
    write = Task(name="post it", description="post the draft", level=Level.APPROVE)
    assert read.needs_a_person is False
    assert write.needs_a_person is True


# --------------------------------------------------------------------
# The registered set
# --------------------------------------------------------------------

def test_no_registered_task_that_reaches_anybody_can_fire_by_itself():
    """The whole safety property, asserted over the real registry rather than
    over a fixture: anything above Level 1 must have no runnable body, so the
    scheduler has nothing to call even if it tried."""
    for task in REGISTERED:
        if task.needs_a_person:
            assert task.run is None, f"{task.name} could be fired unattended"


def test_every_registered_task_survives_its_own_guard():
    """Importing the registry constructs every task, so this passing at all
    means none of them describes something forbidden. Stated explicitly so the
    guarantee is visible rather than incidental."""
    assert REGISTERED
    assert all(isinstance(task, Task) for task in REGISTERED)


def test_the_boundaries_can_be_printed_at_somebody():
    text = describe_boundaries()
    assert "will not be built at all" in text
    for fragment in ("voting", "following", "account farming", "spam"):
        assert fragment in text
    assert len(FORBIDDEN) >= 15


# --------------------------------------------------------------------
# The briefing
# --------------------------------------------------------------------

def _signal(name, value, confidence=Confidence.HARD, error=""):
    return Signal(name=name, value=value, confidence=confidence, error=error)


def test_a_quiet_day_says_so_first_and_invents_nothing():
    """A briefing that manufactures a task every morning to justify itself gets
    ignored within a fortnight, and then it is worse than nothing."""
    quiet = Briefing(when=NOW, signals=[_signal("github open issues", 0)])
    text = quiet.render()
    assert "Nothing needs you today." in text
    assert quiet.needs_attention is False
    assert text.index("Nothing needs you") < text.index("what a person")


def test_hard_evidence_is_printed_above_noise():
    """One person opening an issue outranks four hundred downloads, because the
    downloads are machines. A briefing led by the big number would be pleasant
    and false every morning."""
    report = Briefing(when=NOW, signals=[
        _signal("pypi downloads", "421/month", Confidence.NOISE),
        _signal("github open issues", 2, Confidence.HARD),
    ])
    text = report.render()
    assert text.index("github open issues") < text.index("pypi downloads")


def test_an_unreadable_source_is_never_printed_as_zero():
    """"Could not read pypistats" and "nobody downloaded it" are different
    facts. This whole codebase is built on not conflating them."""
    report = Briefing(when=NOW, signals=[],
                      unavailable=[_signal("pypi downloads", None,
                                           Confidence.NOISE,
                                           error="pypistats did not answer")])
    text = report.render()
    assert "not the same as zero" in text
    assert "pypistats did not answer" in text


def test_an_action_says_what_it_is_for_and_how_long():
    action = Action("Post to one channel.", "Zero strangers have run it.", 45)
    line = action.line()
    assert "45 min" in line and "Zero strangers" in line


def test_the_briefing_reads_the_real_project_without_crashing():
    """It runs against live sources, so it must degrade rather than fail. A
    scheduled job that raises at 6am is a job somebody deletes."""
    report = build()
    text = report.render()
    assert "Helix briefing" in text
    assert isinstance(report.needs_attention, bool)


def test_nothing_in_this_package_can_post():
    """The structural claim, asserted over the modules rather than trusted.
    A method that does not exist cannot be called by an agent improvising."""
    import helix_auto
    from helix_auto import briefing, cli, levels, signals, tasks

    forbidden = {"post", "publish", "comment", "reply", "vote", "upvote",
                 "downvote", "like", "follow", "send", "dm"}
    for module in (helix_auto, briefing, cli, levels, signals, tasks):
        for name in dir(module):
            if name.startswith("_"):
                continue
            assert name.lower() not in forbidden, \
                f"{module.__name__} grew {name}()"
