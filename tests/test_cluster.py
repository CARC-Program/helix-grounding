"""
Tests for the clusterer.

Two things need proving here and they are different in kind.

The first is that the mechanism does what it says: similar questions meet,
dissimilar ones do not, the same corpus produces the same groups every time.

The second is that the *ranking* is not nonsense, and that is the one that
matters. The first ranking this module produced put six groups of four
questions above a group of a hundred and thirty-seven, because each of the small
ones had won a percentage computed from three questions. Nothing was broken. The
arithmetic was right. It was simply a confident number that meant nothing, which
is the failure mode this whole project exists to argue against, so the test that
catches it is written out below in the terms of the mistake.
"""

from datetime import datetime, timedelta, timezone

import pytest

from helix_signal.cluster import (
    BODY_WEIGHT,
    TITLE_WEIGHT,
    Baselines,
    baselines_for,
    build_vocabulary,
    cluster_items,
    cosine,
    measure,
    terms_of,
    tokenise,
    vectorise,
)
from helix_signal.sources.base import SourceItem

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _item(number, title, body="", tags=(), answered=False, answers=0,
          age_days=100, score=1) -> SourceItem:
    return SourceItem(
        source="test:site",
        external_id=str(number),
        title=title,
        body=body,
        url=f"https://example.com/{number}",
        created_at=NOW - timedelta(days=age_days),
        tags=tuple(tags),
        engagement_score=score,
        answer_count=answers,
        is_answered=answered,
        content_license="CC BY-SA 4.0",
    )


def _family(prefix, subject, count, start=0, **kw):
    """A group of questions that are genuinely about the same thing."""
    return [_item(f"{prefix}{start + i}",
                  f"How do I fix the {subject} in my project number {start + i}",
                  body=f"The {subject} keeps going wrong when I export.",
                  **kw)
            for i in range(count)]


# A synthetic corpus of twenty questions in two subjects has each subject's
# words in half of it, and the real max_df of 20% would correctly delete every
# term that could group anything -- leaving empty vectors and no clusters. That
# filter is right for ten thousand real questions and meaningless for twenty
# fabricated ones, so these tests set bounds that suit their own corpus. The
# real defaults are exercised against the real corpus, not here.
SMALL = dict(min_df=2, max_df_ratio=0.75)


def _group(items, threshold=0.30, min_size=3, **kw):
    settings = dict(SMALL, **kw)
    return cluster_items(items, threshold=threshold, min_size=min_size, **settings)


# --------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------

def test_stopwords_and_bare_numbers_are_dropped():
    assert tokenise("How do I use the 42 footprint") == ["footprint"]


def test_short_domain_words_survive_the_length_filter():
    """A three-character floor would delete most of this field's vocabulary."""
    assert "bom" in tokenise("the bom is wrong")
    assert "drc" in tokenise("drc errors everywhere")
    assert "xy" not in tokenise("the xy thing")


def test_tags_outweigh_titles_which_outweigh_bodies():
    """A tag was chosen by a person who read the question; a title is a summary;
    a body is a transcript. The weights say so."""
    tagged = terms_of(_item(1, "kicad", body="", tags=("kicad",)))
    assert tagged["tag:kicad"] > tagged["kicad"]
    titled = terms_of(_item(2, "netlist", body="netlist", tags=()))
    assert titled["netlist"] == pytest.approx(TITLE_WEIGHT + BODY_WEIGHT)


def test_a_term_nobody_else_uses_is_dropped_as_unusable():
    """Below min_df a term cannot generalise: it can only ever match the one
    question it came from, which is not a group."""
    items = _family("a", "footprint", 8) + [_item("z", "a completely unique zebra")]
    vocabulary = build_vocabulary([terms_of(i) for i in items], min_df=4, max_df_ratio=0.95)
    assert not vocabulary.keeps("zebra")
    assert vocabulary.keeps("footprint")


def test_a_term_almost_everything_shares_is_dropped_as_undiscriminating():
    items = _family("a", "footprint", 20)
    vocabulary = build_vocabulary([terms_of(i) for i in items], min_df=2,
                                  max_df_ratio=0.20)
    # every one of them says "footprint", so it cannot separate any of them
    assert not vocabulary.keeps("footprint")


