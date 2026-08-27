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

# The detector, split in two, because the first version of it published the
# thing it was built to hide.
#
# It used to hold the operator's real name as a regex literal, right here. That
# made this file a file naming a real person -- in a public repository, and in
# every published sdist, because the sdist ships `src/` whole while the wheel
# does not. The detector reported clean throughout, because this file is on its
# own exemption list. A whole history rewrite had been done to remove those
# names, and the tool doing the checking was carrying them.
#
# So the identifying half now lives outside the repository, and the generic
# half stays here. The generic words name no one: they are worth catching
# because they describe a situation, not a person.
IDENTITY_FILE = Path(__file__).resolve().parent.parent.parent / "private" / "identity.txt"

GENERIC_PATTERNS = (
    r"legal guardian", r"\bguardians?\b", r"\bminors?\b", r"\bunder 18\b",
    r"allows 13\+", r"age 13", r"16-year", r"\bteenager\b",
)


def _identity_pattern(identity_file=None):
    """Just the names, compiled. Returns ``(pattern, count)``.

    ``count`` of zero means the list was not found, and every caller treats
    that as a failure rather than a pass -- a name scanner with no names is a
    check that cannot run.
    """
    path = Path(identity_file) if identity_file else IDENTITY_FILE
    names = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(re.escape(line))
    if not names:
        return re.compile(r"(?!x)x"), 0     # matches nothing
    return re.compile("|".join(names), re.IGNORECASE), len(names)


def load_personal_patterns(identity_file=None):
    """The full detector: generic terms, plus names read from outside the repo.

    Returns ``(pattern, sources_found)``. When the identity file is absent the
    check still runs on the generic half and ``sources_found`` is 0 -- and the
    caller says so out loud, because a detector running at half strength while
    reporting a pass is the failure this whole module exists to prevent.
    """
    path = Path(identity_file) if identity_file else IDENTITY_FILE
    terms = list(GENERIC_PATTERNS)
    found = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            terms.append(re.escape(line))
            found += 1
    return re.compile("|".join(terms), re.IGNORECASE), found


PERSONAL_PATTERNS, _IDENTITY_TERMS = load_personal_patterns()

# Files that necessarily contain the words, because their job is to describe or
# to test for them. `release.py` holds the pattern; `test_release.py` plants a
# name to prove the detector catches one.
#
# This set is the weak point of the whole check and is meant to stay at two
# entries. Every name added here is a file the gate stops looking at, and the
# last detector failed for exactly that reason -- it excluded a folder, and the
# thing it was built to find was sitting in it.
DETECTOR_EXEMPT = {
    "src/helix_ops/release.py",
    "tests/test_release.py",
}


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


def check_exempt_files_name_nobody(root: Path) -> Check:
    """The exempted files must contain the generic words and never a name.

    This is the check that would have stopped a real name going to PyPI. Two
    files are exempt from the detector because their job is to hold and to test
    the words -- and an exemption is a place the gate stops looking, so the
    thing that actually matters gets looked for here instead. The names are read
    from outside the repository; if that file is missing this check cannot run,
    and at release time a check that cannot run is a failure.
    """
    names, terms = _identity_pattern()
    if not terms:
        return Check("exempt files clean", False,
                     f"no identity list at {IDENTITY_FILE.name} -- cannot verify "
                     f"the exempt files name nobody")

    hits = []
    for rel in sorted(DETECTOR_EXEMPT):
        path = root / rel
        if not path.exists():
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if names.search(line):
                hits.append(f"{rel}:{number}")
    if hits:
        return Check("exempt files clean", False,
                     f"a real name sits in an exempted file: {', '.join(hits[:3])}")
    return Check("exempt files clean", True,
                 f"{len(DETECTOR_EXEMPT)} exempt file(s) name nobody")


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
    # Every internal package, named explicitly. A new one that nobody adds
    # here ships silently, which is how helix_signal would have gone out.
    leaked = [name for name in ("helix_ops", "helix_api", "helix_signal")
              if name in body]
    if leaked:
        return Check("wheel contents", False, f"{', '.join(leaked)} would ship")
    return Check("wheel contents", True, "internal packages excluded")


