"""
Launch posts, generated from the repository and checked against it.

`docs/FIRST_USERS.md` sets the strategy: three to five hardware people who have
never spoken to the author run the CLI on a real BOM, and the ask is a bug
report rather than a sale. This module is that document made executable. The
channel order, the cautions, and the drafts, rendered from live facts.

**Why the drafts are generated rather than stored.** Every one of them states a
version, an install command and a count. Stored text goes stale silently, and
the first thing a stranger reads about this project is the worst possible place
to be wrong about it. Generating from `facts.py` means a draft cannot claim a
version the package does not have.

**Why every draft is then verified.** Generating from facts is not enough,
because these drafts are meant to be edited. `FIRST_USERS.md` says so
outright, and a post that reads as copy-and-paste marketing gets ignored. So
after editing, `verify()` runs the project's own library over the text and
refuses any numeric claim not present in the facts. The BOM reviewer checks a
model's output this way; there is no principled reason the company's own
outreach should be held to a looser standard than its customers' documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import re

from helix_grounding import Claim, ClaimKind, Extractor, GroundTruth, Verifier
from helix_grounding.extractors import default_extractors

from .facts import ProjectFacts

# Numbers that appear in prose for reasons unrelated to the product, and would
# otherwise be reported as unfounded claims. Kept explicit and short: a wide
# allowance here would quietly defeat the whole check.
#
#   3, 4, 5  -- "three to five hardware people", "four hours" after posting
#   50       -- the budget figure in the example command, not a claim
#   1, 2     -- list markers that survive the pattern in some drafts
PROSE_NUMBERS = (1.0, 2.0, 3.0, 4.0, 5.0, 50.0)


class CountExtractor(Extractor):
    """Bare integers, which in a launch post are almost always claims.

    The library's own ``QuantityExtractor`` deliberately ignores these, and it
    is right to: in the prose of a BOM review a bare integer is more often a
    list position or a year than a count, and flagging those produces noise
    that trains the reader to ignore the validator.

    A launch post inverts that. "0 runtime dependencies" and "255 tests" are
    the whole substance of the claim, and they are exactly the numbers that go
    stale between drafting and posting. So this domain reads bare integers as
    claims, and says so here rather than widening the shared extractor and
    pushing the noise onto every other caller.

    Deliberately not matched: digits inside an identifier (``U1``, ``Pad7``),
    either half of a decimal (``0.94``, ``$3.20``), and version strings
    (``0.1.1``). The currency extractor already owns money, and a version is
    checked as a token rather than a number.
    """

    _PATTERN = re.compile(r"(?<![\w.])(\d+)(?![\w.])")

    @property
    def kind(self) -> ClaimKind:
        return ClaimKind.QUANTITY

    def extract(self, text: str) -> list:
        return [
            Claim(kind=ClaimKind.QUANTITY, value=float(match.group(1)),
                  raw=match.group(0), span=match.span())
            for match in self._PATTERN.finditer(text)
        ]


def _post_extractors() -> list:
    """The stock set plus this domain's own reading of a bare integer.

    Uses ``Verifier(extractors=...)``, the extension point the library already
    provides, rather than editing the shared defaults.
    """
    return list(default_extractors()) + [CountExtractor()]


class DraftError(RuntimeError):
    """A draft that cannot be rendered truthfully is not rendered."""


@dataclass(frozen=True)
class Channel:
    """One place a post goes, and what it costs to get it wrong there."""

    key: str
    name: str
    url: str
    order: int
    one_shot: bool
    caution: str
    body: Callable

    def render(self, facts: ProjectFacts) -> str:
        return self.body(facts).strip() + "\n"


def _requires_measured_tests(facts: ProjectFacts) -> int:
    if facts.tests_passing is None:
        raise DraftError(
            "this draft states a test count, and the suite was not run. "
            "Gather facts with run_tests=True, or the post claims a number "
            "nobody measured -- which is the exact failure helix-bom exists "
            "to catch, aimed at a larger audience."
        )
    return facts.tests_passing


# --------------------------------------------------------------------
# The drafts
# --------------------------------------------------------------------

def _reddit_pcb(facts: ProjectFacts) -> str:
    """The lead is `enrich`, and that is a deliberate change.

    The first version of this draft led with budget and enclosure-fit checks,
    which is what the tool did when the draft was written. It is not what this
    audience cares about. `docs/DEMAND_EVIDENCE.md` read ten thousand questions
    from hardware people: the biggest cluster is operating a design tool, and
    the commonest BOM defect is not a wrong part number, it is no part number.

    So the opening line is the check that finds that, and it is the one that
    needs no account, no key and no configuration. Anything requiring a signup
    is further down, where somebody already interested can find it.
    """
    return f"""
**Free CLI that checks a BOM export for the mistakes that stop a build, and I want you to break it**

I built a command-line tool that reads a BOM export (KiCad, Altium, or a
spreadsheet) and looks for the things that are invisible until the boards come
back wrong:

