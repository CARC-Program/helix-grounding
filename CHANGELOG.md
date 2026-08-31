# Changelog

## 0.4.1 — 2026-08-31

> **A valid JLCPCB assembly BOM produced seven findings and every one was
> wrong.** It now produces none. Also: the report stays responsive on a real
> board's BOM instead of sweeping the whole document on every mouse move.

### Fixed

**LCSC and JLCPCB part numbers are recognised.** A JLCPCB assembly BOM carries
Comment, Designator, Footprint and an LCSC code, and no manufacturer part
number at all. Every line was reported CRITICAL "no manufacturer part number".
Such a line is orderable and complete; it now gets one informational note
saying the code ties the build to a single supplier.

**Quantity is derived from the designators when a file states none.** A JLCPCB
BOM has no quantity column. The default of 1 was then compared against a four
designator line and reported as a defect. Quantity now comes from the
designator count, which is how an assembler reads it and which also makes the
cost total right, and the designator/quantity check stands down rather than
comparing a number against the number it came from. It still fires normally
when a file does state a quantity.

**The report no longer claims nobody can quote a distributor-coded line.** It
said exactly that about parts LCSC sells from stock.

### Changed

**Cross-highlighting is indexed instead of re-queried.** Every mouse move ran
`querySelectorAll` over every marked element and toggled a class on all of
them. On a thousand line BOM that is about 48,000 elements per hover. A hover
now touches only the elements leaving and entering the highlight.

**The cost and fit views cap what they draw.** Past forty blocks a treemap cell
is smaller than a cursor. The tail is grouped into one block and the areas
still sum to the real total. The enclosure verdict is still computed over every
part, drawn or not, and says how many were left undrawn.

Measured on a 1000 line BOM: 1.3 MB and 47,800 elements before, 719 KB and
36,900 after, generation 27 ms to 14 ms.


## 0.4.0 — 2026-08-30

> **The report now draws what the file contains.** Cost, lead time, supply risk
> and enclosure fit, cross-highlighted so one part lights up in every view at
> once. Views without data say which column they wanted rather than rendering
> an empty frame.

### Added

**Cost view.** A treemap of extended cost -- unit price times quantity, because
four capacitors at five cents are twenty cents of the board. Click a block to
light that part up everywhere else.

**Lead-time view.** The longest bar is the date the board is ready, however
available everything else is. That single fact is normally buried in a column
nobody sorts.

**Supply-risk view.** Lifecycle, stock against the quantity you need, minimum
order quantity, and what a unit actually costs at that quantity. Needs a
distributor key, and says so plainly when there is not one.

**Enclosure fit.** Component volumes in isometric against an envelope given as
`--enclosure WxDxH`, with anything that does not fit in red. It is a volume
check, not a placement -- the drawing says so itself, because neither a BOM nor
a netlist knows where a part goes.

**Cross-highlighting.** Hover or click any part to light it up in the treemap,
the lead-time chart, the enclosure, the line table and the finding that names
it. Matching is exact: a substring test would outline the wrong component.

**`--enclosure WxDxH` on `enrich`**, using the same parser `review` uses.

### Fixed

**The packed footprint is measured, not assumed.** It was reported as the
envelope width, so a board using 58 mm of a 60 mm envelope was described as
using all 60, and a part overflowing a shelf counted as fitting.

### Note

No board render is produced, and none can be from these inputs: a BOM has no
coordinates and a netlist has no coordinates. Reading a pick-and-place export
is the honest route to one.


## 0.3.0 — 2026-08-30

> **Reviews can now be read as a page instead of scrollback.** `--html` writes
> a self-contained report beside the BOM and opens it; `helix-bom-gui` does the
> same from a file picker, with no terminal involved.

### Added

**`helix-bom enrich <file> --html [PATH]`.** One self-contained HTML file,
written beside the BOM by default and opened in the browser. Severity filters,
the full line table, every "not checked" reason with its cause, the column
mapping the parser used, and the interconnect diagram embedded when the input
is a netlist.

Nothing in the page is fetched from anywhere -- no stylesheet, script, font or
image -- so it renders identically with the network unplugged, and a test fails
if an element that could load something is ever added. `--no-open` writes it
without launching a browser.

**`helix-bom-gui`.** A windowed entry point: pick a file, get the report. On
Windows it is a GUI executable, so it can be double-clicked or have a BOM
dragged onto it without a console window. It runs the same review as the
command line rather than a second implementation of it.

### Security

