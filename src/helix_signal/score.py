"""
Scoring, with the reasoning kept.

Two deliberate departures from the specification this was built from.

**It scores usefulness, not purchase intent.** The spec proposes a lead score
with a "Purchase Intent 0-20" term. That is the wrong instrument for this
business at this stage: `FIRST_USERS.md` is explicit that the ask is a bug
report rather than a sale, and the spec itself warns against reading every
question as a lead. So this measures a narrower and more honest thing — *is
this a discussion where the tool would genuinely help somebody?* If the answer
is yes often enough, revenue is a later conversation. If it is no, a purchase
intent score would only have been a confident number attached to nothing.

**It is deterministic and every point is attributable.** The spec says "never
make the score a black box", and a model asked to output 91 cannot tell you
which seven points it would take away if the question were a day older. These
rules can. That is also the whole argument of the product this business sells:
where a value can be computed, computing it beats asking a model to feel it.

The honest limit, stated because a scorer that oversells itself is worse than
none: keyword rules cannot read intent. A question that never says "BOM" but
describes one in longhand scores low and should not. This is a triage aid that
decides reading order for a human, not a judgement, and it must never be the
last thing between a draft and a public post.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Terms this tool can actually act on. Kept narrow on purpose: a wide list
# makes everything look relevant, which is the same as ranking nothing.
DOMAIN_TERMS = (
    "bill of materials", "bom", "netlist", "kicad", "eeschema", "altium",
    "eagle cad", "orcad", "schematic", "part number", "mpn", "manufacturer part",
    "digikey", "digi-key", "mouser", "lcsc", "octopart", "lead time",
    "supply chain", "component cost", "unit price", "assembly house",
    "pick and place", "designator", "footprint", "pcb assembly", "jlcpcb",
)

PROBLEM_LANGUAGE = (
    "wrong", "error", "incorrect", "mistake", "broken", "fails", "failed",
    "does not work", "doesn't work", "missing", "mismatch", "duplicate",
    "off by", "unexpected", "confused", "struggling", "stuck", "problem",
    "issue", "bug", "corrupt", "garbled", "inconsistent",
)

HELP_LANGUAGE = (
    "how do i", "how can i", "how to", "is there a", "any tool", "any software",
    "recommend", "suggestion", "best way", "what is the correct",
    "anyone know", "looking for", "advice", "should i",
)

# The strongest signal available, and the one with the worst failure mode.
#
# "by hand" and "manually" mean two different things depending on what is being
# discussed, and this list cannot tell them apart. In a group about bills of
# materials the hits read "whenever I export a BOM I have to manually remove
# these parts" -- software toil, exactly what is wanted. In a group about
# pick-and-place machines they read "the through-hole parts could be soldered by
# hand" and "counting manually" -- people doing physical work, which no program
# removes. Measured on those two groups: 3 of 4 hits genuine in the first, 2 of 6
# in the second.
#
# So a high manual-work rate is a reason to read the questions, never a finding
# on its own. `cluster.py` reports it as one part of five with the evidence
# attached, which is the only honest way to carry a signal this noisy.
MANUAL_WORK_LANGUAGE = (
    "by hand", "manually", "copy and paste", "copy-paste", "spreadsheet",
    "one by one", "tedious", "hours", "every time", "repetitive", "script to",
)


@dataclass(frozen=True)
class Contribution:
    """One rule's verdict, with what triggered it."""

    rule: str
    points: int
    max_points: int
    evidence: str

    def line(self) -> str:
        return f"  {self.points:>3}/{self.max_points:<3} {self.rule:<22} {self.evidence}"


@dataclass
class Assessment:
    total: int
    band: str
    contributions: list = field(default_factory=list)

    def explain(self) -> str:
        header = f"score {self.total}/100 — {self.band}"
        return "\n".join([header, *(c.line() for c in self.contributions)])

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "band": self.band,
            "contributions": [
                {"rule": c.rule, "points": c.points, "max": c.max_points,
                 "evidence": c.evidence}
                for c in self.contributions
            ],
        }


def _found(text: str, terms) -> list:
    """Which terms appear, matched on word boundaries.

    Boundaries matter more than they look: without them "bom" matches
    "bombard", "bombay" and "bomb", and a scorer that fires on the wrong word
    is worse than one that misses, because it produces confident nonsense.
    """
    hits = []
    for term in terms:
        pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(term)
    return hits


