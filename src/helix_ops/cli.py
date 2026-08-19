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

from .campaign import PREREQUISITES, RESPONSE_KINDS, Campaign
from .drafts import BY_KEY, CHANNELS, DraftError, render, verify
from .facts import gather

EXIT_OK, EXIT_REFUSED = 0, 1


def _facts(args):
    facts = gather(run_tests=args.run_tests)
    print(facts.describe())
    if args.sources:
        print("\nwhere each came from:")
        for key, source in facts.sources.items():
            print(f"  {key:<22} {source}")
    return EXIT_OK


def _report_grounding(text, facts) -> bool:
    """Print the verification result. Returns True if the draft may be used."""
    report = verify(text, facts)
    if report.checked_count == 0:
        # Said out loud rather than reported as a pass. A grounding report of
        # "0 ungrounded" on text containing no numbers is true and useless,
        # and reading it as approval is the same error as a BOM review that
        # stayed quiet about the checks it could not run.
        print("\n[grounding] no numeric claims in this draft — nothing to check.",
              file=sys.stderr)
        return True
    if report.is_grounded:
        print(f"\n[grounding] {report.summary()}", file=sys.stderr)
        return True
    print(f"\n[grounding] {report.summary()}", file=sys.stderr)
    print("[grounding] Refusing. Every number in a launch post has to be one "
          "this repository can produce.", file=sys.stderr)
    return False


def _draft(args):
    facts = gather(run_tests=args.run_tests)
    channel = BY_KEY[args.channel]
    try:
        text = render(args.channel, facts)
    except DraftError as exc:
        print(f"helix-ops: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    if not _report_grounding(text, facts):
        return EXIT_REFUSED

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Draft written to {args.out}", file=sys.stderr)
    else:
        print(text)

    print(f"\n[{channel.name}] {channel.caution}", file=sys.stderr)
    print("\n[reminder] Adapt this before posting. Anything that reads as "
          "copy-and-paste marketing gets ignored, and your own words will land "
          "better than mine. Re-check it afterwards with `check <file>`.",
          file=sys.stderr)
    return EXIT_OK


def _check(args):
    facts = gather(run_tests=args.run_tests)
    text = Path(args.file).read_text(encoding="utf-8")
    return EXIT_OK if _report_grounding(text, facts) else EXIT_REFUSED


def _status(args):
    campaign = Campaign.load(args.store)
    print(campaign.milestone_status())
    print()
    print("prerequisites:")
    for key, description in PREREQUISITES.items():
        mark = "x" if campaign.prerequisites.get(key) else " "
        print(f"  [{mark}] {key:<16} {description}")
    print()
    print("channels:")
    for channel in sorted(CHANNELS, key=lambda c: c.order):
        post = campaign.posts[channel.key]
        detail = f" {post.posted_at} {post.url}".rstrip() if post.url else ""
        print(f"  {post.state:<8} {channel.key:<12} {channel.name}{detail}")
    print()
    print("next:")
    print(f"  {campaign.next_action()}")
    return EXIT_OK


def _next(args):
    print(Campaign.load(args.store).next_action())
    return EXIT_OK


def _mark_ready(args):
    campaign = Campaign.load(args.store)
    campaign.mark_prerequisite(args.prerequisite, not args.undo)
    campaign.save(args.store)
    print(f"{args.prerequisite}: {'met' if not args.undo else 'not met'}")
    print(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _posted(args):
    campaign = Campaign.load(args.store)
    campaign.mark_posted(args.channel, args.url, args.on)
    campaign.save(args.store)
    print(f"Recorded: {BY_KEY[args.channel].name} posted at {args.url}")
    print(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _response(args):
    campaign = Campaign.load(args.store)
    try:
        campaign.record_response(
            args.channel, args.kind, args.summary,
            ran_it=args.ran, action=args.action or "", on=args.on)
    except ValueError as exc:
        print(f"helix-ops: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    campaign.save(args.store)
    print(f"Recorded on {BY_KEY[args.channel].name}: {RESPONSE_KINDS[args.kind]}")
    if args.kind == "ran_nothing_found":
        print("\nAsk them one question: did it tell you anything you did not "
              "already know? A tool that runs cleanly and teaches nothing is "
              "not yet worth money, and that is the single most useful thing "
              "to learn early.")
    print(f"\nnext: {campaign.next_action()}")
    return EXIT_OK


def _resolve(args):
    campaign = Campaign.load(args.store)
    campaign.resolve(args.channel, args.index, args.action)
    campaign.save(args.store)
    print(f"Resolved #{args.index} on {BY_KEY[args.channel].name}.")
    print("\nReply to the reporter with the commit. That reply is worth more "
          "than the original post — it is public evidence you are someone who "
          "fixes things.")
    print(f"\nnext: {campaign.next_action()}")
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
    ready.set_defaults(func=_mark_ready)

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