- a line with no manufacturer part number. A value and a footprint are not
  an orderable part
- a value sitting in the part number column ("10k" is not a part number; two
  thousand different resistors are 10k)
- the same designator on two lines. One of them is wrong, and nothing
  downstream catches it
- designators that do not match the quantity: `R1, R2, R3` with a quantity
  of 2. One of the two numbers is wrong
- the same part on two separate lines, so it gets ordered twice

    {facts.install_command}
    helix-bom enrich your_bom.csv        # the checks above, no account needed
    helix-bom demo                       # bundled example, no file needed

It runs entirely offline for those. Your BOM never leaves your machine, and
there is a test that disables the socket layer to prove it. If you set a
distributor API key it will additionally check lifecycle, stock, minimum order
quantity, and whether the price in your BOM is the price at the quantity you
are actually buying. That part is optional and everything above works without
it.

If you would rather look at it than read a terminal:

    helix-bom enrich your_bom.csv --html

That writes one HTML file next to your BOM and opens it. Findings with
severity filters, a breakdown of where the money actually goes, a chart of
which single part gates the build, and the interconnect diagram if you handed
it a netlist. Hover any part and it lights up in every view at once. The page
loads nothing from anywhere, so it looks the same with the network unplugged.
There is a `helix-bom-gui` too, if you want a file picker instead of a
terminal.

Point it at a KiCad netlist instead and it reads the connectivity too:

    helix-bom review your_board.net --diagram board.svg

Every line in that diagram is a net that exists between pins that are named,
so you can check it against your schematic and tell me it is wrong. It also
flags a net you named that only connects to one thing. That is a label
somebody typed and never joined to anything, and it looks identical to a real
one on a printout.

I would genuinely rather it fail on your file than pass. The part I am least
sure about is column detection. Every EDA tool names things differently, and
I have only tested against exports I could get hold of.

You do not have to send me your BOM to report that. `helix-bom diagnose
your_bom.csv` prints the structure and none of the contents. Safe to paste in
public, and there is a test that fails if component data ever reaches it.

One thing it deliberately does: it tells you which checks it *could not* run.
A netlist has no prices, so the budget check reports itself as unrunnable
rather than staying quiet. A report that said nothing there would read as a
clean bill of health when it means "I could not look".

Source: {facts.repo_url}
"""


def _show_hn(facts: ProjectFacts) -> str:
    passing = _requires_measured_tests(facts)
    return f"""
**Show HN: Catch the numbers an AI made up, without asking another AI**

Every tool I found for checking LLM output does it with another LLM: judge
models, semantic entailment, embedding similarity. All of those are
probabilistic, cost an inference call, and can be wrong themselves.

This takes a narrower approach: extract every currency amount, measurement,
identifier, quantity, percentage and date from the generated text, and check
each against values computed from the source data. For that class of claim the
answer is decidable. The value is in the set or it is not. No model call, no
confidence score, nothing that can itself hallucinate.

It is a smaller claim than the incumbents make and a harder one. "No fabricated
figure reached your customer" is provable. "0.94 faithfulness" is not.

The repo includes a real incident: a model reviewing a bill of materials wrote
two false sentences, and **the checker only catches one of them.** "$3.40" for
a $3.20 part is a fabricated value and gets rejected. Calling a $3.10 part
"cheaper" than a $2.40 one is a wrong *relation* between two real values, which
no value-checker can see. That one is prevented differently, by computing the
comparison in code so it is never generated. There is a script that reproduces
both.

{facts.runtime_dependencies} runtime dependencies, {passing} tests, and one of
them disables Python's socket layer to prove nothing is sent anywhere.

    {facts.install_command}

{facts.repo_url}
"""


def _kicad_community(facts: ProjectFacts) -> str:
    formats = ", ".join(facts.input_formats)
    return f"""
**A BOM/netlist checker that handles KiCad's export quirks, and I am looking for files that break it**

I have been writing a checker for BOM exports and it turned into a KiCad
problem specifically, so this seemed the place to ask.

The ingest layer handles the preamble lines above the header, grouped
reference designators, DNP columns, and semicolon-delimited exports with
comma decimals. It reads {formats} files. It also reads `.net` netlists
directly, which is where the interesting part is: connectivity is in the
schematic, not the BOM, so a wiring diagram drawn from a BOM is not hard,
it is impossible.

From a netlist it will tell you when a net *you* named reaches only one pin.
Nets Eeschema named itself, like `unconnected-(U1-Pad7)` or `Net-(R3-Pad1)`,
are left alone, since those are normal and you already get told about them.

    {facts.install_command}
    helix-bom review your_board.net --diagram board.svg

What I want is a file it reads wrongly. `helix-bom diagnose <file>` prints
the structure and none of the contents, so you can send that instead of your
design.

{facts.repo_url}
"""


def _eevblog(facts: ProjectFacts) -> str:
    return f"""
**Offline BOM checker, and I am asking this forum to find its failure modes**