def _rule_domain_fit(item, text) -> Contribution:
    hits = _found(text, DOMAIN_TERMS)
    tag_hits = [t for t in item.tags
                if t.lower() in {d.replace(" ", "-") for d in DOMAIN_TERMS}
                or t.lower() in {"bom", "kicad", "altium", "eagle", "orcad"}]
    points = min(20, len(hits) * 5 + len(tag_hits) * 5)
    evidence = (f"terms: {', '.join(hits[:4])}" if hits else "no domain terms")
    if tag_hits:
        evidence += f" | tags: {', '.join(tag_hits[:3])}"
    return Contribution("domain fit", points, 20, evidence)


def _rule_problem(item, text) -> Contribution:
    hits = _found(text, PROBLEM_LANGUAGE)
    points = min(20, len(hits) * 5)
    return Contribution("describes a problem", points, 20,
                        f"{', '.join(hits[:4])}" if hits else "no problem language")


def _rule_help_wanted(item, text) -> Contribution:
    hits = _found(text, HELP_LANGUAGE)
    points = min(15, len(hits) * 5)
    return Contribution("asking for help", points, 15,
                        f"{', '.join(hits[:3])}" if hits else "not asking")


def _rule_manual_work(item, text) -> Contribution:
    """Somebody doing by hand what a program could do is the strongest signal
    available here, and it is the one the spec names explicitly."""
    hits = _found(text, MANUAL_WORK_LANGUAGE)
    points = min(15, len(hits) * 5)
    return Contribution("manual work described", points, 15,
                        f"{', '.join(hits[:3])}" if hits else "none described")


def _rule_unanswered(item, text) -> Contribution:
    """An answered question is a closed door. An open one is where help is
    still worth something, which is the opposite of how a sales funnel would
    weight it.

    Careful with the field this reads. Stack Exchange's ``is_answered`` does not
    mean "has an accepted answer" -- it means "has an accepted answer **or** an
    answer scoring one or more". Verified against eight questions that all
    reported answered while only five had anything accepted. The wording below
    says so, because calling it "accepted" made a document draw the wrong
    conclusion once already.
    """
    if not item.is_answered and item.answer_count == 0:
        return Contribution("still unanswered", 15, 15, "no answers yet")
    if not item.is_answered:
        return Contribution("still unanswered", 8, 15,
                            f"{item.answer_count} answer(s), none accepted or upvoted")
    return Contribution("still unanswered", 0, 15, "accepted or upvoted answer")


def _rule_recency(item, text) -> Contribution:
    age = item.age_days
    if age <= 2:
        return Contribution("recent", 10, 10, f"{age:.1f} days old")
    if age <= 7:
        return Contribution("recent", 6, 10, f"{age:.1f} days old")
    if age <= 30:
        return Contribution("recent", 3, 10, f"{age:.0f} days old")
    return Contribution("recent", 0, 10, f"{age:.0f} days old — stale")


def _rule_visibility(item, text) -> Contribution:
    """A thread nobody reads helps nobody, however relevant it is."""
    score = item.engagement_score
    points = 5 if score >= 3 else 3 if score >= 1 else 0
    return Contribution("visibility", points, 5, f"score {score}")


RULES = (
    _rule_domain_fit,
    _rule_problem,
    _rule_help_wanted,
    _rule_manual_work,
    _rule_unanswered,
    _rule_recency,
    _rule_visibility,
)

# Calibrated against scored items, not against the theoretical maximum.
#
# The first version put "high" at 80 and nothing reached it. A near-ideal
# synthetic item -- on topic, unanswered, a day old, describing manual work --
# scores 70, and the best real item in the first live sample scored 55. Bands
# set against an unreachable 100 would have labelled everything "watch", which
# ranks nothing and is the same as having no bands at all.
#
# These want re-calibrating once a few hundred real items have been scored.
# Recorded here so that is a deliberate act rather than a rediscovery.
BANDS = (
    (65, "high — read this today"),
    (45, "good — worth reading"),
    (28, "watch"),
    (15, "low"),
    (0, "ignore"),
)


def band_for(total: int) -> str:
    return next(name for threshold, name in BANDS if total >= threshold)


def assess(item) -> Assessment:
    """Score one item. Pure: no network, no clock beyond the item's own age."""
    text = item.text
    contributions = [rule(item, text) for rule in RULES]
    total = sum(c.points for c in contributions)
    return Assessment(total=total, band=band_for(total), contributions=contributions)
