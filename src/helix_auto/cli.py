"""
`python auto.py` -- the local agent.

    briefing    what happened, and whether anything needs you   (read-only)
    boundaries  what this will and will not do, and why
    tasks       the registered tasks and the rope each one gets

Every command here is Level 1: it reads, measures and prints. Nothing in this
module posts, sends, votes, follows or spends. The things it refuses to do are
refused structurally in `levels.py` rather than by a check somebody can skip.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helix_bom.cli import err, out

from . import briefing as briefing_module
from .levels import Level, describe_boundaries
from .tasks import REGISTERED

EXIT_OK, EXIT_ATTENTION = 0, 1


def _cmd_briefing(args) -> int:
    report = briefing_module.build(store=args.store)
    out(report.render())
    # Exit code carries the answer, so a scheduled run can be quiet unless
    # something wants a person.
    return EXIT_ATTENTION if (args.strict and report.needs_attention) else EXIT_OK


def _cmd_boundaries(args) -> int:
    out(describe_boundaries())
    return EXIT_OK


def _cmd_tasks(args) -> int:
    out(f"{len(REGISTERED)} registered task(s)\n")
    for task in REGISTERED:
        gate = {Level.AUTOMATIC: "runs unattended",
                Level.NOTIFY: "runs, then tells you",
                Level.APPROVE: "waits for you, every time"}[task.level]
        out(f"  {task.name}")
        out(f"    level {int(task.level)} -- {gate}")
        out(f"    {task.description}")
        out("")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto",
        description="The local agent. Reads, measures, drafts. Never posts.")
    parser.add_argument("--store", type=Path, default=None,
                        help="campaign store to read (default: the usual one)")
    sub = parser.add_subparsers(dest="command", required=True)

    brief = sub.add_parser("briefing", help="what happened and what needs you")
    brief.add_argument("--strict", action="store_true",
                       help="exit non-zero when something needs a person")
    brief.set_defaults(func=_cmd_briefing)

    sub.add_parser("boundaries", help="what this will and will not do"
                   ).set_defaults(func=_cmd_boundaries)
    sub.add_parser("tasks", help="registered tasks and their permission level"
                   ).set_defaults(func=_cmd_tasks)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
