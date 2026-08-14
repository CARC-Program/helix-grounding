"""
Extractors — pattern-based claim recovery from generated text.

Every extractor is deterministic and cheap. No model call happens here,
which is the point: verifying an inference with another inference gives
you two things that can be wrong instead of one.

Each extractor documents what it cannot catch. That matters more than
what it can — a validation layer that quietly misses a category is worse
than no validation layer, because it manufactures false confidence.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .claims import Claim, ClaimKind

# Tokens that look like part numbers to a regex but are standards,
# protocols, packages or units. Without this list the identifier
# extractor flags "RS485" and "DDR4" as fabricated part numbers, burns
# every retry, and delivers the safe fallback on a report that was
# actually fine. Found by pattern review, and the reason this list is
# public: no default vocabulary survives contact with a new domain, so
# callers are expected to extend it rather than fight it.
DEFAULT_KNOWN_VOCABULARY: frozenset[str] = frozenset({
    # buses and protocols
    "I2C", "I2S", "SPI", "QSPI", "UART", "USART", "USB", "USB2", "USB3",
    "USB31", "USB4", "RS232", "RS422", "RS485", "CAN", "CANFD", "LIN",
    "MODBUS", "PROFIBUS", "ETHERCAT", "SDIO", "MMC", "PCIE", "SATA",
    "NVME", "MIPI", "LVDS", "HDMI", "DVI", "VGA", "DSI", "CSI", "JTAG",
    "SWD", "ONEWIRE", "PWM", "ADC", "DAC", "GPIO", "IRQ", "DMA",
    # memory and storage
    "DDR", "DDR2", "DDR3", "DDR4", "DDR5", "LPDDR", "LPDDR3", "LPDDR4",
    "LPDDR5", "SRAM", "DRAM", "EEPROM", "EMMC", "NAND", "NOR", "FRAM",
    # wireless
    "BLE", "WIFI", "LORA", "LORAWAN", "ZIGBEE", "NFC", "RFID", "GNSS",
    "GPS", "LTE", "NBIOT", "LTEM", "UWB",
    # packages and process
    "QFN", "QFP", "TQFP", "LQFP", "BGA", "CSP", "WLCSP", "SOIC", "SSOP",
    "TSSOP", "MSOP", "SOT23", "SOT223", "DFN", "DIP", "SMD", "SMT",
    "THT", "PCB", "PCBA", "DFM", "DFA", "ESD", "EMI", "EMC", "RF",
    # certification and compliance
    "ROHS", "REACH", "UL94", "IPC", "ISO9001", "IATF16949", "IP54",
    "IP65", "IP66", "IP67", "IP68", "CE", "FCC", "ETSI", "ATEX",
    # units and generic tech
    "MHZ", "GHZ", "KHZ", "MAH", "WH", "KWH", "AWG", "PPM", "RPM",
    "LED", "OLED", "LCD", "TFT", "EPD", "IMU", "MCU", "MPU", "SOC",
    "FPGA", "CPLD", "ASIC", "RTC", "PMIC", "LDO", "MOSFET", "IGBT",
    "BOM", "MOQ", "EOL", "NRE", "SKU", "API", "SDK", "OS", "IO",
})

# Currency words this library recognises alongside symbols. The original
# Helix validator matched only "$" -- a model writing "36 dollars"
# instead of "$36" bypassed the entire safety net. That gap is closed
# here; the word forms are checked with the same rigour as the symbol.
_CURRENCY_WORDS = r"(?:dollars?|usd|eur|euros?|gbp|pounds?)"

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "").strip())


class Extractor(ABC):
    """Pulls one kind of claim out of text.

    Implement ``kind`` and ``extract``. Extractors must never raise on
    malformed input — text arriving here is model output, and the whole
    reason this library exists is that model output cannot be trusted to
    be well-formed.
    """

    @property
    @abstractmethod
    def kind(self) -> ClaimKind: ...

    @abstractmethod
    def extract(self, text: str) -> list[Claim]: ...


class CurrencyExtractor(Extractor):
    """Monetary amounts, symbol-prefixed or word-suffixed.

    Catches: ``$1,250.00``, ``$45``, ``1,250 dollars``, ``45.50 USD``.

    Does not catch: amounts written as words ("thirty-six dollars"),
    amounts implied by arithmetic the model performs in prose ("roughly
    double the budget"), or amounts inside a larger token. The first is a
    genuine gap; the second is out of scope for any lexical checker.
    """

    def __init__(self, symbols: str = "$€£"):
        self._symbols = symbols
        escaped = re.escape(symbols)
        self._pattern = re.compile(
            rf"(?:[{escaped}]\s?({_NUM}))"
            rf"|(?:({_NUM})\s*{_CURRENCY_WORDS}\b)",
            re.IGNORECASE,
        )

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.CURRENCY

    def extract(self, text: str) -> list[Claim]:
        claims = []
        for match in self._pattern.finditer(text):
            raw_number = match.group(1) or match.group(2)
            if raw_number is None:
                continue
            claims.append(Claim(
                kind=ClaimKind.CURRENCY,
                value=_to_float(raw_number),
                raw=match.group(0).strip(),
                span=match.span(),
            ))
        return claims


class MeasurementExtractor(Extractor):
    """Physical quantities with an explicit unit.

    Unit-aware on purpose. Pooling every figure into one set regardless of
    unit lets a model state the right number against the wrong dimension --
    a width where a height belonged, a weight where a length did -- and pass
    validation because the value existed *somewhere* in the source data.
    Keeping the unit attached lets the ground truth separate those sets.

    Does not catch: unitless numbers, or values whose unit is implied by
    a preceding sentence rather than adjacent to the number.
    """

    # Bare "C" and "K" are deliberately absent. In electronics prose C is
    # a capacitance designator and a coulomb as often as it is a degree,
    # and admitting it made the extractor read the "2C" inside "I2C" as a
    # temperature. Temperatures must carry a degree marker to be checked.
    DEFAULT_UNITS = (
        "mm", "cm", "m", "mil", "in", "inch", "inches",
        "g", "kg", "oz", "lb",
        "W", "mW", "kW", "V", "mV", "kV", "A", "mA", "uA",
        "Wh", "mAh", "Ah", "F", "uF", "nF", "pF",
        "Hz", "kHz", "MHz", "GHz", "ohm", "kohm",
        "°C", "degC", "°F", "degF",
        "days", "day", "weeks", "week", "hours", "hour",
    )

    def __init__(self, units: tuple[str, ...] | None = None):
        self._units = units or self.DEFAULT_UNITS
        # Longest-first so "mAh" wins over "A", "MHz" over "Hz".
        alternation = "|".join(
            re.escape(u) for u in sorted(self._units, key=len, reverse=True)
        )
        # The lookbehind is load-bearing. Without it the digits inside an
        # identifier get read as a measurement -- "I2C" became 2°C, and
        # "AT24C256" would have become 24°C. Part numbers are uppercase
        # and digits, so refusing a match that begins immediately after
        # either rules them out, while still allowing the lowercase "x"
        # that separates dimensions in "60x40x6mm".
        self._pattern = re.compile(rf"(?<![A-Z0-9])({_NUM})\s*({alternation})\b")

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.MEASUREMENT

    def extract(self, text: str) -> list[Claim]:
        claims = []
        for match in self._pattern.finditer(text):
            claims.append(Claim(
                kind=ClaimKind.MEASUREMENT,
                value=_to_float(match.group(1)),
                raw=match.group(0).strip(),
                span=match.span(),
                unit=match.group(2),
            ))
        return claims


class IdentifierExtractor(Extractor):
    """Part numbers, SKUs, model codes — tokens that must exist verbatim.

    This is the extractor most prone to false positives, and it is worth
    being blunt about why: there is no lexical rule that separates a
    manufacturer part number from a standards name. ``RS485`` and
    ``BME280`` are the same shape. The only honest fix is a vocabulary of
    known non-identifiers, which ships as a default and is expected to be
    extended per domain.

    Consequence: a genuinely fabricated part number that happens to sit
    in the vocabulary will pass. That is the deliberate trade — a false
    negative here is recoverable, while a false positive burns every
    retry and suppresses a report that was correct.
    """

    _CANDIDATE = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*\d[A-Z0-9]*(?:[-/][A-Z0-9]+)*\b")

    def __init__(self, vocabulary: frozenset[str] | None = None, min_length: int = 4):
        self._vocabulary = vocabulary if vocabulary is not None else DEFAULT_KNOWN_VOCABULARY
        self._min_length = min_length

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.IDENTIFIER

    def extract(self, text: str) -> list[Claim]:
        claims = []
        for match in self._CANDIDATE.finditer(text):
            token = match.group(0)
            if len(token) < self._min_length:
                continue
            normalised = token.replace("-", "").replace("/", "").upper()
            if normalised in self._vocabulary or token.upper() in self._vocabulary:
                continue
            claims.append(Claim(
                kind=ClaimKind.IDENTIFIER,
                value=token.upper(),
                raw=token,
                span=match.span(),
            ))
        return claims


class QuantityExtractor(Extractor):
    """Counts, restricted to unambiguous multiplier forms.

    Only ``x5``, ``5x``, ``5 units`` and ``quantity of 5`` are read as
    quantities. Bare integers are deliberately ignored: in prose they are
    far more often list positions, priorities or years than counts, and
    flagging them produces noise that trains the caller to ignore the
    validator entirely.
    """

    _PATTERNS = (
        re.compile(r"\bx\s?(\d+)\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s?x\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s*units?\b", re.IGNORECASE),
        re.compile(r"\bquantity\s+of\s+(\d+)\b", re.IGNORECASE),
    )

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.QUANTITY

    def extract(self, text: str) -> list[Claim]:
        claims = []
        seen_spans: set[tuple[int, int]] = set()
        for pattern in self._PATTERNS:
            for match in pattern.finditer(text):
                if match.span() in seen_spans:
                    continue
                seen_spans.add(match.span())
                claims.append(Claim(
                    kind=ClaimKind.QUANTITY,
                    value=float(match.group(1)),
                    raw=match.group(0).strip(),
                    span=match.span(),
                ))
        return claims


class PercentageExtractor(Extractor):
    """Percentages. Common in summaries, easy to invent, easy to check."""

    _PATTERN = re.compile(rf"(?<![A-Z0-9])({_NUM})\s*(?:%|percent\b)", re.IGNORECASE)

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.PERCENTAGE

    def extract(self, text: str) -> list[Claim]:
        return [
            Claim(
                kind=ClaimKind.PERCENTAGE,
                value=_to_float(match.group(1)),
                raw=match.group(0).strip(),
                span=match.span(),
            )
            for match in self._PATTERN.finditer(text)
        ]


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))


class DateExtractor(Extractor):
    """Calendar dates, normalised to ISO ``YYYY-MM-DD``.

    Added because the invoice domain exposed a hole: a due date stated in
    generated text produced no claim at all, so a model could invent one and
    nothing would notice. A date is as decidable as a currency amount -- it
    either appears in the source data or it does not -- so it belongs here
    rather than in a judgement layer.

    Recognises ``2026-09-15``, ``09/15/2026``, ``15.09.2026``,
    ``September 15, 2026`` and ``15 September 2026``.

    Ambiguity, stated rather than hidden: ``03/04/2026`` is March 4th in US
    convention and April 3rd almost everywhere else, and no amount of parsing
    resolves that. ``day_first`` picks the reading, defaulting to month-first;
    set it per domain. Where one component exceeds 12 the order is
    unambiguous and is read correctly regardless of the flag.

    Does not catch: relative dates ("next Tuesday", "in 30 days"), quarters,
    or bare month-year pairs. A relative date is a judgement claim -- it
    depends on what "now" means -- and judgement is out of scope by design.
    """

    _ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
    _NUMERIC = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4}|\d{2})\b")
    _MONTH_FIRST = re.compile(
        rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
        re.IGNORECASE,
    )
    _DAY_FIRST = re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})\b",
        re.IGNORECASE,
    )

    def __init__(self, day_first: bool = False):
        self._day_first = day_first

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.DATE

    @staticmethod
    def _iso(year: int, month: int, day: int) -> str | None:
        """Reject impossible dates rather than normalising them into
        something plausible -- a fabricated 2026-02-31 should not quietly
        become a real day."""
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        days_in_month = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0)
                         else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if day > days_in_month[month - 1]:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"

    def extract(self, text: str) -> list[Claim]:
        claims: list[Claim] = []
        taken: list[tuple[int, int]] = []

        def add(match, year, month, day):
            # Longer written forms are matched first; skip anything that
            # overlaps a claim already recorded so one date isn't reported twice.
            if any(s < match.end() and match.start() < e for s, e in taken):
                return
            iso = self._iso(year, month, day)
            if iso is None:
                return
            taken.append(match.span())
            claims.append(Claim(
                kind=ClaimKind.DATE, value=iso,
                raw=match.group(0).strip(), span=match.span(),
            ))

        for m in self._MONTH_FIRST.finditer(text):
            add(m, int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        for m in self._DAY_FIRST.finditer(text):
            add(m, int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        for m in self._ISO.finditer(text):
            add(m, int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for m in self._NUMERIC.finditer(text):
            first, second = int(m.group(1)), int(m.group(2))
            year = int(m.group(3))
            if year < 100:  # two-digit year: 00-69 -> 2000s, 70-99 -> 1900s
                year += 2000 if year < 70 else 1900
            if first > 12:      # unambiguous: first component must be the day
                day, month = first, second
            elif second > 12:   # unambiguous: second component must be the day
                day, month = second, first
            else:
                day, month = (first, second) if self._day_first else (second, first)
            add(m, year, month, day)

        return claims


def default_extractors() -> list[Extractor]:
    """The standard set. Callers wanting different behaviour should build
    their own list rather than monkey-patching these."""
    return [
        CurrencyExtractor(),
        MeasurementExtractor(),
        IdentifierExtractor(),
        QuantityExtractor(),
        PercentageExtractor(),
        DateExtractor(),
    ]
