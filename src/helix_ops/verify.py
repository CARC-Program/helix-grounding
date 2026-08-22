"""
Check the prerequisites that can be checked, instead of believing them.

On 2026-08-19 the campaign store recorded `repo_public: true` while the
repository was private. Nothing was wrong with the code — somebody ran
`mark-ready repo_public`, which does exactly what it says, and the store
faithfully recorded a claim about the world that was not true. It sat there
until it was noticed by accident two days later.

That is the same failure this whole project is built against, arriving from the
one direction nobody guarded: not a check that silently passed, but a fact
nobody checked because the tool was designed to ask rather than look.

`campaign.py` says prerequisites are recorded rather than inferred because the
module runs offline. That reasoning holds for whether a stranger ran the tool.
It does not hold for whether a repository is public, which is a single API call
away and is not a matter of opinion. So: anything verifiable is verified, and
`mark-ready` refuses to record a claim that contradicts what it can see.

Anything genuinely unverifiable from here still gets recorded on trust, and is
labelled as such rather than being quietly presented as the same kind of fact.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

# Not on PATH in every shell -- winget installs it machine-wide, but a shell
# started before the install will not see it. Checking the known location
# beats failing with "gh: not found" on a machine where gh is present.
GH_FALLBACKS = (
    r"C:\Program Files\GitHub CLI\gh.exe",
    r"C:\Program Files (x86)\GitHub CLI\gh.exe",
)

UNVERIFIABLE = {
    "pypi_published": (
        "needs a network call to the package index, which this module does not "
        "make. Confirm it by installing into a clean virtualenv on a machine "
        "that has never seen the source."
    ),
    "demo_works": (
        "means the demo ran on somebody else's machine. That is a fact about a "
        "person, not about this repository, and nothing here can observe it."
    ),
}


def gh_path() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    return next((p for p in GH_FALLBACKS if Path(p).exists()), None)


def _repo_slug(repo_url: str) -> str | None:
    match = re.search(r"github\.com[:/]([^/]+/[^/.]+)", repo_url or "")
    return match.group(1) if match else None


def check_repo_public(repo_url: str) -> tuple[bool | None, str]:
    """Ask GitHub whether the repository is public.

    Returns ``(state, explanation)``. ``None`` means the question could not be
    answered — which is deliberately not the same as ``False``, because
    "I could not look" and "it is private" are opposite claims and this project
    has spent a lot of effort keeping them apart.
    """
    slug = _repo_slug(repo_url)
    if not slug:
        return None, f"no github.com repository in {repo_url!r}"

    gh = gh_path()
    if gh is None:
        return None, "the GitHub CLI is not installed, so visibility cannot be read"

    try:
        completed = subprocess.run(
            [gh, "repo", "view", slug, "--json", "visibility"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"could not run the GitHub CLI ({exc})"

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        first = detail[0] if detail else "unknown error"
        if "Could not resolve" in first:
            return False, f"{slug} does not exist or is not visible to this account"
        if "authentication" in first.lower() or "gh auth login" in first:
            return None, "the GitHub CLI is not authenticated (`gh auth login`)"
        return None, f"the GitHub CLI failed: {first}"

    try:
        visibility = json.loads(completed.stdout)["visibility"]
    except (ValueError, KeyError):
        return None, "the GitHub CLI returned something unreadable"

    public = visibility.upper() == "PUBLIC"
    return public, f"{slug} is {visibility.lower()}"


def check(key: str, repo_url: str) -> tuple[bool | None, str]:
    """Verify one prerequisite. ``None`` means it is not checkable from here."""
    if key == "repo_public":
        return check_repo_public(repo_url)
    if key in UNVERIFIABLE:
        return None, UNVERIFIABLE[key]
    return None, "no verifier for this prerequisite"
