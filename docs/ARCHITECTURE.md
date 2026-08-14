# Architecture

Replaces the 40-odd design documents that previously lived in folders 04–08.
Those described a system that did not exist. This describes the one that does,
and says plainly where the edges are.

The rule for this file: **if it isn't running, it says so.** A design that has
not been built is a plan, and plans belong in `ROADMAP.md`.

---

## The shape

```
                 ┌─────────────────────────────────────┐
   source data ──┤  helix_bom.agent                     │
   (components,  │    deterministic checks   ← no model │
    constraints) │      budget, power, fit, lead time   │
                 └───────────────┬─────────────────────┘
                                 │ findings + component list
                                 ▼
                 ┌─────────────────────────────────────┐
                 │  helix_llm.client                    │
                 │    Ollama (default) | Anthropic      │
                 └───────────────┬─────────────────────┘
                                 │ narrative text
                                 ▼
                 ┌─────────────────────────────────────┐
   source data ──┤  helix_grounding.Verifier            │
                 │    extract → compare → reject/retry  │
                 └───────────────┬─────────────────────┘
                                 │ validated text, or fallback
                                 ▼
                            deliverable
```

The load-bearing idea is the third box, and the ordering matters: the model
never gets the last word. Its output is checked against the same data it was
given, and text that fails is regenerated with the specific fabricated values
named — or withheld entirely.

## Two layers, deliberately separated

**Deterministic first.** Budget totals, power sums, physical fit, lead-time
risk, and every price comparison are computed in Python. The model is never
asked to do arithmetic or multi-entity bookkeeping.

This was learned, not designed. A live run had a local model call a $3.10 part
"cheaper" than a $2.40 one, and separately conflate two components' lead times
into a single paragraph (`DECISION_LOG.md` D-036). The fix was not a better
prompt — it was moving the comparison into code and leaving the model only the
job of phrasing an already-correct result.

**Model second, and checked.** The narrative layer produces prose. Everything
factual in that prose is verified against ground truth before it goes anywhere.

## helix_grounding

Domain-agnostic by construction. The core knows nothing about components or
enclosures; `domains/bom.py` knows nothing about regexes or tolerances. A new
vertical is a new file in `domains/`, not a change to the verifier.

| Piece | Responsibility |
|---|---|
| `claims.py` | `Claim`, `ClaimKind`, `GroundingReport`, correction-note generation |
| `extractors.py` | Pattern-based claim recovery — currency, measurement, identifier, quantity, percentage, date |
| `truth.py` | `GroundTruth`: allowed values per kind and unit, tolerances, derived differences |
| `verifier.py` | Runs extractors against ground truth; owns the generate-and-validate loop |
| `domains/bom.py` | Builds a `GroundTruth` from components and constraints |
| `domains/invoice.py` | Builds a `GroundTruth` from an invoice and its lines |

**Zero runtime dependencies, deliberately.** The argument for this library is
that checking a model's output should not require another model call. A
dependency on an inference client would undercut that.

### What the second domain proved

The claim "domain-agnostic" is cheap to make with one domain, because a core
shaped around its only caller looks general right up until the second one
arrives. Adding invoices forced exactly two core changes, both general
capabilities rather than special cases:

- **`ClaimKind.DATE` and `DateExtractor`.** A due date stated in generated
  text produced no claim at all, so a model could invent one and nothing
  noticed. Dates are as decidable as currency amounts, so they belong in the
  core. BOM review can use them too, without a line of invoice code involved.
- **Per-kind token storage.** `GroundTruth` kept exact-match values in one
  untyped set, which worked only while identifiers were the sole exact-match
  kind. It is now keyed by kind, so a date cannot satisfy an identifier claim.

Nothing else changed. `tests/test_invoice_domain.py` enforces this
structurally: it parses each core module, strips docstrings, and fails if a
domain concept survives into executable code.

Invoices were chosen because they stress a shape BOM never did. BOM review is
sums and comparisons; an invoice is a *chain* — line totals feed a subtotal,
the subtotal feeds a discount, the remainder feeds a tax, the tax feeds the
total. Every intermediate is a figure a model will quote, so the adapter has
to permit the whole working and not just the answer.

### What it cannot do

