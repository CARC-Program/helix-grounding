"""
Grouping the archive by what people are actually asking about.

The scorer next door judges one question at a time against a list of terms this
project already believes in. That is useful for triage and useless for
discovery: it can only ever find what was written into `DOMAIN_TERMS`, so it
would confirm the existing plan no matter what the corpus contained. This module
exists to be capable of contradicting it. Nothing here knows what a BOM is.
Terms are learned from the corpus, groups fall out of similarity, and the labels
are whatever words the questions themselves cluster around.

How it works, in one paragraph: each question becomes a sparse vector of tf-idf
weights over the words in its title, its tags and the first part of its body;
words too rare to generalise or too common to distinguish are dropped; questions
are linked when their vectors are close enough; and clusters are grown by
repeatedly taking the most-connected unassigned question as a seed. It is
ordinary information retrieval from the 1970s, which is the point -- it is
deterministic, it runs in a second with no dependencies, and every group it
produces can be explained by naming the words that formed it.

Three honest limits, stated here because a clustering that oversells itself is
worse than none:

**Vocabulary, not meaning.** Two questions describing the same problem in
different words will not meet. The output undercounts every subject people have
more than one name for.

**Titles dominate.** They are weighted heavily because they are where the
problem is stated, so a question with a vague title lands badly however clear
its body is.

**Singletons are the normal case.** Most questions are about one board and one
mistake and resemble nothing else. The report says how many failed to cluster
rather than quietly leaving them out, because "we grouped 40% of the corpus" and
"we grouped the corpus" are very different claims.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .score import DOMAIN_TERMS, MANUAL_WORK_LANGUAGE, _found

# Ordinary English, plus the words every question-site title contains and none
# of which separate one question from another.
STOPWORDS = frozenset("""
a an the and or but if then than that this these those there here it its it's
is are was were be been being am do does did doing done have has had having
i i'm ive my me we our you your he she they them his her their
of in on at to from by for with without into onto over under about as
not no nor so such only just also very too much many more most less least
can could should would may might must will shall need needs needed
what which who whom whose when where why how whether
some any all both each few other another same different new old
get gets getting got make makes making made use uses using used
one two three first second next last other any every
question questions answer answers help please thanks thank hi hello
anyone someone somebody something anything nothing everything
way ways thing things work works working problem problems issue issues
possible impossible correct incorrect right wrong good bad best worst
know knows knowing think thinks trying tried try want wants looking
find finds found see seen look looks seems seem appears appear
'' -- --- etc eg ie vs via per
""".split())

# Words shorter than three characters are dropped as noise, which would throw
# away most of the vocabulary of this field. These are kept.
SHORT_TERMS = frozenset("""
bom pcb smd smt esr mcu adc dac spi i2c uart usb led ic cad erc drc drl
bga qfn soic tqfp mpn rf ac dc emi emc esd pwm fet mos jtag swd gnd vcc
kb mb ma mv mw hz db pin nc no
""".split())

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#._/-]*")

# How much each field of a question counts. Tags outrank everything because a
# person read the question and chose that label; titles outrank bodies because
# a title is a summary and a body is a transcript.
TAG_WEIGHT = 4.0
TITLE_WEIGHT = 3.0
BODY_WEIGHT = 1.0

# Bodies are cut here. Past a few hundred characters a Stack Exchange question
# is code, a log, or a schematic description, and those bury the sentence that
# says what went wrong.
BODY_CHARS = 700


def tokenise(text: str) -> list:
    """Words worth keeping, in order, so bigrams can be built from them."""
    kept = []
    for raw in TOKEN.findall(text.lower()):
        word = raw.strip("._-/")
        if not word or word in STOPWORDS:
            continue
        if len(word) < 3 and word not in SHORT_TERMS:
            continue
        if word.isdigit():
            continue
        kept.append(word)
    return kept


def terms_of(item, use_bigrams: bool = True) -> dict:
    """The weighted bag of terms for one question."""
    counts = {}

    def add(term, weight):
        counts[term] = counts.get(term, 0.0) + weight

    for tag in item.tags:
        add(f"tag:{tag.lower()}", TAG_WEIGHT)

    title_tokens = tokenise(item.title)
    body_tokens = tokenise(item.body[:BODY_CHARS])

    for tokens, weight in ((title_tokens, TITLE_WEIGHT),
                           (body_tokens, BODY_WEIGHT)):
        for token in tokens:
            add(token, weight)
        if use_bigrams:
            for left, right in zip(tokens, tokens[1:]):
                add(f"{left} {right}", weight * 0.8)
    return counts


@dataclass
class Vocabulary:
    """Which terms are allowed to carry weight, and how much each is worth."""

    document_frequency: dict
    n_documents: int
    min_df: int
    max_df: int

    def keeps(self, term: str) -> bool:
        df = self.document_frequency.get(term, 0)
        return self.min_df <= df <= self.max_df

    def idf(self, term: str) -> float:
        df = self.document_frequency.get(term, 0)
        return math.log((self.n_documents + 1) / (df + 1)) + 1.0


def build_vocabulary(bags, min_df: int = 4, max_df_ratio: float = 0.20) -> Vocabulary:
    """A term seen fewer than ``min_df`` times cannot generalise; one seen in
    more than a fifth of the corpus cannot distinguish. Both are dropped."""
    df = {}
    for bag in bags:
        for term in bag:
            df[term] = df.get(term, 0) + 1
    n = len(bags)
    return Vocabulary(document_frequency=df, n_documents=n, min_df=min_df,
                      max_df=max(min_df, int(n * max_df_ratio)))


def vectorise(bag: dict, vocabulary: Vocabulary, top_k: int = 20) -> dict:
    """One question as a unit-length sparse vector of its strongest terms."""
    weighted = {}
    for term, count in bag.items():
        if not vocabulary.keeps(term):
            continue
        weighted[term] = (1.0 + math.log(count)) * vocabulary.idf(term)
    if not weighted:
        return {}
    # Keeping only the strongest terms bounds the comparison cost and removes
    # the long tail of words that are in the vector but never decide anything.
    strongest = sorted(weighted.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
    norm = math.sqrt(sum(value * value for _, value in strongest))
    return {term: value / norm for term, value in strongest}


def cosine(left: dict, right: dict) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right[term] for term, value in left.items() if term in right)


@dataclass
class Cluster:
    """A group of questions, with the words that made it a group."""

    label: str
    terms: list
    members: list = field(default_factory=list)
    seed_index: int = -1

    @property
    def size(self) -> int:
        return len(self.members)


def _median(values) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


# Chosen by running the same corpus at 0.22, 0.25 and 0.30 and reading the
# output, because there is no correct answer to be derived -- only a trade to be
# made and recorded.
#
#   0.22   61% of the corpus grouped, but the groups collapse into their tags:
#          the largest is "#kicad", 228 questions, which says only that KiCad
#          exists. Coverage bought with meaning.
#   0.30   26% grouped, and the groups are sub-problems somebody could act on:
#          DRC errors, footprint libraries, gerber output, solder paste stencils.
#
# The question this was built to answer is "which part of the work is painful",
# not "which tools are popular", so specificity wins and the 26% is stated in
# the report rather than tuned away.
DEFAULT_THRESHOLD = 0.30


def cluster_items(items, threshold: float = DEFAULT_THRESHOLD, min_size: int = 4,
                  min_df: int = 4, max_df_ratio: float = 0.20,
                  top_k: int = 20, max_posting: int | None = None,
                  merge_threshold: float = 0.42) -> dict:
    """Group ``items``. Returns clusters, singletons, and how it was done.

    Deterministic: every ordering has an explicit tie-break, so the same corpus
    produces the same clusters on every machine and a change in the output means
    a change in the input or in this file, never a change in dictionary order.
    """
    items = list(items)
    bags = [terms_of(item) for item in items]
    vocabulary = build_vocabulary(bags, min_df=min_df, max_df_ratio=max_df_ratio)
    vectors = [vectorise(bag, vocabulary, top_k=top_k) for bag in bags]

    # Inverted index, so only questions sharing a term are ever compared.
    # A term appearing in a large fraction of the corpus generates enormous
    # candidate lists and decides nothing, so it is skipped here as well.
    if max_posting is None:
        max_posting = max(60, int(len(items) * 0.08))
    postings = {}
    for index, vector in enumerate(vectors):
        for term in vector:
            postings.setdefault(term, []).append(index)

    neighbours = [set() for _ in items]
    for index, vector in enumerate(vectors):
        if not vector:
            continue
        candidates = set()
        for term in vector:
            posting = postings.get(term, ())
            if len(posting) > max_posting:
                continue
            candidates.update(posting)
        candidates.discard(index)
        for other in candidates:
            if other < index:
                continue    # each pair once
            if cosine(vector, vectors[other]) >= threshold:
                neighbours[index].add(other)
                neighbours[other].add(index)

    # Greedy leader clustering: the most-connected unassigned question seeds a
    # cluster and takes its unassigned neighbours. Chosen over connected
    # components, which chain -- A resembles B, B resembles C, and C has nothing
    # to do with A, yet all three end up in one group that means nothing.
    order = sorted(range(len(items)),
                   key=lambda i: (-len(neighbours[i]), items[i].external_id))
    assigned = {}
    clusters = []
    for seed in order:
        if seed in assigned or not neighbours[seed]:
            continue
        members = [seed] + sorted(n for n in neighbours[seed] if n not in assigned)
        if len(members) < min_size:
            continue
        cluster_id = len(clusters)
        for member in members:
            assigned[member] = cluster_id
        clusters.append(Cluster(label="", terms=[], members=members, seed_index=seed))

    clusters = _merge_similar(clusters, vectors, merge_threshold)

    for cluster in clusters:
        cluster.terms = _label_terms(cluster, bags, vocabulary)
        cluster.label = ", ".join(term for term, _ in cluster.terms[:4]) or "unlabelled"

    assigned = {member: i for i, c in enumerate(clusters) for member in c.members}
    singletons = [i for i in range(len(items)) if i not in assigned]
    clusters.sort(key=lambda c: (-c.size, c.label))
    return {
        "clusters": clusters,
        "singletons": singletons,
        "vocabulary": vocabulary,
        "items": items,
        "threshold": threshold,
        "merge_threshold": merge_threshold,
    }


def _centroid(members, vectors) -> dict:
    """The average of a group's vectors, re-normalised: what the group is about."""
    total = {}
    for index in members:
        for term, value in vectors[index].items():
            total[term] = total.get(term, 0.0) + value
    norm = math.sqrt(sum(value * value for value in total.values()))
    if not norm:
        return {}
    return {term: value / norm for term, value in total.items()}


