"""
What a distributor is, from this tool's point of view.

The evidence for building this is in `docs/DEMAND_EVIDENCE.md`. Twenty answers
were read across eight questions about getting a usable bill of materials out of
a CAD tool, and the accepted answer to "can I order components from a BOM?" was
*yes, vendor import works fine — as long as you have a manufacturer part number
in there*. Every distributor already solves ordering. Nobody solves arriving at
the ordering step with part numbers that are correct.

So this layer has one job: **take what the BOM claims and check it against
somebody who actually sells the part.**

Three rules shape everything here, and all three exist because of specific
failures this project has already had.

**Nothing is ever invented.** A language model asked for a part number produces
a plausible one; that is the failure `components.py` was written to prevent and
it is the reason this library exists at all. If a part cannot be looked up, the
answer is "not looked up", never a guess and never silence.

**"Not found" and "not checked" are different answers.** A BOM review that
reports a clean bill because it had no API key is the same lie as the physical
fit check that passed on a BOM with no dimensions in it. `Outcome` has three
values, not two, and the report counts them separately.

**A cached price is not a current price.** Stock and pricing go stale in hours.
Every offer carries the moment it was fetched, and the report says how old it is
rather than presenting yesterday's number as today's.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum


class Outcome(str, Enum):
    """What happened when a part was looked up.

    ``NOT_CHECKED`` is the one that matters. Without it, a run with no API key
    produces a report full of "not found" and somebody concludes their part
    numbers are wrong when in fact nothing was ever asked.
    """

    MATCHED = "matched"           # the distributor sells exactly this part
    CANDIDATES = "candidates"     # near matches only; a human must choose
    NOT_FOUND = "not found"       # the distributor answered, and has no such part
    NOT_CHECKED = "not checked"   # no key, no network, quota spent, or an error


class Lifecycle(str, Enum):
    ACTIVE = "active"
    NRND = "not recommended for new designs"
    OBSOLETE = "obsolete"
    UNKNOWN = "unknown"


# What distributors call the states, mapped to what this tool calls them. Kept
# as data because every distributor words it differently and the differences are
# not interesting -- "Obsolete", "EOL" and "Discontinued at Digi-Key" all mean
# the board cannot be built from this part.
LIFECYCLE_WORDS = {
    Lifecycle.OBSOLETE: ("obsolete", "eol", "end of life", "discontinued",
                         "not manufactured", "inactive"),
    Lifecycle.NRND: ("nrnd", "not recommended", "last time buy", "ltb"),
    Lifecycle.ACTIVE: ("active", "new product", "preliminary", "production"),
}


def read_lifecycle(text: str) -> Lifecycle:
    """Map a distributor's own wording onto a state, or admit it is unknown.

    Order matters: "Not Recommended for New Designs" contains neither
    "obsolete" nor plain "active", but a status like "Active - NRND" contains
    both, and the worse reading is the safe one.
    """
    if not text:
        return Lifecycle.UNKNOWN
    lowered = text.strip().lower()
    for state in (Lifecycle.OBSOLETE, Lifecycle.NRND, Lifecycle.ACTIVE):
        if any(word in lowered for word in LIFECYCLE_WORDS[state]):
            return state
    return Lifecycle.UNKNOWN


_MONEY = re.compile(r"[-+]?\d[\d\s.,]*")


def parse_money(text) -> Decimal | None:
    """Read a price out of whatever the distributor sent.

    Prices arrive as "$0.19", "0,19 €", "1.234,56" and "1,234.56", and the last
    two are the same number written by different halves of the world. Getting
    this wrong by a factor of a thousand on a thousand-piece reel is not a
    rounding error, so the ambiguous cases are worked out from the position of
    the separators rather than assumed.

    Returns None rather than zero when nothing can be read. Zero is a price.
    """
    if text is None:
        return None
    if isinstance(text, (int, float, Decimal)):
        try:
            return Decimal(str(text))
        except InvalidOperation:
            return None
    match = _MONEY.search(str(text))
    if not match:
        return None
    raw = match.group(0).strip().replace(" ", "")

    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        # Both present: whichever comes last is the decimal separator.
        if last_comma > last_dot:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif last_comma >= 0:
        # Only commas. "1,234" is a thousands group; "0,19" is a decimal. The
        # tell is how many digits follow the final comma.
        raw = raw.replace(",", "" if len(raw) - last_comma - 1 == 3 else ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def normalise_mpn(mpn: str) -> str:
    """Fold a part number for comparison, conservatively.

    Case and surrounding whitespace are noise. Nothing else is touched, and
    that restraint is the point: TPS61023DRLR and TPS61023DRLT differ only in
    the reel size and are different orderable parts. A normaliser clever enough
    to call those equal would quietly approve a BOM that cannot be assembled.
    Near matches are reported as candidates for a person to judge, never folded
    into a match here.
    """
    return (mpn or "").strip().upper()


@dataclass(frozen=True)
class PriceBreak:
    quantity: int
    unit_price: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class Offer:
    """One distributor's terms for one part."""

    distributor: str
    distributor_part_number: str
    url: str
    stock: int | None = None            # None means "not stated", which is not zero
    price_breaks: tuple = ()
    minimum_quantity: int = 1
    order_multiple: int = 1
    lead_time_days: int | None = None
    packaging: str = ""
    currency: str = "USD"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def unit_price_at(self, quantity: int) -> Decimal | None:
        """The price actually paid per unit when buying ``quantity``.

        The whole reason this exists: a BOM that costed every line at the
        single-unit price is wrong by a factor of two or three on a real build,
        and one that costed at the thousand-piece price is wrong the other way
        and will not survive contact with a purchase order.
        """
        eligible = [b for b in self.price_breaks if b.quantity <= quantity]
        if not eligible:
            return None
        return max(eligible, key=lambda b: b.quantity).unit_price

    def extended_price_at(self, quantity: int) -> Decimal | None:
        unit = self.unit_price_at(quantity)
        return None if unit is None else unit * Decimal(quantity)

    def age_hours(self, now=None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.fetched_at).total_seconds() / 3600