**BOM content is escaped into the report.** A description or part number field
containing markup is rendered as text, not executed. Tested with a script
payload, because a BOM is somebody else's data being put into a document a
browser will run.


## 0.2.2 — 2026-08-28

> **The Mouser adapter is now checked against Mouser's published schema.** That
> found three fields it was not reading and one it looked for that does not
> exist. Most usefully: when a part is obsolete, the report now carries the
> replacement the distributor suggests.

### Added

**An obsolete part reports the distributor's suggested replacement.** Mouser's
schema has a `SuggestedReplacement` field and the adapter was ignoring it.
"This part is dead" and "this part is dead, and Mouser suggests X" are the same
finding with very different amounts of use to whoever reads it.

It is quoted as *their* suggestion and nothing is substituted. Swapping a part
automatically would be inventing a design decision, which is the thing this
library exists against.

**`IsDiscontinued` is read as well as `LifecycleStatus`.** They are separate
fields. A part can carry a blank or cheerful lifecycle string and still be
flagged discontinued; the worse reading wins.

### Fixed

**Package now comes from `ProductAttributes`.** There is no `Package` field in
Mouser's schema. The adapter looked for one and silently fell through to the
product category every time.

### Notes

The check was done against `https://api.mouser.com/api/docs/v1`, which is a
public Swagger document. Everything else the adapter relies on was confirmed
correct: the `Errors`/`SearchResults` envelope, `SearchResults.Parts`, the
`apiKey` query parameter, the templated version in the path, and
`partSearchOptions` accepting `Exact`.

Two things that check could not settle, both recorded in the source. The
request field is named `mouserPartNumber` while this endpoint is what every
client uses for manufacturer part numbers — `--check-key` probes with an MPN so
that a real key answers it. And the schema permits **ten part numbers per
request**, which against a thousand-a-day limit is the largest efficiency still
on the table; it is not implemented yet.

**Digi-Key could not be checked the same way.** Its specification is behind an
authenticated portal. So Mouser's shapes are schema-verified and Digi-Key's are
not, and neither has been run against a live API. `verified_against_live_api`
remains False for both, because a schema is not a server.

## 0.2.1 — 2026-08-27

> **`helix-bom enrich` now finds real problems with no API key.** 0.2.0 shipped
> it asking a distributor about every line, so without an account it did
> nothing at all: ten lines, zero checked, one message repeated ten times. Six
> checks that need only the file now run first, always.

### Added

**Structural checks, no network, no account, no configuration.** Each is a
defect that ships boards wrong and is visible in the file alone:

- **no manufacturer part number** — the commonest defect in real BOMs, and the
  one `docs/DEMAND_EVIDENCE.md` points straight at. A value and a footprint are
  not an orderable part.
- **a value in the part number column** — `10k` says what the part does, not
  which part it is. Two thousand different resistors are 10k.
- **a placeholder** — TBD, TODO, N/A, XXX, never filled in.
- **the same part on two lines** — ordered twice, costed twice.
- **the same designator on two lines** — a reference designates one part on the
  board; two lines claiming R3 means one is wrong, and no distributor or
  assembly house catches it.
- **designators that do not match the quantity** — `R1, R2, R3` with a quantity
  of 2. One of the two numbers is wrong. Ranges are expanded, so `J1-J4` counts
  as four rather than being called a mismatch.

Distributor lookup is now a bonus on top of these rather than the whole
feature. If a key is set it still runs and still checks lifecycle, stock,
minimum quantity and price at the quantity being bought.

### Changed

**A clean report states the scope of its own claim.** "Nothing wrong found" now
says what was actually checked — structure only, or structure plus a
distributor confirming every part. Those are very different claims and until now
they printed the same sentence.

**`Component` carries its designator.** Both readers had it and both threw it
away. It is the only field that says how many physical parts a line represents.

### Notes

The value-detector requires a unit. Its first version called `61300411121` — a
real Wurth part number — "a value, not a part number", as a CRITICAL finding.
Numeric part numbers are ordinary; Wurth, Molex and TE all use them. So a bare
number is left alone, which costs the rule `10` for a ten-ohm resistor. That is
the right way to be wrong: a missed defect is a nuisance, and a confident
accusation against a correct line is why people stop trusting a tool.

The Mouser and Digi-Key adapters remain unrun against the live APIs. Nothing
about that changed in this release, and the report still says so whenever one
is used.

## 0.2.0 — 2026-08-26

