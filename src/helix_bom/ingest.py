"""
Read a bill of materials the way it actually arrives.

The tests for this agent build ``Component`` objects by hand, with every field
populated. Nobody's real file looks like that. A KiCad export opens with four
lines of tool metadata before the header; Altium calls quantity "Quantity" and
KiCad calls it "Qnty"; a spreadsheet from a purchasing department calls it
"QTY " with a trailing space. Prices arrive as ``$1.23``, ``1,234.56``, and
``1 234,56`` depending on who exported them.

None of that is interesting engineering. All of it is the difference between
a tool a stranger can use and a tool only its author can use.

The rule here: **never guess silently.** Every assumption this module makes is
recorded in the returned ``IngestReport`` — which columns matched which
fields, which fields had no column at all, and every cell that could not be
read. A caller that ignores the report gets working software; a caller that
shows it to the user gets honest software.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .agent import Component

# Candidate headers per field, in priority order: the first alias present in
# the file wins. Order matters — a KiCad export has both "Value" ("10k") and
# "Description" ("Resistor, 0603"), and the description is the more useful
# name for a human reading a report.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "designator": ("ref", "refs", "reference", "references", "designator",
                   "designators", "refdes"),
    "name": ("description", "comment", "value", "cmpname", "componentname",
             "partname", "part", "name", "item", "designation"),
    "quantity": ("qty", "qnty", "quantity", "quantityperboard", "qtyperboard",
                 "count"),
    "cost_usd": ("unitprice", "priceeach", "unitcost", "priceusd", "priceper",
                 "price", "cost", "each"),
    "manufacturer_part_number": ("mpn", "manufacturerpartnumber",
                                 "manufacturerpartno", "mfrpartnumber",
                                 "mfgpartno", "mfrpart", "manufacturerpn",
                                 "partnumber"),
    "manufacturer": ("manufacturer", "mfr", "mfg", "brand", "vendor",
                     "supplier"),
    "lead_time_days": ("leadtimedays", "leadtime", "leadtimedy"),
    "category": ("category", "type", "class", "componenttype"),
    "width_mm": ("widthmm", "width"),
    "depth_mm": ("depthmm", "depth", "lengthmm", "length"),
    "height_mm": ("heightmm", "height", "thicknessmm", "thickness"),
    "power_draw_w": ("powerw", "powerdrawwatts", "powerdraw", "power",
                     "wattage"),
}

# Aliases that could plausibly mean something else. Matching one is fine, but
# it gets flagged so the user can correct an assumption rather than discover
# it in a wrong total.
AMBIGUOUS_ALIASES: dict[str, str] = {
    "cost": "may be a line total rather than a unit price",
    "price": "may be a line total rather than a unit price",
    "each": "may be a line total rather than a unit price",
    "type": "may describe a package or footprint rather than a category",
    "class": "may describe a package or footprint rather than a category",
    "length": "read as depth; may mean a different axis on your part",
}

# Marks a line the board will not be populated with. Such rows cost nothing
# and occupy no space, so counting them inflates every total.
DNP_HEADERS = ("dnp", "donotpopulate", "donotplace", "nofit", "exclude",
               "excludefrombom", "populate")
DNP_TRUTHY = {"1", "y", "yes", "true", "dnp", "x", "do not populate"}

# Summary rows a spreadsheet leaves at the bottom. Matched after
# normalisation, so "Total:", "TOTAL" and "grand total" all land here.
TOTALS_ROW_NAMES = frozenset({
    "total", "totals", "subtotal", "subtotals", "grandtotal", "sum",
    "sumtotal", "totalcost", "totalprice", "bomtotal",
})


def _normalise(header: str) -> str:
    """Reduce a header to letters and digits so 'Unit Price ($)', 'unit_price'
    and 'UNITPRICE' all compare equal."""
    return re.sub(r"[^a-z0-9]", "", header.strip().lower())


@dataclass
class RowProblem:
    """One cell that could not be read. Carries the row number as the user's
    spreadsheet shows it, because 'row 47' is actionable and 'index 45' is
    not."""

    row: int
    column: str
    value: str
    problem: str

    def __str__(self) -> str:
        return f"row {self.row}, {self.column}={self.value!r}: {self.problem}"


@dataclass
class IngestReport:
    """Everything this module assumed, in one object.

    The point is that a caller can show it to the user. Silent coercion is
    how a tool produces a confident total from a file it half-understood.
    """

    source: str = ""
    delimiter: str = ","
    header_row: int = 1
    mapped: dict[str, str] = field(default_factory=dict)
    ambiguous: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    rows_read: int = 0
    rows_skipped_dnp: int = 0
    rows_skipped_totals: int = 0
    rows_skipped_empty: int = 0
    decimal_separator: str = "."
    encoding: str = "utf-8"
    size_bytes: int = 0
    total_rows: int = 0
    headers: list = field(default_factory=list)

    @property
    def rows_used(self) -> int:
        # rows_read counts every non-empty data row, DNP included; blank rows
        # are never counted in the first place. So exactly one subtraction is
        # correct here — the first version also decremented rows_read on a DNP
        # row and reported one line item fewer than the file contained.
        return self.rows_read - self.rows_skipped_dnp - self.rows_skipped_totals

    def summary(self) -> str:
        parts = [
            f"{self.rows_used} line item(s) from {self.source}",
            f"columns matched: {len(self.mapped)}",
        ]
        if self.problems:
            parts.append(f"{len(self.problems)} unreadable cell(s)")
        if self.rows_skipped_dnp:
            parts.append(f"{self.rows_skipped_dnp} DNP row(s) excluded")
        if self.rows_skipped_totals:
            parts.append(f"{self.rows_skipped_totals} summary row(s) excluded")
        return "; ".join(parts)


def detect_decimal_separator(samples) -> str:
    """Decide whether a file writes ``1.234,56`` or ``1,234.56``.

    This has to be a per-*file* decision, not per-cell. Read cell by cell,
    "1.000" is one with three decimal places and also one thousand, and
    nothing in the cell resolves it. The file resolves it: a European export
    that writes "1.234,56" for a price also means one thousand by "1.000" in
    the quantity column two cells over.

    Getting this wrong is not a rounding error. An earlier version parsed
    "1.000" as 1 while parsing "2,000" as 2000 in the same file — a
    thousandfold error in a line quantity, and therefore in the BOM total.

    Votes are weighted: a cell containing *both* separators is decisive,
    since only one ordering is valid in either convention.
    """
    european = us = 0
    for sample in samples:
        text = re.sub(r"[^\d.,]", "", str(sample).strip())
        if not text:
            continue
        if re.search(r"\d\.\d{3},\d", text):            # 1.234,56 — decisive
            european += 3
        elif re.search(r"\d,\d{3}\.\d", text):          # 1,234.56 — decisive
            us += 3
        # A leading zero group settles it on its own. "0.008" is eight
        # thousandths and nothing else: no convention writes eight as a
        # thousands-grouped "0.008", because a grouped number never begins
        # with a zero group. This is weighted decisively because electronics
        # BOMs are full of sub-cent prices, and reading them as thousands
        # multiplies every one by a thousand -- found on the first realistic
        # file tested, where a $15.60 BOM totalled $15,603.00.
        elif re.fullmatch(r"0\.\d+", text):
            us += 3
        elif re.fullmatch(r"0,\d+", text):
            european += 3
        # Thousands grouping, with the same rule applied: the first group
        # cannot start with a zero, so "1.000" groups and "0.008" cannot.
        elif re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", text):   # 1.000
            european += 1
        elif re.fullmatch(r"[1-9]\d{0,2}(,\d{3})+", text):    # 1,000
            us += 1
        elif re.fullmatch(r"\d+,\d{1,2}", text):        # 12,50
            european += 1
        elif re.fullmatch(r"\d+\.\d{1,2}", text):       # 12.50
            us += 1
    return "," if european > us else "."


def _parse_money(raw: str, decimal_sep: str = ".") -> float:
    """Read a price cell using the convention detected for the whole file."""
    text = raw.strip()
    if not text:
        return 0.0

    negative = text.startswith("(") and text.endswith(")")  # accounting style
    text = re.sub(r"[^\d.,-]", "", text)
    if not text:
        raise ValueError("no digits")

    thousands_sep = "," if decimal_sep == "." else "."

    # Refuse a value that does not fit the convention the file established,
    # rather than coercing it into a plausible-looking number.
    #
    # A thousands group is exactly three digits. Under US rules "2,50" is not
    # a small number written oddly -- it is not valid notation at all, and
    # stripping the comma turns two-fifty into two hundred and fifty. Silently.
    # Found on a file that mixed conventions, where a $2 BOM totalled $250.
    #
    # Refusing sends it through the row-problem path, so the cell is named in
    # the report instead of quietly changing the total by a factor of a
    # hundred. That is this module's whole rule: never guess silently.
    if thousands_sep in text:
        body = text.lstrip("-")
        if not re.fullmatch(
            rf"\d{{1,3}}(?:{re.escape(thousands_sep)}\d{{3}})+"
            rf"(?:{re.escape(decimal_sep)}\d+)?", body
        ):
            raise ValueError(
                f"{raw.strip()!r} does not match this file's number format "
                f"(decimal separator {decimal_sep!r})"
            )

    text = text.replace(thousands_sep, "")
    if decimal_sep != ".":
        text = text.replace(decimal_sep, ".")

    value = float(text)
    return -value if negative else value


def _parse_int(raw: str, decimal_sep: str = ".") -> int:
    """Quantities go through the same separator logic as prices.

    They used to strip commas and keep dots, which is the US convention
    hardcoded — the bug described in ``detect_decimal_separator``.
    """
    return int(round(_parse_money(raw, decimal_sep)))


def _looks_like_header(cells: list[str]) -> int:
    """Score a row by how many of its cells name a field we recognise.

    KiCad writes four lines of tool metadata before the real header, so the
    first row of the file is frequently not the header. Scoring rather than
    assuming makes that a non-issue instead of a support question.
    """
    known = {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
    known.update(DNP_HEADERS)
    return sum(1 for cell in cells if _normalise(cell) in known)


def _read_text(path: Path) -> tuple[str, str]:
    """Excel writes a BOM; older tools write Latin-1. Try in that order and
    fall back rather than dying on a stray accented character.

    Returns the text and which encoding worked, because "it decoded as
    cp1252" is often the whole explanation for a mangled part number, and
    a diagnostic that omits it sends the reporter looking in the wrong
    place.
    """
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1 (with replacements)"


def load_bom(path, max_header_scan: int = 20) -> tuple[list[Component], IngestReport]:
    """Load a BOM CSV into ``Component`` objects plus a report of every
    assumption made.

    Raises ``ValueError`` only when no header row can be found at all — that
    is not a messy file, it is a different kind of file, and guessing at it
    would be worse than saying so.
    """
    path = Path(path)
    text, encoding = _read_text(path)
    report = IngestReport(source=path.name, encoding=encoding,
                          size_bytes=path.stat().st_size)

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        report.delimiter = dialect.delimiter
    except csv.Error:
        report.delimiter = ","  # a one-column file sniffs as nothing

    rows = list(csv.reader(io.StringIO(text), delimiter=report.delimiter))
    if not rows:
        raise ValueError(f"{path.name} is empty")

    # --- find the header -------------------------------------------
    best_index, best_score = -1, 0
    for index, row in enumerate(rows[:max_header_scan]):
        score = _looks_like_header(row)
        if score > best_score:
            best_index, best_score = index, score
    if best_score < 2:
        raise ValueError(
            f"{path.name}: no header row found in the first {max_header_scan} "
            f"lines. Expected a row naming at least two of: quantity, price, "
            f"description, part number. Is this a BOM export?"
        )

    header = rows[best_index]
    report.header_row = best_index + 1
    report.headers = [c.strip() for c in header if c.strip()]
    report.total_rows = len(rows)

    # --- map columns to fields -------------------------------------
    normalised = {_normalise(cell): index for index, cell in enumerate(header) if cell.strip()}
    column_index: dict[str, int] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                column_index[field_name] = normalised[alias]
                report.mapped[field_name] = header[normalised[alias]].strip()
                if alias in AMBIGUOUS_ALIASES:
                    report.ambiguous[report.mapped[field_name]] = AMBIGUOUS_ALIASES[alias]
                break

    dnp_index = next((normalised[h] for h in DNP_HEADERS if h in normalised), None)
    dnp_is_inverted = dnp_index is not None and _normalise(header[dnp_index]) == "populate"

    claimed = set(column_index.values()) | ({dnp_index} if dnp_index is not None else set())
    report.unmapped_headers = [
        cell.strip() for index, cell in enumerate(header)
        if cell.strip() and index not in claimed
    ]
    report.missing_fields = [f for f in COLUMN_ALIASES if f not in column_index]

    if "name" not in column_index and "designator" not in column_index:
        raise ValueError(
            f"{path.name}: no column names the parts. Expected one of: "
            f"Description, Comment, Value, Part, or a reference designator."
        )

    # --- decide the number convention, once, for the whole file -----
    numeric_fields = ("cost_usd", "quantity", "width_mm", "depth_mm",
                      "height_mm", "power_draw_w")
    samples = [
        row[column_index[f]]
        for row in rows[best_index + 1:]
        for f in numeric_fields
        if f in column_index and column_index[f] < len(row)
    ]
    report.decimal_separator = detect_decimal_separator(samples)

    # --- read the rows ---------------------------------------------
    components: list[Component] = []
    for offset, row in enumerate(rows[best_index + 1:], start=best_index + 2):
        if not any(cell.strip() for cell in row):
            report.rows_skipped_empty += 1
            continue
        report.rows_read += 1

        def cell(field_name: str) -> str:
            index = column_index.get(field_name)
            return row[index].strip() if index is not None and index < len(row) else ""

        if dnp_index is not None and dnp_index < len(row):
            flag = row[dnp_index].strip().lower()
            excluded = (flag not in DNP_TRUTHY and flag != "") if dnp_is_inverted \
                else (flag in DNP_TRUTHY)
            if excluded:
                report.rows_skipped_dnp += 1
                continue

        designator = cell("designator")
        name = cell("name") or designator or "(unnamed)"

        # A spreadsheet BOM usually ends in a summary row. Counting it as a
        # line item inflates the part count, and if its cost column happens to
        # hold the extended total, it doubles the BOM. Found on the first
        # realistic file tested, where a 24-part BOM reported 46 parts.
        #
        # Conservative on purpose: the name has to *be* a totals word, and the
        # row must carry no part identifier. A real component called
        # "Total Phase Beagle I2C probe" has an MPN and a designator, so it
        # survives; a row reading only "TOTAL" in the description column does
        # not.
        if (_normalise(name) in TOTALS_ROW_NAMES
                and not cell("manufacturer_part_number")
                and not cell("designator")):
            report.rows_skipped_totals += 1
            continue

        def number(field_name: str, parser, default):
            raw = cell(field_name)
            if not raw:
                return default
            try:
                return parser(raw, report.decimal_separator)
            except (ValueError, TypeError) as exc:
                # The parser explains a convention mismatch in its own words;
                # anything else is just unreadable.
                detail = str(exc)
                reason = (detail if "number format" in detail
                          else "could not be read as a number")
                report.problems.append(RowProblem(
                    offset, report.mapped.get(field_name, field_name), raw,
                    f"{reason}; treated as missing",
                ))
                return default

        components.append(Component(
            name=name,
            cost_usd=number("cost_usd", _parse_money, 0.0),
            width_mm=number("width_mm", _parse_money, 0.0),
            depth_mm=number("depth_mm", _parse_money, 0.0),
            height_mm=number("height_mm", _parse_money, 0.0),
            power_draw_w=number("power_draw_w", _parse_money, 0.0),
            category=cell("category").lower(),
            quantity=max(1, number("quantity", _parse_int, 1)),
            manufacturer=cell("manufacturer"),
            manufacturer_part_number=cell("manufacturer_part_number"),
            lead_time_days=number("lead_time_days", _parse_int, 0),
            designator=designator,
        ))

    return components, report
