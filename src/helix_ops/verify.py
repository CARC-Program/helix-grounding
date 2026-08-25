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
    "demo_works": (
        "means the demo ran on somebody else's machine. That is a fact about a "
        "person, not about this repository, and nothing here can observe it."
    ),
}

PYPI_JSON = "https://pypi.org/pypi/{package}/json"


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


def check_pypi_published(package: str) -> tuple[bool | None, str]:
    """Ask the package index whether this package exists, and at what version.

    This makes a network call, which is a deliberate exception worth naming.
    The offline guarantee belongs to `helix_grounding` and `helix_bom` — the
    shipped product, where a customer's bill of materials must never leave
    their machine, and where a test disables the socket layer to prove it.
    `helix_ops` is internal tooling that already shells out to git, pytest and
    the GitHub CLI. Nothing here touches customer data.

    The reason it is worth the exception: this prerequisite was declared
    unverifiable and recorded on trust, and it sat reading ``false`` for a week
    while the package was live on PyPI. A question answerable by one public GET
    should not be answered by asking a person to remember.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
                PYPI_JSON.format(package=package), timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, f"{package} is not on PyPI"
        return None, f"the package index returned HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # No network is "I could not look", never "it is not published".
        return None, f"could not reach the package index ({exc})"

    latest = payload.get("info", {}).get("version", "?")
    count = len(payload.get("releases", {}))
    return True, f"{package} {latest} is live ({count} release(s) published)"


def check(key: str, repo_url: str, package: str = "helix-grounding") -> tuple[bool | None, str]:
    """Verify one prerequisite. ``None`` means it is not checkable from here."""
    if key == "repo_public":
        return check_repo_public(repo_url)
    if key == "pypi_published":
        return check_pypi_published(package)
    if key in UNVERIFIABLE:
        return None, UNVERIFIABLE[key]
    return None, "no verifier for this prerequisite"
