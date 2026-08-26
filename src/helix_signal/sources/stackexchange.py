"""
Stack Exchange as an opportunity source.

Chosen as the first adapter for a reason that is not enthusiasm: it is the one
that can actually run today. Reddit's commercial Data API needs a signed
contract, which is closed to this operator. Stack Exchange's API is open, needs
no key at low volume, and `electronics.stackexchange.com` is where hardware
people ask the exact questions this business exists to answer — the first live
probe returned somebody trying to clean up a bill of materials for a KiCad
layout, which is the target user describing the target problem unprompted.

Verified live rather than read from documentation, because the documentation
pages block automated requests:

    quota_max        300 per day, per IP, with no API key
    content_license  reported per item (CC BY-SA 4.0 on what was sampled)
    backoff          returned in-band when the server wants a pause

Three things this adapter will not do:

**It will not ignore ``backoff``.** The API tells you when to wait. Ignoring
that is rate-limit evasion by another name, and the whole reason this source
was chosen is that it can be used without pretending.

**It will not exceed the daily quota silently.** 300 is small. Running out
mid-day with no warning would look like the source going down.

**It will not write.** There is no method to. See ``base.py``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .base import Capabilities, OpportunitySource, SourceItem

API_ROOT = "https://api.stackexchange.com/2.3"
TERMS_URL = "https://stackexchange.com/legal/api-terms-of-use"

# Strips HTML without a dependency. The API returns question bodies as HTML and
# this layer wants text to match against; a parser dependency for this would
# cost more than it is worth in a package whose neighbours have none.
import html as _html
import re as _re

_TAG = _re.compile(r"<[^>]+>")
_WS = _re.compile(r"[ \t]+")


def html_to_text(text: str) -> str:
    """Tags out first, then entities decoded. The order is the whole point.

    Stack Exchange escapes titles, so ``&lt;b&gt;`` in a title means the user
    literally typed ``<b>``. Decoding before stripping would turn their text
    into markup and then delete it; stripping first means real markup goes and
    typed-out markup stays.

    Entity decoding started as a hand-written table of nine common names. Across
    ten thousand harvested questions it left 84 entities undecoded -- the
    degree, micro, delta and ohm signs that electronics questions are full of,
    plus every numeric escape. ``html.unescape`` ships with Python and knows all
    of them, so the table was a worse version of something already installed.
    """
    stripped = _TAG.sub(" ", text or "")
    decoded = _html.unescape(stripped)
    collapsed = _WS.sub(" ", decoded)
    return "\n".join(line.strip() for line in collapsed.splitlines() if line.strip())


class QuotaExhausted(RuntimeError):
    """The daily allowance is gone. Not an error to retry through."""


class StackExchangeSource(OpportunitySource):
    """Read questions from one Stack Exchange site."""

    def __init__(self, site: str = "electronics", api_key: str | None = None,
                 opener=None, sleep=time.sleep):
        self.site = site
        self.api_key = api_key
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self.quota_remaining: int | None = None
        self.last_backoff: float = 0.0
        # Set from every response. The caller needs it to know whether a page
        # limit truncated a read or the archive genuinely ended -- reporting a
        # truncated corpus as a complete one is how a sample gets mistaken for
        # a census.
        self.has_more: bool = False

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            key=f"stackexchange:{self.site}",
            display_name=f"Stack Exchange ({self.site})",
            terms_url=TERMS_URL,
            content_license="CC BY-SA (reported per item)",
            read=True,
            search=True,
            write=False,
            requires_api_key=False,   # a key raises the quota; none is needed
            requires_contract=False,
            rate_limit_per_day=10000 if self.api_key else 300,
            attribution_required=True,
        )

    # ---------------------------------------------------------------- http
    def _get(self, path: str, params: dict) -> dict:
        if self.quota_remaining is not None and self.quota_remaining <= 0:
            raise QuotaExhausted(
                f"Stack Exchange daily quota for this IP is spent "
                f"({self.capabilities.rate_limit_per_day}/day). It resets at "
                f"UTC midnight. Register an API key to raise it rather than "
                f"working around it."
            )

        query = {"site": self.site, **params}
        if self.api_key:
            query["key"] = self.api_key
        url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(query)}"

        request = urllib.request.Request(
            url, headers={"Accept-Encoding": "gzip", "User-Agent": "helix-signal"})
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                payload = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Stack Exchange returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"could not reach Stack Exchange ({exc})") from exc

        self.quota_remaining = payload.get("quota_remaining", self.quota_remaining)
        self.has_more = bool(payload.get("has_more", False))

        # The server asks for a pause in-band. Honouring it is the difference
        # between using an API and abusing one.
        backoff = payload.get("backoff")
        if backoff:
            self.last_backoff = float(backoff)
            self._sleep(float(backoff))

        return payload

    # ------------------------------------------------------------- collect
    def collect(self, query: str = "", limit: int = 25, page: int = 1,
                tagged: str = "", sort: str = "creation") -> list:
        """Search the site, or read questions by tag, or read the newest.

        ``tagged`` is the precise instrument and ``query`` the blunt one: a tag
        was applied by a person who read the question, whereas a text search
        matches whatever the words happen to hit. Prefer a tag where one exists.
        """
        params = {
            "pagesize": min(max(limit, 1), 100),
            "page": max(int(page), 1),
            "order": "desc",
            "sort": sort,
            "filter": "withbody",
        }
        if tagged:
            params["tagged"] = tagged
        if query:
            params["q"] = query
            path = "search/advanced"
        else:
            path = "questions"

        payload = self._get(path, params)
        return [self._normalise(item) for item in payload.get("items", [])]

    def tags(self, limit: int = 100, page: int = 1, inname: str = "") -> list:
        """The site's real tags, with how many questions carry each.

        This exists so a corpus read is aimed at labels that exist rather than
        at ones that seemed plausible. A corpus assembled from guessed search
        terms is evidence about the guesser.
        """
        params = {
            "pagesize": min(max(limit, 1), 100),
            "page": max(int(page), 1),
            "order": "desc",
            "sort": "popular",
        }
        if inname:
            params["inname"] = inname
        payload = self._get("tags", params)
        return [{"name": t.get("name", ""), "count": int(t.get("count", 0))}
                for t in payload.get("items", [])]

    def _normalise(self, item: dict) -> SourceItem:
        return SourceItem(
            source=self.capabilities.key,
            external_id=str(item.get("question_id", "")),
            title=html_to_text(item.get("title", "")),
            body=html_to_text(item.get("body", "")),
            url=item.get("link", ""),
            created_at=datetime.fromtimestamp(
                item.get("creation_date", 0), tz=timezone.utc),
            tags=tuple(item.get("tags", ())),
            engagement_score=int(item.get("score", 0)),
            answer_count=int(item.get("answer_count", 0)),
            is_answered=bool(item.get("is_answered", False)),
            content_license=item.get("content_license", ""),
        )