def check_history_names(root: Path | None = None, max_bytes: int = 80_000_000) -> Check:
    """Scan every object in git history for an identifying name.

    The third place the gate did not look. `check_no_personal_details` reads the
    working tree, `check_built_artifacts` reads what would be uploaded, and
    until this existed nothing read *history* — where a name survives long after
    it is deleted from HEAD, and where the fix costs a rewrite and a
    force-push instead of an edit.

    That is not hypothetical. A name sat in nine blob versions of this very
    file, in a public repository, while the tree scan reported clean because
    this file is on its own exemption list. Removing it took a `filter-repo`
    run, a force-push, and a repository deletion, because GitHub keeps
    unreachable objects fetchable by SHA.

    Also catches what the rewrite itself nearly missed: a stale branch keeping
    an old root alive. `refs/heads/master` was still pointing at a commit
    authored from a personal email address, three rewrites after that address
    was supposed to be gone.

    Scans blobs, commit messages, author and committer identities, and tag
    taggers. Bounded by ``max_bytes``; if the bound is hit the check fails
    rather than reporting a clean partial scan.
    """
    root = root or REPO_ROOT
    names, terms = _identity_pattern()
    if not terms:
        return Check("history clean", False,
                     f"no identity list at {IDENTITY_FILE.name} -- cannot scan history")

    def git(args, binary=False):
        return subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=not binary, errors="replace" if not binary else None,
                              timeout=300)

    # Identities and messages, across every ref.
    try:
        log = git(["log", "--all", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x00END"])
        refs = git(["for-each-ref", "--format=%(refname)%00%(taggername)%00%(taggeremail)"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("history clean", False, f"could not read history ({exc})")
    if log.returncode != 0:
        return Check("history clean", False, "git log failed")

    hits = []
    for entry in log.stdout.split("\x00END"):
        parts = entry.strip("\n").split("\x00")
        if len(parts) < 6:
            continue
        for value in parts[1:6]:
            if names.search(value or ""):
                hits.append(f"commit {parts[0][:9]}")
                break
    for line in refs.stdout.splitlines():
        if names.search(line):
            hits.append(f"ref {line.split(chr(0))[0]}")

    # Every object ever stored, streamed in one pass.
    try:
        blobs = subprocess.run(
            ["git", "cat-file", "--batch-all-objects", "--batch", "--buffer"],
            cwd=root, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("history clean", False, f"could not read objects ({exc})")

    raw = blobs.stdout
    if len(raw) > max_bytes:
        return Check("history clean", False,
                     f"history is larger than the {max_bytes // 1_000_000}MB scan "
                     f"bound -- raise max_bytes rather than trusting a partial scan")
    text = raw.decode("utf-8", errors="replace")
    scanned = text.count("\n")
    for match in names.finditer(text):
        hits.append(f"object content at offset {match.start()}")
        break       # one is enough; the rewrite is the same either way

    if hits:
        return Check("history clean", False,
                     f"{len(hits)} place(s) in history name somebody: "
                     f"{', '.join(hits[:3])} -- this needs a rewrite, not an edit")
    return Check("history clean", True,
                 f"{scanned} line(s) of history scanned, nobody named")


def check_built_artifacts(root: Path | None = None) -> Check:
    """Scan what would actually be uploaded, not what is in the tree.

    Every other check here reads the working tree, and the working tree is not
    what gets published. The wheel excludes the internal packages; the sdist
    ships ``src/`` and ``tests/`` whole, so it carried `helix_ops` and
    `helix_signal` and — until this was found — a real name inside one of them.

    A blind spot in exactly the place the gate exists to guard. This opens the
    files that would go to PyPI and reads them.
    """
    root = root or REPO_ROOT
    dist = root / "dist"
    if not dist.exists():
        return Check("built artifacts", True, "nothing built yet, nothing to check")

    # Names only, not the generic terms. The invariant that must hold for
    # anything published is "this names nobody"; the generic words are a
    # working-tree concern where DETECTOR_EXEMPT applies, and scanning for them
    # here would fail on the very test fixture that proves the detector works.
    pattern, terms = _identity_pattern()
    artifacts = sorted(list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz")))
    if not artifacts:
        return Check("built artifacts", True, "dist/ is empty")
    if not terms:
        return Check("built artifacts", False,
                     f"no identity list at {IDENTITY_FILE.name} -- cannot scan "
                     f"what would be uploaded")

    hits, internal = [], set()
    for artifact in artifacts:
        for name, text in _artifact_files(artifact):
            leaf = name.split("/", 1)[-1] if artifact.suffix == ".gz" else name
            for package in ("helix_ops", "helix_api", "helix_signal"):
                if f"{package}/" in leaf and artifact.suffix != ".gz":
                    internal.add(f"{package} in {artifact.name}")
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{artifact.name}:{leaf}:{number}")
    if hits:
        return Check("built artifacts", False,
                     f"{len(hits)} personal-detail hit(s) in what would be "
                     f"uploaded: {', '.join(hits[:3])}")
    if internal:
        return Check("built artifacts", False,
                     f"internal package(s) would ship: {', '.join(sorted(internal))}")
    return Check("built artifacts", True,
                 f"{len(artifacts)} artifact(s) scanned, no names, no internals")


def _artifact_files(path: Path):
    """Yield ``(name, text_or_None)`` for every file inside a wheel or sdist."""
    import tarfile
    import zipfile

    readable = (".py", ".md", ".txt", ".toml", ".cfg", ".csv", ".json", ".net")
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                yield name, (_decode(archive.read(name))
                             if name.endswith(readable) else None)
    else:
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                handle = archive.extractfile(member)
                yield member.name, (_decode(handle.read())
                                    if handle and member.name.endswith(readable)
                                    else None)


def _decode(raw: bytes):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


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
        check_exempt_files_name_nobody(root),
        check_history_names(root),
        check_wheel_excludes_internal(root),
        check_built_artifacts(root),
        check_working_tree(root),
    ]
