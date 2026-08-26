#!/usr/bin/env python
"""
Launcher for the operations console:  python ops.py status

`helix_ops` is deliberately not in the published wheel -- it runs this
business, not a user's board, and nobody installing a verification library
should receive a launch tracker. The cost of that decision is that
`python -m helix_ops.cli` only works if `src/` happens to be on the path,
which is true in a checkout with an editable install and false everywhere
else.

That failed the first time somebody who was not me typed the command, which is
the only test of an instruction that counts. This file removes the question:
it works from a fresh clone, with no install, no PYTHONPATH, and no editable
mode.

It must stay dependency-free and import nothing before the path is set.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from helix_ops.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
