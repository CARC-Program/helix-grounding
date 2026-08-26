"""
`python mine.py` from the repository root.

The same launcher as `ops.py`, for the same reason: `python -m helix_signal.cli`
only works if `src` is already on the path, and every command that starts with
`PYTHONPATH=src` is a command somebody will eventually run without it and get a
confusing ImportError instead of a program.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from helix_signal.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