> **`helix-bom enrich` checks your part numbers against somebody who actually
> sells the part.** Obsolete parts, reel-only minimums, prices that are wrong at
> the quantity you are buying, and near-matches that are a different part. It
> says which lines it could not check, and why, as loudly as what it found.

### Added

**`helix-bom enrich <file>`.** Reads a BOM or a KiCad netlist and asks a
distributor about every manufacturer part number in it. Seven checks:

- the part does not exist — a typo, or an internal number nobody else knows
- the part is obsolete — the board cannot be built from this design
- the part is NRND — buildable once, probably not next year
- stock is short of the build, or there is none and a lead time instead
- the quantity is below the minimum — you need three, they sell a reel of 3000
- the price is not the price — costed at one-off while buying a hundred, or the reverse
- only near matches came back — a suffix apart is a different reel, tape or grade

Why this and not something else: `docs/DEMAND_EVIDENCE.md` reads twenty answers
to eight questions about getting a usable BOM out of a CAD tool. The accepted
answer to "can I order components from a BOM?" is *yes, vendor import works
fine — as long as you have a manufacturer part number in there*. Every
distributor already solves ordering. Nobody solves arriving at it with part
numbers that are real, current, and priced at the quantity being bought.

**Mouser and Digi-Key adapters.** Credentials come from the environment
(`MOUSER_API_KEY`, or `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET`) and are
never written to the cache, a log, or an error message. Set `DIGIKEY_SANDBOX=1`
to use Digi-Key's sandbox host.

**These two adapters have never been run against the live APIs from here.**
Getting credentials needs an account, and the account terms are the account
holder's to read and accept. The request and response handling is written from
the published specifications and tested against recorded fixtures, which proves
the parsing and proves nothing about the network. The report says so on every
run, and `helix-bom enrich --check-key` looks one known part up and tells you
exactly what happened, in a form you can paste into an issue. If it works,
please say so, and the flag can stop saying False.

**A price cache**, on by default, twelve hours. The call limits are small —
Mouser allows a thousand a day and thirty a minute — and a two-hundred-line BOM
re-run five times would spend the day's allowance. Every price carries the
moment it was fetched and the report prints its age, because a cached price
presented as current is worse than no price: somebody quotes it. `--fresh`
re-fetches, `--clear-cache` empties it.

**`--offline`** runs against six built-in parts with invented prices, so the
feature can be seen working without a key. The report leads with a banner
saying the numbers are made up, and the catalogue answers "not checked" rather
than "not found" for anything it does not hold — six invented parts cannot
support the claim that a part does not exist.

### Notes

Still no runtime dependencies. Prices are parsed as decimals rather than floats,
and read correctly whether they arrive as `$0.19`, `0,19 €`, `1,234.56` or
`1.234,56` — the last two being the same number written by different halves of
the world, and confusing them is a factor-of-a-thousand error on a reel.

Part numbers are folded for case and nothing else. `TPS61023DRLR` and
`TPS61023DRLT` differ only in the reel and are different orderable parts; a
normaliser clever enough to call them equal would approve a BOM that cannot be
assembled. Near matches are shown to you to choose from, never substituted.

Nothing in this release can spend money. There is no ordering method and no
cart method, and the base class has none to override.

## 0.1.2 — 2026-08-22

> **If you review boards as well as buy parts, this is the release that
> matters.** `helix-bom` now reads a KiCad netlist, so the wiring stops being
> guesswork. And if your terminal is not UTF-8, the previous release crashed on
> the first command in the README — that is fixed.


### Added

**Read a KiCad netlist, not just a BOM.** `helix-bom review board.net` reads
the file that knows how the board is wired. A BOM is a shopping list — which
parts, how many — and it says nothing about how they connect, so a wiring
diagram drawn from one is not difficult, it is impossible. A netlist has the
connectivity, and the same review pipeline runs on it unchanged.

The file's contents decide which reader handles it, not its extension, because
exports get renamed and a CSV called `board.net` should not produce a parse
error about parentheses.

**`--diagram out.svg`** writes the interconnect. Every line drawn corresponds
to a net that exists between pins that are named, so the diagram can be
checked against the schematic and found wrong. Power and ground are excluded —
they touch nearly every part, and drawing them produces a hairball that says
less than drawing nothing. Asking for a diagram from a BOM is refused, with a
pointer to the file that would work, rather than silently producing the empty
canvas that used to come back.

