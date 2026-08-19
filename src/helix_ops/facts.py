"""
What is true about this project right now, computed from the repository.

Every outreach post makes claims: a version number, an install command, how
many tests pass, what file formats it reads. Those claims decay. A post
written on Tuesday and published on Friday can already be wrong, and being
publicly wrong about your own tool in the first thing a stranger reads about
it is expensive in a way that is hard to undo.

So no draft in this package contains a hand-typed number. Facts are gathered
here, from the files that define them, and `drafts.py` refuses to render a
post whose claims are not in this object.

One rule carried over from the review agent, because it is the same mistake in
a different suit: **a test count that was not measured is `None`, not a
guess.** `helix-bom` learned not to report an unrun check as a pass. A launch
post claiming "255 tests pass" because that was true last week is the same
error aimed at a larger audience.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class ProjectFacts:
    """The claims a post is allowed to make, and where each came from."""

    package: str
    version: str
    repo_url: str
    runtime_dependencies: int
    input_formats: tuple = ()
    commands: tuple = ()
    # None means "not measured on this run". It is never 0 and never stale --
    # a draft that wants to state a number gets refused instead.
    tests_passing: int | None = None
    sources: dict = field(default_factory=dict)

    @property
    def install_command(self) -> str:
        return f"pip install {self.package}"

    def describe(self) -> str:
        lines = [
            f"package                {self.package} {self.version}",
            f"repository             {self.repo_url}",
            f"runtime dependencies   {self.runtime_dependencies}",
            f"input formats          {', '.join(self.input_formats) or 'none found'}",
            f"CLI commands           {', '.join(self.commands) or 'none found'}",
        ]
        lines.append(
            f"tests passing          {self.tests_passing}"
            if self.tests_passing is not None
            else "tests passing          not measured on this run"
        )
        return "\n".join(lines)


def _read_pyproject(root: Path) -> str:
    return (root / "pyproject.toml").read_text(encoding="utf-8")


def _version(text: str) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("pyproject.toml has no version field")
    return match.group(1)


def _package(text: str) -> str:
    match = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("pyproject.toml has no name field")
    return match.group(1)


def _repo_url(text: str) -> str:
    match = re.search(r'^Source\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else ""


def _runtime_dependency_count(text: str) -> int:
    """Count `dependencies = [...]` only.

    Deliberately not the optional-dependency groups. "Zero runtime
    dependencies" is the library's central claim and the thing a reader will
    check first, so the number behind it has to mean exactly what the sentence
    says -- not "zero unless you count the extras", which is how a true
    statement becomes a misleading one.
    """
    match = re.search(r'^dependencies\s*=\s*\[(.*?)\]', text, re.MULTILINE | re.DOTALL)
    if not match:
        return 0
    body = match.group(1).strip()
    return len([item for item in body.split(",") if item.strip()])


def _input_formats(root: Path) -> tuple:
    """What the tool demonstrably reads, taken from the fixtures.

    Fixtures rather than a written list, because a fixture is exercised by the
    suite. A list in a docstring is exercised by nobody, which is how a README
    ends up advertising a format that stopped working.
    """
    fixtures = root / "tests" / "fixtures"
    if not fixtures.is_dir():
        return ()
    suffixes = {path.suffix.lower() for path in fixtures.iterdir() if path.is_file()}
    return tuple(sorted(suffixes))


def _commands(root: Path) -> tuple:
    """The CLI's own declaration, imported rather than transcribed."""
    sys.path.insert(0, str(root / "src"))
    try:
        from helix_bom.cli import COMMANDS
        return tuple(COMMANDS)
    except ImportError:
        return ()


def measure_tests(root: Path | None = None, pytest_args: list | None = None) -> int:
    """Run the suite and return how many passed.

    A subprocess rather than an in-process call, because pytest inside pytest
    shares state in ways that make the number untrustworthy -- and an
    untrustworthy number here is worse than no number, since the whole purpose
    of this function is to be quotable in public.
    """
    root = root or REPO_ROOT
    command = [sys.executable, "-m", "pytest", "-q"] + list(pytest_args or [])
    completed = subprocess.run(
        command, cwd=root, capture_output=True, text=True, timeout=600
    )
    # Exit code first, deliberately. When every test fails there is no
    # "N passed" line at all, so parsing first reports "could not read the
    # output" -- which is true, and sends the reader to debug their pytest
    # invocation instead of their failing tests. An accurate refusal with a
    # misleading reason is its own bug.
    if completed.returncode != 0:
        raise RuntimeError(
            f"the suite did not pass (exit {completed.returncode}). Nothing "
            f"should be posted about a project whose tests are failing. "
            f"Last lines:\n" + "\n".join(completed.stdout.splitlines()[-5:])
        )
    match = re.search(r"(\d+) passed", completed.stdout)
    if not match:
        raise RuntimeError(
            "the suite passed but printed no count -- refusing to guess at "
            "a number that is going into a public post. Last lines:\n"
            + "\n".join(completed.stdout.splitlines()[-5:])
        )
    return int(match.group(1))


def gather(root: Path | None = None, run_tests: bool = False,
           pytest_args: list | None = None) -> ProjectFacts:
    """Read the repository and return what can be claimed about it.

    ``run_tests`` is off by default and costs a full suite run when on. That
    asymmetry is intentional: gathering facts should be cheap enough that
    nobody is tempted to skip it, and the one expensive fact is the one nobody
    should quote without measuring.
    """
    root = root or REPO_ROOT
    text = _read_pyproject(root)

    return ProjectFacts(
        package=_package(text),
        version=_version(text),
        repo_url=_repo_url(text),
        runtime_dependencies=_runtime_dependency_count(text),
        input_formats=_input_formats(root),
        commands=_commands(root),
        tests_passing=measure_tests(root, pytest_args) if run_tests else None,
        sources={
            "package": "pyproject.toml [project].name",
            "version": "pyproject.toml [project].version",
            "repo_url": "pyproject.toml [project.urls].Source",
            "runtime_dependencies": "pyproject.toml [project].dependencies",
            "input_formats": "tests/fixtures/*",
            "commands": "helix_bom.cli.COMMANDS",
            "tests_passing": "pytest -q" if run_tests else "not measured",
        },
    )
