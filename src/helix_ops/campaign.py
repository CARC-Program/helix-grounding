"""
The launch record: what was posted where, what came back, and what to do next.

`docs/FIRST_USERS.md` contains a strategy. A strategy in a document is a
strategy nobody is held to — the same failure the old roadmap had, where seven
checkpoints were marked CLOSED for systems that did not exist. This module
holds the same rules as executable state, so the answer to "what should I do
next" is computed from what actually happened rather than remembered.

Three rules from that document are enforced here rather than merely written
down, because each one is expensive to break and easy to break by accident:

**One channel at a time.** Five posts in a day is a spam pattern; five posts
over three weeks, each better than the last, is a launch. `next_action` will
not offer a second channel while the first has an unresolved bug report.

**Show HN is one shot.** You cannot repost the same project effectively, so it
stays locked until the prerequisites are recorded as met — not assumed met.

**Prerequisites are recorded, not inferred.** Whether the package is on PyPI
and the repository is public are real-world facts about the world, and this
module runs offline by design. It asks; it does not guess. That is the same
rule the review agent follows about a check it cannot run.

The store is JSON in the repository, deliberately. A launch record that lives
only on one machine is a launch record that a reinstall deletes — which has
already happened to this project once (D-043).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date as date_type
from pathlib import Path

from .drafts import BY_KEY, CHANNELS

DEFAULT_STORE = Path(__file__).resolve().parent.parent.parent / "ops" / "campaign.json"

PLANNED, POSTED, CLOSED = "planned", "posted", "closed"

# What came back, in the categories FIRST_USERS.md defines a response to.
RESPONSE_KINDS = {
    "bug": "reported something wrong — the best possible outcome",
    "ran_nothing_found": "ran it, nothing useful found",
    "feature": "asked for a feature — record it, do not build it yet",
    "question": "asked something that is not a bug",
}

# Real-world events that gate the campaign. Each is something a person does,
# not something code can detect from inside an offline process.
PREREQUISITES = {
    "repo_public": "the GitHub repository is public and its URL loads",
    "pypi_published": "`pip install helix-grounding` works from a clean machine",
    "demo_works": "`helix-bom demo` runs correctly on a machine that is not yours",
}


@dataclass
class Response:
    date: str
    kind: str
    ran_it: bool
    summary: str
    action: str = ""
    resolved: bool = False


@dataclass
class Post:
    channel: str
    state: str = PLANNED
    posted_at: str = ""
    url: str = ""
    responses: list = field(default_factory=list)

    @property
    def unresolved_bugs(self) -> list:
        return [r for r in self.responses
                if r.kind == "bug" and not r.resolved]


class Campaign:
    """The record. Loads from and saves to one JSON file."""

    def __init__(self, posts=None, prerequisites=None):
        self.posts = posts if posts is not None else {
            channel.key: Post(channel=channel.key) for channel in CHANNELS
        }
        self.prerequisites = prerequisites if prerequisites is not None else {
            key: False for key in PREREQUISITES
        }

    # ---------------------------------------------------------------- io
    @classmethod
    def load(cls, path: Path | None = None) -> "Campaign":
        path = Path(path) if path else DEFAULT_STORE
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        posts = {}
        for key, data in raw.get("posts", {}).items():
            responses = [Response(**r) for r in data.pop("responses", [])]
            posts[key] = Post(responses=responses, **data)
        # A channel added to drafts.py after this file was written must appear,
        # or the new channel is invisible to every report below.
        for channel in CHANNELS:
            posts.setdefault(channel.key, Post(channel=channel.key))
        prerequisites = {key: False for key in PREREQUISITES}
        prerequisites.update(raw.get("prerequisites", {}))
        return cls(posts=posts, prerequisites=prerequisites)

    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else DEFAULT_STORE
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "prerequisites": self.prerequisites,
            "posts": {key: asdict(post) for key, post in self.posts.items()},
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    # ------------------------------------------------------------ record
    def mark_prerequisite(self, key: str, met: bool = True) -> None:
        if key not in PREREQUISITES:
            raise KeyError(f"unknown prerequisite {key!r}. "
                           f"Known: {', '.join(sorted(PREREQUISITES))}")
        self.prerequisites[key] = met

    def mark_posted(self, channel: str, url: str, on: str | None = None) -> Post:
        post = self._post(channel)
        post.state = POSTED
        post.posted_at = on or date_type.today().isoformat()
        post.url = url
        return post

    def record_response(self, channel: str, kind: str, summary: str,
                        ran_it: bool, action: str = "", on: str | None = None) -> Response:
        if kind not in RESPONSE_KINDS:
            raise KeyError(f"unknown response kind {kind!r}. "
                           f"Known: {', '.join(sorted(RESPONSE_KINDS))}")
        post = self._post(channel)
        if post.state == PLANNED:
            raise ValueError(
                f"{channel} is not posted yet — a response to a post that was "
                f"never made is a record of something that did not happen."
            )
        response = Response(
            date=on or date_type.today().isoformat(),
            kind=kind, ran_it=ran_it, summary=summary, action=action,
            resolved=bool(action) and kind != "bug",
        )
        post.responses.append(response)
        return response

    def resolve(self, channel: str, index: int, action: str) -> Response:
        post = self._post(channel)
        response = post.responses[index]
        response.action = action
        response.resolved = True
        return response

    def _post(self, channel: str) -> Post:
        if channel not in self.posts:
            raise KeyError(f"unknown channel {channel!r}. "
                           f"Known: {', '.join(sorted(self.posts))}")
        return self.posts[channel]

    # ------------------------------------------------------------ report
    @property
    def strangers_who_ran_it(self) -> int:
        """The only number that closes M2.

        Counted from responses that say somebody ran the tool, not from post
        views, upvotes or clicks. `docs/ROADMAP.md` closes a milestone on a
        real person doing something they did not do before, and every other
        number available here is a proxy for that one.
        """
        return sum(1 for post in self.posts.values()
                   for response in post.responses if response.ran_it)

    @property
    def unmet_prerequisites(self) -> list:
        return [key for key, met in self.prerequisites.items() if not met]

    def open_bugs(self) -> list:
        return [(post.channel, index, response)
                for post in self.posts.values()
                for index, response in enumerate(post.responses)
                if response.kind == "bug" and not response.resolved]

    def feature_requests(self) -> dict:
        """Counted, because one request is a conversation and three is a
        signal. FIRST_USERS.md says write them down and do not build them; a
        count is what turns that from restraint into a decision rule."""
        counts: dict = {}
        for post in self.posts.values():
            for response in post.responses:
                if response.kind == "feature":
                    counts[response.summary] = counts.get(response.summary, 0) + 1
        return counts

    def next_action(self) -> str:
        """What to do now, and nothing else.

        Deliberately returns one thing. A list of everything outstanding is a
        list that gets skimmed; the whole value of ordering the channels was
        that each round improves on the last.
        """
        unmet = self.unmet_prerequisites
        if unmet:
            first = unmet[0]
            return (f"Not ready to post. {PREREQUISITES[first]} — "
                    f"record it with `mark-ready {first}` once it is true.")

        bugs = self.open_bugs()
        if bugs:
            channel, index, response = bugs[0]
            return (f"Fix the bug from {BY_KEY[channel].name} first: "
                    f"\"{response.summary}\". Reproduce it, write a failing "
                    f"test, fix it, then reply with the commit — that reply is "
                    f"worth more than the original post. "
                    f"Resolve it with `resolve {channel} {index} \"<what you did>\"`.")

        for channel in sorted(CHANNELS, key=lambda c: c.order):
            post = self.posts[channel.key]
            if post.state == PLANNED:
                if channel.one_shot:
                    return (f"Next: {channel.name} — and this is the one-shot. "
                            f"{channel.caution} Draft it with "
                            f"`draft {channel.key} --run-tests`.")
                return (f"Next: {channel.name}. {channel.caution} "
                        f"Draft it with `draft {channel.key}`.")

        ran = self.strangers_who_ran_it
        if ran >= 3:
            return (f"M2 is met: {ran} stranger(s) ran it. The milestone closed "
                    f"on a real event, which is the only way it closes. What "
                    f"they said decides M3 — see the outcome table in "
                    f"docs/FIRST_USERS.md.")
        return (f"Every channel has been posted and {ran} stranger(s) have run "
                f"it. Fewer than three is a distribution problem rather than a "
                f"product one — try a community not on this list before "
                f"concluding anything about the tool.")

    @property
    def said_it_caught_something(self) -> int:
        """Responses where the tool found a real problem for a real person.

        A property rather than a local sum because `helix_auto` reports this
        number too, and two places computing one number is how they drift --
        which is the same fault as the README test count that went stale three
        times.
        """
        return sum(
            1 for post in self.posts.values() for response in post.responses
            if response.kind == "bug" or (response.ran_it and response.kind == "question")
        )

    def milestone_status(self) -> str:
        ran = self.strangers_who_ran_it
        found_something = self.said_it_caught_something
        lines = [
            f"strangers who ran it       {ran} (3 closes M2)",
            f"said it caught something   {found_something} (1 means it is worth pricing)",
            f"channels posted            "
            f"{sum(1 for p in self.posts.values() if p.state != PLANNED)} of {len(CHANNELS)}",
            f"open bug reports           {len(self.open_bugs())}",
        ]
        requests = self.feature_requests()
        if requests:
            lines.append("feature requests")
            for summary, count in sorted(requests.items(), key=lambda kv: -kv[1]):
                marker = "  <- three is a signal" if count >= 3 else ""
                lines.append(f"  {count}x  {summary}{marker}")
        return "\n".join(lines)
