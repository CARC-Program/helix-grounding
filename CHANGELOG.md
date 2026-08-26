# Changelog

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
