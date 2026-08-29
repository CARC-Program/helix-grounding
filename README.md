# helix-grounding

**Catch the numbers an AI made up — without asking another AI.**

A language model states a figure that isn't in its source data. In anything
touching money, specifications, or deadlines, that's not a quality issue —
it's a liability.

The usual defence is to check the output with another model: LLM-as-judge,
semantic entailment, embedding similarity. All three are probabilistic, all
three cost an inference call, and all three can be wrong themselves.

This doesn't do that. It extracts every currency amount, measurement,
identifier, quantity, percentage and date from generated text and checks each
against values computed from your source data. For that class of claim the
answer is decidable: a value is in the set or it isn't. **No model call, no
judgement, no confidence score.**

```bash
pip install helix-grounding
helix-bom demo          # see it catch something, no file needed
```

```python
from helix_grounding import Verifier, GroundTruth, ClaimKind

truth = GroundTruth().allow_many(ClaimKind.CURRENCY, [18.00, 22.00, 40.00])
report = Verifier().verify(model_output, truth)

if not report.is_grounded:
    print(report.summary())
    # -> UNGROUNDED: 1 of 4 claims not found in source data — $36.00 (currency)
    retry = base_prompt + report.correction_note()
```

The correction names the specific invented value and quotes the sentence it
appeared in, because a blind re-roll reproduces the same error at roughly the
same rate.

---

## See it work on your own file

The package ships a complete worked example: a bill-of-materials reviewer
built on the library. `helix-bom demo` runs it against a bundled sample;
point it at your own CSV export when you want a real answer.

```bash
helix-bom review my_bom.csv --budget 10
```

```
BOM total: $13.81  (budget $10.00)

Findings:
  [CRITICAL] BOM total ($13.81) exceeds stated budget ($10.00) by $3.81.
  [WARNING]  ARM Cortex-M4 MCU has a stated lead time of 120 days — this is a
             real supply-chain risk that can silently become the critical path.

NOT CHECKED (3):
  physical fit
      no component dimensions in the submitted data — standard EDA exports
      carry footprints, not millimetres

  These are not passes. Supply the missing columns to check them.
```

It reads what KiCad, Altium and spreadsheets actually export: preamble lines
before the header, semicolon delimiters, do-not-populate rows, and `1.234,56`
versus `1,234.56` decided per file rather than per cell.

### Or hand it the schematic instead

A BOM is a shopping list. It says which parts and how many, and it is silent
on how any of them connect — so a wiring diagram drawn from one is not hard to
produce, it is impossible. The data is not in the file. Point it at a KiCad
netlist and that changes:

```bash
helix-bom review sensor_board.net --diagram board.svg
```

```
Interconnect (6 link(s), read from the file — not inferred):
  U1 <-> U2        I2C_SDA, I2C_SCL
  J1 <-> U1        USB_DP
  R1 <-> U1        I2C_SDA
  ...

Findings:
  [WARNING] Net 'SENSOR_INT' reaches only U1 pin 12 (PA12). A named net with
            one connection is a label that was typed but never joined anything.
```

Every line drawn is a net that exists between pins that are named, so the
diagram can be checked against the schematic and found wrong. Power and ground
are left out — they touch nearly every part, and drawing them yields a
hairball that says less than drawing nothing.

The dangling-label finding is the one worth having. On a schematic printout a
net label that connected to nothing looks exactly like one that connected, so
it is invisible to review and trivial to a parser. Labels KiCad generated
itself (`unconnected-(U1-Pad7)`) are left alone; only a name a person typed is
flagged.

A netlist carries no prices, no dimensions and no power figures, and no export
option adds them — so all five BOM checks report themselves as unrun rather
than passing quietly. Run both files to cover both halves.

**A check that couldn't run is never reported as a pass.** `--strict` makes
"couldn't check" a non-zero exit; `--json` emits the same for a machine.

**If it reads your file wrong, don't send me the file.** Send this instead:

```bash
helix-bom diagnose my_bom.csv
```

