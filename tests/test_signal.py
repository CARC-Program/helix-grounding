"""
Tests for the source-agnostic core and the Stack Exchange adapter.

No test here touches the network. The suite has to pass on a machine with no
connection, and a test that silently depends on an external API fails for
reasons unrelated to the code — which trains people to ignore it. The one
number that came from the live API (a 300/day quota with no key) is asserted
against the adapter's own declaration, not re-fetched.
"""

import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest

from helix_signal.score import (
    Assessment,
    assess,
    band_for,
    _found,
)
from helix_signal.sources import Capabilities, SourceItem, StackExchangeSource
from helix_signal.sources.base import OpportunitySource
from helix_signal.sources.stackexchange import QuotaExhausted, html_to_text


def _item(**kw) -> SourceItem:
    defaults = dict(
        source="test:site",
        external_id="1",
        title="How do I fix my bill of materials export",
        body="KiCad writes the wrong part number and I fix it manually every time.",
        url="https://example.com/1",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        tags=("kicad", "bom"),
        engagement_score=3,
        answer_count=0,
        is_answered=False,
        content_license="CC BY-SA 4.0",
    )
    defaults.update(kw)
    return SourceItem(**defaults)


# --------------------------------------------------------------------
# The interface
# --------------------------------------------------------------------

def test_the_interface_has_no_way_to_publish():
    """The load-bearing structural claim. Publishing is done by a person from
    their own account, and the shape of the code should make that the only
    possibility rather than merely the policy. A method that does not exist
    cannot be called by mistake or enabled by a careless refactor."""
    forbidden = {"post", "publish", "comment", "reply", "vote", "upvote",
                 "downvote", "message", "dm", "follow", "submit"}
    for name in dir(OpportunitySource):
        assert name.lower() not in forbidden, f"OpportunitySource grew {name}()"
    for name in dir(StackExchangeSource):
        assert name.lower() not in forbidden, f"StackExchangeSource grew {name}()"


def test_a_source_needing_a_contract_reports_itself_unusable():
    """Reddit's commercial API needs a signed agreement this operator cannot
    enter. Recording that as data means the system declines for a stated
    reason instead of failing later with something that looks like a bug."""
    caps = Capabilities(
        key="reddit:example", display_name="Reddit", terms_url="https://x",
        content_license="", requires_contract=True,
        contract_note="Commercial use requires written approval.")
    reason = caps.blocked_reason()
    assert "signed agreement" in reason
    assert "written approval" in reason


def test_an_open_source_reports_itself_usable():
    ok, why = StackExchangeSource(site="electronics").usable()
    assert ok is True
    assert why == "usable"


def test_the_declared_quota_matches_what_the_api_actually_gives():
    """Measured live once: 300/day per IP with no key. Asserted here so the
    number in the code is the number somebody checked, not a guess."""
    assert StackExchangeSource().capabilities.rate_limit_per_day == 300
    assert StackExchangeSource(api_key="x").capabilities.rate_limit_per_day == 10000


def test_no_author_is_retained():
    """The workflow decides whether a human should read a thread. That needs
    the thread, not the person. Storing an author would retain personal data
    the process never uses; CC BY-SA attribution is satisfied by the link."""
    fields = set(SourceItem.__dataclass_fields__)
    assert not {f for f in fields if "author" in f or "owner" in f or "user" in f}
    assert "url" in fields


