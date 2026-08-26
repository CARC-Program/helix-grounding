"""
A local record of what distributors said, and when.

Two reasons this is not optional.

**The call limits are small.** Mouser allows a thousand calls a day and thirty a
minute. A two-hundred-line BOM re-run five times while somebody tunes the report
is a thousand calls. Without a cache the tool would be unusable on exactly the
workflow it is for.

**A cached price is not a current price.** That is the whole hazard of caching
prices, so the moment of fetching is stored with the answer and the report says
how old it is. A stale number that announces itself is useful; a stale number
that looks fresh is worse than no number, because somebody will quote it.

Entries expire. The default is short by the standards of most caches and long by
the standards of a stock level, and the trade is stated where it is set.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .base import Lifecycle, Lookup, Offer, Outcome, PartRecord, PriceBreak

# Stock moves in minutes on a popular part and prices move in days. Twelve hours
# is the compromise: long enough that iterating on a BOM costs nothing, short
# enough that a number is never more than half a day out. Anyone quoting a
# customer should pass --fresh, and the report prints the age either way.
DEFAULT_TTL_HOURS = 12


def default_cache_path() -> Path:
    """Beside the user's other cached data, not in the project directory.

    A cache written into the current working directory ends up committed to
    somebody's repository, and this one holds pricing that a distributor's terms
    may not permit redistributing.
    """
    base = os.environ.get("XDG_CACHE_HOME") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "helix-bom" / "distributors.json"
    return Path.home() / ".cache" / "helix-bom" / "distributors.json"


def _encode(value):
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, (Lifecycle, Outcome)):
        return value.value
    raise TypeError(f"cannot store {type(value).__name__}")


def _decode(raw: dict):
    if "__decimal__" in raw:
        return Decimal(raw["__decimal__"])
    if "__datetime__" in raw:
        parsed = datetime.fromisoformat(raw["__datetime__"])
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return raw


class LookupCache:
    """Distributor answers, keyed by distributor and part number."""

    def __init__(self, path=None, ttl_hours: float = DEFAULT_TTL_HOURS,
                 enabled: bool = True):
        self.path = Path(path) if path else default_cache_path()
        self.ttl = timedelta(hours=ttl_hours)
        self.enabled = enabled
        self._entries = {}
        self.hits = 0
        self.misses = 0
        if self.enabled:
            self._read()

    # ------------------------------------------------------------- storage
    def _read(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"),
                             object_hook=_decode)
        except (OSError, json.JSONDecodeError, ValueError):
            # A corrupt cache is a cache miss, never a crash. It costs a
            # re-fetch; refusing to start would cost the whole run.
            return
        if isinstance(raw, dict):
            self._entries = raw.get("entries", {})

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": self._entries}
        try:
            self.path.write_text(
                json.dumps(payload, default=_encode, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass    # an unwritable cache is a slow tool, not a broken one

    # ------------------------------------------------------------- lookups
    @staticmethod
    def _key(distributor: str, mpn: str) -> str:
        return f"{distributor}|{mpn.strip().upper()}"

    def get(self, distributor: str, mpn: str, now=None) -> Lookup | None:
        """A cached answer, or None if absent or too old to trust."""
        if not self.enabled:
            return None
        entry = self._entries.get(self._key(distributor, mpn))
        if not entry:
            self.misses += 1
            return None
        stored = entry.get("stored_at")
        if not isinstance(stored, datetime):
            self.misses += 1
            return None
        if (now or datetime.now(timezone.utc)) - stored > self.ttl:
            self.misses += 1
            return None
        self.hits += 1
        return _lookup_from(entry["lookup"])

    def put(self, distributor: str, mpn: str, lookup: Lookup, now=None) -> None:
        """Store an answer. Answers that were never obtained are not stored.

        Caching a NOT_CHECKED would turn one missing API key into twelve hours
        of a report insisting nothing could be checked, long after the key was
        set.
        """
        if not self.enabled or lookup.outcome is Outcome.NOT_CHECKED:
            return
        self._entries[self._key(distributor, mpn)] = {
            "stored_at": now or datetime.now(timezone.utc),
            "lookup": _lookup_to(lookup),
        }

    def clear(self) -> int:
        count = len(self._entries)
        self._entries = {}
        self.save()
        return count


# --------------------------------------------------------------------
# Plain-data conversion. Written out rather than pickled so the file can be
# read by a person, and so a schema change fails loudly instead of executing.
# --------------------------------------------------------------------

def _offer_to(offer: Offer) -> dict:
    data = asdict(offer)
    data["price_breaks"] = [asdict(b) for b in offer.price_breaks]
    return data


def _offer_from(data: dict) -> Offer:
    breaks = tuple(PriceBreak(quantity=int(b["quantity"]),
                              unit_price=b["unit_price"],
                              currency=b.get("currency", "USD"))
                   for b in data.get("price_breaks", ()))
    return Offer(
        distributor=data["distributor"],
        distributor_part_number=data.get("distributor_part_number", ""),
        url=data.get("url", ""),
        stock=data.get("stock"),
        price_breaks=breaks,
        minimum_quantity=int(data.get("minimum_quantity", 1)),
        order_multiple=int(data.get("order_multiple", 1)),
        lead_time_days=data.get("lead_time_days"),
        packaging=data.get("packaging", ""),
        currency=data.get("currency", "USD"),
        fetched_at=data["fetched_at"],
    )


def _record_to(record: PartRecord) -> dict:
    return {
        "manufacturer_part_number": record.manufacturer_part_number,
        "manufacturer": record.manufacturer,
        "description": record.description,
        "lifecycle": record.lifecycle.value,
        "lifecycle_text": record.lifecycle_text,
        "datasheet_url": record.datasheet_url,
        "package": record.package,
        "offers": [_offer_to(o) for o in record.offers],
    }


def _record_from(data: dict) -> PartRecord:
    return PartRecord(
        manufacturer_part_number=data["manufacturer_part_number"],
        manufacturer=data.get("manufacturer", ""),
        description=data.get("description", ""),
        lifecycle=Lifecycle(data.get("lifecycle", Lifecycle.UNKNOWN.value)),
        lifecycle_text=data.get("lifecycle_text", ""),
        datasheet_url=data.get("datasheet_url", ""),
        package=data.get("package", ""),
        offers=tuple(_offer_from(o) for o in data.get("offers", ())),
    )


def _lookup_to(lookup: Lookup) -> dict:
    return {
        "query": lookup.query,
        "outcome": lookup.outcome.value,
        "record": _record_to(lookup.record) if lookup.record else None,
        "candidates": [_record_to(c) for c in lookup.candidates],
        "reason": lookup.reason,
    }


def _lookup_from(data: dict) -> Lookup:
    return Lookup(
        query=data["query"],
        outcome=Outcome(data["outcome"]),
        record=_record_from(data["record"]) if data.get("record") else None,
        candidates=tuple(_record_from(c) for c in data.get("candidates", ())),
        reason=data.get("reason", ""),
    )
