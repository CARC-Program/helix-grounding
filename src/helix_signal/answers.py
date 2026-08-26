"""
Reading what the answers actually say.

`DEMAND_EVIDENCE.md` reported a group of eight BOM questions as an unmet need
and was wrong: all eight have accepted answers. The correction raised the
question this module exists for. **Answered and solved are different claims.**
An accepted answer that says "open the export dialog and tick the box" means the
problem is solved and there is nothing to build. An accepted answer that says
"write a ULP script to post-process it" means the problem is *acknowledged and
handed back to the asker*, which is the definition of an opening.

That distinction cannot be read off question metadata. It requires the answers.

The classifier below is deliberately modest, and this is the third time in this
project's history that overstating a small measurement has caused a wrong
conclusion, so it is worth being explicit: **on thirty answers, these counts are
an index, not a finding.** They exist so the reading is reproducible and so
somebody can check which words drove which label. The conclusion in the write-up
comes from reading the thirty answers, because thirty is a number a person can
read, and a keyword tally over thirty texts is a confident number attached to
almost nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .score import _found

# The answer's remedy is code the asker has to go and write. "ULP" is Eagle's
# User Language Program and is the single most common answer in this corner of
# the site, which is itself the finding.
# "manually" and "by hand" were in this list and had to come out. In a group
# about pick-and-place machines they fire on "the through-hole parts could be
# soldered by hand" and "is there a best practice for manually dealing with
# reels" -- people doing physical work, which no software removes. Three of six
# spot-checked hits were that. They never belonged here anyway: this bucket is
# about an answer telling somebody to *write code*, and hand-soldering is not
# code. The same words cause the same trouble in `score.py`, which says so.
SCRIPT_WORK = (
    "script", "ulp", "write your own", "you could write", "you can write",
    "python", "perl", "xslt", "xsl", "macro", "regex", "vba", "awk", "sed",
    "write a program", "roll your own", "post-process", "post process",
    "parse the", "parse it", "spreadsheet", "excel", "libreoffice",
    "text editor", "command line", "grep",
)

# Go and get a different program. Also an opening, but somebody else's.
ANOTHER_TOOL = (
    "kicost", "octopart", "partkeepr", "bomist", "kibom", "bom2buy",
    "third-party", "third party", "another tool", "different tool",
    "switch to", "instead use", "use instead", "an alternative", "alternative is",
    "plugin", "add-on", "addon", "extension",
)

# The tool already does it and here is where. Nothing to build.
BUILT_IN = (
    "built-in", "built in", "there is an option", "there's an option",
    "you can set", "in the menu", "export dialog", "preferences", "properties",
    "attribute", "template", "configure", "setting", "checkbox", "tick the",
    "select the", "file menu", "tools menu", "under file", "under tools",
)

# It cannot be done.
IMPOSSIBLE = (
    "not possible", "no way to", "cannot be done", "can't be done",
    "does not support", "doesn't support", "no built-in", "not supported",
    "no standard", "there is no",
)

BUCKETS = (
    ("hands back a scripting job", SCRIPT_WORK),
    ("points at another tool", ANOTHER_TOOL),
    ("points at a built-in feature", BUILT_IN),
    ("says it cannot be done", IMPOSSIBLE),
)


@dataclass(frozen=True)
class Reading:
    """One answer, with what it appears to tell the asker to do."""

    answer_id: str
    question_id: str
    label: str
    evidence: tuple
    is_accepted: bool
    score: int
    url: str
    words: int

    def line(self) -> str:
        mark = "accepted" if self.is_accepted else "        "
        return (f"  {mark} {self.score:>4}v {self.words:>5}w  {self.label:<28} "
                f"{', '.join(self.evidence[:3])}")


def read_answer(answer: dict) -> Reading:
    """Label one answer by the strongest signal in it.

    Ties go to the earlier bucket, which orders scripting above built-in
    deliberately: an answer saying "there's a template, but you'll need a script
    to fill it" is describing work, not a feature.
    """
    body = answer.get("body", "")
    best_label, best_hits = "unclear", ()
    best_count = 0
    for label, terms in BUCKETS:
        hits = _found(body, terms)
        if len(hits) > best_count:
            best_label, best_hits, best_count = label, tuple(hits), len(hits)
    return Reading(
        answer_id=answer.get("answer_id", ""),
        question_id=answer.get("question_id", ""),
        label=best_label,
        evidence=best_hits,
        is_accepted=bool(answer.get("is_accepted")),
        score=int(answer.get("score", 0)),
        url=answer.get("url", ""),
        words=len(body.split()),
    )


def tally(readings) -> dict:
    counts = {}
    for reading in readings:
        counts[reading.label] = counts.get(reading.label, 0) + 1
    return counts


def summarise(readings) -> str:
    counts = tally(readings)
    total = len(readings) or 1
    accepted = [r for r in readings if r.is_accepted]
    lines = [f"{len(readings)} answers, {len(accepted)} of them accepted"]
    for label, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        share = count / total
        lines.append(f"  {count:>3}  {share:>4.0%}  {label}")
    if accepted:
        lines.append("\namong the accepted answers only:")
        for label, count in sorted(tally(accepted).items(),
                                   key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {count:>3}  {count / len(accepted):>4.0%}  {label}")
    lines.append("\nA keyword index over a few dozen texts, not a finding. "
                 "Read the answers.")
    return "\n".join(lines)