def _merge_similar(clusters, vectors, threshold: float, max_rounds: int = 6) -> list:
    """Join groups that are about the same thing.

    Growing clusters from a seed splits a subject across several groups when no
    single question sits at the middle of it: Altium library management came out
    as three separate groups -- footprints, integrated libraries, and component
    parameters -- which reads as three small problems rather than one substantial
    one. Comparing whole groups to each other rather than question to question
    puts them back together.

    Merging repeats until nothing more meets the threshold, with a round cap so
    a pathological corpus cannot spin here. Order is by size then label so the
    result does not depend on dictionary iteration order.
    """
    for _ in range(max_rounds):
        centroids = [_centroid(c.members, vectors) for c in clusters]
        order = sorted(range(len(clusters)),
                       key=lambda i: (-len(clusters[i].members), i))
        merged_into = {}
        for position, index in enumerate(order):
            if index in merged_into:
                continue
            for other in order[position + 1:]:
                if other in merged_into:
                    continue
                if cosine(centroids[index], centroids[other]) >= threshold:
                    merged_into[other] = index
        if not merged_into:
            break
        survivors = []
        for index, cluster in enumerate(clusters):
            if index in merged_into:
                continue
            absorbed = [o for o, target in merged_into.items() if target == index]
            for other in absorbed:
                cluster.members.extend(clusters[other].members)
            cluster.members = sorted(set(cluster.members))
            survivors.append(cluster)
        clusters = survivors
    return clusters


