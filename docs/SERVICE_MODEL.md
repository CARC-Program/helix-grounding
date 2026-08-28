# How somebody buys a review, and why they never upload their BOM

The operating question: *when someone wants a BOM reviewed, how do they reach
out, upload, and pay — how does the reviewer act on it, what compute handles
it, and how does none of that cost their trust?*

There is a trap in it, and the trap is the word **upload**.

---

## The claim that pays for everything

The tool's differentiator, stated in the README, the Reddit draft, and enforced
by a test that disables the socket layer:

> Your BOM never leaves your machine.

A bill of materials is one of the most sensitive documents a hardware company
owns. It reveals what is being built, what it costs, who supplies it, and
therefore the margin. Engineers are cautious about it for good reason and are
famously unwilling to pay for tools — so the thing that gets a stranger to try
this at all is that trying it risks nothing.

**Accepting uploads destroys that.** Not weakens: destroys. The claim is
absolute and testable, and the moment there is a server it becomes a promise
about a server, which nobody can verify and everybody has heard before.

So the design rule is one sentence, and everything else follows from it:

> **Money moves. The BOM does not.**

## What can safely travel, checked rather than assumed

There are two candidate artefacts and only one of them is safe. This was
verified rather than assumed:

| | contains | safe to send? |
|---|---|---|
| `helix-bom diagnose file.csv` | file size, encoding, delimiter, header row, column *headings*, row counts, parse problems by row number | **yes** — no part numbers, prices, quantities or descriptions, and a test fails if any reach it |
| `helix-bom enrich file.csv --json` | part numbers, manufacturers, quantities, unit and extended prices, findings | **no** |

That table settles the question that follows. `diagnose` is safe precisely
*because* it carries nothing to review, and the JSON report is useful precisely
*because* it carries everything sensitive.

**There is no artefact that is both safe to transmit and sufficient to review
remotely.** A remote review service therefore cannot be built without asking
the customer to trust a server with the document they are most careful about.

That is not a gap to engineer around. It is the reason the local tool is the
product.

---

## The three tiers

### Tier 0 — free, local, no account. *Exists today.*

    pip install helix-grounding
    helix-bom enrich your_bom.csv

No signup, no upload, no key. Finds missing part numbers, values in the part
number column, placeholders, duplicate designators, designator/quantity
mismatches, parts ordered twice.

Its job is not revenue. Its job is to be the thing a stranger tries because
trying costs nothing, and to make `helix_ops status` report a number other
than zero.

### Tier 1 — paid licence key. Still local. **This is the business.**

The customer buys a key. The key unlocks the deeper checks — distributor
lifecycle, stock against build quantity, minimum order quantity, price at the
quantity actually being bought. The tool still runs on their machine.

- **Upload:** none. There is nothing to upload.
- **Reach out:** none required. They install and pay.
- **Payment:** a hosted checkout link (see below).
- **Fulfilment:** an emailed key. Zero human minutes, zero infrastructure.
- **Compute:** theirs.

At $99–299/month this is the band `BUSINESS_MODEL.md` argues for, and 51
customers at $99 is the target that matters.

### Tier 2 — a written review. **Do not build this yet, and possibly ever.**

If somebody asks for a human-read report, the honest options are:

1. **They run the tool and send the output they choose to send.** They decide
   what is redacted; you review what arrives. Trust stays theirs.
2. **A call where they share their screen.** Nothing transmitted, nothing
   stored, and it scales to roughly nobody — which is correct at this stage.

What not to do is build an upload portal because it feels like what a business
looks like. It converts a testable guarantee into an unverifiable promise, in
exchange for revenue from customers who do not exist yet.

---

## Payment

**Do not build payment infrastructure.** Use a hosted checkout — Stripe Payment
Link, Lemon Squeezy, Paddle, Gumroad. A merchant-of-record option (Paddle,
Lemon Squeezy) also handles sales tax and VAT registration, which is real work
a one-person operation should not be doing.

That means no card data touches anything here, no PCI scope, no stored
payment details, and no bespoke code to get wrong.

**The blocking constraint is legal, not technical.** Every payment processor
requires an account holder who can enter a contract. That is not the operator
today. Before any money moves there has to be a legal entity or an adult
account holder, and that is a decision to make with the people who can make
it — not something to work around.

Until then Tier 0 is the whole product, and that is fine: it is what produces
the evidence that anyone wants Tier 1.

---

## Compute, honestly

**There is no compute problem.** The checks are string and number work over a
few hundred rows — milliseconds. A laptop from 2012 runs it. Nothing is
downloaded except the package itself, once, from PyPI.

The real constraint is a different one and it is worth stating clearly:

**API quota, and whose key spends it.** Mouser allows 1,000 calls a day and 30
a minute. If Tier 1 uses one shared key, every customer spends the same
allowance and a handful of large BOMs exhaust the day. Worse, serving
distributor data to third parties is the kind of thing distributor terms
commonly prohibit, and doing it would risk the key being revoked.

So: **each customer uses their own distributor key.** The tool already reads
credentials from the environment and never stores them. This keeps quota
per-customer, keeps the terms relationship between the customer and the
distributor where it belongs, and removes the only piece of infrastructure that
would otherwise need to exist.

The cost of that choice is honest: it asks the customer to register for a
distributor account, and some will not. Which is why every check that does not
need a key runs first, always, and why the free tier is genuinely useful.

---

## Not costing them their trust

The question was how the instructions themselves avoid eroding trust. Six
rules, each of which this project has a way of checking:

1. **Never ask for the sensitive thing.** The strongest possible signal is not
   needing their BOM. Everything above is arranged around keeping that true.

2. **No account to try.** Signup is the largest drop-off in any funnel and the
   first place a cautious engineer stops. `pip install` and go.

3. **Make claims checkable, not reassuring.** "We take security seriously" is
   what everyone says. "There is a test that disables the socket layer, here is
   the file" is something they can verify in thirty seconds. Prefer the second
   every time.

4. **Publish the price.** "Contact us for pricing" reads as *we will work out
   what you can afford*. A number on a page is a trust signal.

5. **Fewer steps.** Every extra instruction is a place to lose somebody. If a
   step exists only because it makes the operation feel more like a company,
   delete it.

6. **Say what was not checked, as loudly as what was.** The tool already does
   this and it is the single most trust-building thing in it. A report that
   admits "6 of 7 lines were not looked up, here is why" is believable in a way
   that a clean bill of health is not.

---

## What to build now

Almost nothing.

There are zero users. Building checkout, licence-key issuance and an upload
path before one stranger has run the free tool is the same over-investment
`FIRST_USERS.md` says this project keeps making, in a new costume.

The order is:

1. **Post it.** Get `strangers who ran it` off zero.
2. **Wait for one person to say it caught something real.** That is the signal
   that Tier 1 is worth pricing, and it costs nothing to wait for.
3. **Then** a payment link and a licence key — a day's work, and only sensible
   once somebody has said they would pay.

The upload portal is not step 4. It is not on the list.
