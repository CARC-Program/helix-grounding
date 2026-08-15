"""
Tests for API key authentication.

The properties here are security properties, so they are tested directly
rather than left to incidental coverage from the endpoint tests. A scheme
that happens to work in the happy path tells you nothing about whether a
leaked key store is a leaked set of keys.
"""

import pytest

from helix_api.auth import KEY_PREFIX, ApiKeyRegistry, extract_bearer


@pytest.fixture
def registry():
    return ApiKeyRegistry()


# --------------------------------------------------------------------
# Issuing
# --------------------------------------------------------------------

def test_an_issued_key_verifies(registry):
    issued = registry.issue("customer A")

    ok, key_id = registry.verify(issued.secret)

    assert ok
    assert key_id == issued.key_id


def test_every_key_is_distinct(registry):
    secrets_seen = {registry.issue().secret for _ in range(50)}

    assert len(secrets_seen) == 50


def test_keys_are_never_stored_in_plaintext(registry):
    """The property this buys: a leaked key store is not a leaked set of
    keys. Anyone reading a backup, a log, or a compromised disk gets digests
    they cannot present as credentials."""
    issued = registry.issue("customer A")

    stored = repr(registry.__dict__)

    assert issued.secret not in stored
    assert KEY_PREFIX not in stored


def test_the_preview_identifies_a_key_without_enabling_its_use(registry):
    """Safe to put in a UI or a log line."""
    issued = registry.issue("customer A")

    assert issued.key_id in issued.preview
    assert issued.secret not in issued.preview
    assert len(issued.preview) < len(issued.secret)


# --------------------------------------------------------------------
# Rejecting
# --------------------------------------------------------------------

@pytest.mark.parametrize("presented", [
    "",
    "   ",
    "not-a-key",
    "helix_sk_wrong",              # right prefix, wrong secret
    "Bearer helix_sk_wrong",       # scheme left in by mistake
])
def test_bad_credentials_are_rejected(registry, presented):
    registry.issue("customer A")

    ok, _ = registry.verify(presented)

    assert not ok


def test_one_customers_key_does_not_authenticate_as_another(registry):
    first = registry.issue("customer A")
    second = registry.issue("customer B")

    ok, key_id = registry.verify(first.secret)

    assert ok and key_id == first.key_id != second.key_id


def test_a_revoked_key_stops_working_immediately(registry):
    issued = registry.issue("customer A")
    assert registry.verify(issued.secret)[0]

    registry.revoke(issued.key_id)

    ok, reason = registry.verify(issued.secret)
    assert not ok
    assert "revoked" in reason


def test_revoking_one_key_leaves_the_others_alone(registry):
    doomed = registry.issue("customer A")
    survivor = registry.issue("customer B")

    registry.revoke(doomed.key_id)

    assert not registry.verify(doomed.secret)[0]
    assert registry.verify(survivor.secret)[0]


def test_revoking_an_unknown_key_id_is_harmless(registry):
    """A revocation call arriving twice, or for a key already deleted, must
    not raise — cleanup paths run in error handlers, where a second failure
    is the worst possible time for one."""
    registry.revoke("key_does_not_exist")


def test_comparison_is_constant_time(registry):
    """Uses hmac.compare_digest rather than ==, so the time taken does not
    depend on how many leading characters matched. Asserted by reading the
    source: timing this reliably in a test is flaky, and a flaky security
    test gets deleted, which is worse than an explicit structural one."""
    import inspect

    import helix_api.auth as auth

    source = inspect.getsource(auth.ApiKeyRegistry.verify)
    # Strip comments first: the method's own comment explains why it avoids
    # `==`, and a naive scan matches that explanation. Same trap as grepping
    # prose for a word the prose is about.
    code = "\n".join(line.split("#")[0] for line in source.splitlines())

    assert "compare_digest" in code
    assert "==" not in code


# --------------------------------------------------------------------
# Header handling
# --------------------------------------------------------------------

@pytest.mark.parametrize("header,expected", [
    ("Bearer helix_sk_abc", "helix_sk_abc"),
    ("bearer helix_sk_abc", "helix_sk_abc"),
    ("BEARER helix_sk_abc", "helix_sk_abc"),
    ("  Bearer   helix_sk_abc  ", "helix_sk_abc"),
    ("helix_sk_abc", "helix_sk_abc"),      # bare key, no scheme
    (None, ""),
    ("", ""),
])
def test_bearer_extraction_tolerates_how_clients_actually_send_it(header, expected):
    """Rejecting a bare key teaches nothing — it is still checked on its
    merits, and a 401 that means "you forgot a word" wastes an afternoon."""
    assert extract_bearer(header) == expected


# --------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------

def test_the_endpoint_rejects_a_request_with_no_key():
    from fastapi.testclient import TestClient

    from helix_api.app import app

    payload = {
        "components": [{"name": "MCU", "cost_usd": 5.0, "width_mm": 10,
                        "depth_mm": 10, "height_mm": 2, "power_draw_w": 0.2,
                        "category": "compute", "quantity": 1}],
        "constraints": {"budget_usd": 50.0, "enclosure_width_mm": 50,
                        "enclosure_depth_mm": 50, "enclosure_height_mm": 20,
                        "power_budget_w": 2.0},
    }

    response = TestClient(app).post("/task/bom-review", json=payload)

    assert response.status_code == 401


def test_the_rejection_reason_is_not_leaked_to_the_client():
    """Telling a caller whether a key is unknown or merely revoked hands an
    attacker a way to enumerate valid key IDs. The reason belongs in the
    audit log."""
    from fastapi.testclient import TestClient

    from helix_api.app import _registry, app

    issued = _registry.issue("about to be revoked")
    _registry.revoke(issued.key_id)

    payload = {
        "components": [{"name": "MCU", "cost_usd": 5.0, "width_mm": 10,
                        "depth_mm": 10, "height_mm": 2, "power_draw_w": 0.2,
                        "category": "compute", "quantity": 1}],
        "constraints": {"budget_usd": 50.0, "enclosure_width_mm": 50,
                        "enclosure_depth_mm": 50, "enclosure_height_mm": 20,
                        "power_budget_w": 2.0},
    }
    response = TestClient(app).post(
        "/task/bom-review", json=payload,
        headers={"Authorization": f"Bearer {issued.secret}"},
    )

    assert response.status_code == 401
    assert "revoked" not in response.text.lower()
    assert issued.key_id not in response.text