def _label_terms(cluster, bags, vocabulary, minimum_share: float = 0.35) -> list:
    """Name a cluster by the terms most of its members share.

    The share floor is what stops a label being a word from one loud member.
    """
    totals = {}
    presence = {}
    for index in cluster.members:
        for term, count in bags[index].items():
            if not vocabulary.keeps(term):
                continue
            totals[term] = totals.get(term, 0.0) + count * vocabulary.idf(term)
            presence[term] = presence.get(term, 0) + 1
    floor = max(2, int(len(cluster.members) * minimum_share))
    shared = [(term, totals[term]) for term in totals if presence[term] >= floor]
    shared.sort(key=lambda kv: (-kv[1], kv[0]))

    # A word usually arrives twice -- once as a tag somebody applied and once
    # as a word in the title -- and the first labels read "bom, bom, altium,
    # altium", which spends four label slots saying two things. Tags keep a
    # leading # so the label still shows which is which.
    labelled = []
    seen = set()
    for term, weight in shared:
        display = f"#{term[4:]}" if term.startswith("tag:") else term
        if display.lstrip("#") in seen:
            continue
        seen.add(display.lstrip("#"))
        labelled.append((display, round(weight, 1)))
        if len(labelled) >= 8:
            break
    return labelled


# --------------------------------------------------------------------
# What each cluster means for a business that has to choose what to build
# --------------------------------------------------------------------

