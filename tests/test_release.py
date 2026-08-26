"""
Tests for the release gate.

A release is the only operation here that cannot be taken back: PyPI refuses a
re-upload of the same version, mirrors copy within hours, and the first thing a
stranger installs is the thing they judge the project by. So every check in
`release.py` is tested against a repository deliberately broken in that one
way — a check nobody has watched fail is a check nobody should trust.

Each fixture below reproduces a mistake this project actually made.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from helix_ops import release
from helix_ops.release import (
    check_changelog,
    check_no_personal_details,
    check_readme_decision_count,
    check_readme_test_count,
    check_versions,
    check_wheel_excludes_internal,
)

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def fake_repo(tmp_path):
    """A minimal repository with everything correct, for tests to break."""
    (tmp_path / "src" / "helix_grounding").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        'name = "helix-grounding"\nversion = "1.2.3"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        'packages = ["src/helix_grounding", "src/helix_bom"]\n',
        encoding="utf-8")
    (tmp_path / "src" / "helix_grounding" / "__init__.py").write_text(
        '__version__ = "1.2.3"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "42 tests, nothing skipped, no database and no services required.\n"
        "`docs/DECISION_LOG.md` is 2 decisions with the reasoning attached.\n",
        encoding="utf-8")
    (tmp_path / "docs" / "DECISION_LOG.md").write_text(
        "## D-001 — first\n\n## D-002 — second\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.2.3 — 2026-01-01\n\nThings.\n", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------
# Each check, watched failing
# --------------------------------------------------------------------

def test_a_correct_repo_passes_everything(fake_repo):
    """The baseline. Without it, a check that always fails looks rigorous."""
    for check in (check_versions(fake_repo),
                  check_readme_test_count(fake_repo, 42),
                  check_readme_decision_count(fake_repo),
                  check_changelog(fake_repo, "1.2.3"),
                  check_wheel_excludes_internal(fake_repo)):
        assert check.ok, check.line()


def test_a_version_that_drifted_is_caught(fake_repo):
    """`helix_grounding.__version__` said 0.1.0 while the wheel shipped 0.1.1."""
    (fake_repo / "src" / "helix_grounding" / "__init__.py").write_text(
        '__version__ = "1.2.2"\n', encoding="utf-8")
    check = check_versions(fake_repo)
    assert not check.ok
    assert "1.2.3" in check.detail and "1.2.2" in check.detail


def test_a_stale_readme_test_count_is_caught(fake_repo):
    """This went stale three times: 190, then 292, against 292 and 316."""
    check = check_readme_test_count(fake_repo, 99)
    assert not check.ok
    assert "README says 42" in check.detail


def test_a_missing_test_claim_is_a_failure_not_a_pass(fake_repo):
    """Nothing to check is not the same as nothing wrong. If the claim cannot
    be found, the check has not run, and at release time that is a failure."""
    (fake_repo / "README.md").write_text("no numbers here\n", encoding="utf-8")
    assert not check_readme_test_count(fake_repo, 42).ok


def test_a_stale_decision_count_is_caught(fake_repo):
    (fake_repo / "docs" / "DECISION_LOG.md").write_text(
        "## D-001 — a\n\n## D-002 — b\n\n## D-003 — c\n", encoding="utf-8")
    check = check_readme_decision_count(fake_repo)
    assert not check.ok
    assert "README says 2" in check.detail


def test_work_left_under_unreleased_is_caught(fake_repo):
    """The mistake the first version of this check missed: it asked only
    whether a section for the current version existed, and passed while every
    new feature sat under Unreleased against an already-published number."""
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n### Added\n\nA new thing.\n\n"
        "## 1.2.3 — 2026-01-01\n\nThings.\n", encoding="utf-8")
    check = check_changelog(fake_repo, "1.2.3")
    assert not check.ok
    assert "Unreleased" in check.detail


def test_an_empty_unreleased_heading_is_not_a_failure(fake_repo):
    """A left-behind empty heading is untidy, not a reason to block a release.
    Failing on it would train somebody to pass --force out of habit."""
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n## 1.2.3 — 2026-01-01\n\nThings.\n",
        encoding="utf-8")
    assert check_changelog(fake_repo, "1.2.3").ok


def test_a_missing_version_section_is_caught(fake_repo):
    assert not check_changelog(fake_repo, "9.9.9").ok


def test_internal_packages_leaking_into_the_wheel_are_caught(fake_repo):
    """Nobody installing a verification library should receive a launch
    tracker or an undeployed API skeleton."""
    (fake_repo / "pyproject.toml").write_text(
        'version = "1.2.3"\n\n[tool.hatch.build.targets.wheel]\n'
        'packages = ["src/helix_grounding", "src/helix_ops"]\n', encoding="utf-8")
    check = check_wheel_excludes_internal(fake_repo)
    assert not check.ok
    assert "helix_ops" in check.detail


def test_every_internal_package_is_named_in_the_wheel_check():
    """A new internal package that nobody adds to the check ships silently.
    helix_signal was created after this check was written and would have gone
    out in the wheel had the list not been updated with it."""
    import inspect
    from helix_ops import release as release_module
    source = inspect.getsource(release_module.check_wheel_excludes_internal)
    for name in ("helix_ops", "helix_api", "helix_signal"):
        assert name in source, f"{name} is not checked for"


# --------------------------------------------------------------------
# The detector
# --------------------------------------------------------------------

def test_the_detector_finds_a_planted_name(tmp_path):
    """Proven by planting one, because the previous detector excluded the
    folder that held the problem and reported clean. A detector nobody has
    watched catch something is decoration."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "notes.md").write_text(
        "the account owner is fine\nbut a legal guardian is not\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    check = check_no_personal_details(tmp_path)
    assert not check.ok
    assert "notes.md:2" in check.detail


def test_the_detector_passes_a_clean_tree(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "notes.md").write_text("nothing to see\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert check_no_personal_details(tmp_path).ok


def test_the_detector_covers_untracked_free_but_not_ignored_files(tmp_path):
    """It reads `git ls-files`, so it sees exactly what would be published --
    which is the only set that matters. A file git does not track cannot reach
    a stranger."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "notes.md").write_text("a legal guardian\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("private/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert check_no_personal_details(tmp_path).ok


def test_this_repository_currently_passes_the_detector():
    """The real one, over the real tree."""
    assert check_no_personal_details(REPO_ROOT).ok


def test_the_exemption_list_stays_tiny():
    """The exemption list is the weak point of the whole check: every entry is
    a file the gate stops looking at. The previous detector failed for exactly
    that reason, excluding a folder that held the thing it was built to find.

    Two files legitimately name the words -- the one holding the pattern and
    the one planting a name to prove it works. A third should have to justify
    itself by breaking this test."""
    assert release.DETECTOR_EXEMPT == {
        "src/helix_ops/release.py",
        "tests/test_release.py",
    }
