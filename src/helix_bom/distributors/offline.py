"""
A stand-in distributor, for the demo and for tests.

This exists so `helix-bom enrich` can be shown working to somebody who has no
API key, and so the test suite never touches the network. It is the most
dangerous file in this package, because plausible-looking prices attached to
real part numbers are exactly what somebody quotes by accident.

So three things are true of it and enforced by tests:

**It says it is not live.** ``capabilities.live`` is False, and the enrichment
report prints a banner at the top saying the numbers are invented.

**It knows almost nothing, and says so.** Six parts. Anything else comes back
NOT_CHECKED -- never NOT_FOUND, because "a distributor answered and does not
sell this" is a claim six invented parts cannot support. Run against a real BOM
before that was fixed, it produced nine CRITICAL findings against parts every
distributor on earth stocks.

**It is never selected automatically.** The CLI uses it only when explicitly
asked with ``--offline``, or by the demo, which announces itself.

The part numbers below are real and the manufacturers are real. The prices,
stock levels and lead times are invented, and the numbers are chosen to be
faintly implausible for that reason -- nothing here is a market price.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from .base import (
    Capabilities,
    Lifecycle,
    Lookup,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
    normalise_mpn,
)

NOTICE = ("offline demonstration data -- invented prices and stock, "
          "not from any distributor")


def _offer(stock, breaks, minimum=1, lead=None, now=None):
    return Offer(
        distributor="offline",
        distributor_part_number="DEMO-" + str(abs(hash(str(breaks))) % 100000),
        url="",
        stock=stock,
        price_breaks=tuple(PriceBreak(quantity=q, unit_price=Decimal(p))
                           for q, p in breaks),
        minimum_quantity=minimum,
        lead_time_days=lead,
        packaging="demo",
        fetched_at=now or datetime.now(timezone.utc),
    )


def _catalogue(now=None):
    return {
        "BME280": PartRecord(
            manufacturer_part_number="BME280", manufacturer="Bosch",
            description="Humidity, pressure and temperature sensor",
            lifecycle=Lifecycle.ACTIVE, lifecycle_text="Active",
            package="LGA-8",
            offers=(_offer(4210, [(1, "7.77"), (10, "6.66"), (100, "5.55")], now=now),)),
        "BME680": PartRecord(
            manufacturer_part_number="BME680", manufacturer="Bosch",
            description="Gas, humidity, pressure and temperature sensor",
            lifecycle=Lifecycle.ACTIVE, lifecycle_text="Active",
            package="LGA-8",
            offers=(_offer(880, [(1, "9.99"), (10, "8.88")], now=now),)),
        # Deliberately obsolete, so the demo shows the check that matters most.
        "LM3914N": PartRecord(
            manufacturer_part_number="LM3914N", manufacturer="Texas Instruments",
            description="Dot/bar display driver",
            lifecycle=Lifecycle.OBSOLETE, lifecycle_text="Obsolete",
            package="DIP-18",
            offers=(_offer(0, [(1, "4.44")], lead=365, now=now),)),
        "TPS61023DRLR": PartRecord(
            manufacturer_part_number="TPS61023DRLR", manufacturer="Texas Instruments",
            description="Boost converter, 3.7A switch",
            lifecycle=Lifecycle.ACTIVE, lifecycle_text="Active",
            package="SOT-563",
            offers=(_offer(15000, [(1, "1.11"), (100, "0.88"), (1000, "0.66")],
                           now=now),)),
        # NRND, and sold only in reels of 3000 -- the minimum-quantity check.
        "SN74LVC1G14DBVR": PartRecord(
            manufacturer_part_number="SN74LVC1G14DBVR",
            manufacturer="Texas Instruments",
            description="Single Schmitt-trigger inverter",
            lifecycle=Lifecycle.NRND, lifecycle_text="Not Recommended for New Designs",
            package="SOT-23-5",
            offers=(_offer(3000, [(3000, "0.05")], minimum=3000, now=now),)),
        "GRM188R71H104KA93D": PartRecord(
            manufacturer_part_number="GRM188R71H104KA93D", manufacturer="Murata",
            description="100nF 50V X7R 0603 capacitor",
            lifecycle=Lifecycle.ACTIVE, lifecycle_text="Active",
            package="0603",
            offers=(_offer(220000, [(1, "0.22"), (100, "0.11"), (1000, "0.055")],
                           now=now),)),
    }


class OfflineDistributor:
    """Six parts, invented prices, and a loud label."""

    def __init__(self, now=None):
        self._now = now
        self._parts = _catalogue(now)
        self.calls_made = 0

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            key="offline",
            display_name="offline demo data",
            terms_url="",
            requires_api_key=False,
            env_vars=(),
            live=False,
            verified_against_live_api=False,
            notes=NOTICE,
        )

    def usable(self, environment=None) -> tuple:
        return (True, "usable")

    def lookup(self, mpn: str) -> Lookup:
        wanted = normalise_mpn(mpn)
        if not wanted:
            return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED,
                          reason="no part number given")
        self.calls_made += 1
        record = self._parts.get(wanted)
        if record:
            return Lookup(query=mpn, outcome=Outcome.MATCHED, record=record)

        # A near match is offered as a candidate and never as a match, which is
        # the behaviour the live adapters have and the one worth demonstrating:
        # TPS61023DRLR and TPS61023DRLT are different orderable parts.
        stem = wanted[:-1]
        if len(stem) >= 6:
            near = [r for key, r in self._parts.items() if key.startswith(stem)]
            if near:
                return Lookup(query=mpn, outcome=Outcome.CANDIDATES,
                              candidates=tuple(near))

        # Never NOT_FOUND. That verdict means "a distributor answered and does
        # not sell this", and six invented parts cannot support it. Run against
        # a real BOM this returned nine CRITICAL "no distributor has this part
        # number" findings for STM32F401RET6, RC0603FR-0710KL and seven others
        # that every distributor on earth stocks -- a demo catalogue passing
        # itself off as the market. NOT_CHECKED is the true answer.
        return Lookup(query=mpn, outcome=Outcome.NOT_CHECKED,
                      reason="the offline demo catalogue holds six parts and "
                             "this is not one of them -- nothing real was asked")