# A proportion measured over four questions is not evidence, it is an accident.
# The first ranking this module produced was topped by six groups of four,
# every one of them winning on a percentage computed from three or fewer
# questions, while a group of 132 sat at rank five. That is the same mistake as
# the scoring bands calibrated against a maximum nothing reaches: a number that
# is arithmetically correct and means nothing.
#
# So every proportion below is pulled toward the corpus-wide value with weight
# k/(n+k). A group of fifteen is believed half on its own evidence; a group of
# four has to be extremely lopsided to move at all; a group of two hundred is
# trusted on its own numbers.
SHRINK = 15.0


def _shrink(hits: int, size: int, baseline: float, k: float = SHRINK) -> float:
    if size <= 0:
        return baseline
    return (hits + k * baseline) / (size + k)


@dataclass(frozen=True)
class Baselines:
    """What the corpus as a whole looks like, so a group can be compared to it.

    Without this the scores would answer "is this group unanswered?" when the
    useful question is "is this group *more* unanswered than everything else
    here?" -- and on a site where 14% of questions never get an accepted
    answer, a group at 14% is not a finding.
    """

    unanswered: float
    recent: float
    toil: float
    domain: float


@dataclass
class Demand:
    """A cluster measured, with every number kept next to what produced it.

    The composite at the end is a sort key, not a verdict. It is printed beside
    its parts on purpose: a single number nobody can decompose is exactly the
    black box `score.py` refuses to be, and the point of ranking clusters is to
    decide reading order for a person, not to decide what gets built.
    """

    cluster: Cluster
    size: int
    unanswered: int
    recent: int
    toil: int
    domain: int
    median_score: float
    median_age_days: float
    exemplars: list
    baselines: Baselines
    largest: int = 1

    @property
    def unanswered_share(self) -> float:
        return self.unanswered / self.size if self.size else 0.0

    @property
    def recent_share(self) -> float:
        return self.recent / self.size if self.size else 0.0

    @property
    def toil_share(self) -> float:
        return self.toil / self.size if self.size else 0.0

    @property
    def domain_share(self) -> float:
        return self.domain / self.size if self.size else 0.0

    def _lift(self, hits: int, baseline: float, maximum: float) -> float:
        """Points for being more than usually X, where usual is the corpus.

        At the corpus rate a group scores half marks; at twice the corpus rate,
        full marks. Below average scores below half, which is the intended
        message -- a group that is unremarkable on a dimension should not
        collect points for it.
        """
        if baseline <= 0:
            return 0.0
        shrunk = _shrink(hits, self.size, baseline)
        return maximum * min(1.0, (shrunk / baseline) / 2.0)

    def parts(self) -> list:
        # Log-scaled, because the useful distinction is between a group of four
        # and a group of forty, not between forty and forty-four. Linear
        # scaling against the biggest group gave a group of four 0.9 points out
        # of 30 and let the noisy small-sample terms decide the whole ranking.
        volume = (35.0 * (math.log(self.size) / math.log(self.largest))
                  if self.largest > 1 else 35.0)
        base = self.baselines
        return [
            ("volume", volume, f"{self.size} questions"),
            ("unmet", self._lift(self.unanswered, base.unanswered, 20.0),
             f"{self.unanswered_share:.0%} unanswered (corpus {base.unanswered:.0%})"),
            ("alive", 15.0 * min(1.0, _shrink(self.recent, self.size, base.recent) / 0.5),
             f"{self.recent_share:.0%} from the last 2 years (corpus {base.recent:.0%})"),
            ("toil", self._lift(self.toil, base.toil, 15.0),
             f"{self.toil_share:.0%} describe manual work (corpus {base.toil:.0%})"),
            ("fit", self._lift(self.domain, base.domain, 15.0),
             f"{self.domain_share:.0%} name something we handle (corpus {base.domain:.0%})"),
        ]

    def total(self) -> int:
        return int(round(sum(points for _, points, _ in self.parts())))


