"""
`python auto.py` from the repository root.

Same launcher as `ops.py` and `mine.py`, for the same reason: a command that
begins with PYTHONPATH=src is one somebody will eventually run without it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from helix_auto.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
