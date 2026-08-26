"""
The source-agnostic core: what every opportunity source must look like.

The point of this layer is that Reddit is one channel and not the company. That
is not an aspiration — it is already load-bearing, because Reddit's commercial
Data API requires a signed contract and the operator cannot enter one yet. A
system built directly against Reddit would currently be a system that cannot
run at all.

So the interface comes first and the sources plug into it. Two rules make that
real rather than decorative:

**Capabilities are declared, never assumed.** A source states what it can do,
including whether using it commercially needs a contract. That turns the Reddit
situation into data the system can act on — it can be listed, reported, and
refused — instead of a comment in a file somebody has to remember to read.

**There is no write method.** Not a disabled one, not one behind a flag: the
interface has no way to publish anything. A method that does not exist cannot
be called by mistake, cannot be enabled by a future refactor that looked
harmless, and cannot be reached by an agent improvising. Publishing is done by
a person from their own account, and the shape of this code should make that
the only possibility rather than merely the policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Capabilities:
    """What a source permits, as fact rather than intention.

    ``requires_contract`` is the field that matters most. Reddit's Data API
    needs a signed agreement for commercial use, which is closed to an operator
    who cannot enter contracts. Recording that here means the system can decline
    to enable a source for a stated reason, instead of failing at runtime with
    an authentication error that looks like a bug.
    """

    key: str
    display_name: str
    terms_url: str
    content_license: str
    read: bool = True
    search: bool = False
    # Deliberately absent from the interface entirely; kept here only so a
    # report can state plainly that nothing publishes.
    write: bool = False
    requires_api_key: bool = False
    requires_contract: bool = False
    contract_note: str = ""
    rate_limit_per_day: int | None = None
    attribution_required: bool = False

    def blocked_reason(self) -> str:
        """Why this source cannot be used, or an empty string if it can."""
        if self.requires_contract:
            return (f"{self.display_name} requires a signed agreement for "
                    f"commercial use. {self.contract_note}".strip())
        return ""


@dataclass(frozen=True)
class SourceItem:
    """One post, question or thread, normalised.

    Deliberately carries no author name or identifier. The workflow is "decide
    whether a human should read this thread", and that needs the thread, not
    the person. Storing an author would be retaining personal data the process
    never uses, and the licence attribution that CC BY-SA requires is satisfied
    by the canonical link, which is here.

    ``content_license`` travels with the item rather than being assumed per
    source, because the API reports it per item and a site can change it.
    """

    source: str
    external_id: str
    title: str
    body: str
    url: str
    created_at: datetime
    tags: tuple = ()
    engagement_score: int = 0
    answer_count: int = 0
    is_answered: bool = False
    content_license: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Title and body together, for matching. Title is repeated because a
        term in the title is a stronger signal than the same term buried in
        paragraph six, and this is the cheapest honest way to weight it."""
        return f"{self.title}\n{self.title}\n{self.body}"

    @property
    def age_days(self) -> float:
        delta = datetime.now(timezone.utc) - self.created_at
        return delta.total_seconds() / 86400


class OpportunitySource(ABC):
    """A place worth watching.

    Implementations provide reading and searching. There is no publish, post,
    comment, vote or message method, and adding one would be a change to this
    base class that a reviewer would have to approve on purpose.
    """

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    @abstractmethod
    def collect(self, query: str = "", limit: int = 25) -> list:
        """Return normalised ``SourceItem`` objects. Read-only."""

    def usable(self) -> tuple:
        """``(ok, reason)``. False means do not call ``collect``."""
        blocked = self.capabilities.blocked_reason()
        return (not blocked, blocked or "usable")
