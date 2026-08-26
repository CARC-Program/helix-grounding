"""
`python mine.py` -- read an archive, then find out what is in it.

Not shipped in the wheel. This is research apparatus for deciding what to build
next, and nobody installing a verification library should receive it.

Five commands, and the split between them is the design:

    tags       ask the site which labels actually exist, and how big each is
    harvest    read questions into a local file, once, within quota
    clusters   group what was read and rank the groups   (offline)
    show       print one group in full                   (offline)
    answers    read what one group's answers actually say

``answers`` is the odd one: it spends quota, because "answered" and "solved" are
different claims and the difference is only visible in the answer text. It
caches what it fetches like everything else, and ``--offline`` refuses to spend
anything.

Only ``harvest``, ``tags`` and ``answers`` touch the network. Everything else reads the
file on disk, so the analysis can be re-run, argued with and re-run again at no
cost -- which is the only way an honest conclusion gets reached, because the
first clustering is never the right one and a re-run that costs quota is a
re-run that does not happen.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from helix_bom.cli import err, out

from .answers import read_answer, summarise
from .cluster import cluster_items, measure
from .corpus import DEFAULT_CACHE, CorpusStore, Probe, harvest
from .sources.stackexchange import QuotaExhausted, StackExchangeSource

EXIT_OK, EXIT_FAILED = 0, 1

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _cache_path(args) -> Path:
    if args.corpus:
        return Path(args.corpus)
    return REPO_ROOT / DEFAULT_CACHE / f"{args.site}.jsonl"


def _cmd_tags(args) -> int:
    source = StackExchangeSource(site=args.site)
    try:
        tags = source.tags(limit=args.limit, inname=args.inname)
    except RuntimeError as exc:
        err(f"could not read tags: {exc}")
        return EXIT_FAILED
    out(f"{args.site}.stackexchange.com -- {len(tags)} tags")
    for tag in tags:
        out(f"  {tag['count']:>7}  {tag['name']}")
    if source.quota_remaining is not None:
        err(f"\nquota left today: {source.quota_remaining}")
    return EXIT_OK


def _cmd_harvest(args) -> int:
    probes = []
    for value in args.tag:
        probes.append(Probe("tag", value))
    for value in args.query:
        probes.append(Probe("query", value))
    if not probes:
        err("nothing to read: pass at least one --tag or --query.")
        err("run `tags` first to see which labels exist and how big they are.")
        return EXIT_FAILED

    path = _cache_path(args)
    store = CorpusStore(path)
    before = len(store)
    source = StackExchangeSource(site=args.site)

    def progress(probe, page, count, report):
        err(f"  {probe.describe():<28} page {page:>2}  +{count}")

    out(f"reading {args.site}.stackexchange.com into {path}")
    out(f"holding {before} questions before this run\n")
    report = harvest(source, probes, store, max_pages=args.pages,
                     pagesize=args.pagesize,
                     on_progress=progress if args.verbose else None)
    store.save()

    out(report.describe())
    out(f"\ncorpus: {before} -> {len(store)} questions ({report.total_new} new)")
    out(f"saved to {path}")
    if report.stopped_early:
        return EXIT_FAILED
    return EXIT_OK


def _load(args):
    path = _cache_path(args)
    if not path.exists():
        err(f"no corpus at {path}. Run `harvest` first.")
        return None
    store = CorpusStore(path)
    if not len(store):
        err(f"{path} is empty.")
        return None
    return store


def _corpus_summary(items) -> str:
    now = datetime.now(timezone.utc)
    ages = [(now - item.created_at).total_seconds() / 86400 for item in items]
    recent = sum(1 for age in ages if age <= 365)
    unanswered = sum(1 for item in items if not item.is_answered)
    licences = {}
    for item in items:
        licences[item.content_license or "unstated"] = \
            licences.get(item.content_license or "unstated", 0) + 1
    span = ""
    if ages:
        oldest = max(ages) / 365.25
        span = f", spanning {oldest:.1f} years"
    # "unanswered" here is Stack Exchange's own test: no accepted answer AND no
    # answer scoring one or more. Not the same as "nobody replied", and not the
    # same as "has no accepted answer" either -- of eight questions all reporting
    # answered, only five had anything accepted.
    return (f"{len(items)} questions{span}\n"
            f"  {recent} from the last year, {unanswered} the site does not count\n"
            f"  as answered (nothing accepted, nothing upvoted)\n"
            f"  licence: " + ", ".join(f"{name} x{count}"
                                      for name, count in sorted(licences.items())))


def _cmd_clusters(args) -> int:
    store = _load(args)
    if store is None:
        return EXIT_FAILED
    items = store.items()
    out(_corpus_summary(items))

    result = cluster_items(items, threshold=args.threshold, min_size=args.min_size,
                           min_df=args.min_df, max_df_ratio=args.max_df)
    clusters = result["clusters"]
    grouped = sum(c.size for c in clusters)
    out(f"\n{len(clusters)} groups covering {grouped} of {len(items)} questions "
        f"({grouped / len(items):.0%}); {len(result['singletons'])} resembled "
        f"nothing else")
    out(f"similarity threshold {args.threshold}, minimum group {args.min_size}\n")

    ranked = measure(clusters, items)
    if not ranked:
        out("no groups met the minimum size. Lower --threshold or --min-size.")
        return EXIT_OK

    if args.json:
        payload = {
            "site": args.site,
            "questions": len(items),
            "grouped": grouped,
            "threshold": args.threshold,
            "groups": [_as_dict(d, i) for i, d in enumerate(ranked, 1)],
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        err(f"written to {args.json}")

    out("  #  demand  size  unans  recent  toil  group")
    out("  " + "-" * 72)
    for number, demand in enumerate(ranked[:args.top], 1):
        out(f"  {number:>2}  {demand.total():>6}  {demand.size:>4}  "
            f"{demand.unanswered_share:>4.0%}  {demand.recent_share:>5.0%}  "
            f"{demand.toil_share:>4.0%}  {demand.cluster.label}")

    out("\nthe top groups in detail")
    for number, demand in enumerate(ranked[:args.detail], 1):
        out(f"\n{number}. {demand.cluster.label}   [{demand.size} questions, "
            f"demand {demand.total()}/100]")
        for name, points, evidence in demand.parts():
            out(f"     {points:>5.1f}  {name:<8} {evidence}")
        out(f"     terms: " + ", ".join(
            f"{term}" for term, _ in demand.cluster.terms[:6]))
        for item in demand.exemplars:
            out(f"     - {item.title[:76]}")
            out(f"       {item.url}")
    out("\ncontent from Stack Exchange, CC BY-SA; every link above is the "
        "attribution the licence asks for.")
    return EXIT_OK


def _as_dict(demand, number) -> dict:
    return {
        "rank": number,
        "label": demand.cluster.label,
        "terms": [term for term, _ in demand.cluster.terms],
        "size": demand.size,
        "unanswered_share": round(demand.unanswered_share, 3),
        "recent_share": round(demand.recent_share, 3),
        "toil_share": round(demand.toil_share, 3),
        "domain_share": round(demand.domain_share, 3),
        "median_score": demand.median_score,
        "median_age_days": round(demand.median_age_days, 1),
        "demand": demand.total(),
        "parts": [{"name": n, "points": round(p, 1), "evidence": e}
                  for n, p, e in demand.parts()],
        "examples": [{"title": i.title, "url": i.url, "score": i.engagement_score,
                      "answered": i.is_answered} for i in demand.exemplars],
    }


def _cmd_show(args) -> int:
    store = _load(args)
    if store is None:
        return EXIT_FAILED
    items = store.items()
    result = cluster_items(items, threshold=args.threshold, min_size=args.min_size,
                           min_df=args.min_df, max_df_ratio=args.max_df)
    ranked = measure(result["clusters"], items)
    if not 1 <= args.number <= len(ranked):
        err(f"there are {len(ranked)} groups; asked for {args.number}.")
        return EXIT_FAILED
    demand = ranked[args.number - 1]
    out(f"group {args.number}: {demand.cluster.label}  ({demand.size} questions)")
    out("terms that formed it: " + ", ".join(
        f"{term} ({weight})" for term, weight in demand.cluster.terms))
    out("")
    members = sorted((items[i] for i in demand.cluster.members),
                     key=lambda m: (-m.engagement_score, m.external_id))
    # Both numbers are named on every line. The first version printed a bare
    # "[ 0]" for the vote count and marked unanswered questions with an
    # asterisk, and the first person to read it -- the author -- took the votes
    # for an answer count and wrote up a well-answered group as an unmet need.
    # A column nobody can misread is worth eight characters a line.
    out(f"{'votes':>6} {'answers':>8}  question")
    for item in members:
        answers = f"{item.answer_count}" + ("" if item.is_answered else " (none accepted)")
        out(f"{item.engagement_score:>6} {answers:>8}  {item.title}")
        out(f"{'':>16}{item.url}")
    return EXIT_OK


def _answers_path(args) -> Path:
    return _cache_path(args).with_name(_cache_path(args).stem + "-answers.jsonl")


def _cmd_answers(args) -> int:
    """Fetch and read the answers to one group's questions.

    Separate from `clusters` because it costs quota and the rest does not, and
    because the question it settles is a different one: not "what do people ask
    about" but "did asking get them anywhere".
    """
    store = _load(args)
    if store is None:
        return EXIT_FAILED
    items = store.items()
    result = cluster_items(items, threshold=args.threshold, min_size=args.min_size,
                           min_df=args.min_df, max_df_ratio=args.max_df)
    ranked = measure(result["clusters"], items)
    if not 1 <= args.number <= len(ranked):
        err(f"there are {len(ranked)} groups; asked for {args.number}.")
        return EXIT_FAILED

    demand = ranked[args.number - 1]
    members = {items[i].external_id: items[i] for i in demand.cluster.members}

    path = _answers_path(args)
    cached = _load_answers(path)
    wanted = [qid for qid in members if qid not in {a["question_id"] for a in cached}]

    if wanted and not args.offline:
        source = StackExchangeSource(site=args.site)
        try:
            fetched = source.answers(wanted)
        except (RuntimeError, QuotaExhausted) as exc:
            err(f"could not read answers: {exc}")
            return EXIT_FAILED
        cached.extend(fetched)
        _save_answers(path, cached)
        err(f"fetched {len(fetched)} answers for {len(wanted)} questions; "
            f"quota left {source.quota_remaining}")
    elif wanted:
        err(f"{len(wanted)} questions have no cached answers and --offline is set.")

    relevant = [a for a in cached if a["question_id"] in members]
    if not relevant:
        out("no answers held for this group.")
        return EXIT_OK

    readings = [read_answer(a) for a in relevant]
    out(f"group {args.number}: {demand.cluster.label}  "
        f"({len(members)} questions)\n")
    out(summarise(readings))

    by_question = {}
    for reading in readings:
        by_question.setdefault(reading.question_id, []).append(reading)
    out("\nby question, best-scoring answer first")
    for qid, item in sorted(members.items(),
                            key=lambda kv: -kv[1].engagement_score):
        out(f"\n  {item.title}")
        out(f"  {item.url}")
        for reading in sorted(by_question.get(qid, []),
                              key=lambda r: (not r.is_accepted, -r.score)):
            out(reading.line())
            out(f"           {reading.url}")
    out("\ncontent from Stack Exchange, CC BY-SA; the links are the attribution.")
    return EXIT_OK


def _load_answers(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _save_answers(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen, unique = set(), []
    for row in rows:
        if row["answer_id"] in seen:
            continue
        seen.add(row["answer_id"])
        unique.append(row)
    with path.open("w", encoding="utf-8") as handle:
        for row in unique:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mine",
        description="Read a question archive and find out what is in it.")
    parser.add_argument("--site", default="electronics",
                        help="Stack Exchange site (default: electronics)")
    parser.add_argument("--corpus", default="",
                        help="path to the corpus file (default: data/corpus/<site>.jsonl)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tags = subparsers.add_parser("tags", help="list the site's real tags by size")
    tags.add_argument("--limit", type=int, default=100)
    tags.add_argument("--inname", default="", help="only tags containing this")
    tags.set_defaults(func=_cmd_tags)

    read = subparsers.add_parser("harvest", help="read questions into the corpus")
    read.add_argument("--tag", action="append", default=[],
                      help="a tag to read (repeatable)")
    read.add_argument("--query", action="append", default=[],
                      help="a text search to read (repeatable)")
    read.add_argument("--pages", type=int, default=10,
                      help="page limit per probe (default 10, i.e. 1000 questions)")
    read.add_argument("--pagesize", type=int, default=100)
    read.add_argument("--verbose", action="store_true")
    read.set_defaults(func=_cmd_harvest)

    for name, func, helptext in (("clusters", _cmd_clusters, "group and rank"),
                                 ("show", _cmd_show, "print one group in full"),
                                 ("answers", _cmd_answers,
                                  "read what one group's answers actually say")):
        sub = subparsers.add_parser(name, help=helptext)
        sub.add_argument("--threshold", type=float, default=0.30)
        sub.add_argument("--min-size", type=int, default=4, dest="min_size")
        sub.add_argument("--min-df", type=int, default=4, dest="min_df")
        sub.add_argument("--max-df", type=float, default=0.20, dest="max_df")
        if name == "clusters":
            sub.add_argument("--top", type=int, default=25)
            sub.add_argument("--detail", type=int, default=8)
            sub.add_argument("--json", default="", help="also write the ranking here")
        else:
            sub.add_argument("number", type=int, help="which group, by rank")
        if name == "answers":
            sub.add_argument("--offline", action="store_true",
                             help="use only cached answers, spend no quota")
        sub.set_defaults(func=func)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
