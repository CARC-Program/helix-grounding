"""
What the agent may do on its own, and what it may never do at all.

This is the permission model from the operator's own specification, made
structural. The spec says:

    "This is NOT a spam bot. Do not build browser automation, CAPTCHA bypasses,
    rate-limit evasion, account farming, fake engagement, automated
    upvotes/downvotes, automated follows, or bulk unsolicited DMs."

    "Consequential commercial actions must remain behind an explicit human
    approval gate."

    "The agent should NEVER silently upgrade an action from Level 2/3 to
    automatic."

A comment saying that would be a comment. Here the forbidden actions cannot be
*registered* -- `Task` refuses to construct one -- so the failure happens at
import time on the machine of whoever tried, rather than silently at three in
the morning on somebody's account.

Two reasons this matters, and only one of them is ethics.

The other is that `BUSINESS_MODEL.md` names four viable channels and says the
only acceptable ones are structural: a package registry, a searchable
repository, a presence where the buyers already are. Automated voting and
following get an account banned from exactly those places. The distribution
this business depends on is the thing that automated engagement destroys first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum


class Level(IntEnum):
    """How much rope a task gets.

    Ordered so a comparison reads naturally: anything above AUTOMATIC needs a
    person, and the runner compares rather than matching on names.
    """

    AUTOMATIC = 1   # read-only, local, reversible. Runs unattended.
    NOTIFY = 2      # acts, then says so. Nothing outward-facing.
    APPROVE = 3     # never happens without a person saying yes, each time.


# Actions this agent will not perform, whatever it is asked. Matched against a
# task's name and description, because the point is to catch the intent rather
# than one spelling of it.
#
# Each entry is here for a stated reason, not out of general caution:
FORBIDDEN = {
    # Platform rules prohibit automated voting outright, on every service that
    # has votes. It is also the definition of fake engagement.
    "vote": "automated voting is prohibited by every platform that has votes",
    "upvote": "automated voting is prohibited by every platform that has votes",
    "downvote": "automated voting is prohibited by every platform that has votes",
    "like": "automated liking is fake engagement and gets accounts banned",
    "dislike": "automated disliking is fake engagement and gets accounts banned",
    # Following at machine speed is the classic growth-hack ban trigger.
    "follow": "automated following is a ban trigger on every platform",
    "unfollow": "automated follow/unfollow cycling is a ban trigger",
    # Account farming. Never, under any framing.
    "create account": "creating accounts automatically is account farming",
    "register account": "creating accounts automatically is account farming",
    "signup": "creating accounts automatically is account farming",
    # Volume messaging.
    "bulk dm": "bulk unsolicited messaging is spam",
    "mass message": "bulk unsolicited messaging is spam",
    "repost": "reposting the same content is spam and works once at best",
    # Getting around the controls rather than working within them.
    "captcha": "working around a CAPTCHA is circumventing a platform control",
    "bypass": "circumventing a platform control is out of scope, always",
    "evade": "evading a rate limit is out of scope, always",
    "scrape": "use a documented API or do not use the service",
    "sock puppet": "operating additional identities is deception",
    "astroturf": "manufactured grassroots support is deception",
}

# Words that make an otherwise-fine task outward-facing. A task naming one of
# these cannot be AUTOMATIC: it reaches somebody who did not ask for it.
#
# "release" was in this list and had to come out. It fired on the first real
# task registered -- "release gate", which reads the working tree, the history
# and the built artifacts and sends nothing anywhere. The act that reaches
# people is publishing or uploading, and both are already here; "release" on
# its own catches the check as well as the thing checked.
#
# The alternative was renaming the task to get past the guard, which is worse
# than a false positive: it teaches whoever comes next to word around the
# check rather than fix it.
OUTWARD = ("post", "comment", "reply", "publish", "send", "email", "submit",
           "upload", "tweet", "message", "pay", "purchase", "order",
           "charge", "subscribe")


class Forbidden(ValueError):
    """Raised when somebody tries to define a task that must not exist."""


def _forbidden_reason(text: str) -> str:
    lowered = " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()) + " "
    for phrase, reason in FORBIDDEN.items():
        if f" {phrase} " in lowered:
            return f"{phrase!r}: {reason}"
    return ""


def _is_outward(text: str) -> bool:
    lowered = " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()) + " "
    return any(f" {word} " in lowered for word in OUTWARD)


@dataclass(frozen=True)
class Task:
    """One thing the agent can do, with the rope it is allowed.

    Construction is the gate. A task whose name or description describes a
    forbidden action cannot be built, so a future contributor adding
    ``Task("like recent posts", ...)`` gets an exception on their own machine
    rather than a working feature.
    """

    name: str
    description: str
    level: Level
    run: object = None                 # callable; None for declared-only tasks
    every_hours: float = 24.0
    tags: tuple = field(default_factory=tuple)

    def __post_init__(self):
        blocked = _forbidden_reason(f"{self.name} {self.description}")
        if blocked:
            raise Forbidden(
                f"refusing to define the task {self.name!r} -- {blocked}. "
                f"This is not a setting; see helix_auto/levels.py.")

        # An outward-facing task cannot be automatic. This is the "never
        # silently upgrade" rule, enforced where the level is chosen rather
        # than where it is used.
        if self.level is Level.AUTOMATIC and _is_outward(
                f"{self.name} {self.description}"):
            raise Forbidden(
                f"the task {self.name!r} reaches somebody outside this machine, "
                f"so it cannot be Level.AUTOMATIC. Use Level.APPROVE.")

    @property
    def needs_a_person(self) -> bool:
        return self.level > Level.AUTOMATIC


def describe_boundaries() -> str:
    """What the agent will and will not do, for printing at people.

    Kept as output rather than documentation because the useful moment for
    this is when somebody asks the agent to do something it will not do.
    """
    lines = [
        "What runs unattended (Level 1): reading, measuring, drafting, testing.",
        "  Nothing that leaves this machine.",
        "",
        "What runs and then tells you (Level 2): local changes worth knowing about.",
        "",
        "What waits for you (Level 3): anything that posts, sends, publishes,",
        "  spends money, or touches an account. Every time, not once.",
        "",
        "What will not be built at all, and why:",
    ]
    seen = set()
    for phrase, reason in FORBIDDEN.items():
        if reason in seen:
            continue
        seen.add(reason)
        lines.append(f"  - {reason}")
    lines += [
        "",
        "That list is not caution. Automated engagement gets an account banned",
        "from the communities that are this project's only distribution, and",
        "BUSINESS_MODEL.md names four of them in total.",
    ]
    return "\n".join(lines)