It prints the structure — encoding, delimiter, which line the header was
found on, how each column mapped, and the *shape* of any cell that failed to
parse (`21 chars, letters`) rather than its contents. Safe to paste into a
public issue. There is a test that fails if any component data ever reaches
that output.

### Your BOM never leaves your machine

A bill of materials exposes a design, its costs and its suppliers. Reading
and reviewing one here is **entirely offline** — no upload, no telemetry, no
account, no network call of any kind.

That is not a promise, it is a test. `tests/test_offline_guarantee.py`
disables Python's socket layer outright and then runs the real code path
end to end, so any attempt to reach the network by any library at any depth
is a hard failure rather than a quiet one. It also asserts the block itself
works, because a guard that silently stops guarding is worse than none.

The only component that can reach out is the optional narrative writer, and
it defaults to a model running on your own hardware.

---

## A real fabrication, caught

Not a demo — a model actually wrote both of these while reviewing a BOM:

> "the Bosch BME680 at **$3.10** is slightly cheaper than your current part at
> **$2.40**"

> "The ESP32-S3 module at **$3.40** has a lead time concern"

The second is caught: $3.20 is the real price, and $3.40 appears nowhere in
the source data.

**The first passes the check — and should.** Both numbers are real. What's
false is the word *cheaper*, a claim about the *relation* between two values.
No value-checker can see that, and a library claiming otherwise would be
misrepresenting its own scope. It's prevented a different way: the comparison
is computed in Python before the prompt is built, so the model is only asked
to phrase an answer that's already correct.

Reproduce both yourself:

```bash
python scripts/reproduce_d036.py
```

Full write-up: `docs/CASE_STUDY.html`.

---

## What it can't do

Stated plainly, because a validation layer that quietly misses a category is
worse than none — it manufactures false confidence.

- **Judgement claims are out of scope.** Whether advice is good, whether a
  summary is complete, whether a conclusion follows. Those need an
  LLM-as-judge layer. This is not one.
- **Identifiers need a vocabulary.** No lexical rule separates a part number
  from a standards name — `RS485` and `BME280` are the same shape. A default
  vocabulary of known non-identifiers ships in, and is meant to be extended.
- **Amounts written as words** ("thirty-six dollars") aren't caught. Symbol
  and suffix forms are: `$36`, `36 dollars`, `36 USD`.
- **Relative dates are out of scope** ("next Tuesday", "in 30 days") — those
  depend on what *now* means, which makes them judgement claims.

---

## Your own data

A domain adapter turns your data into a `GroundTruth`. The core never learns
what your data is — two ship as reference implementations, and a third is a
new file, not a change to the verifier.

```python
from helix_grounding.domains.invoice import ground_truth_for_invoice

report = Verifier().verify(summary, ground_truth_for_invoice(invoice))
```

Invoices exercise a shape a BOM never does: a *chain*, where line totals feed
a subtotal, the subtotal feeds a discount, the remainder feeds a tax. Every
intermediate is a figure a model will quote, so the adapter permits the whole
working — not just the answer.

Adding that second domain is what forced date support into the core. Before
it, a fabricated due date produced no claim at all and passed straight
through.

**Zero runtime dependencies, deliberately.** The argument for this library is
that checking a model's output shouldn't require another model. A dependency
on an inference client would undercut that.

---

## Development

Python 3.10+.

```bash
pip install -e ".[dev]"
pytest
```

648 tests, nothing skipped, no database and no services required.

```
src/helix_grounding/   the library
    domains/           bom.py, invoice.py — add a vertical here
src/helix_bom/         the worked example: ingest, checks, CLI
src/helix_llm/         optional model client (local Ollama, or Anthropic)
CHANGELOG.md           what changed, and whether you need to re-run anything
docs/                  decision log, architecture, business model, case study
                       FIRST_USERS.md — how the first users get found
```

`docs/DECISION_LOG.md` is 55 decisions with the reasoning attached, including
the bugs that produced the design above. It is the most useful file here for
understanding *why* rather than *what*.

## Licence

MIT.
