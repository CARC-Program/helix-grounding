# Getting the first users

The milestone: **three to five hardware people who have never spoken to you
run the CLI on a real BOM.** Not customers yet. Users.

Everything built so far is preparation for this. No further code substitutes
for it.

---

## The reframe that makes this doable

You are not selling anything. **You are asking for a bug report.**

That distinction changes everything about how hard the ask is:

| Selling | Asking for a bug report |
|---|---|
| "Will you pay for this?" | "Will you try to break this?" |
| They owe you a decision | They owe you nothing |
| Rejection is personal | Silence is just silence |
| Needs trust up front | Needs thirty seconds |

Hardware engineers *like* finding faults in tools. Handing one a thing that
claims to check their BOM and saying "I bet it gets your file wrong" is an
invitation, not a pitch. Some will try it purely to prove you wrong — and a
person who runs it to prove you wrong has still run it.

**This does not violate the no-outreach constraint.** That rule is about the
*business model*: revenue must not depend on you cold-pitching strangers
every month. Getting the first handful of users is a one-time act of putting
the thing where people can find it. Those are different problems, and
confusing them means never starting.

---

## Order of operations

Each step needs the one before it. Doing them out of order wastes the post.

1. **GitHub repo public.** A post needs something to link to, and a private
   repo link is worse than no link.
2. **Published to PyPI.** `pip install helix-grounding` is a far lower bar
   than "clone this repo and set a PYTHONPATH". Most people who would have
   tried it will not clone.
3. **Then post.** Not before. A "coming soon" post spends your one good
   first impression on nothing.

---

## Where to post, in order of expected yield

### 1. r/PrintedCircuitBoard

People post boards for critique there constantly — it is literally the
subreddit's purpose. A free tool that checks the BOM half of that is on
topic rather than an intrusion.

Read the rules before posting; some subreddits require a flair or forbid
links from new accounts. If yours is new, comment helpfully on other posts
for a few days first. An account with no history posting a link reads as
spam no matter how good the link is.

### 2. Show HN

The single highest-yield technical audience, and a genuine one-shot: you
cannot repost the same project effectively. Save it until the README, the
demo, and the install path are all working, because everyone who arrives
does so within about four hours.

Post on a weekday morning US time. Then **stay at the keyboard for those four
hours** and answer every comment. On Show HN the author replying carefully is
most of what makes a post go well.

### 3. The KiCad community

The forum and Discord. The ingest layer specifically handles KiCad's preamble
lines and grouped-reference exports, and saying so gives you a reason to be
there that is not "please look at my thing".

### 4. EEVblog forum, Hackaday.io

Slower, older, more skeptical. Worth doing after you have survived one round
of feedback elsewhere.

**Post in one place at a time.** Fix what the first round finds before the
second. Five posts in a day is a spam pattern; five posts over three weeks,
each better than the last, is a launch.

---

## Drafts

Adapt these — do not paste them verbatim. Anything that reads as
copy-and-paste marketing gets ignored, and the honest version in your own
words will land better than a polished version in mine.

### Reddit

> **Free CLI that sanity-checks a BOM export — trying to break it**
>
> I built a command-line tool that reads a BOM CSV (KiCad, Altium, or a
> spreadsheet) and flags budget overruns, long-lead parts, and enclosure fit.
> It runs entirely offline — your BOM never leaves your machine, and there is
> a test that disables the socket layer to prove it.
>
> ```
> pip install helix-grounding
> helix-bom demo                       # bundled example
> helix-bom review your_bom.csv --budget 50
> ```
>
> I would genuinely rather it fail on your file than pass. The part I am
> least sure about is column detection — every EDA tool names things
> differently, and I have only tested against exports I could get hold of. If
> it misreads your header, mangles a price, or misses something obvious, that
> is what I want to hear.
>
> One thing it deliberately does: it tells you which checks it *could not*
> run. A standard export has no dimensions or power figures, so those checks
> get skipped — and a report that stayed quiet about that would read as a
> clean bill of health when it means "I could not look".
>
> Source: <link>

### Show HN

> **Show HN: Catch the numbers an AI made up, without asking another AI**
>
> Every tool I found for checking LLM output does it with another LLM —
> judge models, semantic entailment, embedding similarity. All of those are
> probabilistic, cost an inference call, and can be wrong themselves.
>
> This takes a narrower approach: extract every currency amount, measurement,
> identifier, quantity, percentage and date from the generated text, and check
> each against values computed from the source data. For that class of claim
> the answer is decidable — the value is in the set or it is not. No model
> call, no confidence score, nothing that can itself hallucinate.
>
> It is a smaller claim than the incumbents make and a harder one. "No
> fabricated figure reached your customer" is provable. "0.94 faithfulness"
> is not.
>
> The repo includes a real incident: a model reviewing a bill of materials
> wrote two false sentences, and **the checker only catches one of them.**
> "$3.40" for a $3.20 part is a fabricated value and gets rejected. Calling a
> $3.10 part "cheaper" than a $2.40 one is a wrong *relation* between two real
> values, which no value-checker can see — that one is prevented differently,
> by computing the comparison in code so it is never generated. There is a
> script that reproduces both.
>
> Zero runtime dependencies, and a test that disables Python's socket layer
> to prove nothing is sent anywhere.

---

## What not to do

- **No DMs.** Post in public where people opted in to seeing things.
- **Do not post to five places at once.** That is the spam pattern.
- **Do not argue with criticism.** "Good catch, fixing it" ends well;
  defending a bug does not, in public, permanently.
- **Do not promise a feature to win an argument.** "Not planned right now" is
  a complete answer.
- **Do not mention pricing yet.** You are asking for bug reports. Pricing
  turns the conversation into a negotiation you are not ready for and cannot
  legally close.

### On mentioning your age

Entirely your call, and there is no wrong answer.

It generates real goodwill — people root for a someone who shipped something
that works. It also means some readers judge the code by the age rather than
on merit, and it attaches your age to a public post permanently.

The work stands on its own either way. If you would rather it be judged
without that context, say nothing; it is not dishonest to simply not
volunteer it.

---

## Handling what comes back

**Someone reports a bug.** Best possible outcome. Reproduce it, write a test
that fails, fix it, reply with the commit. That reply is worth more than the
original post — it is public evidence you are someone who fixes things.

**Someone says "it worked, nothing to report."** Ask one question: *did it
tell you anything you did not already know?* A tool that runs cleanly and
teaches nothing is not yet worth money, and that is the single most useful
thing to learn early.

**Someone asks for a feature.** Write it down. Do not build it yet. Three
people asking for the same thing is a signal; one person asking is a
conversation.

**Nobody responds.** That is information too, and it arrives in a week rather
than after three more months of code. It usually means the post was wrong
rather than the product — try a different community and a different framing
before concluding anything about the tool.

---

## What counts as done

| Outcome | Meaning |
|---|---|
| 3+ strangers ran it | Milestone met, whatever they said |
| 1+ said it caught something real | You have something worth pricing |
| Ran it, nothing useful found | The checks are not valuable enough yet — fix that before pricing |
| Nobody ran it | A distribution problem, not a product problem. Try again elsewhere |

Only the first row closes M2. The rest tells you what M3 should be.
