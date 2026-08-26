"""
Digi-Key's Product Information API, version 4.

Two-legged OAuth: a client id and secret are exchanged for a bearer token at
``https://api.digikey.com/v1/oauth2/token``, and that token lasts ten minutes.
Ten minutes is short enough that a long BOM run will cross the boundary, so the
token is refreshed on demand and a little early rather than after a request has
already failed.

Every Product Information call carries the bearer token *and* an
``X-DIGIKEY-Client-Id`` header; sending one without the other is rejected, which
is a mistake worth making only once.

**Not run against the live API from here**, for the same reason as Mouser:
credentials require an account, and the account terms are the account holder's
to read and accept. Parsing is tested against recorded fixtures.
``verified_against_live_api`` is False and the report says so.

Set ``DIGIKEY_CLIENT_ID`` and ``DIGIKEY_CLIENT_SECRET``. Setting
``DIGIKEY_SANDBOX=1`` points everything at Digi-Key's sandbox host, which is the
right way to try this out without touching production quota.
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
    Lookup,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
    normalise_mpn,
    parse_money,
    read_lifecycle,
)

PRODUCTION_HOST = "https://api.digikey.com"
SANDBOX_HOST = "https://sandbox-api.digikey.com"
TERMS_URL = "https://developer.digikey.com/terms"

# Tokens live ten minutes. Renewing with a minute to spare costs one extra call
# an hour and removes a whole class of failure that only appears on long runs.
TOKEN_MARGIN_SECONDS = 60


class DigiKeyDistributor:
    """Look parts up at Digi-Key. Read-only; there is no ordering method."""

    def __init__(self, environment=None, opener=None, sleep=time.sleep,
                 now=None, monotonic=time.monotonic):
        self._environment = environment if environment is not None else os.environ
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic
        self._token = ""
        self._token_expires_at = 0.0
        self.calls_made = 0

    @property
    def _host(self) -> str:
        return (SANDBOX_HOST if self._environment.get("DIGIKEY_SANDBOX")
                else PRODUCTION_HOST)

    @property
    def capabilities(self) -> Capabilities:
        sandbox = bool(self._environment.get("DIGIKEY_SANDBOX"))
        return Capabilities(
            key="digikey",
            display_name="Digi-Key" + (" (sandbox)" if sandbox else ""),
            terms_url=TERMS_URL,
            requires_api_key=True,
            env_vars=("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"),
            rate_limit_per_day=1000,
            live=True,
            verified_against_live_api=False,
            notes="Written from the published v4 API shape; never run against "
                  "the live service from here. Set DIGIKEY_SANDBOX=1 to try it "
                  "without touching production quota.",
        )

    def usable(self, environment=None) -> tuple:
        blocked = self.capabilities.blocked_reason(
            environment if environment is not None else self._environment)
        return (not blocked, blocked or "usable")

    # ------------------------------------------------------------------ auth
    def _access_token(self) -> str:
        if self._token and self._monotonic() < self._token_expires_at:
            return self._token
        body = urllib.parse.urlencode({
            "client_id": self._environment.get("DIGIKEY_CLIENT_ID", ""),
            "client_secret": self._environment.get("DIGIKEY_CLIENT_SECRET", ""),
            "grant_type": "client_credentials",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self._host}/v1/oauth2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        try:
            with self._opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 401 here means the credentials are wrong, which is worth saying
            # plainly because it is otherwise indistinguishable from a part
            # simply not existing.
            hint = " (check DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET)" \
                if exc.code in (400, 401) else ""
            raise RuntimeError(f"Digi-Key refused the credentials: "
                               f"HTTP {exc.code}{hint}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(
                f"could not reach Digi-Key ({exc.__class__.__name__})") from None
        except json.JSONDecodeError:
            raise RuntimeError("Digi-Key sent a token response that was not JSON") from None

        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Digi-Key returned no access token")
        lifetime = float(payload.get("expires_in", 600))
        self._token = token
        self._token_expires_at = self._monotonic() + max(
            lifetime - TOKEN_MARGIN_SECONDS, 30.0)
        return token

    # ------------------------------------------------------------------ http
    def _post(self, path: str, body: dict) -> dict:
        token = self._access_token()
        request = urllib.request.Request(
            f"{self._host}/{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Client-Id": self._environment.get("DIGIKEY_CLIENT_ID", ""),
                "X-DIGIKEY-Locale-Site": self._environment.get("DIGIKEY_SITE", "US"),
                "X-DIGIKEY-Locale-Language": self._environment.get("DIGIKEY_LANGUAGE", "en"),
                "X-DIGIKEY-Locale-Currency": self._environment.get("DIGIKEY_CURRENCY", "USD"),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST")
        try:
            with self._opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError("Digi-Key rate limit reached; try again later") from None
            raise RuntimeError(f"Digi-Key returned HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"could not reach Digi-Key ({exc.__class__.__name__})") from None
        except json.JSONDecodeError:
            raise RuntimeError("Digi-Key sent a response that was not JSON") from None
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
            payload = self._post("products/v4/search/keyword", {
                "Keywords": mpn,
                "Limit": 10,
                "Offset": 0,
            })
        except RuntimeError as exc:
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED, reason=str(exc))

        products = payload.get("Products") or []
        if not products:
            return Lookup(query=mpn, outcome=Outcome.NOT_FOUND)

        records = [self._record(p) for p in products]
        exact = [r for r in records
                 if normalise_mpn(r.manufacturer_part_number) == wanted]
        if exact:
            return Lookup(query=mpn, outcome=Outcome.MATCHED, record=exact[0],
                          candidates=tuple(r for r in records if r not in exact)[:4])
        return Lookup(query=mpn, outcome=Outcome.CANDIDATES,
                      candidates=tuple(records[:5]))

    @staticmethod
    def _text(value) -> str:
        """v4 wraps many fields as {"Id": n, "Name": "..."} rather than a string."""
        if isinstance(value, dict):
            return str(value.get("Name", "") or value.get("Value", "") or "")
        return "" if value is None else str(value)

    def _record(self, product: dict) -> PartRecord:
        status = self._text(product.get("ProductStatus"))
        return PartRecord(
            manufacturer_part_number=self._text(product.get("ManufacturerProductNumber")
                                                or product.get("ManufacturerPartNumber")),
            manufacturer=self._text(product.get("Manufacturer")),
            description=self._text((product.get("Description") or {}).get("ProductDescription")
                                   if isinstance(product.get("Description"), dict)
                                   else product.get("Description")),
            lifecycle=read_lifecycle(status),
            lifecycle_text=status,
            datasheet_url=self._text(product.get("DatasheetUrl")),
            package=self._text(product.get("Packaging")),
            offers=(self._offer(product),),
        )

    def _offer(self, product: dict) -> Offer:
        variations = product.get("ProductVariations") or []
        # The cut-tape or bulk variation is the one a prototype BOM wants; the
        # first listed is used when nothing says otherwise.
        variation = variations[0] if variations else {}

        breaks = []
        for entry in (variation.get("StandardPricing")
                      or product.get("StandardPricing") or []):
            price = parse_money(entry.get("UnitPrice"))
            quantity = entry.get("BreakQuantity")
            if price is None or not quantity:
                continue
            breaks.append(PriceBreak(quantity=int(quantity), unit_price=price,
                                     currency=self._environment.get(
                                         "DIGIKEY_CURRENCY", "USD")))
        breaks.sort(key=lambda b: b.quantity)

        stock = product.get("QuantityAvailable")
        if stock is None:
            stock = variation.get("QuantityAvailableforPackageType")

        return Offer(
            distributor="digikey",
            distributor_part_number=self._text(variation.get("DigiKeyProductNumber")
                                               or product.get("DigiKeyProductNumber")),
            url=self._text(product.get("ProductUrl")),
            stock=int(stock) if isinstance(stock, (int, float)) else None,
            price_breaks=tuple(breaks),
            minimum_quantity=int(variation.get("MinimumOrderQuantity") or 1),
            order_multiple=int(variation.get("StandardPackage") or 1),
            lead_time_days=(int(product["ManufacturerLeadWeeks"]) * 7
                            if str(product.get("ManufacturerLeadWeeks", "")).isdigit()
                            else None),
            packaging=self._text(variation.get("PackageType")),
            currency=self._environment.get("DIGIKEY_CURRENCY", "USD"),
            fetched_at=self._now(),
        )
