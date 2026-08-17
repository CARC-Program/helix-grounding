# Changelog

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
