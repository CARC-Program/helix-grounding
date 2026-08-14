"""
The real integration gap this closes: every prior orchestrator test used
the small 5-item deliberately-broken BOM. Every realistic-scale test
called the agent directly, bypassing the API layer entirely. This test
runs the 18-item realistic BOM THROUGH the full orchestrator — auth,
routing, deterministic checks, grounded synthesis (component lookup
included), and audit logging — all together, for the first time.
"""

import sys, os

from fastapi.testclient import TestClient
from helix_api.app import app, _registry, _audit, BOMReviewRequest
from helix_api.auth import provision_simulated_terminal, sign_request
from test_bom_review_realistic_scale_sandbox import build_realistic_synthetic_bom

client = TestClient(app)


def run():
    components, constraints = build_realistic_synthetic_bom()

    # Build the exact JSON payload the API expects -- now including the
    # full D-033 field set (quantity, manufacturer, mpn, lead_time_days),
    # which the API schema previously dropped silently. See D-035.
    payload = {
        "components": [
            {
                "name": c.name, "cost_usd": c.cost_usd, "width_mm": c.width_mm,
                "depth_mm": c.depth_mm, "height_mm": c.height_mm,
                "power_draw_w": c.power_draw_w, "category": c.category,
                "quantity": c.quantity, "manufacturer": c.manufacturer,
                "manufacturer_part_number": c.manufacturer_part_number,
                "lead_time_days": c.lead_time_days,
            }
            for c in components
        ],
        "constraints": {
            "budget_usd": constraints.budget_usd,
            "enclosure_width_mm": constraints.enclosure_width_mm,
            "enclosure_depth_mm": constraints.enclosure_depth_mm,
            "enclosure_height_mm": constraints.enclosure_height_mm,
            "power_budget_w": constraints.power_budget_w,
        },
    }

    terminal = provision_simulated_terminal("terminal-realistic-scale-001")
    _registry.register(terminal.terminal_id, terminal.public_key_pem)

    model = BOMReviewRequest(**payload)
    payload_bytes = model.model_dump_json().encode()
    signature = sign_request(terminal.private_key, payload_bytes)
    headers = {"X-Terminal-Id": terminal.terminal_id, "X-Signature": signature.hex()}

    print(f"=== Full pipeline, realistic {len(components)}-item BOM, through the actual API ===\n")
    r = client.post("/task/bom-review", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    print(f"Total cost: ${data['total_cost_usd']:.2f}   Total power: {data['total_power_w']:.3f}W")
    print(f"Findings ({len(data['findings'])}):")
    for f in data["findings"]:
        print(f"  [{f['severity'].upper()}] {f['message']}")
    print(f"\nSynthesis:\n  {data['synthesis']}")

    # Verify the fix: cost must match the hand-computed quantity-aware
    # total, and the 112-day BME280 lead-time warning must actually fire
    # through the API now -- both were silently broken before D-035.
    expected_cost = sum(c.cost_usd * c.quantity for c in components)
    assert abs(data["total_cost_usd"] - expected_cost) < 0.01, (
        f"Cost mismatch: API returned {data['total_cost_usd']}, expected {expected_cost} "
        f"-- quantity is being dropped at the HTTP boundary again"
    )
    print(f"\n[PASS] Cost matches quantity-aware total (${expected_cost:.2f}) through the full API")

    lead_time_findings = [f for f in data["findings"] if "lead time" in f["message"]]
    assert len(lead_time_findings) == 1, (
        "Expected the 112-day BME280 lead-time warning through the API -- "
        "got none, meaning lead_time_days is still being dropped"
    )
    print(f"[PASS] Lead-time warning correctly fires through the API: {lead_time_findings[0]['message']}")

    entries = _audit.all_entries()
    matching = [e for e in entries if "18" in e.summary or str(len(components)) in e.summary]
    print(f"\nAudit log entries so far this run: {len(entries)}")
    for e in entries:
        print(f"    {e.action_type:15} {e.summary}")

    print("\n[SANDBOX TEST PASSED] Realistic-scale BOM handled correctly through the full API pipeline.")


if __name__ == "__main__":
    run()
