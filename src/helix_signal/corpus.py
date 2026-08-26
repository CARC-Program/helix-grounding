"""
Read the archive once, then work offline.

The measurement that produced this module: electronics.stackexchange.com has
had zero new "bill of materials" questions in ninety days, and about one KiCad
question every nine days. As a stream to poll every five minutes there is
nothing there. As an archive there are several thousand questions already
written, and they answer a question this business cannot otherwise answer
honestly -- what do hardware people actually get stuck on, as opposed to what
would be convenient to believe they get stuck on.

So this is a miner, not a monitor, and three rules follow from that:

**Read once.** The daily quota is 300 requests per IP. A full read is roughly
forty. Re-running the analysis must cost nothing, so everything fetched is
written to disk and the next run loads from there. Quota spent re-fetching
something already held is quota stolen from a question not yet asked.

**Keep the licence and the link.** Stack Exchange content is CC BY-SA, which
permits this use and requires attribution. The canonical URL travels with every
item and the licence string is recorded per item as the API reports it. No
author name is stored -- see ``sources/base.py``; the workflow needs the
question, not the person.

**The cache stays out of git.** It is several megabytes of other people's
copyrighted-but-licensed prose. What belongs in the repository is what this
project derived from it -- counts, clusters, conclusions -- plus the links back.
Facts about a corpus are not the corpus.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .sources.base import SourceItem

# Where a harvest lands by default. Gitignored: see the module docstring.
DEFAULT_CACHE = Path("data/corpus")


def _to_row(item: SourceItem) -> dict:
    return {
        "source": item.source,
        "external_id": item.external_id,
        "title": item.title,
        "body": item.body,
        "url": item.url,
        "created_at": item.created_at.isoformat(),
        "tags": list(item.tags),
        "engagement_score": item.engagement_score,
        "answer_count": item.answer_count,
        "is_answered": item.is_answered,
        "content_license": item.content_license,
    }


def _from_row(row: dict) -> SourceItem:
    created = row.get("created_at") or ""
    try:
        when = datetime.fromisoformat(created)
    except ValueError:
        when = datetime.fromtimestamp(0, tz=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return SourceItem(
        source=row.get("source", ""),
        external_id=str(row.get("external_id", "")),
        title=row.get("title", ""),
        body=row.get("body", ""),
        url=row.get("url", ""),
        created_at=when,
        tags=tuple(row.get("tags", ())),
        engagement_score=int(row.get("engagement_score", 0)),
        answer_count=int(row.get("answer_count", 0)),
        is_answered=bool(row.get("is_answered", False)),
        content_license=row.get("content_license", ""),
    )


class CorpusStore:
    """A JSONL file of normalised items, deduplicated by source and id.

    JSONL rather than a database because the whole point of this layer is that
    a second run is free: the file can be inspected with `head`, counted with
    `wc -l`, and deleted without ceremony when a schema changes.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._items = {}
        if self.path.exists():
            self._read()

    def _read(self) -> None:
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # One corrupt line should not lose the other four thousand.
                    continue
                item = _from_row(row)
                self._items[(item.source, item.external_id)] = item

    def add(self, items) -> int:
        """Add items, ignoring ones already held. Returns how many were new."""
        added = 0
        for item in items:
            key = (item.source, item.external_id)
            if key in self._items:
                continue
            self._items[key] = item
            added += 1
        return added

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for item in self._items.values():
                handle.write(json.dumps(_to_row(item), ensure_ascii=False) + "\n")
        return self.path

    def items(self) -> list:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class Probe:
    """One thing to ask the archive for.

    ``tag`` is the precise instrument: a human applied that label to that
    question. ``query`` is the blunt one, for subjects nobody made a tag for.
    Both are recorded in the harvest report so a cluster can always be traced
    back to how it was found -- a corpus assembled by forgotten search terms is
    evidence of the search terms, not of the subject.
    """

    kind: str   # "tag" or "query"
    value: str

    def describe(self) -> str:
        return f"{self.kind}:{self.value}"


@dataclass
class ProbeResult:
    probe: Probe
    fetched: int = 0
    new: int = 0
    pages: int = 0
    exhausted: bool = False     # True when the archive ran out before we did
    error: str = ""


@dataclass
class HarvestReport:
    results: list = field(default_factory=list)
    quota_after: int | None = None
    stopped_early: str = ""

    @property
    def requests(self) -> int:
        """Counted, not inferred.

        The first version of this subtracted the remaining quota after the run
        from the remaining quota before it, and printed "0 requests spent" for a
        run that made 104 -- because before the first call the source has never
        spoken to the API and does not know the quota, so the subtraction was
        against nothing. A page fetched is a request made; count those.
        """
        return sum(r.pages for r in self.results)

    @property
    def total_new(self) -> int:
        return sum(r.new for r in self.results)

    @property
    def total_fetched(self) -> int:
        return sum(r.fetched for r in self.results)

    def describe(self) -> str:
        lines = ["probe                          fetched    new  pages"]
        for result in self.results:
            flag = ""
            if result.error:
                flag = f"  ERROR {result.error}"
            elif not result.exhausted:
                # Said out loud. A truncated read that reports a clean total is
                # the same failure as a check that passes without running.
                flag = "  (more available, page limit reached)"
            lines.append(
                f"{result.probe.describe():<30} {result.fetched:>7} "
                f"{result.new:>6} {result.pages:>6}{flag}")
        left = ("unknown" if self.quota_after is None
                else f"{self.quota_after} left today")
        lines.append(f"\nquota: {self.requests} requests made, {left}")
        if self.stopped_early:
            lines.append(f"\nstopped early: {self.stopped_early}")
        return "\n".join(lines)


def harvest(source, probes, store, max_pages: int = 10, pagesize: int = 100,
            on_progress=None) -> HarvestReport:
    """Read every probe into the store, page by page, and stop when told to.

    Stops for three reasons and says which: the archive ran out, the page limit
    was hit, or the daily quota was spent. The third is not an error to retry
    through -- it is the API saying no, and the correct response is to come back
    tomorrow with what was already saved.
    """
    from .sources.stackexchange import QuotaExhausted

    report = HarvestReport()

    for probe in probes:
        result = ProbeResult(probe=probe)
        report.results.append(result)
        for page in range(1, max_pages + 1):
            try:
                if probe.kind == "tag":
                    items = source.collect(limit=pagesize, page=page,
                                           tagged=probe.value)
                else:
                    items = source.collect(query=probe.value, limit=pagesize,
                                           page=page)
            except QuotaExhausted as exc:
                report.stopped_early = str(exc)
                report.quota_after = getattr(source, "quota_remaining", None)
                return report
            except RuntimeError as exc:
                result.error = str(exc)
                break

            result.pages = page
            result.fetched += len(items)
            result.new += store.add(items)
            if on_progress:
                on_progress(probe, page, len(items), report)

            if not getattr(source, "has_more", False):
                result.exhausted = True
                break

    report.quota_after = getattr(source, "quota_remaining", None)
    return report