Stated because a validation layer that quietly misses a category is worse than
none — it manufactures false confidence.

- **Judgement claims are out of scope.** Whether advice is good, whether a
  summary is complete, whether a conclusion follows. Those need an
  LLM-as-judge layer; this is not one.
- **Identifiers need a vocabulary.** No lexical rule separates a manufacturer
  part number from a standards name — `RS485` and `BME280` are the same shape.
  A default vocabulary of known non-identifiers ships in `extractors.py` and is
  expected to be extended per domain. A fabricated part number that happens to
  sit in the vocabulary will pass. That is the deliberate trade: a false
  negative is recoverable, while a false positive burns every retry and
  suppresses a report that was correct.
- **Amounts written as words** ("thirty-six dollars") are not caught. Symbol
  and word-suffix forms are (`$36`, `36 dollars`, `36 USD`).
- **Units must be adjacent to the number.** A value whose unit is implied by a
  previous sentence reads as unitless.
- **Relative dates are out of scope** ("next Tuesday", "in 30 days", "Q3").
  A relative date depends on what *now* means, which makes it a judgement
  claim. Absolute dates are checked in ISO, slash, and written forms, with
  impossible ones rejected rather than normalised into a real day.
- **Ambiguous numeric dates need a convention.** `03/04/2026` is March 4th in
  US usage and April 3rd nearly everywhere else, and no parser resolves that.
  `DateExtractor(day_first=...)` picks; where a component exceeds 12 the order
  is unambiguous and read correctly regardless.
- **An empty `GroundTruth` raises** rather than reporting everything
  ungrounded — that state almost always means the caller forgot a step, and a
  loud failure beats a confidently wrong verdict.

## helix_bom

The wedge. Deterministic checks against a submitted BOM:

- budget total vs. stated budget (quantity-aware — a fix from D-033)
- power draw total vs. power budget
- physical fit against the enclosure envelope
- missing-category sanity check
- long-lead-time supply risk

Plus SVG diagram generation (interconnect sketch, top-down placement blueprint)
gated by service tier. Both diagrams state in their own rendered text that they
are suggestions derived from category tags, not verified schematics — the
caveat travels with the artifact rather than living in a code comment.

## helix_llm

One interface, swappable backend. `LocalOllamaLLMClient` is the default: no API
key, no subscription, inference on the owner's own hardware. `AnthropicLLMClient`
is the hosted fallback, selected by `HELIX_LLM_BACKEND=hosted`.

Currently CPU-only (`force_cpu=True`) because the GPU's VRAM is fully claimed by
a separate system. That is a stated temporary constraint, not a design choice —
flip `force_cpu=False` and use a larger model when the GPU frees up.

## helix_api

A skeleton, and labelled as one. The routing shape works and is tested:
signature verification against a terminal registry, tier gating, audit logging
of every request including rejected ones. What is **not** wired: real
hardware-backed auth (the ECDSA keypair here is a software stand-in for a
secure element that does not exist), the Postgres connection, and Redis-backed
rate limiting. It has never been deployed or exposed to a network.

## Audit logging

Every request is logged — including auth failures and every rejected synthesis
attempt with the specific values that were fabricated. Rejections are recorded
rather than discarded on purpose: a fabrication that was caught is the evidence
the safety net works, and throwing it away destroys the only proof.

SQLite in-memory for tests, with an explicit lock around writes because ASGI
servers run handlers across a thread pool and SQLite forbids cross-thread use
by default (D-019). Production would use the Postgres schema in `migrations/`.

## Open questions

Recorded here rather than answered confidently:

- **The Postgres schema serves a business model that was eliminated.** Its
  tables are `clients`, `deliverables`, and retainer status — the consulting
  shape ruled out by `MARKET_RESEARCH.html`. The audit-trail and pgvector parts
  may survive a rewrite; the client-relationship parts probably should not.
- **`helix_api`'s auth models hardware that no longer exists.** With the
  cyberdeck cut, the terminal registry is a solution to a problem the project
  does not have. If the product is a library and a hosted API, ordinary API-key
  auth is the honest replacement.
- **The local model path has not been verified end-to-end on this machine.**
  Its "server unreachable" branch is genuinely tested; a full round trip with
  real weights has not been run here.