Posting here after one round of feedback elsewhere, because this crowd is
harder to please and that is the point.

A CLI that reads a BOM export or a KiCad netlist and reports budget, lead-time
and fit problems. Two design choices I expect argument about, and would rather
have it:

1. It reports checks that *could not run* as loudly as findings. A standard
   EDA export carries no dimensions and no power figures, so those checks get
   named as skipped. I think a silent report there is dangerous; it reads as a
   clean bill of health when it means "I could not look".

2. It refuses to draw a wiring diagram from a BOM. The data is not in the
   file. It will draw one from a netlist, where every line is a net that
   exists.

Runs entirely offline. {facts.runtime_dependencies} runtime dependencies.

    {facts.install_command}

{facts.repo_url}
"""


CHANNELS = (
    Channel(
        key="reddit_pcb",
        name="r/PrintedCircuitBoard",
        url="https://reddit.com/r/PrintedCircuitBoard",
        order=1,
        one_shot=False,
        caution=(
            "Read the subreddit rules first; some require a flair or forbid links "
            "from new accounts. If your account is new, comment helpfully on other "
            "posts for a few days before posting a link. An account with no "
            "history posting a link reads as spam no matter how good the link is."
        ),
        body=_reddit_pcb,
    ),
    Channel(
        key="show_hn",
        name="Show HN",
        url="https://news.ycombinator.com/showhn.html",
        order=2,
        one_shot=True,
        caution=(
            "ONE SHOT. You cannot repost the same project effectively. Post on a "
            "weekday morning US time and stay at the keyboard for four hours "
            "afterwards; everyone who arrives does so in that window, and the "
            "author replying carefully is most of what makes a post go well. Do "
            "not post here until the README, the demo and the install path all "
            "work for a stranger."
        ),
        body=_show_hn,
    ),
    Channel(
        key="kicad",
        name="KiCad forum and Discord",
        url="https://forum.kicad.info",
        order=3,
        one_shot=False,
        caution=(
            "You have a real reason to be there. The ingest layer handles KiCad's "
            "specific export quirks. Say that rather than 'please look at my "
            "thing'."
        ),
        body=_kicad_community,
    ),
    Channel(
        key="eevblog",
        name="EEVblog forum",
        url="https://eevblog.com/forum",
        order=4,
        one_shot=False,
        caution=(
            "Slower, older, more skeptical. Worth doing only after you have "
            "survived one round of feedback elsewhere and fixed what it found."
        ),
        body=_eevblog,
    ),
)

BY_KEY = {channel.key: channel for channel in CHANNELS}


# --------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------

def ground_truth_for(facts: ProjectFacts) -> GroundTruth:
    """The set of numbers a post about this project is allowed to contain."""
    quantities = [
        float(facts.runtime_dependencies),
        float(len(facts.commands)),
        float(len(facts.input_formats)),
        *PROSE_NUMBERS,
    ]
    # The version's own digits, so "0.1.1" in prose does not read as a claim
    # about a count. Checked as a token as well, below.
    quantities += [float(part) for part in facts.version.split(".") if part.isdigit()]
    if facts.tests_passing is not None:
        quantities.append(float(facts.tests_passing))

    truth = (
        GroundTruth()
        .allow_many(ClaimKind.QUANTITY, quantities)
        .allow_tokens([facts.package, facts.version])
    )

    # The case-study figures are quoted verbatim in the Show HN draft and are
    # asserted by tests/test_case_study.py, so they are ground truth in the
    # strict sense: a test fails if they ever stop being the real numbers.
    truth = truth.allow_many(ClaimKind.CURRENCY, [3.40, 3.20, 3.10, 2.40, 50.0])

    # Dates and measurements are prose here (release dates, "four hours"), and
    # a post is not a document with a source dataset behind those. Skipping is
    # recorded in the report rather than done silently.
    truth = truth.skip(ClaimKind.DATE).skip(ClaimKind.MEASUREMENT)
    return truth


def verify(text: str, facts: ProjectFacts):
    """Check a post's numeric claims against the repository.

    Returns a ``GroundingReport``. The caller decides what to do with it.
    `cli.py` refuses to mark a post ready while it is ungrounded.

    What this does and does not cover, stated because a check that quietly
    verifies nothing is worse than no check: currency amounts, percentages and
    bare counts are checked against the facts. Dates and measurements are
    skipped, and the report says so. Nothing here evaluates whether the *prose*
    is true. "runs entirely offline" is a claim no value-checker can see, and
    it is held up by `tests/test_offline_guarantee.py` instead.
    """
    return Verifier(extractors=_post_extractors()).verify(text, ground_truth_for(facts))


def render(channel_key: str, facts: ProjectFacts) -> str:
    if channel_key not in BY_KEY:
        raise DraftError(
            f"unknown channel {channel_key!r}. Known: {', '.join(sorted(BY_KEY))}"
        )
    return BY_KEY[channel_key].render(facts)
