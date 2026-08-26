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

| theme | groups | questions | share | describe manual work | unanswered |
|---|---:|---:|---:|---:|---:|
| operating an EDA tool | 78 | 1,176 | 42% | 7% | 14% |
| choosing or identifying a part | 49 | 764 | 27% | 1% | 15% |
| circuit design and everything else | 47 | 513 | 18% | 4% | 14% |
| manufacturing and assembly | 28 | 373 | 13% | 7% | 9% |

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

**All eight have accepted answers**, and so do all twenty in the pick-and-place
group below. That is worth stating plainly because the first draft of this
document said the opposite: it read the vote count in the tool's output as an
answer count and concluded the group was an unmet need. It is not. These are
chronic, well-trodden problems that people ask about and get answered.

Which leaves the manual-work rate as the real signal, and one honest caveat with
it: **the answers were not read.** A 50% manual-work rate measures the language
of the *questions*. Whether the accepted answers resolve the problem or tell
somebody to write a script is the obvious next check, and it is not answered
here. Nothing below should be read as "these people got no help".

Group 23 — pick-and-place data, 20 questions, **30% describe manual work**, all
answered. Export a centroid file, get the rotations right, work out what a
machine needs. Same shape of problem, further down the same pipeline.

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

1. **The netlist reader and part-number enrichment are pointed at the right
   thing.** Confirmed, not assumed — group 40 is that problem, in users' own
   words, recurring across three different CAD tools over a decade.
2. **Pick-and-place export is the strongest candidate for the third line.**
   Adjacent to what exists, and the highest manual-work rate of any large group.
3. **Read the accepted answers in groups 40 and 23 before committing to
   either.** Roughly thirty answers. If they resolve the problem cleanly, the
   opportunity is smaller than the question count suggests; if they say "write
   a script", it is larger. This is cheap and it is the difference between
   evidence and a hunch.
4. **The 24/7 monitor should not be built for this source.** There is nothing to
   monitor. Re-run the miner quarterly instead; that is one hour of quota.
5. **Re-run this against a source with live volume before drawing conclusions
   about what people need *today*.** The candidate is Reddit, which is blocked on
   a contract — see `sources/base.py`.

---

*Question titles and links are from Stack Exchange, licensed CC BY-SA. The links
above are the attribution the licence asks for. No author names were collected
or stored; the harvested corpus is kept out of this repository, and what is
committed is what this project derived from it.*
