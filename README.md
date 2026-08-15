# Project Helix

Deterministic verification of factual values in AI-generated text, proven on
hardware bills of materials.

The problem: a language model states a number that does not appear in its
source data. Anywhere AI touches money, specifications, or deadlines, that is
not a quality issue — it is a liability.

The usual answer is to check the output with another model: LLM-as-judge,
semantic entailment, embedding similarity. All three are probabilistic, all
three cost an inference call, and all three can themselves be wrong.

`helix_grounding` does not do that. It extracts every currency amount,
measurement, identifier, quantity and percentage from generated text and checks
each against a set of values computed from the source data. For that class of
claim the answer is decidable: a value is in the set or it is not. No model
call, no judgement, no confidence score.

```python
from helix_grounding import Verifier, GroundTruth, ClaimKind

truth = GroundTruth().allow_many(ClaimKind.CURRENCY, [18.00, 22.00, 40.00])
report = Verifier().verify(model_output, truth)

if not report.is_grounded:
    print(report.summary())
    retry_prompt = base_prompt + report.correction_note()
```

**Scope, stated plainly:** this verifies *values*, not claims requiring
judgement. It cannot tell you whether advice is good, whether a summary is
complete, or whether a conclusion follows — those need a different layer. What
it can tell you is that no figure reached your customer that you did not put in
front of the model. Unlike a faithfulness score, that is something you can
prove.

### Two domains, one core

A domain adapter turns your data into a `GroundTruth`. The core never learns
what your data is.

```python
from helix_grounding.domains.invoice import ground_truth_for_invoice

report = Verifier().verify(summary, ground_truth_for_invoice(invoice))
```

Given a $1,000 invoice with 10% off and 8.25% tax, this text produces three
findings:

> Invoice INV-2026-0412 totals **$1,074.25** after 8.25% tax of **$82.50**,
> and payment is due **2026-10-01**.

The total is wrong. The tax is 8.25% of the *subtotal* rather than the
discounted base — the arithmetic slip a model actually makes, and one that
reads as correct to a human skimming. The due date is invented. Meanwhile
`INV-2026-0412` and `8.25%` are recognised as genuine and pass.

Adding that second domain is what forced date support into the core: before
it, a fabricated due date produced no claim at all and passed through
silently.

---

## What is actually built

Every row below is running code with tests behind it. Nothing is listed here
because it is planned.

| Module | What it does | State |
|---|---|---|
| `src/helix_grounding/` | The verification library — extractors, ground truth, retry loop | Working, 53 tests, two domains |
| `src/helix_bom/` | BOM review: CSV ingest, deterministic checks, `helix-bom` CLI | Working, 57 tests + 14 sandbox suites |
| `src/helix_llm/` | Backend-agnostic model client (local Ollama by default, Anthropic optional) | Working, local path unverified end-to-end on this machine |
| `src/helix_api/` | FastAPI surface: API key auth, tier gating, audit log | Skeleton — routes work and are tested, never deployed |

## Running it

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
pytest
```

### Reviewing a real BOM

```bash
helix-bom review my_bom.csv --budget 50 --enclosure 100x80x25
```

Takes a CSV export from KiCad, Altium, or a spreadsheet as-is: it finds the
header past KiCad's preamble lines, detects semicolon delimiters, excludes
do-not-populate rows, and reads `1.234,56` and `1,234.56` as the same amount
by deciding the convention per file rather than per cell.

It reports what it **could not** check as loudly as what it could. A plain
KiCad export has no prices, dimensions, power figures or lead times, so most
checks cannot run — and a report that stayed quiet about that would read as a
clean bill of health. `--strict` turns "could not check" into a non-zero exit,
which is what you want gating a build. `--json` emits the same information for
a machine.

161 tests pass, nothing is skipped, and nothing but Python is required. The
project has no database and no server dependency — the library and the CLI
are both stateless.

The BOM agent's LLM synthesis layer needs a backend. By default it calls a
local Ollama instance — see `docs/OLLAMA_SETUP.md`. To use the hosted Anthropic
path instead, set `HELIX_LLM_BACKEND=hosted` and put `ANTHROPIC_API_KEY` in a
`.env` at the repository root. That file is gitignored; `.env.example` is the
template. Never paste a real key into a chat.

## Layout

```
src/helix_grounding/   the product — domain-agnostic, zero dependencies
    domains/           bom.py, invoice.py; a new vertical is a new file here
src/helix_bom/         the proving ground
    ingest.py          reads real CSV exports, reports every assumption
    agent.py           the deterministic checks
    cli.py             the helix-bom command
src/helix_llm/         model client abstraction
src/helix_api/         HTTP surface
tests/                 pytest suite
    sandbox/           script-style suites, run as subprocesses
docs/DECISION_LOG.md   45 decisions with reasoning — read this one
docs/BUSINESS_MODEL.md who pays for what, and the honest ceilings
docs/CASE_STUDY.html   a real caught fabrication, reproducible
docs/MARKET_RESEARCH.html
scripts/               developer utilities
```

## Evidence

`docs/CASE_STUDY.html` walks through two false statements a model actually
made reviewing a BOM, and why catching them took two different defences —
only one was a fabricated *value*; the other was a wrong *relation* between
two real ones. Reproduce both:

```bash
python scripts/reproduce_d036.py
```

It is part of the test suite, so the case study cannot quietly stop being
true while still making its claims.

## History

This repository was rebuilt on 2026-08-14. The `master` branch holds the prior
structure verbatim: 87 markdown documents across 16 numbered folders, against
five real source modules. The documents described systems that did not exist,
and checkpoints were marked complete for having been written about.

Nothing was thrown away — the baseline commit is what makes the restructure
recoverable. `docs/DECISION_LOG.md` survives intact and is the single most
valuable artifact here: 43 decisions with the reasoning attached, including
several real bugs found by running things rather than thinking about them.

`docs/MARKET_RESEARCH.html` records why the direction changed, and which
constraints eliminated which options.
