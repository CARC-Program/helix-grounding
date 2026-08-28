"""
The numbers, and how much each of them is worth.

An agent that reports every metric it can reach is a machine for producing
false encouragement. This package downloads 421 times a month with no
promotion whatsoever, which is not 421 people -- it is mirrors, CI runners and
security scanners, and a briefing that led with it would be lying pleasantly
every morning.

So every signal carries a ``confidence``, and the briefing sorts by it. The
honest ordering puts one GitHub issue above four hundred downloads, because a
person typing a sentence is evidence and a bot fetching a tarball is not.

    HARD      a person did something deliberate that costs them effort
    SOFT      probably people, probably some machines, direction is readable
    NOISE     mostly or entirely automated; report it, never lead with it

Nothing here writes, posts or authenticates as anybody. Every source is either
a public endpoint or the operator's own repository read with their own token.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import IntEnum


class Confidence(IntEnum):
    NOISE = 1
    SOFT = 2
    HARD = 3


@dataclass(frozen=True)
class Signal:
    name: str
    value: object
    confidence: Confidence
    note: str = ""
    error: str = ""

    @property
    def readable(self) -> bool:
        return not self.error

    def line(self) -> str:
        mark = {Confidence.HARD: "**", Confidence.SOFT: " *",
                Confidence.NOISE: "  "}[self.confidence]
        if self.error:
            return f"  {mark} {self.name:<26} unavailable -- {self.error}"
        text = f"  {mark} {self.name:<26} {self.value}"
        return text + (f"\n       {self.note}" if self.note else "")


def _get_json(url: str, timeout: int = 20):
    request = urllib.request.Request(
        url, headers={"User-Agent": "helix-auto (project self-monitoring)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def pypi_downloads(package: str = "helix-grounding") -> list:
    """Download counts, reported with their well-known unreliability attached.

    PyPI counts every fetch: mirrors, CI, dependency scanners, someone's Docker
    build looping. For a package nobody has promoted, essentially all of it is
    machines. It is tracked because a *change* in the shape is mildly
    informative, and reported as NOISE because the absolute number is not.
    """
    try:
        data = _get_json(f"https://pypistats.org/api/packages/{package}/recent")
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Signal("pypi downloads", None, Confidence.NOISE,
                       error=f"could not read pypistats ({exc.__class__.__name__})")]
    recent = data.get("data", {})
    return [Signal(
        "pypi downloads",
        f"{recent.get('last_day', '?')}/day  {recent.get('last_week', '?')}/week  "
        f"{recent.get('last_month', '?')}/month",
        Confidence.NOISE,
        note="mostly mirrors and CI. Not users. Watch the shape, not the number.")]


def _gh(args, repo: str) -> tuple:
    """Run `gh api` and return (payload, error). Never raises."""
    for executable in ("gh", r"C:/Program Files/GitHub CLI/gh.exe"):
        try:
            done = subprocess.run([executable, "api", *args],
                                  capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode != 0:
            return None, (done.stderr or "gh api failed").strip().splitlines()[0][:90]
        try:
            return json.loads(done.stdout), ""
        except json.JSONDecodeError:
            return None, "gh returned something that was not JSON"
    return None, "the gh CLI is not installed or not on the path"


def github(repo: str = "CARC-Program/helix-grounding") -> list:
    """Stars, issues and clones. Clones are the interesting one.

    A star is one click. An issue is somebody typing sentences about your
    software, which is the most expensive thing anybody here does for free and
    therefore the most meaningful. A clone is somebody taking the source, which
    is more effort than a star and less than an issue -- and it is also what CI
    does, so it is soft rather than hard.
    """
    signals = []
    payload, error = _gh([f"repos/{repo}"], repo)
    if error:
        return [Signal("github", None, Confidence.HARD, error=error)]

    signals.append(Signal("github stars", payload.get("stargazers_count", 0),
                          Confidence.SOFT,
                          note="one click each. Direction, not demand."))
    issues = payload.get("open_issues_count", 0)
    signals.append(Signal(
        "github open issues", issues, Confidence.HARD,
        note=("somebody typed sentences about your software -- read these first"
              if issues else "nobody has reported anything yet")))

    clones, clone_error = _gh([f"repos/{repo}/traffic/clones"], repo)
    if clone_error:
        signals.append(Signal("github clones", None, Confidence.SOFT,
                              error=clone_error))
    else:
        uniques = clones.get("uniques", 0)
        signals.append(Signal(
            "github clones (14d)",
            f"{clones.get('count', 0)} clones from {uniques} unique sources",
            Confidence.SOFT,
            note="some of these are CI. A unique source is still somebody or "
                 "something choosing to take the code."))
    return signals


def campaign(store=None) -> list:
    """The only numbers that decide anything, read from the local record."""
    try:
        from helix_ops.campaign import Campaign
        state = Campaign.load(store) if store else Campaign.load()
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        return [Signal("campaign", None, Confidence.HARD,
                       error=f"could not read the campaign store ({exc})")]

    ran = state.strangers_who_ran_it
    caught = state.said_it_caught_something
    return [
        Signal("strangers who ran it", ran, Confidence.HARD,
               note=("3 closes the milestone" if ran < 3 else "milestone met")),
        Signal("said it caught something", caught, Confidence.HARD,
               note=("one of these means it is worth pricing" if not caught
                     else "this is the number that mattered")),
    ]


def gather(repo: str = "CARC-Program/helix-grounding", store=None) -> list:
    """Every signal, hardest evidence first.

    A source that cannot be read is reported as unavailable, never as zero.
    Zero downloads and "pypistats did not answer" are different facts and the
    briefing must not print them the same way -- the same rule the BOM reviewer
    applies to a check it could not run.
    """
    signals = campaign(store) + github(repo) + pypi_downloads()
    signals.sort(key=lambda s: (-int(s.confidence), s.name))
    return signals
