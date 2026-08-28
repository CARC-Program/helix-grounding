"""
Mouser's Search API.

Endpoint and payload shapes are as documented at
https://api.mouser.com/api/docs/ui — search by part number is a POST to
``/api/v1/search/partnumber`` with the key in the query string and the request
in the body. The limits are thirty calls a minute and a thousand a day, which is
why `cache.py` exists and is on by default.

**The request and response shapes are checked against the published
specification.** `https://api.mouser.com/api/docs/v1` is a public Swagger
document and every field name used here was compared against it: the
`Errors`/`SearchResults` envelope, `SearchResults.Parts`, the `apiKey` query
parameter, the templated version in the path, `SearchByPartRequest` with
`mouserPartNumber` and `partSearchOptions` (valid values None and Exact), and
every part field read below. That check found three things this adapter was
missing and one field it looked for that does not exist.

**It has still never been run against the live API.** Nobody here has a Mouser
key: getting one requires an account, and the account terms are the account
holder's to read and accept. A schema is not a server, so
``capabilities.verified_against_live_api`` is False and stays False until
somebody runs `helix-bom enrich --check-key` with a real key and reports back.
That flag is printed in the report, so no reader is misled about what has
actually been exercised.

One thing the schema cannot settle: the request field is named
`mouserPartNumber` and its description says "the specific Mouser part number",
yet this endpoint is what every client uses for manufacturer part numbers.
`--check-key` probes with an MPN precisely so that a real key answers this.

Not used yet, and worth doing: the schema allows **ten part numbers per
request**, separated. Against a thousand-a-day limit that is a tenfold
improvement on a long BOM, and it is the single best efficiency left here.

The key is read from ``MOUSER_API_KEY`` and never written anywhere: not to the
cache, not to the log, not into an error message. Errors quote the HTTP status
and nothing from the request.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .base import (
    Capabilities,
    Lifecycle,
    Lookup,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
    normalise_mpn,
    parse_money,
    read_lifecycle,
)

API_ROOT = "https://api.mouser.com/api/v1"
TERMS_URL = "https://www.mouser.com/en/apiterms/"


def _attribute(part: dict, name: str) -> str:
    """One of a part's ProductAttributes, by name.

    The schema gives attributes as {AttributeName, AttributeValue} pairs rather
    than as fields, so package, tolerance and voltage rating all arrive here.
    """
    for entry in part.get("ProductAttributes") or []:
        if name.lower() in str(entry.get("AttributeName", "")).lower():
            return str(entry.get("AttributeValue", "") or "")
    return ""


def _as_int(value):
    """Read a count that may arrive as 1234, "1,234" or "1234 In Stock"."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = "".join(ch for ch in str(value).replace(",", "") if ch.isdigit())
    return int(digits) if digits else None


