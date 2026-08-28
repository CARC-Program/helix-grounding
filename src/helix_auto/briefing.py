"""
One report, once a day, that is worth ten minutes.

The point is not to list what happened. It is to answer *does anything need
you today*, and on most days the honest answer is no. A briefing that
manufactures a task every morning to justify its own existence trains somebody
to stop reading it, and then it is worse than nothing.

So it says "nothing needs you" when nothing does, and it says so first.

The ordering rule is the same one `signals.py` sets: hard evidence above soft,
soft above noise. One person opening an issue outranks four hundred downloads,
because the downloads are machines. A briefing that led with the big number
would be pleasant and false every single morning, which is the failure this
project keeps finding in its own work under different names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .signals import Confidence, gather


@dataclass
class Action:
    """Something worth a person's time, with what it is for."""

    what: str
    why: str
    minutes: int = 10

    def line(self) -> str:
        return f"  [{self.minutes:>2} min] {self.what}\n           {self.why}"


@dataclass
class Briefing:
    when: datetime
    signals: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    unavailable: list = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.actions)

    def render(self) -> str:
        stamp = self.when.strftime("%Y-%m-%d %H:%M UTC")
        out = [f"Helix briefing -- {stamp}", "=" * 58, ""]

        if self.actions:
            out.append(f"{len(self.actions)} thing(s) worth your time:")
            out.extend(action.line() for action in self.actions)
        else:
            # Said plainly and first. Most days this is the true answer, and a
            # briefing that invents a task to look useful gets ignored within a
            # fortnight.
            out.append("Nothing needs you today.")
            out.append("  No new issues, no new responses, nothing broken.")
        out.append("")

        hard = [s for s in self.signals
                if s.confidence is Confidence.HARD and s.readable]
        rest = [s for s in self.signals
                if s.confidence is not Confidence.HARD and s.readable]

        out.append("what a person actually did (** = someone made an effort)")
        out.extend(s.line() for s in hard)
        if rest:
            out.append("")
            out.append("weaker signals, in descending order of meaning")
            out.extend(s.line() for s in rest)

        if self.unavailable:
            # Never printed as zero. "Could not read" and "is zero" are
            # different facts, and this whole codebase is built on not
            # conflating them.
            out.append("")
            out.append("could not be read (not the same as zero):")
            out.extend(s.line() for s in self.unavailable)
        return "\n".join(out)


def _actions_from(signals, campaign_state=None) -> list:
    """What is worth doing, derived from the numbers rather than a wish list."""
    actions = []
    by_name = {s.name: s for s in signals}

    issues = by_name.get("github open issues")
    if issues is not None and issues.readable and issues.value:
        actions.append(Action(
            f"Read and answer {issues.value} GitHub issue(s).",
            "Somebody typed sentences about your software. This is the most "
            "expensive thing anyone does for you for free.",
            minutes=20))

    ran = by_name.get("strangers who ran it")
    if ran is not None and ran.readable and ran.value == 0:
        posted = getattr(campaign_state, "posts", {}) if campaign_state else {}
        unposted = [key for key, post in posted.items()
                    if not getattr(post, "url", "")]
        if unposted:
            actions.append(Action(
                f"Post to one channel. {len(unposted)} still unposted: "
                f"{', '.join(sorted(unposted)[:3])}.",
                "Zero strangers have run it. Nothing else in this project "
                "moves until that changes, and no amount of building moves it.",
                minutes=45))
    return actions


def build(repo: str = "CARC-Program/helix-grounding", store=None,
          now=None) -> Briefing:
    signals = gather(repo=repo, store=store)
    state = None
    try:
        from helix_ops.campaign import Campaign
        state = Campaign.load(store) if store else Campaign.load()
    except Exception:                             # noqa: BLE001 - optional input
        state = None

    return Briefing(
        when=now or datetime.now(timezone.utc),
        signals=[s for s in signals if s.readable],
        unavailable=[s for s in signals if not s.readable],
        actions=_actions_from(signals, state),
    )
