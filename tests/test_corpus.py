"""
Tests for the corpus reader.

No test here touches the network. The point of this layer is that a read costs
quota once and everything afterwards is free, so a test suite that spent quota
to check it would be arguing against the thing it is testing.

The fake source below is the whole apparatus: it hands out pages, reports
whether more exist, and can be told to run out or fall over.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from helix_signal.corpus import (
    CorpusStore,
    HarvestReport,
    Probe,
    ProbeResult,
    harvest,
)
from helix_signal.sources.base import SourceItem
from helix_signal.sources.stackexchange import QuotaExhausted

WHEN = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _item(number: int, **kw) -> SourceItem:
    defaults = dict(
        source="test:site",
        external_id=str(number),
        title=f"question {number}",
        body="body text",
        url=f"https://example.com/{number}",
        created_at=WHEN,
        tags=("kicad",),
        engagement_score=1,
        answer_count=0,
        is_answered=False,
        content_license="CC BY-SA 4.0",
    )
    defaults.update(kw)
    return SourceItem(**defaults)


class _FakeSource:
    """Hands out ``pages`` pages of ``per_page`` items, then says it is done."""

    def __init__(self, pages=3, per_page=2, quota=300, fail_on=None,
                 exhaust_after=None):
        self.pages = pages
        self.per_page = per_page
        self.quota_remaining = quota
        self.has_more = False
        self.calls = []
        self._fail_on = fail_on
        self._exhaust_after = exhaust_after
        self._counter = 0

    def collect(self, query="", limit=25, page=1, tagged="", sort="creation"):
        label = tagged or query
        self.calls.append((label, page))
        self._counter += 1
        if self._exhaust_after is not None and self._counter > self._exhaust_after:
            raise QuotaExhausted("daily quota is spent. It resets at UTC midnight.")
        if label == self._fail_on:
            raise RuntimeError("could not reach the site")
        if self.quota_remaining is not None:
            self.quota_remaining -= 1
        self.has_more = page < self.pages
        start = (page - 1) * self.per_page
        return [_item(f"{label}-{start + i}") for i in range(self.per_page)]


# --------------------------------------------------------------------
# The store
# --------------------------------------------------------------------

def test_a_saved_corpus_reloads_identically(tmp_path):
    path = tmp_path / "c.jsonl"
    store = CorpusStore(path)
    store.add([_item(1), _item(2)])
    store.save()

    reloaded = CorpusStore(path).items()
    assert len(reloaded) == 2
    first = reloaded[0]
    assert first.title == "question 1"
    assert first.tags == ("kicad",)
    assert first.content_license == "CC BY-SA 4.0"
    assert first.created_at == WHEN
    assert first.created_at.tzinfo is not None


def test_the_same_question_is_never_stored_twice(tmp_path):
    """Probes overlap heavily -- a KiCad question is usually also tagged
    pcb-design -- so without this the corpus would be mostly duplicates and
    every count derived from it would be inflated."""
    store = CorpusStore(tmp_path / "c.jsonl")
    assert store.add([_item(1), _item(2)]) == 2
    assert store.add([_item(1), _item(3)]) == 1
    assert len(store) == 3


def test_a_second_harvest_adds_to_the_first(tmp_path):
    path = tmp_path / "c.jsonl"
    first = CorpusStore(path)
    first.add([_item(1)])
    first.save()

    second = CorpusStore(path)
    second.add([_item(2)])
    second.save()

    assert len(CorpusStore(path)) == 2


def test_one_corrupt_line_does_not_lose_the_others(tmp_path):
    path = tmp_path / "c.jsonl"
    store = CorpusStore(path)
    store.add([_item(1), _item(2)])
    store.save()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    assert len(CorpusStore(path)) == 2


def test_a_row_with_an_unreadable_date_still_loads(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text(json.dumps({"source": "s", "external_id": "9",
                                "created_at": "not a date"}) + "\n",
                    encoding="utf-8")
    item = CorpusStore(path).items()[0]
    assert item.external_id == "9"
    assert item.created_at.tzinfo is timezone.utc


def test_no_author_field_survives_a_round_trip(tmp_path):
    """The no-author rule has to hold at the storage layer too, or the
    guarantee in `sources/base.py` is one careless `_to_row` away from being
    false on disk."""
    path = tmp_path / "c.jsonl"
    store = CorpusStore(path)
    store.add([_item(1)])
    store.save()
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert not [key for key in row if "author" in key or "owner" in key
                or "user" in key]
    assert row["url"]


# --------------------------------------------------------------------
# The harvest
# --------------------------------------------------------------------

def test_a_probe_stops_when_the_archive_runs_out(tmp_path):
    source = _FakeSource(pages=3, per_page=2)
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "kicad")], store, max_pages=10)
    result = report.results[0]
    assert result.pages == 3
    assert result.exhausted is True
    assert result.fetched == 6


def test_hitting_the_page_limit_is_reported_not_hidden(tmp_path):
    """A truncated read that prints a clean total is a sample presented as a
    census, which is the mistake this whole project keeps finding."""
    source = _FakeSource(pages=50, per_page=2)
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "pcb")], store, max_pages=3)
    result = report.results[0]
    assert result.pages == 3
    assert result.exhausted is False
    assert "more available" in report.describe()


def test_the_request_count_is_counted_not_inferred(tmp_path):
    """The first version subtracted the quota after the run from the quota
    before it and printed "0 requests spent" for a run that made 104 -- because
    before the first call the source has never spoken to the API and has no
    quota to subtract from. A page fetched is a request made."""
    source = _FakeSource(pages=4, per_page=2)
    source.quota_remaining = None          # exactly the real starting state
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "a"), Probe("tag", "b")], store,
                     max_pages=10)
    assert report.requests == 8
    assert "8 requests made" in report.describe()


def test_an_unknown_quota_says_unknown(tmp_path):
    source = _FakeSource(pages=1, per_page=1)
    source.quota_remaining = None
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "a")], store)
    assert "unknown" in report.describe()


def test_an_exhausted_quota_stops_the_run_and_says_so(tmp_path):
    """Not an error to retry through. The correct response is to keep what was
    already saved and come back tomorrow."""
    source = _FakeSource(pages=50, per_page=2, exhaust_after=3)
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "a"), Probe("tag", "b")], store,
                     max_pages=50)
    assert "quota" in report.stopped_early.lower()
    assert store.items(), "items read before the quota ran out must be kept"


def test_one_failing_probe_does_not_lose_the_others(tmp_path):
    source = _FakeSource(pages=2, per_page=2, fail_on="broken")
    store = CorpusStore(tmp_path / "c.jsonl")
    report = harvest(source, [Probe("tag", "broken"), Probe("tag", "fine")],
                     store, max_pages=5)
    broken, fine = report.results
    assert broken.error and broken.fetched == 0
    assert fine.fetched == 4
    assert "ERROR" in report.describe()


def test_tags_and_queries_reach_the_source_as_different_things(tmp_path):
    """A tag was applied by a person who read the question; a text search
    matches whatever the words hit. Confusing the two would make the corpus
    evidence about the search terms."""
    source = _FakeSource(pages=1, per_page=1)
    store = CorpusStore(tmp_path / "c.jsonl")
    harvest(source, [Probe("tag", "kicad"), Probe("query", "netlist")], store)
    assert ("kicad", 1) in source.calls
    assert ("netlist", 1) in source.calls


def test_progress_is_reported_per_page(tmp_path):
    seen = []
    source = _FakeSource(pages=3, per_page=2)
    store = CorpusStore(tmp_path / "c.jsonl")
    harvest(source, [Probe("tag", "a")], store,
            on_progress=lambda probe, page, count, report: seen.append((page, count)))
    assert seen == [(1, 2), (2, 2), (3, 2)]


def test_an_empty_report_describes_itself_without_crashing():
    assert "quota" in HarvestReport().describe()


def test_probe_and_result_describe_themselves():
    probe = Probe("tag", "kicad")
    assert probe.describe() == "tag:kicad"
    assert ProbeResult(probe=probe).fetched == 0
