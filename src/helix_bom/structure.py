"""
Checks that need nothing but the file.

`enrich` shipped in 0.2.0 asking every line's part number of a distributor, and
without an API key it did nothing at all: ten lines, zero checked, one message
repeated ten times. A headline feature behind a door most people will not open,
in a project whose first-user strategy is that a stranger installs it and
reports a bug. That was a mistake in what to build, not in how.

So these checks run first, always, and never touch the network. Every one of
them is a defect that ships boards wrong, and every one is visible in the file
alone:

    no part number at all       a value and a footprint are not orderable
    a value in the MPN column   "10k" is not a part number
    a placeholder               TBD, TODO, XXX, N/A
    the same part twice         two lines, one part: ordered twice
    the same designator twice   two lines claim R1: one of them is wrong
    designators against qty     "R1, R2, R3" with a quantity of 2

The first is not a guess about what matters. `docs/DEMAND_EVIDENCE.md` reads
twenty answers to eight questions about getting a usable BOM out of a CAD tool,
and the accepted answer to "can I order components from a BOM?" is *yes, as
long as you have a manufacturer part number in there*. The commonest defect in
those questions was not a wrong part number. It was no part number.

The honest limit: these check the document, not the design. A BOM can pass every
one of them and still specify the wrong capacitor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A designator list: "R1", "R1, R2", "R1-R3", "R1..R3", "C1;C2".
DESIGNATOR_SPLIT = re.compile(r"[,;/]+|\s+(?=[A-Za-z]+\d)")
DESIGNATOR = re.compile(r"^([A-Za-z]{1,4})(\d+)$")
RANGE = re.compile(r"^([A-Za-z]{1,4})(\d+)\s*(?:-|\.\.|to|through)\s*(?:[A-Za-z]{1,4})?(\d+)$",
                   re.IGNORECASE)

# A component value rather than a part number. Deliberately narrow: it has to
# look like a quantity *with a unit* and nothing else. Real part numbers such as
# CRCW060310K0FKEA contain a value inside a longer string and must not match.
#
# The unit is required, and that requirement was added after this rule called
# 61300411121 -- a real Wurth part number -- "a value, not a part number", as a
# CRITICAL finding. Numeric part numbers are ordinary: Wurth, Molex and TE all
# use them. A bare number is far more likely to be a part number than a value,
# so it is left alone. That costs the rule "10" for a ten-ohm resistor, which is
# the right way to be wrong: a missed defect is a nuisance, and a confident
# accusation against a correct line is why people stop trusting a tool.
VALUE_LIKE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*"
    r"(?:(?P<multiplier>[pnuµmkKMGR])\s*)?"
    r"(?P<unit>[FHΩ]|ohms?|farads?|f|h|v|a|w|hz|khz|mhz|ghz|nf|uf|pf|mf|nh|uh|mh|va)?"
    r"\s*(?:[±+-]?\s*\d+(?:[.,]\d+)?\s*%)?\s*$",
    re.IGNORECASE)

PLACEHOLDERS = {
    "tbd", "tba", "todo", "to do", "xxx", "xxxx", "n/a", "na", "none", "null",
    "?", "??", "???", "-", "--", "fixme", "unknown", "tbc", "placeholder",
    "see notes", "see note", "same as above", "dnp", "0", "x",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    reference: str
    message: str
    evidence: str = ""


def _reference(component) -> str:
    return (getattr(component, "designator", "")
            or getattr(component, "manufacturer_part_number", "")
            or getattr(component, "name", "") or "?")


def expand_designators(text: str) -> list:
    """"R1, R3-R5, R9" becomes five references.

    Ranges are what makes this worth doing: a line reading "R3-R5" covers three
    parts, and comparing a raw comma count against the quantity would call that
    a mismatch on every well-formed BOM that uses them.
    """
    if not text:
        return []
    found = []
    for piece in DESIGNATOR_SPLIT.split(text):
        piece = piece.strip()
        if not piece:
            continue
        span = RANGE.match(piece)
        if span:
            prefix, first, last = span.group(1), int(span.group(2)), int(span.group(3))
            if 0 <= last - first <= 999:
                found.extend(f"{prefix.upper()}{n}" for n in range(first, last + 1))
                continue
        match = DESIGNATOR.match(piece)
        found.append(f"{match.group(1).upper()}{int(match.group(2))}"
                     if match else piece.upper())
    return found


def looks_like_a_value(text: str) -> bool:
    """True when the text is a component value rather than a part number.

    A number on its own is not enough. It must carry a multiplier or a unit --
    see the note on ``VALUE_LIKE`` for the real part number this rule accused
    before that was required.
    """
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 12:
        return False
    if not any(ch.isdigit() for ch in stripped):
        return False
    match = VALUE_LIKE.match(stripped)
    if not match:
        return False
    return bool(match.group("multiplier") or match.group("unit"))


# --------------------------------------------------------------------
# Per line
# --------------------------------------------------------------------

def _no_part_number(components) -> list:
    """The commonest thing wrong with a real BOM, and the one the archive
    points straight at. A distributor cannot quote a value and a footprint."""
    missing = [c for c in components
               if not (getattr(c, "manufacturer_part_number", "") or "").strip()]
    if not missing:
        return []
    return [Finding("critical", _reference(c),
                    "no manufacturer part number",
                    "Nothing can be looked up or ordered for this line. A value "
                    "and a footprint are not an orderable part.")
            for c in missing]


def _value_in_the_part_number(components) -> list:
    findings = []
    for component in components:
        mpn = (getattr(component, "manufacturer_part_number", "") or "").strip()
        if mpn and looks_like_a_value(mpn):
            findings.append(Finding(
                "critical", _reference(component),
                "the part number is a value, not a part number",
                f"{mpn!r} describes what the part does, not which part it is. "
                f"Two thousand different resistors are 10k."))
    return findings


def _placeholder_part_number(components) -> list:
    findings = []
    for component in components:
        mpn = (getattr(component, "manufacturer_part_number", "") or "").strip()
        if mpn and mpn.lower() in PLACEHOLDERS:
            findings.append(Finding(
                "critical", _reference(component),
                "the part number is a placeholder",
                f"{mpn!r} was never filled in."))
    return findings


# --------------------------------------------------------------------
# Across lines
# --------------------------------------------------------------------

def _repeated_part_number(components) -> list:
    """Two lines, one part. Ordered twice, and the board costed twice.

    Only reported when the part numbers match exactly and the lines are
    separate entries -- which is a merge that did not happen, not a design
    decision.
    """
    seen = {}
    for component in components:
        mpn = (getattr(component, "manufacturer_part_number", "") or "").strip().upper()
        if mpn:
            seen.setdefault(mpn, []).append(component)
    findings = []
    for mpn, group in sorted(seen.items()):
        if len(group) < 2:
            continue
        total = sum(max(int(getattr(c, "quantity", 1) or 1), 1) for c in group)
        refs = ", ".join(_reference(c) for c in group[:4])
        findings.append(Finding(
            "warning", mpn,
            f"the same part is on {len(group)} separate lines",
            f"{refs} -- {total} will be ordered in total. If that is one part "
            f"used in several places, the lines want merging."))
    return findings


def _repeated_designator(components) -> list:
    """Two lines claim the same reference. One of them is wrong, and no
    distributor or assembly house will catch it."""
    seen = {}
    for component in components:
        for ref in expand_designators(getattr(component, "designator", "")):
            seen.setdefault(ref, []).append(component)
    findings = []
    for ref, group in sorted(seen.items()):
        if len(group) < 2:
            continue
        names = " | ".join((getattr(c, "name", "") or "?")[:34] for c in group[:3])
        findings.append(Finding(
            "critical", ref,
            f"{ref} appears on {len(group)} lines",
            f"A reference designates one part on the board. {names}"))
    return findings


def _designators_against_quantity(components) -> list:
    """"R1, R2, R3" with a quantity of 2.

    One of the two numbers is wrong and the tool cannot say which. Both
    readings are expensive: order too few and the build stops, order by the
    designator count and the cost is wrong.
    """
    findings = []
    for component in components:
        refs = expand_designators(getattr(component, "designator", ""))
        if len(refs) < 1:
            continue
        quantity = max(int(getattr(component, "quantity", 1) or 1), 1)
        if len(refs) != quantity:
            findings.append(Finding(
                "warning", _reference(component),
                f"{len(refs)} designator(s) but a quantity of {quantity}",
                f"{', '.join(refs[:6])}{' ...' if len(refs) > 6 else ''}. "
                f"One of the two numbers is wrong."))
    return findings


CHECKS = (
    _no_part_number,
    _value_in_the_part_number,
    _placeholder_part_number,
    _repeated_part_number,
    _repeated_designator,
    _designators_against_quantity,
)

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def check(components) -> list:
    """Every structural check, worst first. No network, no configuration."""
    findings = []
    for rule in CHECKS:
        findings.extend(rule(components))
    findings.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.reference))
    return findings
