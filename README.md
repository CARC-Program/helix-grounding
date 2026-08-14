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

---

## What is actually built

Every row below is running code with tests behind it. Nothing is listed here
because it is planned.

| Module | What it does | State |
|---|---|---|
| `src/helix_grounding/` | The verification library — extractors, ground truth, retry loop | Working, 22 tests |
| `src/helix_bom/` | BOM review agent: budget, power, physical fit, lead-time checks | Working, 14 sandbox suites |
| `src/helix_llm/` | Backend-agnostic model client (local Ollama by default, Anthropic optional) | Working, local path unverified end-to-end on this machine |
| `src/helix_api/` | FastAPI orchestrator with signature auth and audit logging | Skeleton — routes work, not deployed |
| `migrations/` | PostgreSQL schema (audit trail, pgvector memory) | Written, not currently exercised — see Roadmap |

## Running it

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
pytest
```

45 tests pass, 1 skips. The skip is `test_database_sandbox.py`, which needs a
live PostgreSQL 16 + pgvector instance; it is skipped rather than failed so a
red suite always means a real regression.

The BOM agent's LLM synthesis layer needs a backend. By default it calls a
local Ollama instance — see `docs/OLLAMA_SETUP.md`. To use the hosted Anthropic
path instead, set `HELIX_LLM_BACKEND=hosted` and put `ANTHROPIC_API_KEY` in a
`.env` at the repository root. That file is gitignored; `.env.example` is the
template. Never paste a real key into a chat.

## Layout

```
src/helix_grounding/   the product — domain-agnostic, zero dependencies
    domains/bom.py     reference adapter; a new vertical is a new file here
src/helix_bom/         the proving ground: BOM review agent
src/helix_llm/         model client abstraction
src/helix_api/         HTTP surface
tests/                 pytest suite
    sandbox/           script-style suites, run as subprocesses
docs/DECISION_LOG.md   43 decisions with reasoning — read this one
docs/MARKET_RESEARCH.html
migrations/            PostgreSQL schema
scripts/               developer utilities
```

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