class MouserDistributor:
    """Look parts up at Mouser. Read-only; there is no ordering method."""

    def __init__(self, api_key=None, environment=None, opener=None,
                 sleep=time.sleep, now=None):
        self._environment = environment if environment is not None else os.environ
        self._api_key = api_key or self._environment.get("MOUSER_API_KEY", "")
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.calls_made = 0
        self._last_call = 0.0

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            key="mouser",
            display_name="Mouser",
            terms_url=TERMS_URL,
            requires_api_key=True,
            env_vars=("MOUSER_API_KEY",),
            rate_limit_per_day=1000,
            rate_limit_per_minute=30,
            live=True,
            verified_against_live_api=False,
            notes="Field names checked against the published Swagger schema; "
                  "never run against the live service from here. Read the terms "
                  "before commercial use.",
        )

    def usable(self, environment=None) -> tuple:
        blocked = self.capabilities.blocked_reason(
            environment if environment is not None else self._environment)
        return (not blocked, blocked or "usable")

    # ------------------------------------------------------------------ http
    def _throttle(self) -> None:
        """Thirty a minute means one every two seconds. Waiting is the whole
        mechanism: there is no version of this that goes faster, and pretending
        otherwise gets a key revoked."""
        gap = 60.0 / (self.capabilities.rate_limit_per_minute or 30)
        waited = time.monotonic() - self._last_call
        if self._last_call and waited < gap:
            self._sleep(gap - waited)
        self._last_call = time.monotonic()

    def _post(self, path: str, body: dict) -> dict:
        self._throttle()
        url = f"{API_ROOT}/{path}?" + urllib.parse.urlencode({"apiKey": self._api_key})
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST")
        try:
            with self._opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The status only. The URL carries the key, and an error message is
            # the most likely thing in this program to end up in a bug report.
            raise RuntimeError(f"Mouser returned HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"could not reach Mouser ({exc.__class__.__name__})") from None
        except json.JSONDecodeError:
            raise RuntimeError("Mouser sent a response that was not JSON") from None
        self.calls_made += 1
        return payload

    # --------------------------------------------------------------- lookup
    def lookup(self, mpn: str) -> Lookup:
        wanted = normalise_mpn(mpn)
        if not wanted:
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED,
                          reason="no part number given")
        usable, why = self.usable()
        if not usable:
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED, reason=why)

        try:
            payload = self._post("search/partnumber", {
                "SearchByPartRequest": {
                    "mouserPartNumber": mpn,
                    "partSearchOptions": "Exact",
                }
            })
        except RuntimeError as exc:
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED, reason=str(exc))

        errors = payload.get("Errors") or []
        if errors:
            message = "; ".join(str(e.get("Message", e)) for e in errors[:2])
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED,
                          reason=f"Mouser reported: {message}")

        parts = (payload.get("SearchResults") or {}).get("Parts") or []
        if not parts:
            return Lookup(query=mpn, outcome=Outcome.NOT_FOUND)

        records = [self._record(part) for part in parts]
        exact = [r for r in records
                 if normalise_mpn(r.manufacturer_part_number) == wanted]
        if exact:
            return Lookup(query=mpn, outcome=Outcome.MATCHED, record=exact[0],
                          candidates=tuple(r for r in records if r not in exact))
        # Mouser answered with parts, none of which is the one asked for. That
        # is not a match and must never be silently treated as one: a suffix
        # difference is usually a different reel, tape or temperature grade.
        return Lookup(query=mpn, outcome=Outcome.CANDIDATES,
                      candidates=tuple(records[:5]))

    def _record(self, part: dict) -> PartRecord:
        # `IsDiscontinued` is a separate signal from `LifecycleStatus` and both
        # appear in the published schema. A part can carry a blank or cheerful
        # lifecycle string and still be flagged discontinued, so the two are
        # read together and the worse reading wins -- the same rule
        # `read_lifecycle` applies within a single string.
        status = part.get("LifecycleStatus") or ""
        discontinued = str(part.get("IsDiscontinued", "")).strip().lower()
        lifecycle = read_lifecycle(status)
        if discontinued in ("true", "yes", "1"):
            lifecycle = Lifecycle.OBSOLETE
            status = (status + " (Mouser: discontinued)").strip()

        return PartRecord(
            manufacturer_part_number=part.get("ManufacturerPartNumber", ""),
            manufacturer=part.get("Manufacturer", ""),
            description=part.get("Description", ""),
            lifecycle=lifecycle,
            lifecycle_text=status,
            datasheet_url=part.get("DataSheetUrl", ""),
            # There is no `Package` field in the published schema -- the first
            # version of this looked for one and always fell through to
            # Category. Package is one of the ProductAttributes when present.
            package=_attribute(part, "package") or part.get("Category", ""),
            suggested_replacement=part.get("SuggestedReplacement", "") or "",
            offers=(self._offer(part),),
        )

    def _offer(self, part: dict) -> Offer:
        breaks = []
        for entry in part.get("PriceBreaks") or []:
            price = parse_money(entry.get("Price"))
            quantity = _as_int(entry.get("Quantity"))
            if price is None or not quantity:
                continue
            breaks.append(PriceBreak(quantity=quantity, unit_price=price,
                                     currency=entry.get("Currency", "USD")))
        breaks.sort(key=lambda b: b.quantity)

        lead = part.get("LeadTime") or ""
        lead_days = _as_int(lead) if "day" in str(lead).lower() else None
        if lead_days is None and "week" in str(lead).lower():
            weeks = _as_int(lead)
            lead_days = weeks * 7 if weeks else None

        return Offer(
            distributor="mouser",
            distributor_part_number=part.get("MouserPartNumber", ""),
            url=part.get("ProductDetailUrl", ""),
            stock=_as_int(part.get("AvailabilityInStock")
                          if part.get("AvailabilityInStock") is not None
                          else part.get("Availability")),
            price_breaks=tuple(breaks),
            minimum_quantity=_as_int(part.get("Min")) or 1,
            order_multiple=_as_int(part.get("Mult")) or 1,
            lead_time_days=lead_days,
            packaging=part.get("Packaging", "") or "",
            currency=breaks[0].currency if breaks else "USD",
            fetched_at=self._now(),
        )
