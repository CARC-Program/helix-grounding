"""
Pre-flight checks for a release.

Every one of these exists because the thing it checks has already gone wrong at
least once in this repository:

- `helix_grounding.__version__` said 0.1.0 while the package shipped 0.1.1, so
  anyone reading it programmatically got the wrong answer.
- The README advertised 190 tests, then 292, against real counts of 292 and 316.
  Three times, and each time it was fixed by hand and went stale again — which
  is the argument for a check rather than more care.
- Internal documents naming real people sat in the committed tree while a
  detector that excluded their folder reported clean.
- A CHANGELOG section sat under "Unreleased" while the version had already
  moved on.

A release is the one operation this project cannot take back. PyPI does not
allow re-uploading a version, mirrors copy within hours, and the first thing a
stranger installs is the thing they judge it by. So the rule here is stricter
than elsewhere: **a check that could not run is a failure, not a pass.**
Everywhere else in this codebase an unrunnable check is reported honestly and
the caller decides. Here there is nothing to decide — if the version cannot be
read, the release does not go.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .facts import REPO_ROOT, measure_tests

# The same pattern used to scrub the history. Kept here rather than in a shell
# script so it runs as part of the release gate, and deliberately without any
# path exclusions -- the last version of this detector excluded the folder that
# held the problem and reported clean.
PERSONAL_PATTERNS = re.compile(
    r"NAME-REMOVED-FROM-HISTORY"
    r"|legal guardian|\bguardians?\b|\bminors?\b|\bunder 18\b"
    r"|allows 13\+|age 13|16-year|\bteenager\b",
    re.IGNORECASE,
)

# Files whose whole job is to describe this problem, so they name the words.
DETECTOR_EXEMPT = {"src/helix_ops/release.py"}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    def line(self) -> str:
        return f"  [{'PASS' if self.ok else 'FAIL'}] {self.name:<26} {self.detail}"


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def check_versions(root: Path) -> Check:
    pyproject = _read(root, "pyproject.toml")
    init = _read(root, "src/helix_grounding/__init__.py")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    exported = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    if not declared or not exported:
        return Check("version readable", False, "could not read one of the two")
    if declared.group(1) != exported.group(1):
        return Check("versions agree", False,
                     f"pyproject {declared.group(1)} vs __version__ {exported.group(1)}")
    return Check("versions agree", True, declared.group(1))


def check_readme_test_count(root: Path, measured: int) -> Check:
    match = re.search(r"(\d+) tests, nothing skipped", _read(root, "README.md"))
    if not match:
        return Check("README test count", False, "no test-count claim found to check")
    claimed = int(match.group(1))
    if claimed != measured:
        return Check("README test count", False,
                     f"README says {claimed}, the suite reports {measured}")
    return Check("README test count", True, f"{measured}")


def check_readme_decision_count(root: Path) -> Check:
    actual = len(re.findall(r"^## D-\d+", _read(root, "docs/DECISION_LOG.md"), re.MULTILINE))
    match = re.search(r"is (\d+) decisions", _read(root, "README.md"))
    if not match:
        return Check("README decision count", False, "no decision-count claim found")
    claimed = int(match.group(1))
    if claimed != actual:
        return Check("README decision count", False,
                     f"README says {claimed}, DECISION_LOG has {actual}")
    return Check("README decision count", True, f"{actual}")


def check_changelog(root: Path, version: str) -> Check:
    """The version must have its own section, and nothing may still be pending.

    The first version of this only asked whether a section for the current
    version existed. That passed while every new feature sat under
    "Unreleased" against an already-published version number -- which is
    precisely the mistake it was written to catch. An unreleased section with
    content at release time means the bump never happened.
    """
    text = _read(root, "CHANGELOG.md")

    pending = re.search(r"^## Unreleased\s*$(.*?)(?=^## |\Z)", text,
                        re.MULTILINE | re.DOTALL)
    if pending and pending.group(1).strip(" \n-—\t"):
        return Check("CHANGELOG entry", False,
                     "work still sits under Unreleased — bump the version first")

    if re.search(rf"^## {re.escape(version)}\b", text, re.MULTILINE):
        return Check("CHANGELOG entry", True, f"{version} has a section")
    return Check("CHANGELOG entry", False, f"no section for {version}")


def check_no_personal_details(root: Path) -> Check:
    """Run the detector over every tracked file, with no exclusions."""
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=root,
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("no personal details", False, f"could not list tracked files ({exc})")
    if listed.returncode != 0:
        return Check("no personal details", False, "git ls-files failed")

    hits = []
    for rel in listed.stdout.split("\n"):
        rel = rel.strip()
        if not rel or rel in DETECTOR_EXEMPT:
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if PERSONAL_PATTERNS.search(line):
                hits.append(f"{rel}:{number}")
    if hits:
        return Check("no personal details", False,
                     f"{len(hits)} hit(s): {', '.join(hits[:3])}")
    return Check("no personal details", True, "clean across all tracked files")


def check_working_tree(root: Path) -> Check:
    try:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("working tree clean", False, f"could not read git status ({exc})")
    dirty = [l for l in status.stdout.split("\n") if l.strip()]
    if dirty:
        return Check("working tree clean", False, f"{len(dirty)} uncommitted change(s)")
    return Check("working tree clean", True, "nothing uncommitted")


def check_wheel_excludes_internal(root: Path) -> Check:
    match = re.search(r"\[tool\.hatch\.build\.targets\.wheel\].*?packages\s*=\s*\[(.*?)\]",
                      _read(root, "pyproject.toml"), re.DOTALL)
    if not match:
        return Check("wheel contents", False, "no wheel packages list found")
    body = match.group(1)
    leaked = [name for name in ("helix_ops", "helix_api") if name in body]
    if leaked:
        return Check("wheel contents", False, f"{', '.join(leaked)} would ship")
    return Check("wheel contents", True, "internal packages excluded")


def run_all(root: Path | None = None, measured: int | None = None) -> list:
    """Every check. ``measured`` is the real pass count; if None the suite runs."""
    root = root or REPO_ROOT
    if measured is None:
        measured = measure_tests(root)

    version_check = check_versions(root)
    version = version_check.detail if version_check.ok else ""
    return [
        version_check,
        check_readme_test_count(root, measured),
        check_readme_decision_count(root),
        check_changelog(root, version) if version else
        Check("CHANGELOG entry", False, "version unknown, cannot check"),
        check_no_personal_details(root),
        check_wheel_excludes_internal(root),
        check_working_tree(root),
    ]
