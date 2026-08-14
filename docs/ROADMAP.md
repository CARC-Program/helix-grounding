# Roadmap

Replaces `HELIX_PROJECT_ROADMAP.md` and the checkpoint table in the old master
document.

**Why the old one failed.** Checkpoints were closed by writing documents. Seven
of sixteen were marked *CLOSED — all files complete* while the systems they
described did not exist, so the project reported itself half-finished having
built one agent. A scoring system that rewards typing will be gamed by typing.

**The rule here:** a milestone closes when something runs and a test proves it,
or when a real person does something they did not do before. Nothing closes for
having been written about.

---

## Now

Direction set by `MARKET_RESEARCH.html`: a deterministic grounding layer,
proven in hardware BOM review. Two constraints bind everything — no
outreach-dependent acquisition, and no negotiated contracts before 18. Both
select the same shape: self-serve, credit-card, no signature required.

### M1 — The library stands alone
*Closes when: someone who is not the author can install it and verify their own
output.*

- [x] Extract the validator from the BOM agent into `helix_grounding`
- [x] Domain-agnostic core with a reference adapter (`domains/bom.py`)
- [x] Fix the six real defects the extraction surfaced
- [x] A second domain adapter — `domains/invoice.py`. Chose invoices over lab
      results because they stress a shape BOM never did: a derivation chain
      (subtotal → discount → tax → total) rather than flat sums
- [x] Prove the abstraction structurally, not by assertion. The core is now
      parsed, stripped of docstrings, and checked for domain coupling by test
- [ ] Publish to PyPI under a name that is actually available
- [ ] A third domain, ideally chosen by whoever adopts it first rather than
      guessed at here

### M2 — The wedge is usable by a stranger
*Closes when: a hardware maker who has never spoken to the author runs a BOM
through it and gets a report back.*

- [x] Surface chosen: a CLI. The audience already has a terminal open next
      to their EDA tool and a file on disk; a web form asks for more work
      than the tool saves
- [x] Read the formats people actually have — KiCad preamble lines,
      semicolon delimiters, DNP columns, European decimal commas, Excel BOMs
- [x] Legible failure modes: every assumption is reported, unreadable cells
      are named with their spreadsheet row, and a file that is not a BOM is
      refused rather than guessed at
- [x] **Never report a check that did not run as a pass.** The agent now
      names each skipped check and what it needs
- [ ] Get it in front of one hardware maker who has never spoken to the
      author. Everything above is preparation; this is the milestone
- [ ] Publish one real caught fabrication as a case study — D-036 is already
      written up and is the strongest evidence the approach works

### M3 — First payment
*Closes when: money arrives from someone unrelated to the author.*

- [ ] account owner on the Stripe account. An adult account owner is required, but a
      adult account owner must be the account owner before it accepts charges or
      transfers funds. Arrange this deliberately, not at first sale
- [ ] Price in the $99–$299/month band. The arithmetic is in the research:
      ~51 customers at $99 reaches teacher-salary income; ~264 at $19 does not
- [ ] No contracts, no invoicing, no negotiated terms — card on file only

## Next

Ordered by evidence, not appeal.

- **Rewrite or retire the Postgres schema.** It models `clients`,
  `deliverables`, and retainer status: the consulting business that was
  eliminated. The audit-trail and pgvector portions may be worth keeping; the
  client-relationship tables should not be resurrected unmodified. Decide
  before installing Postgres to make one test pass.
- **Replace terminal-signature auth with API keys.** `helix_api.auth` models a
  secure element on hardware that was cut. It is a well-built solution to a
  problem the project no longer has.
- **Verify the local model path end-to-end.** The unreachable-server branch is
  genuinely tested; a full round trip with real weights has not been run on
  this machine.

## Not doing

Recorded so they are not quietly reconsidered.

- **The cyberdeck** (old folders 02, 03, 14 — terminal, custom PCB,
  manufacturing). A portable AI terminal is a good object with no causal path
  to revenue. Cut 2026-08-14 by the owner's own decision.
- **Consulting on retainer.** The prior business model. Fails the
  no-outreach constraint outright, and requires signing agreements a non-signing party
  cannot enforceably sign.
- **Anything consumer-priced.** 264 customers at $19/month is not reachable
  without an audience; 51 at $99 is.
- **Competing with Braintrust head-on.** They have $120M and an $800M
  valuation. Coexistence is the plan — a specific defensible claim they are not
  making, not a better version of theirs.

## How to close a milestone

Tick a box when the test exists and passes, or when the real-world event
happened. If a box has been open a long time, that is information: either the
work is harder than it looked or it is not actually the next thing. Both are
worth writing down in `DECISION_LOG.md` — which is what that file has always
been good at.
