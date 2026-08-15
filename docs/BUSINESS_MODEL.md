# Business model

Replaces `HELIX_BUSINESS_MODEL.md`, deleted in the rebuild because it
specified cold-outreach retainer consulting — a model the market research
eliminated on two independent constraints.

---

## First, a distinction that keeps getting blurred

**"Agentic" is an operating model, not a business model.** It answers *how
much of the work happens without a human*, never *who pays and for what*.

A business can be fully agentic and earn nothing. That is in fact the normal
outcome, because automation reduces the cost of delivering work and does
nothing about the harder problem of someone deciding to buy it.

So the two questions are separate, and the second one is the one that has
never been answered here:

| Question | Status |
|---|---|
| Can the work run without a human? | **Yes, per job.** Deterministic checks need no model at all; the narrative layer is model-written and machine-verified. Zero human minutes per review. |
| Will a stranger pay for it? | **Unknown. Never tested.** Zero customers, zero revenue, zero users other than the author. |

Everything below is written against the second row.

---

## What is actually sellable

Two assets, and they are not the same business. Their economics differ enough
that treating them as one product is the main strategic error available here.

### Asset A — `helix-bom`, the BOM reviewer

| | |
|---|---|
| **Buyer** | Hardware startups, solo hardware engineers, small assembly shops |
| **Pays for** | Catching a costly mistake before a board is fabricated |
| **Price band** | $99–299/month, or $25–75 per review |
| **Human minutes per job** | Zero |
| **Acquisition** | Hardware communities, the KiCad/Altium ecosystem, search for "BOM checker" |
| **Time to first dollar** | Shortest available — the product exists and runs today |
| **Honest ceiling** | **Small.** Perhaps $5–20k/month at maturity |

The ceiling deserves emphasis rather than burial. There are not that many
hardware companies, and hardware engineers are famously unwilling to pay for
tools. This will not become a large business.

That is acceptable, because its job is not to be large. Its job is to convert
*"nobody has ever paid for this"* into *"a stranger paid for this"*, which is
the single most valuable piece of information the project can acquire and the
one it has never had.

### Asset B — `helix_grounding`, the verification library

| | |
|---|---|
| **Buyer** | Developers shipping AI features where numbers must be right |
| **Pays for** | Being able to *prove* no fabricated figure reached a customer |
| **Price band** | Free library; hosted API metered, or a commercial licence |
| **Human minutes per job** | Zero |
| **Acquisition** | GitHub, PyPI, technical writing — structural, no outreach |
| **Time to first dollar** | Long. Six to eighteen months is normal for library-to-revenue |
| **Honest ceiling** | **High, and uncertain.** Braintrust is at $800M on the adjacent problem |

The differentiator is narrow and defensible: every funded competitor checks AI
output using more AI. This does not. For values — currency, measurements,
identifiers, quantities, percentages, dates — the answer is decidable, needs
no inference call, and cannot itself hallucinate.

That is a smaller claim than the incumbents make, and a *harder* one. "We can
prove no fabricated figure reached your customer" is something a regulated
buyer can act on. "Our judge model scored it 0.94 for faithfulness" is not.

---

## The plan: run both, on different clocks

They are not competing options. They cost nothing to run in parallel, because
B is already built and needs no ongoing work to sit on a package registry.

**Now → six months — A earns, B accumulates.** The reviewer is the only thing
that can produce revenue this year. Publish the library at the same time and
let it collect users while the reviewer collects customers.

**Then — generalise from what A teaches.** The pattern underneath both is *a
small business has data, needs a document written from it, and the numbers
must be right.* BOM review is one instance. The invoice adapter already
proves a second exists. Which third one to build should be decided by what
the first paying customers actually ask for — not chosen here, in advance, on
no evidence.

**Not before then.** Picking the big market now would repeat the original
mistake in a new costume: choosing a direction from reasoning rather than
from contact with someone who pays.

---

## The constraint that is not going away

**Distribution is the bottleneck, and automation cannot fix it.**

The delivery side is genuinely solved — zero human minutes per job. What is
not automated, and cannot be, is a stranger learning the tool exists. That
requires either an audience, paid acquisition, or being present where the
buyers already are.

Given the standing constraint against outreach-dependent business, the only
acceptable channels are structural: a package registry, a searchable
repository, a tool that appears in the ecosystem people already work in. Those
are slow and they compound. Cold messaging is fast and does not.

Which means the realistic first-revenue horizon is **months, not weeks**, and
any plan implying otherwise is wrong.

---

## What "more than a teacher" requires

$5,000/month, from the research:

| Price | Customers needed | Reachable? |
|---|---|---|
| $19/mo | 264 | No — needs an audience that does not exist |
| $99/mo | 51 | Plausible |
| $299/mo | 17 | Very achievable |

Fifty-one is a findable number. Two hundred and sixty-four is not. This is the
whole argument for B2B pricing from day one and against anything
consumer-priced, and it has not changed.

Against base rates — 70% of micro-SaaS never clears $1,000/month, 6.1% clear
$10,000 — reaching that figure puts this in roughly the top decile of
outcomes for its class. Achievable; not typical.
