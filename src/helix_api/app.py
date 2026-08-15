"""
HTTP surface: submit a BOM, get a reviewed report back.

A skeleton, and labelled as one. The routing shape works and is tested
— API key verification, tier gating, and audit logging of every request
including rejected ones. It has never been deployed or exposed to a
network.

What is not here: rate limiting, persistence beyond the in-process audit
log, and any billing hook. Those become real requirements the day there
is a paying user, and building them before that is how the previous
version of this project spent a year at 8% complete.
"""

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import os
import time
import json

from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints
from helix_api.auth import ApiKeyRegistry, extract_bearer
from helix_api.audit import AuditLog, ActionLogEntry

app = FastAPI(title="HELIX NEXUS Orchestrator (skeleton)")

_agent = BOMReviewAgent()
_registry = ApiKeyRegistry()
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
    authorization: str = Header(None),
    include_synthesis: bool = True,
    tier: str = "basic",
):
    """
    Submit a BOM for review. Requires `Authorization: Bearer <api key>`.

    The agent is read-only: it analyses and reports, and takes no action with
    financial or legal consequence, so no human approval gate sits in front of
    it. Every request is written to the audit log regardless of outcome —
    including rejected ones, because a rejection that leaves no trace is
    indistinguishable from a request that never arrived.

    tier: "basic" (default), "standard", or "senior". Gates deliverable DEPTH
    only, never correctness — the grounding check applies identically at every
    tier. A cheaper report is shorter, never less true.
    """
    if tier not in ("basic", "standard", "senior"):
        raise HTTPException(status_code=422, detail=f"Unknown tier '{tier}' — must be basic, standard, or senior")

    ok, reason = _registry.verify(extract_bearer(authorization))
    if not ok:
        _audit.log(ActionLogEntry(
            agent_name="bom_review_agent", action_type="auth_failure",
            authorization_tier="read-only", summary=f"Rejected: {reason}",
            timestamp=time.time(),
        ))
        # The specific reason goes to the audit log, not to the client.
        # Distinguishing "unknown key" from "revoked key" in the response
        # tells an attacker which key IDs are real.
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

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