**Two findings a BOM cannot express.** A *named* net with only one connection
is flagged: that is a label somebody typed which joined nothing, and on a
schematic printout it looks exactly like a label that connected. Nets KiCad
named itself (`unconnected-(U1-Pad7)`, `Net-(R3-Pad1)`, `N$12`) are left alone
— those are ordinary and already reported by KiCad. Components on no net at
all are flagged too, except where the reference designator says the part is
meant to be unconnected, such as a mounting hole or a fiducial.

**`helix-bom diagnose` handles netlists**, and is stricter with them than with
a CSV. A spreadsheet's column headings are printed because the parser matches
on them; a netlist's equivalents are net names and part values, which are the
design itself. Only counts and structure go into that report.

### Changed

Two skipped-check reasons no longer tell you to add a column. That was
workable advice for a spreadsheet and impossible for a netlist, which has no
columns at all.

### Fixed

**`helix-bom demo` crashed on a Windows console that is not UTF-8.** On cp437
and cp850 — both ordinary console defaults — the first command in the README
raised `UnicodeEncodeError` and printed a traceback instead of a report,
because the output contains em dashes. Anyone whose terminal was configured
that way met a stack trace before they saw a single finding.

Output is now checked against the stream's own encoding and transliterated
when it will not fit: an em dash becomes `--`, which still reads, rather than
`?`, which does not. A UTF-8 console is left exactly as it was. Tests run the
CLI as a subprocess under each legacy encoding, because in-process capture
replaces the stream and hides the problem entirely — which is why the existing
suite passed while the bug was live.

`scripts/export_diagrams.py` ran again. It had been importing modules from a
folder the 2026-08-14 rebuild deleted, so it crashed on import. Every script
in `scripts/` is now imported by the test suite, which is what would have
caught it.

---

## 0.1.1 — 2026-08-17

> **If you reviewed a BOM with 0.1.0, run it again.** Three parsing bugs
> could change a total silently, two of them by a factor of a thousand or a
> hundred. Nothing warned you, because the file parsed cleanly — it just
> parsed wrongly. This release fixes all three.

### Fixed

**Sub-cent prices were read as thousands — totals up to 1000× too high.**
A price of `0.008` matched the pattern for European thousands grouping, so a
file full of sub-cent passive pricing — which is to say almost every real
electronics BOM — was detected as European, and every price was multiplied by
a thousand. A $15.60 BOM reported $15,603.00.

Fixed by the rule that resolves it: a grouped number never begins with a zero
group. `1.000` can still be one thousand; `0.008` cannot be eight.

**A spreadsheet `TOTAL` row was counted as a component.** Purchasing
departments leave a summary row at the bottom of an exported BOM. It was read
as a line item, inflating the part count — and where the row carried an
extended total in the price column, it doubled the cost.

Summary rows are now skipped, and the exclusion is stated in the report
rather than done quietly. The check is deliberately narrow: the description
must *be* a totals word and the row must carry no part number or designator,
so a real component called "Total Phase Beagle I2C probe" is unaffected.

**A value that contradicted the file's number format was coerced — totals up
to 100× too high.** In a file otherwise using US convention, `2,50` had its
comma stripped as a thousands separator and became `250`. A thousands group
is exactly three digits, so `2,50` is not valid US notation at all.

Such a value is now refused and named in the report — `row 7, Unit
Price='2,50': does not match this file's number format` — instead of being
guessed at.

### Added

**`helix-bom diagnose <file>`** — prints how a file was parsed, and none of
what was in it. Encoding, delimiter, which line the header was found on, how
each column mapped, which checks could run, and the *shape* of any cell that
failed to parse (`21 chars, letters`) rather than its contents.

It exists so a bug report is possible at all. A bill of materials names your
suppliers and exposes your costs, so nobody can attach the file that broke
the parser. There is a test that fails if any component data ever reaches
this output.

### Unchanged

No API changes. Nothing to update in your code, and `helix_grounding` itself
is untouched — all three bugs were in the BOM reader.

---

## 0.1.0 — 2026-08-16

First release.

- `helix_grounding` — deterministic verification of currency amounts,
  measurements, identifiers, quantities, percentages and dates in generated
  text, checked against values computed from source data. No model call.
- Domain adapters for bills of materials and invoices.
- `helix-bom review` — BOM review reading KiCad, Altium and spreadsheet
  exports, reporting what it *could not* check as clearly as what it could.
- `helix-bom demo` — runs against a bundled sample, no file needed.
- Zero runtime dependencies, and a test suite that disables the socket layer
  to prove nothing is sent anywhere.
