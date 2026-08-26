# What hardware people actually ask about

Read on 26 August 2026 from `electronics.stackexchange.com`, 10,823 questions
spanning 16.8 years. Reproduce with `python mine.py clusters`; the raw ranking
is `data/report/electronics-groups.json`.

This document exists because `BUSINESS_MODEL.md` says the third product line
should be chosen by what people actually ask for, and until now nothing in this
repository could tell us what that was. Every number below was measured. Where a
judgement is mine rather than the data's, it says so.

---

## Why an archive rather than a live feed

The plan was a 24/7 agent watching for new questions. Before building it, the
volume was measured:

| search on electronics.stackexchange.com | all time | last 90 days |
|---|---:|---:|
| "bill of materials" | 55 | **0** |
| "netlist" | 424 | 5 |
| "kicad" | 1,014 | 10 |
| "component sourcing" | 2,707 | 26 |

Zero new BOM questions in three months. KiCad gets roughly one every nine days.
A poller on a five-minute cycle would make 288 requests a day — against a
300-request quota — to find about one relevant question a week.

So the architecture changed and the goal did not. The same source that is
nearly empty as a stream is substantial as an archive, and an archive answers a
better question anyway: not *what came in today*, but *what has gone wrong
repeatedly for sixteen years*.

## What was read

Tag names and sizes were asked of the API first, so the corpus is aimed at
labels that exist rather than at ones that seemed plausible. Twenty tags and six
text searches, 134 requests, capped at 1,000 questions per probe.

The four largest tags (`components`, `schematics`, `pcb-design`, `datasheet`)
hit that cap, so for those the corpus holds the **most recent** 1,000 rather
than all of them. That biases those four toward the present. It is a real limit
on the counts below and is not corrected for.

## How the grouping works, and what it cannot do

Each question becomes a vector of tf-idf weights over the words in its title,
tags and opening body text. Questions link when their vectors are close, groups
grow from the most-connected question outward, and groups that turn out to be
about the same thing are merged. Ordinary information retrieval, no dependencies,
deterministic, about twenty seconds.

Nothing in it knows what a BOM is. That is deliberate: the per-question scorer in
`score.py` matches against terms this project already believes in, so it would
confirm the existing plan whatever the corpus contained. This had to be able to
disagree.

**202 groups covering 2,826 of 10,823 questions — 26%.** The other 7,997
resembled nothing else strongly enough to group. That is the expected outcome:
most questions are about one board and one mistake. The number is stated rather
than tuned away, because a looser threshold reaches 61% coverage only by
collapsing groups into their tags — the largest becomes "#kicad, 228 questions",
which says only that KiCad exists.

---

## The finding

**42% of everything that grouped is about operating a design tool, not about
electronics.**

| theme | groups | questions | share | manual-work words | unanswered\* |
|---|---:|---:|---:|---:|---:|
| operating an EDA tool | 78 | 1,176 | 42% | 7% | 14% |
| choosing or identifying a part | 49 | 764 | 27% | 1% | 15% |
| circuit design and everything else | 47 | 513 | 18% | 4% | 14% |
| manufacturing and assembly | 28 | 373 | 13% | 7% | 9% |

\* *Stack Exchange's test: no accepted answer and no answer scoring 1+.
"Manual-work words" counts questions containing them, and the section below shows
what that measure gets wrong in a group about physical assembly.*

*The four theme names are mine. The 202 groups are the algorithm's; sorting them
onto four shelves is a human judgement and someone could reasonably draw the
lines elsewhere.*

The ten largest tool groups:

| questions | manual work | group |
|---:|---:|---|
| 137 | 16% | Altium Designer, components and parameters |
| 69 | 6% | Gerber file output |
| 67 | 4% | KiCad footprints and packages |
| 56 | 11% | OrCAD / PSpice capture and models |
| 44 | 2% | ground planes |
| 44 | 0% | schematic symbols |
| 44 | 2% | Eagle CAD |
| 32 | 0% | Cadence Virtuoso |
| 25 | 4% | SPICE models |
| 24 | 12% | DRC errors |

These people are not stuck on circuits. They know what they want the board to
be. They are stuck on getting the software to emit it.

## The group that matters most to this business

Group 40 — eight questions tagged `bom`, and **half of them describe doing
something by hand** against a corpus average of 5%. Two are definitional. The
other six are all one question:

> *How do I make my CAD tool export the bill of materials I actually need?*

