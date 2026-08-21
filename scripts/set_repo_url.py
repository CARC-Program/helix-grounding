"""
Point every URL in the project at the repository, in one pass.

Originally written to replace a placeholder owner, which no longer exists --
the URLs are real now. What it is still for is the move that breaks
everything: renaming the account or the repository. Those URLs are the
Homepage and Source buttons on the PyPI page, and they live in four files, so
changing them by hand means missing one and shipping a dead link.

    python scripts/set_repo_url.py <github-owner>

<github-owner> is the user or organisation the repo lives under -- the part
between github.com/ and /helix-grounding. The current owner is detected from
pyproject.toml rather than hardcoded, so this keeps working after the first
rename instead of silently doing nothing.
"""

import pathlib
import re
import sys

# docs/PUBLISHING.md is deliberately absent: it is an internal checklist and is
# not published with the repository. Missing entries are skipped rather than
# fatal, so this keeps working for a checkout that does have it.
FILES = ["pyproject.toml", "README.md", "docs/FIRST_USERS.md",
         "private/PUBLISHING.md"]
OWNER_PATTERN = re.compile(r"github\.com/([A-Za-z0-9-]+)/helix-grounding")


def current_owner(root: pathlib.Path) -> str:
    """Read the owner out of pyproject rather than assuming it.

    The previous version matched a hardcoded placeholder. Once that placeholder
    was replaced the script still ran, still reported success, and changed
    nothing -- the failure mode this project keeps finding, where a tool is
    honest about what it did and silent about having done nothing useful.
    """
    match = OWNER_PATTERN.search((root / "pyproject.toml").read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("pyproject.toml has no github.com/<owner>/helix-grounding URL")
    return match.group(1)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    owner = argv[1].strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}", owner):
        # GitHub's own rule: alphanumerics and single hyphens, max 39 chars.
        # Catching it here beats discovering it in a 404 after publishing.
        print(f"'{owner}' is not a valid GitHub owner name.")
        return 2

    root = pathlib.Path(__file__).parent.parent
    placeholder = f"github.com/{current_owner(root)}/"
    if placeholder == f"github.com/{owner}/":
        print(f"Already pointing at {owner}. Nothing to do.")
        return 0

    print(f"Rewriting {placeholder} -> github.com/{owner}/")
    changed = 0
    for name in FILES:
        path = root / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if placeholder not in text:
            continue
        path.write_text(text.replace(placeholder, f"github.com/{owner}/"), encoding="utf-8")
        print(f"  updated {name}")
        changed += 1

    if not changed:
        print("Nothing changed -- no file contained that owner.")
        return 0

    print(f"\nDone. Verify with:  grep -rn 'github.com' pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
