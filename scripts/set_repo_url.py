"""
Point every URL in the project at the real repository.

The placeholders exist because the GitHub username was not known when the
packaging was written, and dead links on a PyPI page read as an abandoned
project. Run this once, then never again.

    python scripts/set_repo_url.py <github-owner>

<github-owner> is the user or organisation the repo lives under -- the part
between github.com/ and /helix-grounding.
"""

import pathlib
import re
import sys

PLACEHOLDER = "github.com/bobby/"
FILES = ["pyproject.toml", "README.md", "docs/PUBLISHING.md", "docs/FIRST_USERS.md"]


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
    changed = 0
    for name in FILES:
        path = root / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            continue
        path.write_text(text.replace(PLACEHOLDER, f"github.com/{owner}/"), encoding="utf-8")
        print(f"  updated {name}")
        changed += 1

    if not changed:
        print("Nothing to change -- no placeholder URLs left.")
        return 0

    print(f"\nDone. Verify with:  grep -rn 'github.com' pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