- [How to Fix LTSpice Bill of Materials to Include Actual Capacitor and Resistor Manufacturer and Part Numbers…](https://electronics.stackexchange.com/questions/768965/how-to-fix-ltspice-bill-of-materials-to-include-actual-capacitor-and-resistor-ma)
- [How can I tell Eagle to not export a 'part' to Bill of Materials?](https://electronics.stackexchange.com/questions/286604/how-can-i-tell-eagle-to-not-export-a-part-to-bill-of-materials)
- [Eagle Multilevel BOM](https://electronics.stackexchange.com/questions/391415/eagle-multilevel-bom)
- [Can I use Bill of Materials to order components online?](https://electronics.stackexchange.com/questions/437226/can-i-use-bill-of-materials-to-order-components-online)
- [Altium: Bill of materials organization](https://electronics.stackexchange.com/questions/245379/altium-bill-of-materials-organization)
- [How can I set a custom form of my Bill of materials in Eagle](https://electronics.stackexchange.com/questions/237575/how-can-i-set-a-custom-form-of-my-bill-of-materials-in-eagle)

This reframes the product. The demand is not "give me a BOM tool" — it is "the
BOM my tool gave me is missing the things I need", which is exactly what
manufacturer part number enrichment addresses. The first question in that list
is the one that opened this investigation.

All eight are marked answered — but **only five have an accepted answer.**
Stack Exchange's `is_answered` means "has an accepted answer *or* an answer
scoring one or more", which is not the same claim and is verified here: three of
these eight have nothing accepted. Every "unanswered" figure in this document
uses the site's looser test, not "nobody replied" and not "nothing accepted".

## What the answers actually say

Twenty answers to those eight questions were read — all of them, not sampled.
**Not one points at a feature that solves the problem.**

| question | what the best answer says |
|---|---|
| Eagle: custom BOM fields | use the Attribute tool on *each device*, or write a script to do it |
| Eagle: exclude a part from the BOM | "I haven't seen such an option" — rename parts with a prefix and `grep -v` them out. The answerer adds: *"This is not what you asked for"* |
| Eagle: multilevel BOM | *accepted* — build an internal part-number system and a relational database |
| LTspice: real manufacturer part numbers | *accepted* — hand-edit LTspice's component database row by row. Runner-up: "LTspice is practically useless for making boards … you need a different tool flow" |
| Altium: BOM organisation | the grouping is confused because a value and its description disagree — *"you have a whole different issue"* |
| Is there a BOM standard? | *accepted, 9 votes* — "I don't think there is a standard … I've written my own part searcher for EAGLE and KiCad" |
| Can I order parts from a BOM? | *accepted* — yes, vendor import works fine **as long as you have a manufacturer part number in there** |

That last one is the whole business in one sentence. The ordering step is solved;
the bottleneck is arriving at it with correct part numbers. And the Altium answer
is a value/description mismatch — precisely the class of defect `helix-bom`
already detects.

So the group is answered and *not solved*. The answers are workarounds, scripts,
"write your own", and one "your tool cannot do this". That is what an opening
looks like when a site has been running for sixteen years: not silence, but a
decade of people being handed the work back.

## Where this went wrong, and what it cost

Group 23 — pick-and-place data — was recommended in an earlier draft of this
document as the strongest third-line candidate, on a **30% manual-work rate**.
Reading the six questions behind that number:

| text | is this work software could remove? |
|---|---|
| "manually calculate the center of the part body" | yes |
| "manually remove the unused components from the pick and place file and BOM" | yes |
| "the through-hole components could be soldered by hand" | no — soldering |
| "best practice for manually dealing with such reels" | no — handling parts |
| "Sparkfun say they do this sort of work by hand" | no — hand assembly |
| "any better estimate except counting manually?" | no — counting parts |

**Two of six.** The real rate is nearer 10% than 30%. In a group about physical
assembly, "by hand" mostly means a soldering iron, and the keyword list cannot
tell that from "I edit this spreadsheet by hand every time". The same check on
group 40 gives three of four genuine — in a BOM context those words do mean
software toil.

The same fault ran through the answer classifier, which reported 58% of group
23's accepted answers as "hands back a scripting job" on hits like "soldered by
hand". Corrected, it reads 33%.

**Group 23 is therefore downgraded**, and this is left in rather than edited out
because it is the third time in this investigation that a small measurement got
reported as a conclusion. The instrument now prints "not a finding — read the
answers" every time it runs, and `score.py` carries the limitation next to the
word list that causes it.

## What this does not say

- **Volume is not willingness to pay.** Nothing here is evidence anyone would
  buy anything. It is evidence of where the work hurts.
- **The tool groups are dominated by Altium, OrCAD and Cadence** — expensive
  commercial packages whose users are companies. `helix-bom` reads KiCad. Whether
  that gap is a market or a mismatch is not answerable from this data.
- **Only 26% grouped**, and vocabulary clustering cannot see two people
  describing one problem in different words. Every count here is a floor.
- **Four tags were truncated at 1,000**, biasing those toward recent questions.
- **The archive is old.** Median group age runs to several years. These are
  durable problems, not current events — which is the case for a reference tool
  and against a live feed.

## What follows

1. **Manufacturer part number enrichment is the right next thing**, and this
   is now evidence rather than assumption. Across eight questions and the twenty
   answers to them, people using Eagle, Altium and LTspice are told to hand-edit
   databases, write ULP scripts, or change tools — and the single answer saying
   ordering works fine names correct part numbers as the precondition.
2. **Aim at the export gap, not at BOM management.** Octopart, Digi-Key's BOM
   manager and Arena already own "upload a good BOM, get parts". They all assume
   the BOM is already correct. Nobody in these twenty answers is served on the
   step before that, which is where `helix-bom` sits.
3. **Pick-and-place is not the third line.** Downgraded on inspection: most of
   its manual-work signal is physical assembly. It stays on the list, no longer
   at the top of it.
4. **Do not trust a keyword rate again without reading the text under it.**
   Three separate wrong conclusions in this investigation came from that, and all
   three were caught by reading perhaps thirty items. Reading is cheap at this
   scale; it stops being cheap at the scale where the rates would be reliable.
5. **The 24/7 monitor should not be built for this source.** There is nothing to
   monitor. Re-run the miner quarterly instead; that is one hour of quota.
6. **Re-run this against a source with live volume before drawing conclusions
   about what people need *today*.** The candidate is Reddit, which is blocked on
   a contract — see `sources/base.py`.

---

*Question titles and links are from Stack Exchange, licensed CC BY-SA. The links
above are the attribution the licence asks for. No author names were collected
or stored; the harvested corpus is kept out of this repository, and what is
committed is what this project derived from it.*
