"""
Verifier — runs extractors against a GroundTruth and returns a verdict.

Also holds the generate-and-validate loop, which is the piece that turns
a checker into a safety net: unvalidated text is never returned, and a
failed attempt is fed back with its specific fabrications named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .claims import Claim, ClaimKind, GroundingReport
from .extractors import Extractor, default_extractors
from .truth import GroundTruth


class TextGenerator(Protocol):
    """Anything that turns a prompt into text.

    Kept structural rather than a base class so callers can pass an
    existing client, a lambda, or a test double without inheriting from
    this library.
    """

    def __call__(self, prompt: str) -> str: ...


@dataclass
class ValidatedGeneration:
    """The outcome of generate-and-validate.

    ``validated`` is the field that gates delivery. ``text`` is safe to
    show a customer in both branches — on failure it holds the fallback,
    never the ungrounded draft.
    """

    text: str
    validated: bool
    attempts: int
    rejected: list[GroundingReport] = field(default_factory=list)

    def audit_summary(self) -> str:
        if self.validated:
            return f"validated after {self.attempts} attempt(s)"
        reasons = "; ".join(r.summary() for r in self.rejected)
        return f"REJECTED after {self.attempts} attempt(s) — {reasons}"


DEFAULT_FALLBACK = (
    "[Automated narrative withheld: it could not be verified against the "
    "source data within the allowed number of attempts. The findings "
    "above are produced by deterministic checks and are unaffected by "
    "this — they remain safe to rely on.]"
)


class Verifier:
    """Checks generated text against a GroundTruth.

    Construct once, reuse across calls; extractors are stateless.
    """

    def __init__(self, extractors: list[Extractor] | None = None):
        self._extractors = extractors if extractors is not None else default_extractors()

    def verify(self, text: str, truth: GroundTruth) -> GroundingReport:
        """Extract every claim and partition it into grounded/ungrounded."""
        report = GroundingReport(text=text)

        if truth.is_empty():
            # An empty ground truth would mark every claim ungrounded and
            # look like catastrophic fabrication. Almost always it means
            # the caller forgot to populate it. Say so rather than
            # returning a confidently wrong verdict.
            raise ValueError(
                "GroundTruth is empty — every claim would be reported "
                "ungrounded. Populate it with the source data, or call "
                "skip() on the kinds you deliberately cannot check."
            )

        for extractor in self._extractors:
            if extractor.kind in truth.unchecked_kinds:
                if extractor.kind not in report.skipped_kinds:
                    report.skipped_kinds.append(extractor.kind)
                continue
            for claim in extractor.extract(text):
                if truth.permits(claim.kind, claim.value, claim.unit):
                    report.grounded.append(claim)
                else:
                    report.ungrounded.append(claim)

        report.ungrounded = self._deduplicate(report.ungrounded)
        return report

    @staticmethod
    def _deduplicate(claims: list[Claim]) -> list[Claim]:
        """Overlapping extractors can report the same span twice — "$36"
        is currency, and a bare "36" inside a longer measurement match
        could surface again. Keep the first, drop later claims whose span
        is contained by one already kept, so a correction note names each
        problem once."""
        kept: list[Claim] = []
        for claim in sorted(claims, key=lambda c: (c.span[0], -(c.span[1] - c.span[0]))):
            start, end = claim.span
            if any(k.span[0] <= start and end <= k.span[1] for k in kept):
                continue
            kept.append(claim)
        return kept

    def generate_validated(
        self,
        generate: TextGenerator,
        prompt: str,
        truth: GroundTruth,
        max_attempts: int = 3,
        fallback: str = DEFAULT_FALLBACK,
        on_reject: Callable[[GroundingReport], None] | None = None,
    ) -> ValidatedGeneration:
        """Generate, verify, and retry with a correction — never return
        unvalidated text.

        ``on_reject`` fires for each failed attempt, which is where an
        audit log hooks in. Rejections are recorded rather than
        discarded: a fabrication that happened and was caught is evidence
        the safety net is working, and throwing it away destroys the only
        data that proves it.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        rejected: list[GroundingReport] = []
        correction = ""

        for attempt in range(1, max_attempts + 1):
            text = generate(prompt + correction)
            report = self.verify(text, truth)

            if report.is_grounded:
                return ValidatedGeneration(
                    text=text, validated=True, attempts=attempt, rejected=rejected
                )

            rejected.append(report)
            if on_reject is not None:
                on_reject(report)
            correction = "\n\n" + report.correction_note()

        return ValidatedGeneration(
            text=fallback, validated=False, attempts=max_attempts, rejected=rejected
        )
