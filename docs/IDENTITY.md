# Names

What each thing is called, and the rule that names the next one.

The rule matters more than any individual name here. A naming system that
answers "what do we call the next vertical" costs one decision total; a list of
clever names costs a decision every time, and the decisions get made under
deadline pressure by whoever is typing.

---

## The four names

| | Name | What it is | Where it appears |
|---|---|---|---|
| **The operator** | **Helix** | The AI that runs the operations — checks, drafts, tracking, proposed fixes | Internally; in commit trailers; never sold as a product |
| **The entity** | **Helix Labs** | The commercial identity, and eventually the registered company | PyPI `authors`, the repository, invoices, the eventual LLC |
| **The library** | **helix-grounding** | Deterministic verification of values in generated text | PyPI package name, imports, docs |
| **The reviewer** | **helix-bom** | BOM and netlist review, built on the library | CLI command, docs |

**Helix is the operator, not a product.** It is the layer that runs the
business: gathering facts, drafting outreach, tracking the campaign, turning a
bug report into a failing test. Nothing is sold under the bare name "Helix", and
no customer is ever asked to buy "Helix" — they buy a `helix-<something>`.

That separation is what stops the name meaning nothing. "Helix" appearing on
the operator, the company, and every product would make it a prefix rather than
a name.

---

## The rule for every future vertical

```
helix-<domain>
```

`<domain>` is the noun a buyer already uses for their own problem, not a word
invented here. `helix-bom` because hardware people say BOM. `helix-invoice`
because bookkeepers say invoice.

Three properties this buys, all of which are worth more than distinctiveness:

- **A new vertical costs zero naming decisions.** `docs/ARCHITECTURE.md`
  already says a new domain is a new file in `helix_grounding/domains/`. This
  makes the name fall out of the same choice.
- **It is searchable.** People look for "BOM checker", not for a brand they
  have never heard. A name that describes the job is discoverable; a clever one
  has to be marketed into recognition, which costs money this business does not
  have.
- **It states the relationship.** Every product visibly sits on the same
  library, which is the actual technical claim and the reason a second vertical
  was cheap to build.

### Reserved, not built

| Name | State |
|---|---|
| `helix-invoice` | The adapter exists (`helix_grounding/domains/invoice.py`) and is tested. It is **not a product** — nothing is packaged, priced or documented for a buyer. |

`docs/BUSINESS_MODEL.md` is explicit that the third vertical should be chosen
by what a paying customer asks for, not picked here in advance. The name is
reserved so that decision, when it comes, is not also a naming decision.

---

## What must not be renamed

**`helix-grounding` is the PyPI package name and it is load-bearing.** It
appears in `pyproject.toml`, the CI workflow, four URLs, every install command
in every draft post, and the README. Renaming it after publication breaks every
link anyone saved and splits the download history across two names.

If it is ever going to change, it changes *before* the first upload. After
that, the cost is permanent.

---

## The trademark caution

Not legal advice, and stated as a flag rather than a conclusion.

**"Helix" is heavily used.** There is a genomics company, a mattress company,
and assorted software projects using it. For a developer-tools company the
relevant question is whether there is confusion within the same class of goods,
and coexistence across different industries is ordinary — but that judgement is
not one to make from a search engine.

Two practical consequences:

1. **Before registering an entity or filing a trademark, get a knockout search
   done.** That is a real service with a real (small) cost, and it is cheaper
   than renaming a company that has customers.
2. **Publishing a package under the name is not the same commitment.** A PyPI
   name is a username, not a trademark claim. Publishing first and deciding on
   the entity name later is the ordinary sequence and does not foreclose
   anything.

**Re-check availability at upload time.** `docs/PUBLISHING.md` records that
`helix-grounding` was confirmed available — that was a check on a date, not a
reservation. PyPI names are claimed continuously.

---

## Why not something more distinctive

Considered and rejected: an invented word, or a name with no relationship to
what the thing does.

A distinctive name is an asset when you can afford to teach an audience what it
means. That costs marketing spend or an existing audience, and
`docs/BUSINESS_MODEL.md` is blunt that this business has neither and that
distribution is its binding constraint. A name that describes the job is found
by people searching for the job.

The counter-argument is real and worth recording: descriptive names are harder
to trademark and easier to be crowded out of. That is a cost accepted
deliberately, and it is reversible in the direction that matters — a product
can acquire a distinctive brand later, on top of a package name that stays put.

Related: [`BUSINESS_MODEL.md`](BUSINESS_MODEL.md), [`PUBLISHING.md`](PUBLISHING.md),
[`LEGAL_CHECKLIST.md`](LEGAL_CHECKLIST.md), decision `D-047`.
