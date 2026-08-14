"""
The D-036 reproduction is evidence shown to strangers, so it is tested like
code rather than left as prose that quietly stops being true.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_the_published_reproduction_still_reproduces():
    """`scripts/reproduce_d036.py` exits non-zero if either error stops
    behaving as the case study describes: the backwards comparison passing
    the grounding check, and the fabricated $3.40 failing it."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "reproduce_d036.py")],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reproduction confirmed" in result.stdout
