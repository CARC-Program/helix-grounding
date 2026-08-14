"""
Claims and reports — the vocabulary the rest of the library speaks.

A Claim is one verifiable assertion pulled out of generated text: a
number, a measurement, an identifier. A Claim is not "true" or "false" on
its own; it is only grounded or ungrounded *relative to a GroundTruth*.
That distinction is the whole design. This library never asks whether a
statement is correct in the world, only whether every checkable value in
it traces back to data the caller supplied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaimKind(str, Enum):
    """The categories of claim this library can verify deterministically.

    Deliberately narrow. Each kind here has the property that membership
    in a known set is decidable without judgement — a number either
    appears in the source data or it does not. Claims that require
    judgement (tone, completeness, whether advice is *good*) are out of
    scope by design, and belong to an LLM-as-judge layer, not this one.
    """

    CURRENCY = "currency"
    MEASUREMENT = "measurement"
    IDENTIFIER = "identifier"
    QUANTITY = "quantity"
    PERCENTAGE = "percentage"


@dataclass(frozen=True)
class Claim:
    """One extracted assertion, with enough context to point a human at it.

    ``span`` is the (start, end) offset into the source text. Carrying it
    is what lets a correction note quote the surrounding sentence instead
    of just naming a bare number, which measurably improves the odds that
    a regeneration fixes the right thing.
    """

    kind: ClaimKind
    value: float | str
    raw: str          # exactly as it appeared, e.g. "$1,250.00"
    span: tuple[int, int]
    unit: str = ""    # e.g. "mm", "W" — empty for unitless kinds

    def context(self, text: str, window: int = 60) -> str:
        """The claim's surrounding text, for human-readable reporting."""
        start = max(0, self.span[0] - window)
        end = min(len(text), self.span[1] + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end].strip()}{suffix}"

    def describe(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        return f"{self.raw} ({self.kind.value}{unit})"


@dataclass
class GroundingReport:
    """The result of verifying one piece of generated text.

    ``is_grounded`` is the only field callers must check before delivery.
    Everything else exists to explain the failure — to a retry prompt, to
    an audit log, or to a human.
    """

    text: str
    grounded: list[Claim] = field(default_factory=list)
    ungrounded: list[Claim] = field(default_factory=list)
    skipped_kinds: list[ClaimKind] = field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return not self.ungrounded

    @property
    def checked_count(self) -> int:
        return len(self.grounded) + len(self.ungrounded)

    def by_kind(self) -> dict[ClaimKind, list[Claim]]:
        """Ungrounded claims bucketed by kind — the shape the old
        check_full_grounding() returned, kept available because audit
        records and dashboards want to count failures per category."""
        buckets: dict[ClaimKind, list[Claim]] = {}
        for claim in self.ungrounded:
            buckets.setdefault(claim.kind, []).append(claim)
        return buckets

    def summary(self) -> str:
        """One line, suitable for an audit log entry."""
        if self.is_grounded:
            return f"grounded: {self.checked_count} claims verified, 0 ungrounded"
        offenders = ", ".join(c.describe() for c in self.ungrounded)
        return (
            f"UNGROUNDED: {len(self.ungrounded)} of {self.checked_count} "
            f"claims not found in source data — {offenders}"
        )

    def correction_note(self, max_quoted: int = 8) -> str:
        """A corrective instruction naming exactly what was invented.

        Feeding the specific bad values back beats a blind resample; that
        was established by field testing before this library existed
        (Helix D-040). What is new here is quoting the *context* around
        each one, so the model can locate the sentence it needs to fix
        rather than searching for a bare number.
        """
        if self.is_grounded:
            return ""

        lines = [
            "YOUR PREVIOUS ATTEMPT CONTAINED VALUES THAT DO NOT APPEAR IN "
            "THE SOURCE DATA. Each is quoted below with its surrounding "
            "text. Remove or correct every one of them, and do not "
            "introduce any other value that was not given to you:",
            "",
        ]
        for claim in self.ungrounded[:max_quoted]:
            lines.append(f'  - {claim.describe()} in: "{claim.context(self.text)}"')
        remaining = len(self.ungrounded) - max_quoted
        if remaining > 0:
            lines.append(f"  - ...and {remaining} more.")
        lines.append("")
        lines.append(
            "State only values that appear explicitly in the data provided "
            "above. If you need a value you were not given, omit the claim "
            "entirely rather than estimating it."
        )
        return "\n".join(lines)
