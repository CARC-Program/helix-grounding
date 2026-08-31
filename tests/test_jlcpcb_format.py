"""
A JLCPCB assembly BOM is a valid, complete file. This proves it reads as one.

Why this file exists. JLCPCB is the commonest small-run assembly service in
exactly the communities this tool is shown to, and its BOM carries Comment,
Designator, Footprint and an LCSC code, with **no quantity column and no
manufacturer part number**. Against that file the tool used to report seven
findings and every one of them was wrong:

  * five CRITICAL "no manufacturer part number", because the LCSC column was
    not recognised at all;
  * two designator/quantity warnings, because the absent quantity defaulted
    to 1 and was then compared against the designator list.

It also printed "no distributor can quote them either", which is false: LCSC
quotes them, which is the entire point of the file.

The failure was found by constructing the format from JLCPCB's own published
requirements and running it, not by reading the code.
"""

from pathlib import Path

import pytest

from helix_bom.cli import main
from helix_bom.enrich import enrich
from helix_bom.enrich_cli import EXIT_OK
from helix_bom.ingest import load_bom
from helix_bom.structure import check as structural_check

FIXTURE = str(Path(__file__).parent / "fixtures" / "jlcpcb_assembly.csv")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for name in ("MOUSER_API_KEY", "DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------
# Reading the file
# --------------------------------------------------------------------

def test_the_lcsc_column_is_recognised():
    components, _ = load_bom(FIXTURE)

    codes = [c.distributor_part_number for c in components]

    assert codes == ["C25804", "C14663", "C92489", "C2894570", "C165948"]
    assert all(not c.manufacturer_part_number for c in components)


def test_quantity_comes_from_the_designators_when_there_is_no_column():
    """A JLCPCB BOM states quantity by listing designators, which is how every
    assembler reads it. Defaulting to 1 made a four-capacitor line cost a
    quarter of what it costs."""
    components, report = load_bom(FIXTURE)
    by_ref = {c.designator: c for c in components}

    assert by_ref["R1,R2,R3"].quantity == 3
    assert by_ref["C1,C2,C3,C4"].quantity == 4
    assert by_ref["U1"].quantity == 1
    assert all(not c.quantity_stated for c in components)
    assert "quantity" in report.missing_fields


def test_a_file_that_states_quantity_is_still_believed():
    """The derivation must not start overriding a stated number."""
    components, _ = load_bom(
        str(Path(__file__).parent.parent / "src" / "helix_bom" / "examples"
            / "enrich_demo.csv"))

    assert all(c.quantity_stated for c in components)


# --------------------------------------------------------------------
# What it says about the file
# --------------------------------------------------------------------

def test_a_valid_jlcpcb_bom_produces_no_critical_findings():
    """The whole bug in one assertion."""
    components, _ = load_bom(FIXTURE)

    findings = structural_check(components)

    assert not [f for f in findings if f.severity == "critical"]
    assert not [f for f in findings if f.severity == "warning"]


def test_the_designator_check_stands_down_when_quantity_was_not_stated():
    components, _ = load_bom(FIXTURE)

    messages = [f.message for f in structural_check(components)]

    assert not [m for m in messages if "designator(s) but a quantity of" in m]


def test_the_designator_check_still_fires_when_quantity_was_stated(tmp_path):
    """The other half. Standing down on a missing column must not become
    standing down generally, or a real mismatch stops being caught."""
    bom = tmp_path / "stated.csv"
    bom.write_text(
        "Designator,Description,Quantity,Manufacturer Part Number\n"
        '"R1, R2, R3",Resistor,2,RC0603FR-0710KL\n', encoding="utf-8")
    components, _ = load_bom(str(bom))

    messages = [f.message for f in structural_check(components)]

    assert any("3 designator(s) but a quantity of 2" in m for m in messages)


def test_a_distributor_code_is_reported_but_not_as_a_defect():
    components, _ = load_bom(FIXTURE)

    notes = [f for f in structural_check(components) if f.severity == "info"]

    assert len(notes) == 5
    assert all("distributor code" in f.message for f in notes)
    assert any("C25804" in f.evidence for f in notes)


# --------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------

def test_the_command_exits_clean_on_a_valid_jlcpcb_bom(capsys):
    code = main(["enrich", FIXTURE])

    assert code == EXIT_OK


def test_the_report_never_claims_nobody_can_quote_a_distributor_line(capsys):
    """It said exactly that, on every line, about parts LCSC sells from
    stock. A tool that states something false about a good file has done
    worse than miss a problem."""
    main(["enrich", FIXTURE])
    text = capsys.readouterr().out

    assert "no distributor can quote them" not in text
    assert "carry no part number of any kind" not in text
    assert "ordered by a distributor code" in text


def test_the_lookup_reason_does_not_say_there_is_nothing_to_look_up():
    """There is something to look up. It is simply not resolvable by a
    manufacturer part number search, which is a different sentence."""
    components, _ = load_bom(FIXTURE)

    report = enrich(components, [])
    reasons = report.reasons_not_checked()

    assert not any("nothing to look up" in reason for reason in reasons)
    assert any("distributor code" in reason for reason in reasons)