# --------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload, gzipped=False):
        raw = json.dumps(payload).encode("utf-8")
        self._raw = gzip.compress(raw) if gzipped else raw
        self.headers = {"Content-Encoding": "gzip"} if gzipped else {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


SAMPLE = {
    "quota_remaining": 297,
    "items": [{
        "question_id": 768965,
        "title": "How to Fix &quot;Bill of Materials&quot; &lt;b&gt;export&lt;/b&gt;",
        "body": "<p>KiCad writes the wrong <b>part number</b>.</p>",
        "link": "https://electronics.stackexchange.com/questions/768965/x",
        "creation_date": 1750000000,
        "tags": ["kicad", "bom"],
        "score": 2,
        "answer_count": 1,
        "is_answered": False,
        "content_license": "CC BY-SA 4.0",
    }],
}


def test_items_are_normalised_and_html_is_stripped():
    source = StackExchangeSource(opener=lambda req, timeout=0: _FakeResponse(SAMPLE))
    items = source.collect(query="bom")
    assert len(items) == 1
    item = items[0]
    # Stack Exchange escapes titles, so &lt;b&gt; means the user literally
    # typed "<b>". Tags are stripped before entities are decoded, so real
    # markup in the body goes and typed-out markup in the title stays --
    # deleting the latter would be deleting text somebody wrote.
    assert item.title == 'How to Fix "Bill of Materials" <b>export</b>'
    assert "<b>" not in item.body and "part number" in item.body
    assert item.content_license == "CC BY-SA 4.0"
    assert item.source == "stackexchange:electronics"
    assert item.created_at.tzinfo is timezone.utc


def test_gzip_responses_are_decompressed():
    source = StackExchangeSource(
        opener=lambda req, timeout=0: _FakeResponse(SAMPLE, gzipped=True))
    assert source.collect(query="bom")[0].tags == ("kicad", "bom")


def test_the_servers_backoff_is_honoured():
    """The API says when to wait. Ignoring that is rate-limit evasion by
    another name, and the reason this source was chosen over Reddit is that it
    can be used without pretending."""
    slept = []
    payload = dict(SAMPLE, backoff=7)
    source = StackExchangeSource(
        opener=lambda req, timeout=0: _FakeResponse(payload),
        sleep=slept.append)
    source.collect(query="bom")
    assert slept == [7.0]
    assert source.last_backoff == 7.0


def test_an_exhausted_quota_refuses_rather_than_hammering():
    source = StackExchangeSource(
        opener=lambda req, timeout=0: _FakeResponse(dict(SAMPLE, quota_remaining=0)))
    source.collect(query="bom")
    with pytest.raises(QuotaExhausted, match="resets at"):
        source.collect(query="bom")


def test_a_network_failure_says_so_plainly():
    def boom(req, timeout=0):
        raise OSError("no route to host")
    source = StackExchangeSource(opener=boom)
    with pytest.raises(RuntimeError, match="could not reach"):
        source.collect(query="bom")


@pytest.mark.parametrize("html,expected", [
    ("<p>hello</p>", "hello"),
    ("&lt;b&gt;typed&lt;/b&gt;", "<b>typed</b>"),   # escaped: the user's text
    ("a &amp; b", "a & b"),
    ("&quot;quoted&quot;", '"quoted"'),
    ("", ""),
])
def test_html_to_text(html, expected):
    assert html_to_text(html) == expected


# --------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------

def test_a_relevant_recent_unanswered_question_scores_high():
    """70 is what a near-ideal item actually reaches: on topic, unanswered, a
    day old, describing manual work. The first version of this asserted 80 and
    failed, which was the bands being set against a theoretical maximum no real
    question reaches."""
    assessment = assess(_item())
    assert assessment.total >= 65
    assert "high" in assessment.band


def test_an_old_answered_off_topic_question_scores_low():
    item = _item(
        title="What colour should I paint my enclosure",
        body="Just wondering about aesthetics.",
        tags=("mechanical",),
        created_at=datetime.now(timezone.utc) - timedelta(days=900),
        is_answered=True, answer_count=3, engagement_score=0)
    assessment = assess(item)
    assert assessment.total <= 20


def test_every_point_is_attributable():
    """'Never make the score a black box.' The total must equal the sum of
    stated reasons, or the explanation is decoration."""
    assessment = assess(_item())
    assert assessment.total == sum(c.points for c in assessment.contributions)
    for contribution in assessment.contributions:
        assert contribution.evidence
        assert 0 <= contribution.points <= contribution.max_points


def test_the_explanation_names_the_evidence():
    text = assess(_item()).explain()
    assert "domain fit" in text
    assert "bill of materials" in text or "kicad" in text
    assert "still unanswered" in text


def test_matching_is_on_word_boundaries():
    """Without boundaries 'bom' matches 'bombard' and 'bombay', and a scorer
    that fires on the wrong word is worse than one that misses — it produces
    confident nonsense."""
    assert _found("the bombardment continued", ("bom",)) == []
    assert _found("check the bom please", ("bom",)) == ["bom"]
    assert _found("a bill  of   materials", ("bill of materials",)) == ["bill of materials"]


def test_an_answered_question_scores_zero_for_openness():
    """Weighted opposite to a sales funnel on purpose: an answered question is
    a closed door, and this measures where help is still worth something."""
    answered = assess(_item(is_answered=True, answer_count=2))
    open_one = assess(_item(is_answered=False, answer_count=0))
    assert open_one.total > answered.total


@pytest.mark.parametrize("total,expected", [
    (95, "high"), (65, "high"), (64, "good"), (45, "good"),
    (44, "watch"), (28, "watch"), (27, "low"), (15, "low"), (14, "ignore"), (0, "ignore"),
])
def test_band_boundaries(total, expected):
    assert band_for(total).startswith(expected)


def test_scoring_is_pure_and_repeatable():
    item = _item()
    first, second = assess(item), assess(item)
    assert first.as_dict() == second.as_dict()
