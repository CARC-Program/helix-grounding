"""
`python -m helix_ops.cli` — the operations console.

Not shipped in the wheel. This runs the business, not the user's board, and
nobody installing a verification library should receive a launch tracker.

The command set is small on purpose. Every one of these either states what is
true, records what happened, or says what to do next — there is nothing here
that sends anything anywhere. Posting is done by a person from their own
accounts, which is both the strategy `docs/FIRST_USERS.md` argues for and the
only version of it that does not get an account banned from the two channels
that matter most.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helix_bom.cli import err, out

from . import release as release_checks
from . import verify as verifier
from .campaign import PREREQUISITES, RESPONSE_KINDS, Campaign
from .drafts import BY_KEY, CHANNELS, DraftError, render, verify
from .facts import gather

EXIT_OK, EXIT_REFUSED = 0, 1

# `out` and `err` come from the BOM CLI rather than being reimplemented,
# because this console has exactly the same problem: the drafts are full of em
# dashes, and `helix-ops draft` on a cp437 terminal would die the same way
# `helix-bom demo` did. One implementation, tested in one place.


def _facts(args):
    facts = gather(run_tests=args.run_tests)
    out(facts.describe())
    if args.sources:
        out("\nwhere each came from:")
        for key, source in facts.sources.items():
            out(f"  {key:<22} {source}")
    return EXIT_OK


def _report_grounding(text, facts) -> bool:
    """Print the verification result. Returns True if the draft may be used."""
    report = verify(text, facts)
    if report.checked_count == 0:
        # Said out loud rather than reported as a pass. A grounding report of
        # "0 ungrounded" on text containing no numbers is true and useless,
        # and reading it as approval is the same error as a BOM review that
        # stayed quiet about the checks it could not run.
        err("\n[grounding] no numeric claims in this draft — nothing to check.")
        return True
    if report.is_grounded:
        err(f"\n[grounding] {report.summary()}")
        return True
    err(f"\n[grounding] {report.summary()}")
    err("[grounding] Refusing. Every number in a launch post has to be one "
        "this repository can produce.")
    return False


def _draft(args):
    facts = gather(run_tests=args.run_tests)
    channel = BY_KEY[args.channel]
    try:
        text = render(args.channel, facts)
    except DraftError as exc:
        err(f"helix-ops: {exc}")
        return EXIT_REFUSED

    if not _report_grounding(text, facts):
        return EXIT_REFUSED

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        err(f"Draft written to {args.out}")
    else:
        out(text)

    err(f"\n[{channel.name}] {channel.caution}")
    err("\n[reminder] Adapt this before posting. Anything that reads as "
        "copy-and-paste marketing gets ignored, and your own words will land "
        "better than mine. Re-check it afterwards with `check <file>`.")
    return EXIT_OK


def _check(args):
    facts = gather(run_tests=args.run_tests)
    text = Path(args.file).read_text(encoding="utf-8")
    return EXIT_OK if _report_grounding(text, facts) else EXIT_REFUSED


def _status(args):
    campaign = Campaign.load(args.store)
    out(campaign.milestone_status())
    out()
    facts = gather()
    out("prerequisites:")
    for key, description in PREREQUISITES.items():
        recorded = bool(campaign.prerequisites.get(key))
        mark = "x" if recorded else " "
        observed, why = verifier.check(key, facts.repo_url, facts.package)
        if observed is None:
            note = "  (on trust)"
        elif observed == recorded:
            note = "  (verified)"
        else:
            note = f"  <- DISAGREES: {why}"
        out(f"  [{mark}] {key:<16} {description}{note}")
    out()
    out("channels:")
    for channel in sorted(CHANNELS, key=lambda c: c.order):
        post = campaign.posts[channel.key]
        detail = f" {post.posted_at} {post.url}".rstrip() if post.url else ""
        out(f"  {post.state:<8} {channel.key:<12} {channel.name}{detail}")
    out()
    out("next:")
    out(f"  {campaign.next_action()}")
    return EXIT_OK


def _next(args):
    out(Campaign.load(args.store).next_action())
    return EXIT_OK


def _mark_ready(args):
    campaign = Campaign.load(args.store)
    claim = not args.undo

    # The reason this exists: on 2026-08-19 the store recorded
    # repo_public: true against a private repository, and nothing noticed
    # for two days. Where the world can be looked at, looking beats being
    # told -- and a tracker that records a false fact is worse than no
    # tracker, because it is consulted instead of the world.
    facts = gather()
    observed, why = verifier.check(args.prerequisite, facts.repo_url, facts.package)
    if observed is not None and observed != claim and not args.anyway:
        err(f"helix-ops: refusing. You said {args.prerequisite}="
            f"{str(claim).lower()}, but {why}.")
        err("Fix the world, or pass --anyway if the check itself is wrong.")
        return EXIT_REFUSED

    campaign.mark_prerequisite(args.prerequisite, claim)
    campaign.save(args.store)
    state = "met" if claim else "not met"
    if observed is None:
        out(f"{args.prerequisite}: {state} (recorded on trust \u2014 {why})")
    else:
        out(f"{args.prerequisite}: {state} (verified \u2014 {why})")
    out(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _release_check(args):
    """Refuse a release that would ship a claim this repo cannot back.

    Stricter than anything else here: a check that could not run counts as a
    failure. Everywhere else an unrunnable check is reported honestly and the
    caller decides -- but PyPI will not let you re-upload a version, mirrors
    copy within hours, and the first thing a stranger installs is the thing
    they judge this by. There is nothing to decide.
    """
    out("Running the suite to get a real number...")
    checks = release_checks.run_all()
    out("")
    for check in checks:
        out(check.line())
    failed = [c for c in checks if not c.ok]
    out("")
    if failed:
        out(f"{len(failed)} of {len(checks)} checks failed. Not releasable.")
        return EXIT_REFUSED
    out(f"All {len(checks)} checks pass. Safe to build and upload.")
    return EXIT_OK


def _posted(args):
    campaign = Campaign.load(args.store)
    campaign.mark_posted(args.channel, args.url, args.on)
    campaign.save(args.store)
    out(f"Recorded: {BY_KEY[args.channel].name} posted at {args.url}")
    out(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _response(args):
    campaign = Campaign.load(args.store)
    try:
        campaign.record_response(
            args.channel, args.kind, args.summary,
            ran_it=args.ran, action=args.action or "", on=args.on)
    except ValueError as exc:
        err(f"helix-ops: {exc}")
        return EXIT_REFUSED
    campaign.save(args.store)
    out(f"Recorded on {BY_KEY[args.channel].name}: {RESPONSE_KINDS[args.kind]}")
    if args.kind == "ran_nothing_found":
        out("\nAsk them one question: did it tell you anything you did not "
              "already know? A tool that runs cleanly and teaches nothing is "
              "not yet worth money, and that is the single most useful thing "
              "to learn early.")
    out(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _resolve(args):
    campaign = Campaign.load(args.store)
    campaign.resolve(args.channel, args.index, args.action)
    campaign.save(args.store)
    out(f"Resolved #{args.index} on {BY_KEY[args.channel].name}.")
    out("\nReply to the reporter with the commit. That reply is worth more "
          "than the original post — it is public evidence you are someone who "
          "fixes things.")
    out(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix-ops",
        description="Launch operations: what is true, what happened, what next.")
    parser.add_argument("--store", type=Path, default=None,
                        help="campaign JSON (default: ops/campaign.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    channels = sorted(BY_KEY)

    facts = sub.add_parser("facts", help="what this repository can currently claim")
    facts.add_argument("--run-tests", action="store_true",
                       help="measure the pass count (runs the suite)")
    facts.add_argument("--sources", action="store_true",
                       help="show where each fact was read from")
    facts.set_defaults(func=_facts)

    draft = sub.add_parser("draft", help="render a launch post from live facts")
    draft.add_argument("channel", choices=channels)
    draft.add_argument("--run-tests", action="store_true",
                       help="required for drafts that state a test count")
    draft.add_argument("--out", type=Path, help="write to a file instead of stdout")
    draft.set_defaults(func=_draft)

    check = sub.add_parser("check", help="verify an edited draft against the repo")
    check.add_argument("file", type=Path)
    check.add_argument("--run-tests", action="store_true")
    check.set_defaults(func=_check)

    status = sub.add_parser("status", help="milestone position and next action")
    status.set_defaults(func=_status)

    nxt = sub.add_parser("next", help="the one thing to do now")
    nxt.set_defaults(func=_next)

    ready = sub.add_parser("mark-ready", help="record a prerequisite as met")
    ready.add_argument("prerequisite", choices=sorted(PREREQUISITES))
    ready.add_argument("--undo", action="store_true")
    ready.add_argument("--anyway", action="store_true",
                       help="record the claim even though the check "
                            "disagrees (use when the check is wrong, "
                            "not when the world is)")
    ready.set_defaults(func=_mark_ready)

    release = sub.add_parser(
        "release-check", help="pre-flight checks before building and uploading")
    release.set_defaults(func=_release_check)

    posted = sub.add_parser("posted", help="record that a post went up")
    posted.add_argument("channel", choices=channels)
    posted.add_argument("--url", required=True)
    posted.add_argument("--on", help="ISO date (default: today)")
    posted.set_defaults(func=_posted)

    response = sub.add_parser("response", help="record what came back")
    response.add_argument("channel", choices=channels)
    response.add_argument("--kind", required=True, choices=sorted(RESPONSE_KINDS))
    response.add_argument("--summary", required=True)
    response.add_argument("--ran", action="store_true",
                          help="this person actually ran the tool — the only "
                               "thing that counts towards M2")
    response.add_argument("--action", help="what was done about it")
    response.add_argument("--on", help="ISO date (default: today)")
    response.set_defaults(func=_response)

    resolve = sub.add_parser("resolve", help="close a bug report")
    resolve.add_argument("channel", choices=channels)
    resolve.add_argument("index", type=int)
    resolve.add_argument("action")
    resolve.set_defaults(func=_resolve)

    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
