"""
The registered tasks, each with the rope it is allowed.

This file is where somebody will eventually try to add "like recent posts", so
it is worth being clear about what happens then: `Task` refuses to construct,
the import fails, and they read `levels.py`. The boundary is not enforced here;
it is enforced by the type, which means it cannot be forgotten in this file.

What is deliberately absent, and why it is absent rather than disabled:

**Nothing posts.** Not because posting is wrong, but because posting to Reddit
commercially needs a signed Data API agreement the operator cannot enter, and
because a draft written by a machine and posted without being read is how an
account gets a reputation it cannot undo. Drafting is Level 1. Posting is a
person, every time.

**Nothing votes, follows or reposts.** Those cannot be registered at all.

The realistic honest note on all of this: automating outreach is not what
stands between this project and income. Zero strangers have run the tool. A
faster way to send a message nobody responds to is not the missing piece, and
building one before the message is known to work mostly gets an account banned
sooner.
"""

from __future__ import annotations

from .levels import Level, Task


def _run_briefing():
    from .briefing import build
    return build().render()


def _run_release_gate():
    from pathlib import Path

    from helix_ops.release import run_all
    root = Path(__file__).resolve().parent.parent.parent
    checks = run_all(root)
    return "\n".join(check.line() for check in checks)


def _run_miner_refresh():
    """Re-cluster what is already on disk. Deliberately does not fetch.

    A scheduled job that spends API quota unattended is a job that empties the
    day's allowance while nobody is watching. Reading the local corpus costs
    nothing and answers the question the schedule is for -- has the picture
    changed -- and a fetch stays a thing a person asks for.
    """
    from helix_signal.cluster import cluster_items, measure
    from helix_signal.corpus import DEFAULT_CACHE, CorpusStore
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    path = root / DEFAULT_CACHE / "electronics.jsonl"
    if not path.exists():
        return "no corpus on disk -- run `python mine.py harvest` first"
    items = CorpusStore(path).items()
    result = cluster_items(items, min_size=6)
    ranked = measure(result["clusters"], items)
    lines = [f"{len(items)} questions, {len(ranked)} groups"]
    lines += [f"  {d.total():>3}  {d.size:>4}  {d.cluster.label[:52]}"
              for d in ranked[:5]]
    return "\n".join(lines)


REGISTERED = (
    Task(
        name="briefing",
        description="Read the campaign store, GitHub and PyPI, and say whether "
                    "anything needs a person today.",
        level=Level.AUTOMATIC,
        run=_run_briefing,
        every_hours=24.0,
        tags=("read",),
    ),
    Task(
        name="release gate",
        description="Run every pre-flight check over the working tree, the "
                    "history and the built artifacts.",
        level=Level.AUTOMATIC,
        run=_run_release_gate,
        every_hours=24.0,
        tags=("read", "test"),
    ),
    Task(
        name="corpus re-read",
        description="Re-cluster the question archive already on disk and list "
                    "the largest groups. Spends no API quota.",
        level=Level.AUTOMATIC,
        run=_run_miner_refresh,
        every_hours=168.0,
        tags=("read",),
    ),
    # Level 3 by construction: the description says "post", and `Task` refuses
    # to let anything outward-facing be AUTOMATIC. Registered without a `run`
    # on purpose -- it exists to appear in `auto.py tasks` as a thing waiting
    # for a person, not as a thing the runner could ever fire.
    Task(
        name="outreach post",
        description="Post the drafted announcement to a channel. Requires a "
                    "person to read it, edit it, and publish it from their own "
                    "account.",
        level=Level.APPROVE,
        run=None,
        tags=("outward",),
    ),
)
