"""
Tests for the answer reader.

The module exists because a group of questions that all report "answered" is not
a solved problem, and this suite exists because the first version of the reader
said it was measuring one thing while measuring another.

Two claims need pinning here, and both are corrections rather than features:

**What Stack Exchange means by answered.** Not "has an accepted answer". The
field is true when a question has an accepted answer *or* an answer scoring one
or more. Eight questions all reported answered while five had anything accepted,
and a document was written on the wrong reading of that before anyone checked.

**What the classifier does to a manufacturing group.** "By hand" means writing
code in one context and holding a soldering iron in another, and a bucket named
"hands back a scripting job" that fires on hand-soldering is worse than no
bucket at all.
"""

import pytest

from helix_signal.answers import (
    BUCKETS,
    SCRIPT_WORK,
    Reading,
    read_answer,
    summarise,
    tally,
)
from helix_signal.score import _found


def _answer(body, accepted=False, score=1, aid="1", qid="100") -> dict:
    return {"answer_id": aid, "question_id": qid, "body": body,
            "score": score, "is_accepted": accepted,
            "url": f"https://example.com/a/{aid}", "content_license": "CC BY-SA 4.0"}


# --------------------------------------------------------------------
# What the buckets catch
# --------------------------------------------------------------------

def test_an_answer_telling_you_to_write_code_is_labelled_as_such():
    """The finding this module was built to detect: the answer acknowledges the
    problem and hands the work back."""
    reading = read_answer(_answer(
        "There is no option for this. You could write a ULP script to "
        "post-process the export."))
    assert reading.label == "hands back a scripting job"
    assert "ulp" in reading.evidence or "script" in reading.evidence


def test_an_answer_pointing_at_a_feature_is_not_confused_with_one():
    reading = read_answer(_answer(
        "There is an option for it. Open the export dialog, tick the checkbox "
        "and select the template you want."))
    assert reading.label == "points at a built-in feature"


def test_an_answer_naming_a_different_program_is_labelled_as_such():
    reading = read_answer(_answer(
        "KiCost does this. It is a third-party plugin that reads your BOM."))
    assert reading.label == "points at another tool"


def test_an_answer_saying_it_is_impossible_is_labelled_as_such():
    reading = read_answer(_answer(
        "It is not possible. The format does not support that field."))
    assert reading.label == "says it cannot be done"


def test_an_answer_matching_nothing_is_unclear_rather_than_forced():
    """A bucket assigned by default would make every count meaningless."""
    assert read_answer(_answer("Yes, that is correct.")).label == "unclear"


# --------------------------------------------------------------------
# The correction
# --------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "About 90% is surface mount, so the through-hole parts could be soldered by hand.",
    "Is there a best practice for manually dealing with such reels?",
    "I know Sparkfun say they do this sort of work by hand, but I have 90 parts.",
    "Is there a better estimate except counting manually?",
])
def test_physical_handwork_is_not_mistaken_for_a_scripting_job(body):
    """Every one of these is real text from the pick-and-place group, and every
    one of them was labelled "hands back a scripting job" by the first version
    of this classifier, because "manually" and "by hand" were in the list.

    They are people holding a soldering iron and counting parts off a reel. No
    program removes that work. A bucket about being told to write code has no
    business firing on it, and 58% of that group's accepted answers were
    reported as scripting jobs on the strength of it."""
    assert read_answer(_answer(body)).label != "hands back a scripting job"


def test_the_scripting_bucket_holds_no_word_about_physical_work():
    for word in ("manually", "by hand", "one by one", "tedious"):
        assert word not in SCRIPT_WORK, f"{word!r} is back in SCRIPT_WORK"


def test_a_genuine_scripting_answer_from_the_same_group_still_lands():
    """The other side of the correction. Removing the physical-work words must
    not stop the classifier finding what it is for -- this is the real accepted
    answer to an Eagle pick-and-place export question."""
    reading = read_answer(_answer(
        "Find the file mountsmd_mil.ulp in your system. Open it with a text "
        "editor. Change all references to u2mm to u2mil. Save the file."))
    assert reading.label == "hands back a scripting job"


# --------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------

def test_the_summary_says_it_is_an_index_rather_than_a_finding():
    """Three times in this project a small measurement has been reported as a
    conclusion. The instrument now says what it is on every printing."""
    text = summarise([read_answer(_answer("write a python script"))])
    assert "not a finding" in text
    assert "Read the answers" in text


def test_accepted_answers_are_counted_separately():
    """What the accepted answer says is a different question from what the
    thread says. A thread can contain a scripting workaround and still have a
    real feature accepted at the top."""
    readings = [
        read_answer(_answer("you could write a script", accepted=False, aid="1")),
        read_answer(_answer("open the export dialog and tick the checkbox",
                            accepted=True, aid="2")),
    ]
    text = summarise(readings)
    assert "among the accepted answers only" in text
    assert tally([r for r in readings if r.is_accepted]) == {
        "points at a built-in feature": 1}


def test_every_reading_carries_the_link_that_attributes_it():
    """CC BY-SA is satisfied by the link, and the link is the only way a reader
    can check a label they doubt."""
    reading = read_answer(_answer("write a script"))
    assert reading.url.startswith("https://")
    assert reading.words > 0


def test_an_empty_set_of_answers_summarises_without_dividing_by_zero():
    assert "0 answers" in summarise([])


def test_the_bucket_order_puts_work_above_features():
    """A tie goes to the earlier bucket. An answer saying "there is a template,
    but you will need a script to fill it" is describing work, not a feature."""
    labels = [label for label, _ in BUCKETS]
    assert labels.index("hands back a scripting job") < \
        labels.index("points at a built-in feature")
