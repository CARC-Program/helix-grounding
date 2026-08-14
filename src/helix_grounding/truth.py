"""
GroundTruth — the set of values a generated text is allowed to state.

The caller builds this from real data. Nothing in this module infers,
estimates, or guesses; if a value is not put in here explicitly, text
containing it is ungrounded. That strictness is deliberate and is the
only reason the verdict means anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .claims import ClaimKind

# Per-kind comparison tolerance. Currency is compared to the half-cent
# because models legitimately round; measurements to a tenth of a unit
# for the same reason. Identifiers and quantities are exact -- there is
# no such thing as an approximately correct part number.
DEFAULT_TOLERANCES: dict[ClaimKind, float] = {
    ClaimKind.CURRENCY: 0.005,
    ClaimKind.MEASUREMENT: 0.05,
    ClaimKind.PERCENTAGE: 0.05,
    ClaimKind.QUANTITY: 0.0,
    ClaimKind.IDENTIFIER: 0.0,
    ClaimKind.DATE: 0.0,
}

# Kinds compared as exact strings rather than numbers with a tolerance. There
# is no such thing as an approximately correct part number, and a due date is
# either the due date or it is a different day.
TOKEN_KINDS: frozenset[ClaimKind] = frozenset({ClaimKind.IDENTIFIER, ClaimKind.DATE})


@dataclass
class GroundTruth:
    """Allowed values, bucketed by claim kind and (for measurements) unit.

    Measurements are keyed by unit so that a width stated in millimetres
    cannot be validated against a power figure in watts that happens to
    share a numeric value. Callers who genuinely want a shared pool
    across units can pass ``unit=""`` when allowing values, which acts as
    a wildcard.
    """

    _numeric: dict[tuple[ClaimKind, str], set[float]] = field(default_factory=dict)
    _tokens: dict[ClaimKind, set[str]] = field(default_factory=dict)
    tolerances: dict[ClaimKind, float] = field(
        default_factory=lambda: dict(DEFAULT_TOLERANCES)
    )
    unchecked_kinds: set[ClaimKind] = field(default_factory=set)

    # ---- building -------------------------------------------------

    def allow(self, kind: ClaimKind, value: float, unit: str = "") -> "GroundTruth":
        """Permit one numeric value. Returns self so calls can chain."""
        self._numeric.setdefault((kind, unit), set()).add(float(value))
        return self

    def allow_many(self, kind: ClaimKind, values, unit: str = "") -> "GroundTruth":
        for value in values:
            self.allow(kind, value, unit)
        return self

    def allow_token(self, token: str, kind: ClaimKind = ClaimKind.IDENTIFIER) -> "GroundTruth":
        """Permit one exact-match value — an identifier or a date.

        Identifiers are stored twice: verbatim and with separators stripped,
        so "SHT31-DIS-B" still matches when a model writes "SHT31DISB".
        Dates are stored as given, because they arrive already normalised to
        ISO and stripping their hyphens would only invite a false match.
        """
        if not token:
            return self
        bucket = self._tokens.setdefault(kind, set())
        bucket.add(token.upper())
        if kind is ClaimKind.IDENTIFIER:
            bucket.add(token.replace("-", "").replace("/", "").upper())
        return self

    def allow_tokens(self, tokens, kind: ClaimKind = ClaimKind.IDENTIFIER) -> "GroundTruth":
        for token in tokens:
            self.allow_token(token, kind)
        return self

    def allow_date(self, value) -> "GroundTruth":
        """Permit one date. Accepts an ISO string or anything with
        ``.isoformat()`` — a ``date`` or ``datetime`` passes straight through,
        so callers need not stringify their own data first."""
        if value is None:
            return self
        iso = value.isoformat()[:10] if hasattr(value, "isoformat") else str(value)
        return self.allow_token(iso, ClaimKind.DATE)

    def allow_dates(self, values) -> "GroundTruth":
        for value in values:
            self.allow_date(value)
        return self

    def allow_pairwise_differences(
        self, kind: ClaimKind, values, unit: str = "", absolute: bool = True
    ) -> "GroundTruth":
        """Permit every pairwise difference between the given values.

        A report comparing two parts will legitimately state the gap
        between them ("$0.70 cheaper", "14 days faster"). Before this
        existed, every such comparison had to be pre-computed and
        allow()-ed by hand, and the ones that got missed were reported as
        fabrications. That was the single largest source of false
        positives in the original Helix validator.

        Cost is O(n^2); with a large value set, prefer allowing the
        specific differences the prompt actually supplies.
        """
        materialised = [float(v) for v in values]
        for a, b in combinations(materialised, 2):
            delta = a - b
            self.allow(kind, abs(delta) if absolute else delta, unit)
            if not absolute:
                self.allow(kind, -delta, unit)
        return self

    def allow_total(self, kind: ClaimKind, values, unit: str = "") -> "GroundTruth":
        """Permit the sum of the given values — a report almost always
        states its own total."""
        return self.allow(kind, sum(float(v) for v in values), unit)

    def skip(self, kind: ClaimKind) -> "GroundTruth":
        """Declare a kind unchecked.

        Use when the caller genuinely has no ground truth for a category
        — a narrative allowed to cite external percentages, say. The
        verifier records skipped kinds in its report so that "we verified
        this" never silently means "we verified some of this".
        """
        self.unchecked_kinds.add(kind)
        return self

    # ---- querying -------------------------------------------------

    def permits(self, kind: ClaimKind, value: float | str, unit: str = "") -> bool:
        if kind in TOKEN_KINDS:
            token = str(value)
            allowed = self._tokens.get(kind, set())
            if token.upper() in allowed:
                return True
            if kind is ClaimKind.IDENTIFIER:
                return token.replace("-", "").replace("/", "").upper() in allowed
            return False

        tolerance = self.tolerances.get(kind, 0.0)
        candidates: set[float] = set()
        candidates |= self._numeric.get((kind, unit), set())
        if unit:
            candidates |= self._numeric.get((kind, ""), set())  # wildcard pool

        numeric_value = float(value)
        return any(abs(numeric_value - allowed) <= tolerance for allowed in candidates)

    def is_empty(self) -> bool:
        return not self._numeric and not any(self._tokens.values())

    def describe(self) -> str:
        """Human-readable summary — useful when a verdict is surprising
        and the real problem is an under-populated ground truth."""
        parts = []
        for (kind, unit), values in sorted(
            self._numeric.items(), key=lambda kv: (kv[0][0].value, kv[0][1])
        ):
            label = f"{kind.value}[{unit}]" if unit else kind.value
            parts.append(f"{label}: {len(values)} values")
        for kind in sorted(self._tokens, key=lambda k: k.value):
            if self._tokens[kind]:
                parts.append(f"{kind.value}: {len(self._tokens[kind])} tokens")
        if self.unchecked_kinds:
            skipped = ", ".join(sorted(k.value for k in self.unchecked_kinds))
            parts.append(f"unchecked: {skipped}")
        return "; ".join(parts) if parts else "empty"
