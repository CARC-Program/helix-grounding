"""
In-process orchestrator test using FastAPI's TestClient — no real network
connection, no external service contacted. Now exercises the full
request path including API key verification and audit logging.
"""

import sys
import os


from fastapi.testclient import TestClient
from helix_api.app import app, _registry, _audit, BOMReviewRequest

client = TestClient(app)

SYNTHETIC_PAYLOAD = {
    "components": [
        {"name": "Compute module (SBC)", "cost_usd": 45.00, "width_mm": 65, "depth_mm": 30, "height_mm": 12, "power_draw_w": 3.5, "category": "compute"},
        {"name": "WiFi/BT radio module", "cost_usd": 8.50, "width_mm": 15, "depth_mm": 15, "height_mm": 3, "power_draw_w": 0.8, "category": "connectivity"},
        {"name": "Li-ion battery pack", "cost_usd": 12.00, "width_mm": 50, "depth_mm": 34, "height_mm": 8, "power_draw_w": 0.0, "category": "power"},
        {"name": "Custom sensor board", "cost_usd": 22.00, "width_mm": 40, "depth_mm": 25, "height_mm": 6, "power_draw_w": 1.2, "category": "sensor"},
        {"name": "Premium OLED display", "cost_usd": 38.00, "width_mm": 70, "depth_mm": 45, "height_mm": 5, "power_draw_w": 1.5, "category": "display"},
    ],
    "constraints": {
        "budget_usd": 100.00,
        "enclosure_width_mm": 68,
        "enclosure_depth_mm": 50,
        "enclosure_height_mm": 25,
        "power_budget_w": 5.0,
    },
}


def run():
    # Health check
    r = client.get("/health")
    assert r.status_code == 200
    print("[PASS] /health returns ok")

    # Provision a simulated terminal and register its public key server-side
    issued = _registry.issue("sandbox test key")

    # Sign the exact JSON the server will re-serialize and verify against
    model = BOMReviewRequest(**SYNTHETIC_PAYLOAD)
    payload_bytes = model.model_dump_json().encode()
    headers = {"Authorization": f"Bearer {issued.secret}"}

    r = client.post("/task/bom-review", json=SYNTHETIC_PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["over_budget"] is True
    assert data["over_power_budget"] is True
    assert "synthesis" in data, "Expected a 'synthesis' field now that the LLM step is wired in"
    print(f"[PASS] Authenticated request accepted, {len(data['findings'])} findings returned")
    print(f"[PASS] Synthesis field present: {str(data['synthesis'])[:80]}...")

    # Tampered signature must be rejected
    bad_headers = {"Authorization": "Bearer helix_sk_not_a_real_key"}
    r = client.post("/task/bom-review", json=SYNTHETIC_PAYLOAD, headers=bad_headers)
    assert r.status_code == 401, r.text
    print("[PASS] Wrong API key correctly rejected (401)")

    # Unknown terminal_id must be rejected
    unknown_headers = {"Authorization": "Bearer totally-malformed"}
    r = client.post("/task/bom-review", json=SYNTHETIC_PAYLOAD, headers=unknown_headers)
    assert r.status_code == 401, r.text
    print("[PASS] Malformed credential correctly rejected (401)")

    # Revoked terminal must be rejected even with a previously-valid signature
    _registry.revoke(issued.key_id)
    r = client.post("/task/bom-review", json=SYNTHETIC_PAYLOAD, headers=headers)
    assert r.status_code == 401, r.text
    print("[PASS] Revoked key correctly rejected (401), even though the secret is right")

    # Audit log should now contain successful + failed attempts
    entries = _audit.all_entries()
    assert len(entries) >= 4, f"Expected at least 4 audit entries, got {len(entries)}"
    print(f"[PASS] Audit log contains {len(entries)} entries:")
    for e in entries:
        print(f"    {e.action_type:15} [{e.authorization_tier}] {e.summary}")

    print("\n[SANDBOX TEST PASSED] Auth + audit logging verified end-to-end, in-process, no network exposure.")


if __name__ == "__main__":
    run()