def baselines_for(items, now=None) -> Baselines:
    """The corpus-wide rates every group is compared against."""
    now = now or datetime.now(timezone.utc)
    total = len(items) or 1
    ages = [(now - item.created_at).total_seconds() / 86400 for item in items]
    return Baselines(
        unanswered=sum(1 for i in items if not i.is_answered) / total,
        recent=sum(1 for age in ages if age <= 730) / total,
        toil=sum(1 for i in items if _found(i.text, MANUAL_WORK_LANGUAGE)) / total,
        domain=sum(1 for i in items if _found(i.text, DOMAIN_TERMS)) / total,
    )


def measure(clusters, items, now=None, baselines=None) -> list:
    """Turn clusters into ranked demand, highest first."""
    now = now or datetime.now(timezone.utc)
    baselines = baselines or baselines_for(items, now=now)
    measured = []
    for cluster in clusters:
        members = [items[i] for i in cluster.members]
        ages = [(now - m.created_at).total_seconds() / 86400 for m in members]
        measured.append(Demand(
            cluster=cluster,
            size=len(members),
            unanswered=sum(1 for m in members if not m.is_answered),
            recent=sum(1 for age in ages if age <= 730),
            toil=sum(1 for m in members if _found(m.text, MANUAL_WORK_LANGUAGE)),
            domain=sum(1 for m in members if _found(m.text, DOMAIN_TERMS)),
            median_score=_median([m.engagement_score for m in members]),
            median_age_days=_median(ages),
            exemplars=sorted(members,
                             key=lambda m: (-m.engagement_score, m.external_id))[:3],
            baselines=baselines,
        ))
    largest = max((d.size for d in measured), default=1)
    for demand in measured:
        demand.largest = largest
    measured.sort(key=lambda d: (-d.total(), -d.size, d.cluster.label))
    return measured
