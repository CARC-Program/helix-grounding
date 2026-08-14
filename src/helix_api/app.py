"""
HELIX NEXUS — Orchestrator skeleton, per API_SYSTEM_DESIGN.md and
NEXUS_SERVER_ARCHITECTURE.md.

This is a structural skeleton, not a deployed service — it demonstrates
the routing shape (POST /task -> agent -> result) without live
authentication, database, or network exposure. Deploying this for real
requires: the secure-element auth check (AUTHENTICATION_SYSTEM.md), the
Postgres+pgvector connection (DATABASE_ARCHITECTURE.md), and Redis-backed
rate limiting (API_SYSTEM_DESIGN.md Section 4) — none of which are wired
here. This file exists to prove the routing logic works in isolation,
consistent with sandboxed, incremental testing rather than standing up
the full stack before any one piece is verified.
"""

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import os
import time
import json

from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints
from helix_api.auth import TerminalRegistry
from helix_api.audit import AuditLog, ActionLogEntry

app = FastAPI(title="HELIX NEXUS Orchestrator (skeleton)")

_agent = BOMReviewAgent()
_registry = TerminalRegistry()
_audit = AuditLog()  # in-memory SQLite for sandbox testing


class ComponentIn(BaseModel):
    name: str
    cost_usd: float
    width_mm: float
    depth_mm: float
    height_mm: float
    power_draw_w: float
    category: str
    quantity: int = 1
    manufacturer: str = ""
    manufacturer_part_number: str = ""
    lead_time_days: int = 0


class ConstraintsIn(BaseModel):
    budget_usd: float
    enclosure_width_mm: float
    enclosure_depth_mm: float
    enclosure_height_mm: float
    power_budget_w: float


class BOMReviewRequest(BaseModel):
    components: list[ComponentIn]
    constraints: ConstraintsIn


@app.get("/health")
def health():
    """Per NETWORK_MONITORING.md — dedicated health endpoint, not just
    port reachability."""
    return {"status": "ok"}


@app.post("/task/bom-review")
def submit_bom_review(
    request: BOMReviewRequest,
    x_terminal_id: str = Header(...),
    x_signature: str = Header(...),
    include_synthesis: bool = True,
    tier: str = "basic",
):
    """
    Maps to POST /task in API_SYSTEM_DESIGN.md, specialized to the one
    agent that currently exists (AI_AGENT_FRAMEWORK.md — one agent first).
    Authorization tier: read-only per AI_AGENT_FRAMEWORK.md Section 4 —
    no human authorization gate needed for this specific agent, since it
    has no consequential-tier actions in scope.

    Every request must carry a valid signature (AUTHENTICATION_SYSTEM.md)
    verified against the terminal registry before the agent runs. Every
    completed request is written to the audit log
    (AI_SAFETY_CONSTRAINTS.md Section 3) regardless of outcome.

    tier: "basic" (default), "standard", or "senior" — per
    HELIX_REVENUE_SYSTEM_DESIGN.md Section 6. Gates deliverable DEPTH
    only, never correctness: the grounding safety net (D-040) applies
    identically at every tier. Standard/senior visual rendering is not
    yet implemented (D-041, next build step) — requesting those tiers
    currently returns the same content as basic plus an explicit note
    that visual rendering is pending, rather than silently downgrading
    without saying so.
    """
    if tier not in ("basic", "standard", "senior"):
        raise HTTPException(status_code=422, detail=f"Unknown tier '{tier}' — must be basic, standard, or senior")

    payload_bytes = request.model_dump_json().encode()
    signature_bytes = bytes.fromhex(x_signature)
    ok, reason = _registry.verify_request(x_terminal_id, payload_bytes, signature_bytes)
    if not ok:
        _audit.log(ActionLogEntry(
            agent_name="bom_review_agent", action_type="auth_failure",
            authorization_tier="read-only", summary=f"Rejected: {reason}",
            timestamp=time.time(),
        ))
        raise HTTPException(status_code=401, detail=f"Authentication failed: {reason}")

    try:
        # model_dump(), not dict(): .dict() is deprecated in Pydantic v2 (this
        # project runs 2.13) and is removed in v3. It emits a DeprecationWarning
        # today and becomes a hard failure on the next major upgrade -- and the
        # line above already uses the v2 spelling (model_dump_json), so the file
        # was mixing both conventions.
        components = [Component(**c.model_dump()) for c in request.components]
        constraints = DesignConstraints(**request.constraints.model_dump())
    except TypeError as e:
        raise HTTPException(status_code=422, detail=f"Malformed input: {e}")

    result = _agent.review(components, constraints)

    synthesis = None
    synthesis_validated = None
    if include_synthesis:
        # D-040: uses the hard-validated path, never the raw synthesis
        # call directly. Any fabricated attempt is rejected and logged
        # here, not silently discarded, per the no-soft-warnings
        # requirement.
        outcome = _agent.synthesize_recommendations_validated(result, components, constraints)
        synthesis = outcome["text"]
        synthesis_validated = outcome["validated"]
        for rejected in outcome["rejected_attempts"]:
            _audit.log(ActionLogEntry(
                agent_name="bom_review_agent", action_type="synthesis_rejected_ungrounded",
                authorization_tier="read-only",
                summary=f"Attempt {rejected['attempt']} rejected -- fabricated values: {rejected['issues']}",
                timestamp=time.time(),
            ))

    interconnect_diagram = None
    visual_interconnect_svg = None
    placement_blueprint_svg = None
    visual_diagram_status = None
    if tier in ("standard", "senior"):
        interconnect_diagram = _agent.generate_interconnect_diagram(components)
        from helix_bom.diagrams import generate_visual_interconnect_svg, generate_placement_blueprint_svg
        visual_interconnect_svg = generate_visual_interconnect_svg(components)
        if tier == "senior":
            placement_blueprint_svg = generate_placement_blueprint_svg(components, constraints, result)
        visual_diagram_status = (
            f"[{tier.upper()} TIER] Real SVG diagrams generated below. "
            f"Wiring-layout and module-exploded views remain designed but not yet "
            f"implemented (D-041/D-042) -- only the visual interconnect "
            f"{'and placement blueprint ' if tier == 'senior' else ''}are real image output so far."
        )

    _audit.log(ActionLogEntry(
        agent_name="bom_review_agent", action_type="bom_review",
        authorization_tier="read-only",
        summary=f"Reviewed {len(components)} components, "
                f"{len(result.findings)} findings, over_budget={result.over_budget}, "
                f"synthesis_included={include_synthesis}, synthesis_validated={synthesis_validated}, "
                f"tier={tier}",
        timestamp=time.time(),
    ))

    return {
        "total_cost_usd": result.total_cost_usd,
        "total_power_w": result.total_power_w,
        "over_budget": result.over_budget,
        "over_power_budget": result.over_power_budget,
        "findings": [{"severity": f.severity, "message": f.message} for f in result.findings],
        "synthesis": synthesis,
        "synthesis_validated": synthesis_validated,
        "tier": tier,
        "interconnect_diagram": interconnect_diagram,
        "visual_interconnect_svg": visual_interconnect_svg,
        "placement_blueprint_svg": placement_blueprint_svg,
        "visual_diagram_status": visual_diagram_status,
    }