def test_vectors_are_unit_length():
    items = _family("a", "footprint", 6) + _family("b", "netlist export", 6)
    bags = [terms_of(i) for i in items]
    vocabulary = build_vocabulary(bags, min_df=2, max_df_ratio=0.75)
    for bag in bags:
        vector = vectorise(bag, vocabulary)
        if vector:
            assert abs(sum(v * v for v in vector.values()) - 1.0) < 1e-9


def test_cosine_of_identical_and_disjoint_vectors():
    assert abs(cosine({"a": 1.0}, {"a": 1.0}) - 1.0) < 1e-9
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0


# --------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------

def test_questions_about_the_same_thing_group_together():
    items = (_family("f", "footprint library", 8)
             + _family("n", "netlist export order", 8))
    result = _group(items)
    groups = [{items[i].external_id[0] for i in c.members}
              for c in result["clusters"]]
    assert len(result["clusters"]) >= 2
    for group in groups:
        assert len(group) == 1, "a group mixed two unrelated subjects"


def test_a_question_resembling_nothing_is_a_singleton_not_forced_into_a_group():
    items = _family("f", "footprint library", 8) + [
        _item("z", "Why did my lead acid battery explode in the garden shed")]
    result = _group(items)
    assigned = {i for c in result["clusters"] for i in c.members}
    odd = items.index(items[-1])
    assert odd not in assigned
    assert odd in result["singletons"]


def test_singletons_are_counted_rather_than_quietly_dropped():
    """"We grouped 26% of the corpus" and "we grouped the corpus" are very
    different claims, and only one of them is true."""
    items = _family("f", "footprint library", 6) + [
        _item(f"z{i}", f"An entirely unrelated matter about topic {i} of physics")
        for i in range(5)]
    result = _group(items)
    grouped = sum(len(c.members) for c in result["clusters"])
    assert grouped + len(result["singletons"]) == len(items)


def test_the_same_corpus_gives_the_same_groups_whatever_order_it_arrives_in():
    """Determinism is not a nicety here. If the groups depend on input order,
    then a change in the output means nothing -- it could be the corpus, or it
    could be that a probe ran in a different sequence."""
    items = (_family("f", "footprint library", 8)
             + _family("n", "netlist export order", 8)
             + _family("g", "gerber file output", 8))
    forward = _group(items)
    backward = _group(list(reversed(items)))

    def signature(result):
        return sorted(
            tuple(sorted(result["items"][i].external_id for i in c.members))
            for c in result["clusters"])

    assert signature(forward) == signature(backward)


def test_groups_about_one_subject_are_merged_into_one():
    """Growing a group from a seed splits a subject when no single question
    sits at the middle of it: Altium library management came out as three
    separate groups, which reads as three small problems rather than one
    substantial one."""
    # The third family is not decoration. Without it "altium" and "library" sit
    # in 100% of the corpus, max_df correctly discards them as undiscriminating,
    # and the two groups are left sharing literally nothing -- their centroids
    # measure 0.00 apart. Adding unrelated questions puts the shared words back
    # under the ceiling, which is the condition the merge exists for.
    #
    # These two centroids sit 0.27 apart, so the thresholds here bracket that
    # rather than matching the production default of 0.42. What is under test is
    # the mechanism: related groups join, unrelated ones do not, and the
    # threshold decides which. The production number was chosen by watching
    # three real Altium groups become one on the real corpus, and the reasoning
    # for it lives next to it in cluster.py.
    items = (_family("a", "altium footprint library", 6)
             + _family("b", "altium library component", 6)
             + _family("c", "battery charging circuit", 6))
    apart = _group(items, merge_threshold=0.99)
    joined = _group(items, merge_threshold=0.25)

    assert len(apart["clusters"]) == 3
    assert len(joined["clusters"]) == 2, "the two Altium groups did not join"

    # and the unrelated one was left alone rather than swept up
    sizes = sorted(len(c.members) for c in joined["clusters"])
    assert sizes == [6, 12]


def test_no_question_lands_in_two_groups():
    items = (_family("f", "footprint library", 10)
             + _family("n", "netlist export order", 10))
    result = _group(items, threshold=0.28)
    seen = [i for c in result["clusters"] for i in c.members]
    assert len(seen) == len(set(seen))


