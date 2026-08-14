"""
Tests the tier parameter added to /task/bom-review: invalid tier
rejected, basic tier omits the diagram fields, standard/senior tiers
include the text-diagram fallback with an honest status note (not a
silent downgrade).
"""
import sys, os

from fastapi.testclient import TestClient
from helix_api.app import app, _registry
from helix_api.auth import provision_simulated_terminal, sign_request
from helix_api.app import BOMReviewRequest

client = TestClient(app)

PAYLOAD = {
    "components": [
        {"name": "MCU", "cost_usd": 5.0, "width_mm": 10, "depth_mm": 10, "height_mm": 2,
         "power_draw_w": 0.2, "category": "compute", "quantity": 1},
    ],
    "constraints": {
        "budget_usd": 50.0, "enclosure_width_mm": 50, "enclosure_depth_mm": 50,
        "enclosure_height_mm": 20, "power_budget_w": 2.0,
    },
}


def signed_headers(terminal):
    model = BOMReviewRequest(**PAYLOAD)
    payload_bytes = model.model_dump_json().encode()
    signature = sign_request(terminal.private_key, payload_bytes)
    return {"X-Terminal-Id": terminal.terminal_id, "X-Signature": signature.hex()}


def run():
    terminal = provision_simulated_terminal("terminal-tier-test-001")
    _registry.register(terminal.terminal_id, terminal.public_key_pem)
    headers = signed_headers(terminal)

    print("=== Invalid tier rejected ===")
    r = client.post("/task/bom-review?tier=platinum", json=PAYLOAD, headers=headers)
    assert r.status_code == 422, r.text
    print("[PASS] Unknown tier correctly rejected with 422\n")

    print("=== Basic tier (default) — no diagram fields populated ===")
    r = client.post("/task/bom-review", json=PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tier"] == "basic"
    assert data["interconnect_diagram"] is None
    assert data["visual_diagram_status"] is None
    print("[PASS] Basic tier correctly omits diagram fields\n")

    print("=== Standard tier — real SVG interconnect diagram generated ===")
    r = client.post("/task/bom-review?tier=standard", json=PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tier"] == "standard"
    assert data["interconnect_diagram"] is not None
    assert data["visual_interconnect_svg"] is not None
    assert "<svg" in data["visual_interconnect_svg"]
    assert data["placement_blueprint_svg"] is None, "Placement blueprint is senior-tier only"
    print("[PASS] Standard tier includes real SVG interconnect diagram "
          "(placement blueprint correctly withheld -- that's senior-only)\n")

    print("=== Senior tier — both SVG diagrams generated ===")
    r = client.post("/task/bom-review?tier=senior", json=PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tier"] == "senior"
    assert data["visual_interconnect_svg"] is not None
    assert data["placement_blueprint_svg"] is not None
    assert "<svg" in data["placement_blueprint_svg"]
    print("[PASS] Senior tier includes both real SVG diagrams\n")

    print("[SANDBOX TEST PASSED] Tier gating behaves correctly.")


if __name__ == "__main__":
    run()
