"""
Runs the legacy sandbox scripts as a single pytest case each.

These fifteen scripts predate this repository's pytest setup: they are
top-to-bottom narratives with prints and asserts, written to be read as much
as run. Rewriting them as pytest functions would lose that — the prints are
how a run is checked by eye — so they are executed as subprocesses instead
and judged on exit code.

They are excluded from normal collection (see `addopts` in pyproject.toml) so
they run exactly once, here, rather than being half-collected as modules.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SANDBOX_DIR = Path(__file__).parent / "sandbox"
REPO_ROOT = Path(__file__).parent.parent

# Needs a live PostgreSQL 16 + pgvector instance, which is not part of the
# default developer setup. Skipped rather than failed so a red suite always
# means a real regression.
REQUIRES_POSTGRES = {"test_database_sandbox.py"}

SCRIPTS = sorted(p.name for p in SANDBOX_DIR.glob("test_*.py"))


@pytest.mark.parametrize("script", SCRIPTS)
def test_sandbox_script(script):
    if script in REQUIRES_POSTGRES:
        pytest.skip("needs a running PostgreSQL 16 + pgvector instance")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([
        str(REPO_ROOT / "src"),
        str(SANDBOX_DIR),          # a few scripts import fixtures from each other
        env.get("PYTHONPATH", ""),
    ])

    result = subprocess.run(
        [sys.executable, str(SANDBOX_DIR / script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )

    if result.returncode != 0:
        # Show the script's own output — it explains the failure far better
        # than an exit code does, which is the whole reason these are prints.
        pytest.fail(
            f"{script} exited {result.returncode}\n\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
