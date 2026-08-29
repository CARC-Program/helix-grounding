"""
Proof that reviewing a BOM sends nothing anywhere.

This is the test behind a promise made to users, so it is written to fail
loudly rather than to pass easily. A bill of materials is commercially
sensitive — it exposes a company's design, its costs and its suppliers — and
"trust me, it runs locally" is worth exactly nothing without something that
breaks when it stops being true.

The approach: make the network genuinely unusable, then run the real code
path end to end. Not mocking the modules that *would* make requests, which
only proves those specific modules were not called; disabling the socket
layer underneath everything, so any attempt by any library at any depth is a
hard error.
"""

import socket
from pathlib import Path

import pytest

from helix_bom.agent import BOMReviewAgent, DesignConstraints
from helix_bom.cli import main
from helix_bom.enrich_cli import EXIT_PROBLEMS
from helix_bom.ingest import load_bom
from helix_grounding import ClaimKind, GroundTruth, Verifier
from helix_grounding.domains.bom import ground_truth_for_bom
from helix_grounding.domains.invoice import ground_truth_for_invoice

FIXTURE = "tests/fixtures/altium_with_pricing.csv"
# A BOM whose parts *could* be looked up, unlike FIXTURE's. A keyless run
# staying offline means nothing if there was nothing to look up.
ENRICH_DEMO = str(Path(__file__).parent.parent / "src" / "helix_bom"
                  / "examples" / "enrich_demo.csv")


class NetworkAccessAttempted(AssertionError):
    """Raised instead of letting a connection happen, so a regression shows up
    as this test failing by name rather than as a mysterious timeout."""


@pytest.fixture
def no_network(monkeypatch):
    """Cut the network off at the socket layer for the duration of a test.

    Everything that talks to a network in Python — requests, httpx, urllib,
    the ollama and anthropic clients — ends up here. Blocking socket creation
    and name resolution together covers connection attempts and DNS lookups,
    including the ones that would otherwise fail slowly instead of loudly.
    """
    def blocked(*args, **kwargs):
        raise NetworkAccessAttempted(
            "Something tried to use the network during a local-only operation."
        )

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "gethostbyname", blocked)


def test_the_fixture_itself_proves_the_block_works(no_network):
    """A guard that silently stops guarding is worse than no guard. If this
    ever passes, every other test in this file has become theatre."""
    with pytest.raises(NetworkAccessAttempted):
        socket.socket()
    with pytest.raises(NetworkAccessAttempted):
        socket.getaddrinfo("example.com", 443)


# --------------------------------------------------------------------
# The promise
# --------------------------------------------------------------------

def test_reading_a_bom_sends_nothing(no_network):
    components, report = load_bom(FIXTURE)

    assert len(components) == 5
    assert report.rows_used == 5


def test_reviewing_a_bom_sends_nothing(no_network):
    components, _ = load_bom(FIXTURE)

    result = BOMReviewAgent().review(
        components, DesignConstraints(10.0, 100.0, 80.0, 25.0, 5.0)
    )

    assert result.over_budget is True
    assert any(f.severity == "critical" for f in result.findings)


def test_the_whole_cli_run_sends_nothing(no_network, capsys):
    """The end-to-end version: the exact command a stranger is asked to run
    against their own confidential file."""
    exit_code = main(["review", FIXTURE, "--budget", "10"])
    out = capsys.readouterr().out

    assert exit_code == 1                      # over budget, as expected
    assert "BOM total: $13.81" in out


def test_json_output_sends_nothing(no_network, capsys):
    main(["review", FIXTURE, "--budget", "10", "--json"])

    assert '"over_budget": true' in capsys.readouterr().out


# --------------------------------------------------------------------
# The library itself
# --------------------------------------------------------------------

def test_grounding_verification_sends_nothing(no_network):
    """The central claim of the library — checking a model's output needs no
    model call — is only credible if it needs no *network* call either."""
    truth = GroundTruth().allow_many(ClaimKind.CURRENCY, [18.00, 22.00])

    report = Verifier().verify("It costs $18.00, not $99.00.", truth)

    assert not report.is_grounded
    assert 99.0 in [c.value for c in report.ungrounded]


def test_both_domain_adapters_send_nothing(no_network):
    components, _ = load_bom(FIXTURE)
    ground_truth_for_bom(components)

    class Line:
        description, quantity, unit_price, sku = "Widget", 2, 40.00, ""

    class Invoice:
        number, lines, tax_rate, discount_rate = "INV-1", [Line()], 8.25, 0.0
        issue_date = due_date = paid_date = None
        payment_terms_days = amount_paid = None
        purchase_order = account_number = ""

    ground_truth_for_invoice(Invoice())


def test_the_retry_loop_sends_nothing_when_the_generator_is_local(no_network):
    """generate_validated calls whatever the caller passes. With a local
    callable it must stay entirely offline — the verification half of the
    loop must never be what reaches out."""
    truth = GroundTruth().allow(ClaimKind.CURRENCY, 18.00)
    attempts = []

    def generate(prompt):
        attempts.append(prompt)
        return "It costs $18.00." if len(attempts) > 1 else "It costs $99.00."

    outcome = Verifier().generate_validated(generate, "base", truth)

    assert outcome.validated
    assert outcome.attempts == 2


# --------------------------------------------------------------------
# enrich, which is the command a stranger is asked to run first
# --------------------------------------------------------------------

@pytest.fixture
def a_strangers_machine(tmp_path, monkeypatch):
    """No distributor credentials, and a cache belonging to nobody.

    Both halves carry weight. Without the key removal this passes on a machine
    that happens to have no key configured and fails on one that does, which
    makes it a test of the developer's environment rather than of the code.
    Without the cache redirect a previously cached answer could serve the
    lookup, and the network would go untouched for the wrong reason.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for name in ("MOUSER_API_KEY", "DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


def test_enrich_without_a_key_sends_nothing(no_network, a_strangers_machine,
                                            capsys):
    """`helix-bom enrich <file>` is the first command the README and the
    outreach draft put in front of a stranger, and the sentence beside it
    promises their BOM never leaves the machine. Every other test in this file
    covers `review`; this one covers the command that is actually offered
    first, which is the one the promise is read against.
    """
    exit_code = main(["enrich", ENRICH_DEMO])
    out = capsys.readouterr().out

    assert exit_code == EXIT_PROBLEMS
    # Found in the file alone, with no distributor and no network:
    assert "no manufacturer part number" in out
    assert "2 designator(s) but a quantity of 3" in out
    # And it says why it could not do the rest, rather than implying it did.
    assert "7 of 7 lines were NOT CHECKED" in out


def test_a_key_would_have_reached_the_network(no_network, a_strangers_machine,
                                              monkeypatch):
    """The tripwire for the test above.

    A keyless run touching no network is only evidence if the block sits on the
    path a lookup actually takes. Hand the same command a key and it must reach
    the guard. If this ever stops raising, either enrich has quietly stopped
    looking parts up or the block has drifted off its path -- and in both cases
    the test above has become theatre while still passing.
    """
    monkeypatch.setenv("MOUSER_API_KEY", "not-a-real-key")

    with pytest.raises(NetworkAccessAttempted):
        main(["enrich", ENRICH_DEMO])