@dataclass(frozen=True)
class PartRecord:
    """What a distributor knows about one part."""

    manufacturer_part_number: str
    manufacturer: str = ""
    description: str = ""
    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    lifecycle_text: str = ""            # the distributor's own wording, kept verbatim
    datasheet_url: str = ""
    package: str = ""
    offers: tuple = ()

    @property
    def best_offer(self):
        return self.offers[0] if self.offers else None


@dataclass(frozen=True)
class Lookup:
    """The result of asking about one part number.

    ``reason`` is required whenever the outcome is NOT_CHECKED, because a
    report that says "not checked" without saying why gives the reader nothing
    to act on -- and the action is different for a missing key, a dead network
    and a spent quota.
    """

    query: str
    outcome: Outcome
    record: PartRecord | None = None
    candidates: tuple = ()
    reason: str = ""

    def __post_init__(self):
        if self.outcome is Outcome.NOT_CHECKED and not self.reason:
            raise ValueError("a NOT_CHECKED lookup must say why it was not checked")


@dataclass(frozen=True)
class Capabilities:
    """What a distributor permits and requires, as fact rather than intention.

    Modelled on `helix_signal.sources.base.Capabilities` and for the same
    reason: a source that cannot be used should say so as data the program can
    report, not fail later with an authentication error that reads like a bug.
    """

    key: str
    display_name: str
    terms_url: str
    requires_api_key: bool = True
    env_vars: tuple = ()
    rate_limit_per_day: int | None = None
    rate_limit_per_minute: int | None = None
    live: bool = True                   # False for the offline stand-in
    verified_against_live_api: bool = False
    notes: str = ""

    def blocked_reason(self, environment) -> str:
        """Why this distributor cannot be used right now, or an empty string."""
        missing = [name for name in self.env_vars if not environment.get(name)]
        if self.requires_api_key and missing:
            return (f"{self.display_name} needs {' and '.join(missing)} in the "
                    f"environment. Register at {self.terms_url} and read the "
                    f"terms before using it commercially.")
        return ""


class Distributor(ABC):
    """Somewhere parts can be looked up.

    There is no ordering method, no cart method and no method that spends
    money. This layer answers questions about parts; buying them is a person's
    decision made on a distributor's own site, and the shape of the code should
    make that the only possibility rather than merely the policy.
    """

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    @abstractmethod
    def lookup(self, mpn: str) -> Lookup:
        """Look up one manufacturer part number. Read-only."""

    def usable(self, environment) -> tuple:
        blocked = self.capabilities.blocked_reason(environment)
        return (not blocked, blocked or "usable")