def test_a_label_does_not_say_the_same_word_twice():
    """Words arrive twice, once as a tag and once as a title word, and the
    first labels read "bom, bom, altium, altium" -- four label slots spent
    saying two things."""
    items = _family("a", "footprint library", 8, tags=("footprint", "altium"))
    result = _group(items, threshold=0.25)
    for cluster in result["clusters"]:
        plain = [term.lstrip("#") for term, _ in cluster.terms]
        assert len(plain) == len(set(plain))


# --------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------

def _demand_for(members, others, **kw):
    result = _group(members + others, **kw)
    return measure(result["clusters"], result["items"], now=NOW)


def test_a_big_group_outranks_a_tiny_one_with_a_luckier_percentage():
    """The bug this test exists for, in the terms it happened in.

    A group of four whose three unanswered questions make it "75% unanswered"
    beat a group of a hundred and thirty-seven on the first ranking. Four
    questions is not a measurement. Every proportion is now pulled toward the
    corpus rate by weight k/(n+k), so a small group has to be extraordinary to
    move at all, and size is scored on its own terms."""
    big = _family("b", "footprint library export", 40, answered=True, answers=2)
    small = _family("s", "gerber aperture rotation", 4, answered=False)
    # 40 of these 44 say the same words, so the usual max_df would delete the
    # big family's whole vocabulary and leave it unclustered -- which would make
    # the test pass for the wrong reason, by never building the group at all.
    ranked = _demand_for(big, small, max_df_ratio=0.95)
    by_size = {d.size: d for d in ranked}
    assert 40 in by_size and 4 in by_size
    assert by_size[40].total() > by_size[4].total(), (
        "a four-question group outranked a forty-question group again")


def test_a_group_at_the_corpus_rate_scores_around_half_on_that_dimension():
    """Being average is not a finding. The dimensions score lift over the
    corpus, so a group that matches the site's own unanswered rate collects
    half marks rather than full ones."""
    baselines = Baselines(unanswered=0.2, recent=0.2, toil=0.1, domain=0.5)
    items = (_family("a", "footprint library", 20, answered=True)
             + _family("b", "netlist export order", 20, answered=True))
    result = _group(items, threshold=0.25)
    ranked = measure(result["clusters"], result["items"], now=NOW,
                     baselines=baselines)
    unmet = dict((name, points) for name, points, _ in ranked[0].parts())["unmet"]
    assert 0 <= unmet < 20 * 0.6


def test_the_baseline_is_measured_from_the_corpus_not_assumed():
    items = (_family("a", "footprint", 5, answered=True)
             + _family("b", "netlist", 5, answered=False))
    baselines = baselines_for(items, now=NOW)
    assert abs(baselines.unanswered - 0.5) < 1e-9


def test_the_total_is_the_sum_of_its_stated_parts():
    """Same rule as the per-question scorer: a number nobody can decompose is a
    black box, and the point of ranking groups is to decide reading order for a
    person, not to decide what gets built."""
    ranked = _demand_for(_family("a", "footprint library", 12),
                         _family("b", "netlist export order", 12))
    for demand in ranked:
        assert demand.total() == int(round(sum(p for _, p, _ in demand.parts())))
        for name, points, evidence in demand.parts():
            assert evidence, f"{name} scored with no evidence"


def test_every_part_names_the_corpus_rate_it_is_compared_against():
    ranked = _demand_for(_family("a", "footprint library", 12),
                         _family("b", "netlist export order", 12))
    text = " ".join(e for _, _, e in ranked[0].parts())
    assert text.count("corpus") >= 4


def test_ranking_is_stable_across_runs():
    items = (_family("a", "footprint library", 12)
             + _family("b", "netlist export order", 12)
             + _family("c", "gerber file output", 12))
    first = [(d.cluster.label, d.total()) for d in _demand_for(items, [])]
    second = [(d.cluster.label, d.total()) for d in _demand_for(items, [])]
    assert first == second


def test_an_empty_corpus_does_not_crash_the_ranker():
    assert measure([], [], now=NOW) == []
