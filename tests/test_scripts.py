"""
The scripts in `scripts/` have to still run.

`export_diagrams.py` did not. It imported `bom_review_agent` and
`visual_diagram_generator` from an `AI_CODE/` folder the 2026-08-14 rebuild
deleted, so it had been crashing on import for four days without anything
noticing. Nothing imported it and nothing ran it — the repository's own test
suite had no opinion about whether its scripts worked.

That is the failure this file closes. A script is a promise that a command in
the README does something, and an untested script is a promise nobody checked.
"""

import importlib.util
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _load(name: str):
    """Import a script by path. They are not a package, and making them one
    to satisfy a test would be the test changing the code to suit itself."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["export_diagrams", "reproduce_d036",
                                  "set_repo_url", "diagnose_env"])
def test_every_script_still_imports(name):
    """The cheapest test that would have caught the rot, and the reason it is
    parametrized over the whole directory rather than the one script that
    broke: the next one to rot will be a different one."""
    assert _load(name) is not None


def test_export_diagrams_writes_two_real_svgs(tmp_path):
    """--out keeps the test out of the repository. Writing into `scripts/`
    during a test run leaves untracked files behind, and a suite that dirties
    the working tree gets ignored."""
    module = _load("export_diagrams")
    assert module.main(["--no-open", "--out", str(tmp_path)]) == 0

    written = sorted(p.name for p in tmp_path.glob("*.svg"))
    assert written == ["interconnect_from_netlist.svg", "placement_blueprint.svg"]
    for path in tmp_path.glob("*.svg"):
        ET.fromstring(path.read_text(encoding="utf-8"))


def test_the_exported_interconnect_is_not_an_empty_canvas(tmp_path):
    """The specific failure this whole line of work started from: a diagram
    that parsed cleanly and drew nothing. Well-formed XML was never the claim
    worth testing."""
    module = _load("export_diagrams")
    module.main(["--no-open", "--out", str(tmp_path)])

    svg = (tmp_path / "interconnect_from_netlist.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    boxes = [el for el in root if el.tag.endswith("rect") and el.get("x") is not None]
    lines = [el for el in root if el.tag.endswith("line")]

    assert len(boxes) >= 4, "fewer component boxes than the fixture has parts"
    assert lines, "no connections drawn"
    assert all(float(el.get("width")) > 0 for el in boxes), "zero-width boxes"


def test_the_ops_launcher_works_without_an_install(tmp_path):
    """`python -m helix_ops.cli` fails on a fresh checkout, and did so for the
    first person who was not its author.

    helix_ops is deliberately absent from the published wheel, so it is only
    importable when src/ is already on the path -- true in a checkout with an
    editable install, false everywhere else. The instruction in the docs was
    therefore only ever correct on the machine it was written on.

    This runs the launcher as a subprocess with PYTHONPATH stripped and the
    working directory elsewhere, which is the only arrangement that would have
    caught it.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS.parent / "ops.py"), "status"],
        cwd=tmp_path, capture_output=True, text=True, timeout=180, env=env,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "prerequisites:" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
