# HELIX DECISION LOG

Format per entry: Decision, Reasoning, Alternatives Considered, Cost Impact,
Future Implications. Entries are appended chronologically.

---

## D-001 — Component selection philosophy: value density over unit count

**Date:** 2026-07-15
**Decision:** For every MK1 subsystem, prioritize fewer, higher-capability,
pre-validated modules over many generic discrete parts.
**Reasoning:** integration engineering cost (firmware/driver bring-up,
failure surface) scales with part count, and is the dominant cost for a
solo build — more so than unit price.
**Alternatives considered:** optimizing purely for lowest unit cost per
part; rejected as false economy for a one-person team.
**Cost impact:** neutral-to-positive — several "buy the certified part"
decisions below (secure element, power bank) are cheaper AND lower-risk
than the DIY alternative.
**Future implications:** this principle governs every subsystem decision
logged below and should be re-applied at each future MK revision.

---

## D-002 — Compute: Jetson Orin Nano Super (System-on-Module), not custom SoC

**Date:** 2026-07-15
**Decision:** Use NVIDIA Jetson Orin Nano Super module on its stock
reference carrier board for MK1.0.
**Reasoning:** 67 TOPS at $249 with a supported lifecycle through 2032;
full custom silicon is a $500K-$3M+, multi-year undertaking incompatible
with a solo build at any realistic budget tier.
**Alternatives considered:** Raspberry Pi CM5 (insufficient AI acceleration
for HELIX CORE's on-device reasoning goals); Rockchip RK3588 SoM (weaker
software ecosystem for AI workloads specifically).
**Cost impact:** $249, largest single line item in the BOM (~45% of core
subtotal).
**Future implications:** MK1.1 will migrate to a custom carrier board using
the bare module to reduce height and enable the slim clamshell target.

---

## D-003 — Security: ATECC608B, not SE050, not software-only

**Date:** 2026-07-15
**Decision:** Use Microchip ATECC608B secure element in breakout form
factor.
**Reasoning:** hardware-based key storage at ~$6, single I2C interface,
sufficient for MK1.0's actual threat model (protecting local
credentials/API keys). SE050's CC EAL 6+/FIPS 140-2 certification is real
capability but is not required until HELIX NEXUS needs to attest to a third
party.
**Alternatives considered:** NXP SE050 (deferred, not rejected — revisit at
MK1.2); software-only key storage (rejected — this is one of the few areas
where "custom" is worse than "buy," regardless of budget).
**Cost impact:** ~$6.
**Future implications:** migrate from breakout to bare SMD part on the
custom carrier board at MK1.1; re-evaluate SE050 if a third-party
attestation requirement emerges.

---

## D-004 — Power: external tethered PD power bank, no internal battery

**Date:** 2026-07-15
**Decision:** MK1.0 uses an external USB-C PD power bank routed through a
fixed-20V trigger cable into the Jetson's native DC barrel jack. No
internal battery or custom battery-management circuitry in MK1.0.
**Reasoning:** removes DIY battery fire-safety risk entirely by relying on
the power bank's own certified BMS; also removes battery thickness from the
enclosure stack-up, simplifying MK1.0 mechanical design.
**Alternatives considered (and corrected):** originally considered powering
via the carrier board's USB-C port directly — verified against NVIDIA
documentation and forum reports that this does not work; the USB-C port is
host/device/debug only, not a power input.
**Cost impact:** ~$59 (power bank + trigger cable) vs. an estimated
$80-120+ for a proper internal battery + PMIC + fuel gauge + protection
circuit design — cheaper AND lower engineering risk.
**Future implications:** internal battery integration is a genuinely new
design category for MK1.1, not a small extension of MK1.0's power
architecture — schedule and budget accordingly.

---

## D-005 — Enclosure: revised thickness target, field-terminal form factor for MK1.0

**Date:** 2026-07-15
**Decision:** Revise MK1.0 closed-clamshell thickness target from 25-35mm
(original master document spec) to 45-50mm.
**Reasoning:** the stock Jetson compute assembly alone is 21-35mm tall; a
folding clamshell's closed thickness is the sum of both halves' thickness,
not a shared budget. The original target was not physically achievable
without first redesigning the carrier board.
**Alternatives considered:** forcing the original 25-35mm target by
immediately designing a custom carrier board for MK1.0 — rejected; this
would front-load MK1.1's highest-risk work (custom high-speed SO-DIMM
signal routing) into MK1.0, contradicting the project's own "don't build
the final version first" rule.
**Cost impact:** neutral — same components, larger enclosure material only.
**Future implications:** MK1.1 explicitly owns the slim-form-factor goal,
once the custom carrier board and internal battery are both in place.

---

## D-006 — Deferred: biometric/camera authentication and sensor array

**Date:** 2026-07-15
**Decision:** Cut camera-based biometric authentication and the full
sensor array (accelerometer, gyro, ambient light) from MK1.0 scope.
**Reasoning:** no defined business function currently consumes this data;
Rule 1 (ROI first) is not satisfied for either subsystem yet. Possession-
based authentication via the secure element is sufficient for MK1.0.
**Alternatives considered:** including a camera module now "for future
use" — rejected; this is exactly the kind of speculative complexity Rule 1
exists to filter out.
**Cost impact:** avoids an estimated $40-80 in camera/sensor hardware plus
associated CSI-connector interface board complexity.
**Future implications:** revisit at MK1.2 if a concrete threat model or
business function requires either capability.

---

## D-007 — Process correction: checkpoint-gated delivery, Phase 1 reopened

**Date:** 2026-07-15
**Decision:** Adopt checkpoint gating (a numbered project folder is not
"confirmed" until fully complete and internally consistent) and
single-archive delivery (whole project sent as one package, not
individual files) going forward.
**Reasoning:** hardware documentation (Checkpoint 2) was produced before
foundation documentation (Checkpoint 1: 00 + 01) was complete, contradicting
the original master prompt's own stated phase order. This created rework
risk if business-model decisions end up affecting hardware scope, and
individual-file delivery had already caused a naming mismatch requiring
correction.
**Alternatives considered:** continuing file-by-file delivery — rejected
per direct project-owner feedback that this caused confusion and errors.
**Cost impact:** none — process change only.
**Future implications:** Checkpoint 1 must close (business model named,
all 00+01 files complete) before Checkpoint 2 is considered formally
confirmed, even though its files are already drafted.

---

## D-008 — Business model strategic shape locked without deferring to owner

**Date:** 2026-07-15
**Decision:** HELIX generates revenue as a service business (curated
analysis/automation sold on retainer) rather than a product/SaaS business.
Specific client niche intentionally left to Phase 0 empirical testing
rather than invented here.
**Reasoning:** ran a 2035 disruption-survival test (model deprecation, API
price shock, platform disappearance, hardware unavailability, competitor
undercutting) — the service shape survives all five scenarios tested; a
product/SaaS shape fails the "competitor undercuts the AI layer" test by
design, since it has no moat beyond the AI itself. The specific niche was
not invented because doing so would require fabricating facts about the
project owner's expertise/network/interests that only they possess —
inventing them would be presented as research but would actually be a
guess, which fails this project's own rigor standard.
**Alternatives considered:** product/SaaS-wrapper shape (rejected, fails
resilience test above); picking a specific arbitrary niche now (rejected —
would be fabricated, not researched); continuing to ask the project owner
to name the niche (rejected per explicit instruction not to defer
strategic decisions back to them).
**Cost impact:** none — strategic decision only.
**Future implications:** Phase 0 (90-day window) now has a concrete,
falsifiable objective: find one niche meeting all five selection criteria
in HELIX_BUSINESS_MODEL.md with a real paying pilot client. Failure to do
so triggers a revisit of the hypothesis itself, not indefinite niche
cycling.

---

## D-009 — Enclosure width corrected; Checkpoint 2 closed

**Date:** 2026-07-15
**Decision:** Revise MK1.0 enclosure width from 180-200mm to 235-250mm.
Close Checkpoint 2 (02_HELIX_TERMINAL_MK1_CYBERDECK).
**Reasoning:** the original width target was derived from the compute
assembly's own footprint and never checked against the physical keyboard's
footprint. A minimal usable 12x4 Choc-spaced layout needs ~236-240mm of
width on its own — wider than the original target. Caught during
MK1_ENCLOSURE_DESIGN.md drafting, corrected before physical build.
**Alternatives considered:** shrinking the keyboard further (fewer
columns/rows) to preserve the original width — rejected; the project
owner separately confirmed the keyboard needs to retain "main functions"
for reliability, which argues against shrinking it further to fit an
arbitrary case dimension. The case should fit the keyboard, not the
reverse.
**Cost impact:** none — dimension change only, same components.
**Future implications:** Checkpoint 2 is now CLOSED. MK1_INPUT_SYSTEM.md
is being written out as its own file (previously folded into component
selection) to cover the finalized keyboard spec and the touchscreen-as-
pointer interaction model, per project owner direction. MK1_CAMERA_
SECURITY_SYSTEM.md and MK1_SENSOR_SYSTEM.md remain deferred per D-006.
MK1_MANUFACTURING_PLAN.md remains deferred — not needed for a single
prototype unit, only relevant once multi-unit production is considered
(MK2+).

---

## D-010 — Backend architecture: hosting, service shape, agent count

**Date:** 2026-07-15
**Decision:** HELIX NEXUS runs as a single Hetzner CX22 VPS (~$4.50/mo)
running five Docker Compose services (Caddy, FastAPI orchestrator,
Postgres+pgvector, Redis). HELIX CORE builds exactly one agent at MK1.0,
not the full six-agent roster from the original master document, behind a
model-agnostic LLM client abstraction.
**Reasoning:** heavy AI compute happens via hosted API, not on the Nexus
server itself, so a modest VPS suffices — the same value-density logic
applied to hardware now applied to infrastructure. One Postgres instance
with pgvector replaces a separate vector database service. One agent
first keeps Rule 1 enforceable — building six agents before Phase 0
proves even one would be pure speculative cost.
**Alternatives considered:** Kubernetes-class orchestration (rejected —
unjustified complexity at this scale); a dedicated vector database
(rejected — no measured need yet); building the full agent roster upfront
(rejected — contradicts Rule 1 and the Phase 0 gating already established
for the business model).
**Cost impact:** ~$4.50/month server cost, feeds directly into
HELIX_ROI_STRATEGY.md's operating-cost term.
**Future implications:** upgrade triggers are explicit and load-based
(see SERVER_HARDWARE_SPECIFICATION.md, DATABASE_ARCHITECTURE.md) — no
preemptive scaling.

---

## D-011 — Excluded autonomous trading/crypto income generation; declined to fabricate income projections

**Date:** 2026-07-15
**Decision:** HELIX will not train or deploy an agent whose function is
autonomous day trading or cryptocurrency trading for guaranteed income.
Declined to provide specific weekly/4-week income projections; built the
reporting system/template instead, to be populated with real figures once
Phase 0 produces a client.
**Reasoning:** no trading system can reliably guarantee returns — most
retail day traders lose money over time, and this was already excluded by
the original master document's own instruction to avoid unrealistic
guaranteed-profit assumptions. Fabricating specific income numbers before
a niche, client, or pricing exists would present false confidence as
research, exactly the failure mode already avoided when the business
niche itself was left unfabricated (D-008). Business outreach and selling
remain fully in scope — they fit the locked service-business model
directly and are reversible-tier (drafts, not autonomous sends).
**Alternatives considered:** providing "ballpark" numbers with heavy
caveats — rejected; a caveated fabricated number is still a fabricated
number and risks being acted on as if it were real.
**Cost impact:** none.
**Future implications:** the weekly/4-week ROI report (HELIX_ROI_STRATEGY.md
Section 4) populates with real data starting the first week a Phase 0
client exists — no projection model to build or maintain in the meantime.

---

## D-012 — Checkpoints 6 (HELIX OS) and 7 (HELIX SENTINEL) closed

**Date:** 2026-07-15
**Decision:** Qt/QML selected for HELIX OS over Electron (lighter ARM
footprint); command-bar pattern over chat or voice (matches keyboard-first
input, no new hardware); Authorization Center given its own persistent
top-level screen rather than living in dismissible notifications;
WireGuard selected for admin/DB access only, not business API traffic
(already authenticated via secure element).
**Reasoning:** each choice ties directly to a decision already locked in
an earlier checkpoint (touch/keyboard input model, secure-element
authentication, spend guardrails) rather than being decided in isolation
— see each file's own reasoning section for detail.
**Notable finding:** THREAT_MODEL.md identifies the Human Authorization
Gate itself as the most solo-operator-specific attack surface — an
attacker who social-engineers the owner's approval doesn't need to defeat
any technical control. Mitigation is procedural (richer context in the
Authorization Center UI, not just Approve/Deny), logged as a requirement
flowing from security analysis back into the UI checkpoint.
**Alternatives considered:** Electron for HELIX OS (rejected, heavier
footprint); VPN-tunneling all business traffic (rejected, redundant given
existing authentication); dedicated secrets-management service (rejected
at this scale, per proportionate-security principle).
**Cost impact:** none — architecture decisions only.
**Future implications:** Checkpoints 6 and 7 closed. Remaining: Checkpoint
8 (08_HELIX_NETWORK_INFRASTRUCTURE) and Phase 4 business-automation
checkpoints once Phase 0 names a niche.

---

## D-013 — Checkpoint 8 closed; Phase 0 execution steps added

**Date:** 2026-07-15
**Decision:** Closed Checkpoint 8 (6 files). Added a concrete Phase 0
execution checklist to HELIX_BUSINESS_MODEL.md (Section 6) — operationalizes
the niche-selection criteria into an actual weekly process, without
naming the niche itself.
**Reasoning:** GLOBAL_CONNECTIVITY_PLAN.md documents that MK1.0 is
WiFi/hotspot-dependent, not truly cellular-independent, since no cellular
module is in the lean BOM — stated plainly rather than left implied by
"portable" branding elsewhere. LATENCY_OPTIMIZATION.md identifies hosted
model inference, not network transit, as the real latency bottleneck —
prevents wasted effort on network tuning that wouldn't move the number
that matters. CLOUD_INTEGRATION.md and NETWORK_MONITORING.md both
recommend against adding services (object storage, full observability
stack) unjustified at one-server scale, extending the value-density
principle to infrastructure choices.
**Alternatives considered:** adding a cellular module now (rejected, no
Phase 0 data yet showing it's needed); full observability stack
(rejected, disproportionate at this scale).
**Cost impact:** none — architecture and process documentation only.
**Future implications:** Checkpoints 9 onward genuinely require Phase 0's
niche answer to proceed without fabricating content — further planning
work should wait on that, or focus on running Phase 0 itself (Section 6
of HELIX_BUSINESS_MODEL.md), rather than speculative further
documentation.

---

## D-014 — Phase 0 niche confirmed: electronics/hardware BOM consulting

**Date:** 2026-07-15
**Decision:** Confirmed niche as electronics/hardware BOM and
component-selection consulting for small hardware makers/startups.
Extended the falsification window from 90 to 120 days given a confirmed
cold start. Scoped the first HELIX CORE agent to this niche. Drafted
initial outreach (two variants: direct campaign outreach, community post).
**Reasoning:** scored the owner's six stated knowledge domains (AI,
self-defense, reselling, math, computing, electronics) plus one additional
trait observed directly in this project (process/falsifiability rigor)
against the five criteria in HELIX_BUSINESS_MODEL.md Section 4. AI and
computing failed on cold-start reachability (market saturation); self-
defense had an unresolved personal-skill-vs-B2B-consulting gap; reselling
was excluded by the owner directly; electronics was the only candidate
with demonstrated evidence (not just self-report) for Criterion 1, drawn
directly from this project's own component-selection and conflict-
catching work.
**Alternatives considered:** proceeding with the original 90-day window
despite the confirmed cold start — rejected, would repeat the false-
confidence error already avoided in D-008/D-011.
**Cost impact:** none — the free-review go-to-market approach has zero
cost beyond the owner's time.
**Future implications:** Checkpoint 9 (09_BUSINESS_AUTOMATION_SYSTEMS) can
now be scoped concretely, once outreach produces real signal. Weekly
Phase 0 check-ins begin once outreach is actually sent.

---

## D-015 — Multi-business candidate portfolio added; numbering error caught and fixed

**Date:** 2026-07-15
**Decision:** Per direct request, researched and added a queue of five
additional durable AI business categories beyond the active electronics
niche (fraud/anomaly detection, supply chain/inventory, predictive
maintenance, cybersecurity monitoring, customer-service automation,
healthcare admin) to HELIX_BUSINESS_MODEL.md Section 7. Sequenced them
by durability evidence and skill fit rather than treating all as
simultaneously actionable.
**Reasoning:** grounded in 2026 enterprise AI adoption data (McKinsey,
Gartner, IDC figures cited in-conversation) plus pre-2020 use-case
history for fraud detection and predictive maintenance specifically, to
distinguish durable categories from current hype-cycle ones. Declined to
provide a 2045 forecast or a predictable-income claim — no source can
reliably forecast 19 years out, and predictability was already excluded
as a claim this project makes (D-011). Sequential validation (one niche
proven before the next starts) preserves the existing agent-addition rule
in AI_AGENT_FRAMEWORK.md rather than diluting solo-operator effort across
parallel cold-outreach campaigns.
**Error caught during this update:** an earlier str_replace edit deleted
the "Falsification Condition" section heading while inserting the new
portfolio section, leaving its body text orphaned with no header, and
left a numbering gap (jumped 6 to 9, skipping 7 and 8). Both the missing
heading and the numbering gap were caught by direct inspection before
packaging, corrected, and all cross-references in HELIX_ROI_STRATEGY.md
and HELIX_BUSINESS_MODEL.md itself updated to match.
**Alternatives considered:** running multiple niches' outreach in
parallel — rejected, dilutes a solo operator's limited outreach effort
across untested channels rather than producing one clear result.
**Cost impact:** none.
**Future implications:** electronics BOM consulting remains the active
Phase 0 test; fraud/anomaly detection advisory is next in queue once it
clears its ROI gate (or the 120-day window expires without one, per
Section 8).

---

## D-016 — Declined pivot to autonomous/near-autonomous trading infrastructure

**Date:** 2026-07-15
**Decision:** Declined a directed request to build a fine-tuned model and
execution infrastructure for algorithmic/crypto trading (statistical
arbitrage, perpetual funding arbitrage, forex mean-reversion, "alpha
signal" monetization), presented via two externally-sourced documents
proposing specific annualized ROI ranges (15%-150%+, some up to 1000%)
with a "human-in-the-loop" design described as a ~5-minute daily signature
step.
**Reasoning:** this is the same category already excluded in D-011, now
reframed with denser technical vocabulary rather than new justification —
no trading system can reliably guarantee the returns asserted, and the
documents provide no methodology or citation behind the specific figures.
More importantly, the proposed "HITL" design — reducing human review to a
rapid signature over agent-staged trade payloads — directly matches the
failure mode already identified in THREAT_MODEL.md Section 2 (the
Authorization Gate is only as strong as genuine human evaluation, not
formal sign-off speed). Building a system optimized for fast approval
rather than informed approval would be constructing that vulnerability
deliberately rather than defending against it.
**Alternatives considered:** building only the "analysis" half without
execution — remains genuinely available if wanted, as a decision-support
tool with no return promises, consistent with the existing
predictive-analytics-style queue entry. Treating the documents' framing as
credible because it was sourced from other AI output or used sophisticated
terminology — rejected; neither changes the underlying claim.
**Cost impact:** none.
**Future implications:** this boundary applies regardless of how future
requests in this project are framed (new terminology, new sourcing,
renewed urgency) — a correct prior decision is not reopened by restating
the same underlying ask differently.

---

## D-017 — Commercial Rollout Gate formalized; no live outreach until sandbox-validated

**Date:** 2026-07-15
**Decision:** No live external communication (outreach, client contact,
revenue-generating operation) until: (1) backend infrastructure
(Checkpoints 4-8) is not just documented but actually implemented and
running, (2) the first agent (BOM-review, per D-014) passes sandboxed
testing against synthetic/sample data with consistently positive metrics
(AI_TESTING_FRAMEWORK.md's success rate/cost/latency criteria), and (3)
the project owner explicitly authorizes the transition to controlled
live rollout. Revenue from that rollout is earmarked as the primary
capital source for the physical HELIX Terminal MK1 build, deferring
hardware spend until the business validates itself.
**Reasoning:** direct project-owner instruction, and a sound one — it
resolves the hesitation raised about live outreach by removing the live
step entirely until something is actually proven. It also surfaces an
honest gap: Checkpoints 4-8 are architecture and documentation, not
running code. Checkpoint 10 (10_SOFTWARE_DEVELOPMENT) — actual
implementation — has not been started until this decision. That work
begins now, scoped to what can be genuinely sandbox-tested with synthetic
data, with the LLM-calling portion clearly marked as requiring the
project owner's own API credentials to run live, which is not something
to paste into this conversation.
**Alternatives considered:** treating architecture documentation as
equivalent to "backend finalized" — rejected; a design document is not a
tested system, and claiming otherwise would be the same false-confidence
problem already declined elsewhere in this project.
**Cost impact:** none yet — implementation work uses the same
already-budgeted server/API costs (SERVER_HARDWARE_SPECIFICATION.md,
AI_MODEL_STRATEGY.md), not incurred until actually deployed.
**Future implications:** Checkpoint 9 (real client, real revenue) stays
blocked until this gate clears. Checkpoint 10 begins now.

---

## D-018 — Checkpoint 10 started: first working code, sandbox-tested

**Date:** 2026-07-15
**Decision:** Implemented and ran real code for the first time in this
project — BOMReviewAgent (deterministic budget/power/physical-fit checks
+ a structurally-complete but uncredentialed LLM synthesis method),
an orchestrator skeleton (FastAPI, matching API_SYSTEM_DESIGN.md's
routing shape), and two sandbox tests, both passing, both against
fabricated synthetic data.
**What was actually verified:** the deterministic review logic correctly
catches budget overage, power overage, and physical width conflicts on a
synthetic BOM built specifically to contain all three; the orchestrator
correctly routes a request to the agent and returns structured findings,
tested in-process via FastAPI's TestClient (no real network port opened,
no external service contacted); malformed input is correctly rejected.
**What was not verified, and why:** the LLM synthesis layer is
unexercised — it requires a real Anthropic (or configured provider) API
key, which is intentionally not present in this sandbox and should never
be pasted into a chat conversation to test. The deterministic layer above
is complete and valid on its own; synthesis adds narrative framing on top
of it once the owner's own deployment supplies real credentials.
**Alternatives considered:** waiting to write any code until the full
Nexus stack (Postgres, Redis, Caddy, real auth) is deployed — rejected;
testing the agent and routing logic in isolation first, per D-017's own
incremental-and-sandboxed framing, catches logic errors before they're
compounded by infrastructure complexity.
**Cost impact:** none — local sandbox execution only.
**Future implications:** next code-level work is wiring the deterministic
agent to a real LLM client once the owner supplies credentials in their
own environment (not here), then the database/auth layers, per
CONTAINERIZATION_PLAN.md's staged deployment — still entirely pre-live,
per the Commercial Rollout Gate in D-017.

---

## D-019 — Auth + audit logging implemented; real thread-safety bug caught and fixed

**Date:** 2026-07-15
**Decision:** Implemented AUTHENTICATION_SYSTEM.md's signature-verification
flow (software-simulated secure element — real hardware equivalent is the
ATECC608B, not present here) and AI_SAFETY_CONSTRAINTS.md's audit logging
(SQLite standing in for production Postgres), wired both into the
orchestrator, sandbox-tested.
**What was verified, for real:** valid signed requests are accepted;
tampered signatures, unknown terminal IDs, and revoked terminals are all
correctly rejected with 401; every attempt (success and failure) is
written to the audit log with the correct authorization tier.
**Real bug caught during testing:** the first test run failed with a
genuine SQLite cross-thread error — FastAPI's TestClient executes request
handlers in a worker thread pool, and SQLite forbids using a connection
from a different thread than the one that created it by default. Fixed
with `check_same_thread=False` plus an explicit lock to keep writes
serialized rather than just silencing the error. Documented as a
sandbox-only fix — production Postgres via a connection pool
(DATABASE_ARCHITECTURE.md) doesn't have this constraint at all.
**Alternatives considered:** none — this was a correctness bug, not a
design choice with tradeoffs.
**Cost impact:** none — local sandbox execution only.
**Future implications:** LLM synthesis wiring remains the next real gap,
blocked on the owner supplying credentials in their own environment.

---

## D-020 — Missing folders caught: full 16-folder tree now physically exists

**Date:** 2026-07-15
**Decision:** Created all 7 top-level folders from the original project
tree that had never been created (03, 09, 11, 12, 13, 14, 15), each with
a STATUS.md explaining why it's empty (deferred / blocked / not started
/ ongoing) rather than leaving them silently absent.
**Reasoning:** direct project-owner catch — the delivered zip only ever
contained folders that had actual content, which meant 7 folders from the
owner's own original tree simply didn't exist in the archive. An absent
folder is ambiguous (forgotten? deferred? blocked?) in a way a present
folder with an explicit status is not — this matters especially for
continuity into a new conversation window, where the only ground truth
is what's physically in the zip.
**Alternatives considered:** leaving folders absent and relying on
HELIX_PROJECT_ROADMAP.md/HELIX_MASTER_DOCUMENT.md to explain their status
in prose — rejected; a new reader (human or a new Claude session)
shouldn't have to cross-reference a separate document to learn that an
entire folder's absence was intentional.
**Cost impact:** none.
**Future implications:** the full original tree (16 top-level folders)
now physically exists in every future archive of this project, regardless
of how much content each holds.

---

## D-021 — Reprioritized: business/AI model over cyberdeck hardware; autonomy assessed across three dimensions, not one composite number

**Date:** 2026-07-15
**Decision:** Project owner reprioritized — cyberdeck hardware is
secondary; business operation and the AI model running it are primary.
Consistent with the project's own original stated order ("completing
everything here before we touch the physical world," turn 1). Declined
to provide a single composite "% autonomous" figure when asked; provided
a three-dimension breakdown instead (architecture/design: 100%,
implementation: ~45%, real-world validation: 0%).
**Reasoning:** a single composite number would have blended "fully
specified" with "actually coded" with "proven to work unattended against
a real client" — three facts with very different evidentiary bases, and
collapsing them would hide that the most important one (real-world
validation) is genuinely at zero, by design (Commercial Rollout Gate,
D-017), not by technical shortfall. Also corrected the framing that full
completion means zero human involvement: the Human Authorization Gate
(AI_AGENT_FRAMEWORK.md) is a permanent design feature, not a temporary gap
that "100%" removes — what implementation completion actually removes is
the need for constant real-time presence, replaced by periodic
asynchronous approval, which is a different and more honest target than
"no human ever."
**Alternatives considered:** providing a single fabricated composite
percentage — rejected as the same false-precision problem already
declined for income projections (D-011) and niche fabrication (D-008).
**Cost impact:** none.
**Future implications:** track implementation percentage (~45% currently)
as the primary completion metric going forward, since it's the only one
of the three dimensions that moves with further building rather than
requiring an owner decision (rollout) or already being done (architecture).

---

## D-022 — Real PostgreSQL + pgvector implemented; permissions bug caught and fixed

**Date:** 2026-07-15
**Decision:** Replaced the SQLite stand-in with a real, running PostgreSQL
16 instance and pgvector 0.6.0 extension. Wrote and ran the actual
production schema (001_initial_schema.sql) — clients, agent_actions
(with a database-level CHECK constraint on authorization tier, not just
app-level validation), deliverables, memory_embeddings, evolution_log —
against the live database, plus an HNSW vector index.
**Real bug caught:** the migration was run as the postgres superuser,
which meant the tables came out owned by postgres, not the helix_app
application role the code actually connects as — a genuine "permission
denied" error on first real query, not a hypothetical. Fixed with
explicit GRANT statements, added directly into the migration file so a
fresh deploy doesn't repeat it, and noted the cleaner long-term fix (run
migrations as the application role itself).
**What was verified:** the CHECK constraint on authorization_tier rejects
an invalid value at the database level (defense in depth beyond app-level
checks); pgvector's cosine similarity search runs correctly against
synthetic embeddings and returns ranked results.
**Cost impact:** none — local sandbox instance.
**Future implications:** implementation percentage moves up from the
D-021 estimate now that the real database (not a stand-in) is running
and tested. LLM synthesis wiring remains the one piece requiring the
owner's own credentials, in their own environment.

---

## D-023 — Real bug found via field testing on the owner's own machine: .env location wrong

**Date:** 2026-07-15
**Decision:** Fixed a bug where the `.env` file, placed exactly where
instructed (SERVER_APPLICATIONS/), was never actually found by
`bom_review_agent.py` — synthesis stayed skipped even with a real key
present. Fixed by loading `.env` from an explicit path pinned to
bom_review_agent.py's own file location (AI_CODE/) instead of relying on
python-dotenv's default stack-walking search. Moved .env.example to
AI_CODE/ to match.
**Root cause:** python-dotenv's default `load_dotenv()` searches upward
from the calling script's directory through parent folders — it does not
search sideways into a sibling folder. AI_CODE/ and SERVER_APPLICATIONS/
are siblings under 10_SOFTWARE_DEVELOPMENT/, so a `.env` in
SERVER_APPLICATIONS/ was structurally unreachable from AI_CODE/'s
perspective, regardless of what value was in it. My own earlier sandbox
test happened to pass because I created the test .env directly inside
AI_CODE/ — the same directory as the code — which accidentally matched
the correct location without exposing the actual instruction bug. The
real field test (project owner running from SERVER_APPLICATIONS/, per my
own instructions) is what exposed it.
**Verification:** reproduced the exact failure in this sandbox using the
owner's own directory/invocation pattern before touching any code, then
confirmed the fix resolves it in that same reproduction, then re-ran all
three existing test suites to confirm no regression.
**Alternatives considered:** telling the user to always run scripts from
a specific directory instead — rejected, more fragile and easier to get
wrong again than fixing the code to not depend on invocation location at
all.
**Cost impact:** none.
**Future implications:** this is a good example of why sandbox testing
in an isolated environment doesn't fully replace testing in the actual
conditions a user will run in — logged as a general caution for the rest
of this project, not just this one bug.

---

## D-024 — Second real bug found: UTF-8 BOM silently broke .env parsing

**Date:** 2026-07-15
**Decision:** Built diagnose_env.py to get concrete evidence rather than
guess a third time after D-023's fix didn't resolve the issue. Tested it
myself against four realistic failure scenarios (correct file, hidden
.txt extension, BOM present, quoted value) before sending it to the
project owner. Found a real bug in my own diagnostic's test setup first
(shell printf doesn't interpret \x hex escapes the way bash's builtin
does — a testing-methodology bug, corrected by writing raw bytes via
Python instead), then found the actual bug: a UTF-8 byte-order-mark
(BOM), which Windows Notepad commonly adds when saving "UTF-8" files,
silently broke python-dotenv's parsing of the first line. The file looks
completely correct when opened in a text editor -- the BOM is invisible
-- but corrupts the ANTHROPIC_API_KEY variable name so it never matches.
**Fix:** load_dotenv() now passed encoding="utf-8-sig", which transparently
strips a BOM if present and behaves identically when absent -- verified
against both cases before and after the fix, plus a full re-run of all
three existing test suites to confirm no regression.
**Alternatives considered:** telling the user to re-save the file in a
different editor/encoding -- rejected in favor of making the code robust
to the artifact instead, since it's a common enough Windows occurrence
that the fix should live in the code, not in a list of user instructions
to remember.
**Cost impact:** none.
**Future implications:** if the owner's real key still isn't detected
after this fix, the diagnostic script's own output (not another guess)
is the next source of truth -- it now correctly surfaces path, BOM
status, key-line presence, and value length without ever printing the
actual key.

---

## D-025 — Actual root cause found: python-dotenv was never installed

**Date:** 2026-07-15
**Decision:** diagnose_env.py's own output gave a direct, unambiguous
answer: `python-dotenv` was not installed in the project owner's Python
environment. Reproduced this exact condition in this sandbox
(uninstalled python-dotenv, ran the same test) and got the identical
"SYNTHESIS SKIPPED" message the owner had seen from their very first
attempt — confirming this was the actual cause all along, not the
folder-location bug (D-023) or the BOM handling (D-024).
**Why it took three rounds to find:** D-023 and D-024 were both real,
independently-worth-fixing bugs, but neither was the specific thing
blocking this owner's case — bom_review_agent.py's own
`try/except ImportError: pass` around the dotenv import silently
swallows a missing-package error and falls through to checking
os.environ directly, which was never populated. That silent fallback is
reasonable production behavior (don't crash the whole agent over a
missing optional dependency) but made this specific failure mode quiet
and easy to misattribute to something more exotic.
**Fix:** direct instruction to run
`pip install -r SERVER_APPLICATIONS/requirements.txt`, installing
python-dotenv and anthropic (and everything else needed) in one pass
rather than surfacing missing packages one at a time.
**Verification:** reproduced the exact symptom by uninstalling
python-dotenv in this sandbox before concluding this was the cause, not
just inferring it from the diagnostic text alone.
**Cost impact:** none.
**Future implications:** none of the three bugs found this session
(D-023, D-024, D-025) contradict each other -- all three were real and
are now fixed. The lesson worth carrying forward: when a diagnostic
script gives a direct answer, verify it by reproduction before acting on
it, same discipline applied to every other claim in this project.

---

## D-026 — Pivoted to local model deployment; corrected "outmatch all frontier models" framing

**Date:** 2026-07-15
**Decision:** Superseded the hosted three-tier API plan (AI_MODEL_STRATEGY.md
Section 3, kept for reference) with a local deployment default: Qwen3 8B,
Q4 quantized, via Ollama, on the owner's RTX 4060 (8GB VRAM). Fine-tuning
via a rented cloud GPU (not locally — 8GB is insufficient even with
QLoRA), resulting weights run locally afterward at zero ongoing cost.
**Reasoning:** direct owner priority to eliminate API keys/subscriptions
and maximize control — a legitimate, achievable goal that fits the
existing model-agnostic abstraction layer without requiring architecture
changes. Corrected a specific framing before building toward it: a
solo-operator fine-tuned model cannot realistically "outmatch all
frontier models, open or closed" in general capability — training from
scratch is infeasible and even fine-tuning won't produce general
superiority. What's real and was built toward instead: a small model
fine-tuned specifically on the BOM-review synthesis task can genuinely
outperform a generic frontier model *at that one narrow job*, since the
deterministic checks (already built) handle the hard analytical work and
the model's only job is narrative synthesis of already-correct findings.
**Alternatives considered:** running multiple simultaneously-loaded local
models for tiered routing (rejected — needs 24GB+, not available on
8GB); training from scratch (rejected outright, infeasible at any
individual scale).
**Cost impact:** removes ongoing per-token API cost entirely; adds a
one-time rented-GPU fine-tuning cost (hours, not months) and the
owner's own hardware (already owned).
**Future implications:** AI_MODEL_STRATEGY.md Section 6 is now the
current default; Sections 3-4 kept as superseded reference given the
abstraction layer makes either path valid.

---

## D-027 — Job-vs-business 120-day comparison: honest structural answer, not a fabricated business figure

**Date:** 2026-07-15
**Decision:** Declined to provide a matching "business profit" figure
against the computed job-income figure ($4,371-$5,143 gross before tips,
30 hrs/week at $8.50-$10/hr over 120 days). Gave a structural explanation
instead: the business's own 120-day Phase 0 window (HELIX_BUSINESS_MODEL.md)
was designed around validation (free reviews building a case study) not
income generation, so $0-low-revenue is the expected outcome in this
specific window by design, not by failure.
**Reasoning:** fabricating a business-side number to match the job-side
number would repeat the exact error already declined in D-011, D-016,
and D-021 — false precision on something with zero real data behind it.
The honest, useful answer was structural: explain *why* the two numbers
aren't comparable in this window, which directly serves the owner's
stated goal of deciding where to focus.
**Alternatives considered:** giving a hedged/caveated business estimate
anyway — rejected, a caveated fabricated number is still fabricated, per
the same reasoning in D-011.
**Cost impact:** none.
**Future implications:** the honest comparison likely favors the job for
guaranteed short-term income during Phase 0 specifically — this does not
mean abandoning the business, since a converted retainer client scales
in a way hourly wages don't; it means expectations for *this specific
window* should be set accordingly.

---

## D-028 — Real code implementation of the LLM abstraction layer; orchestrator wiring gap closed

**Date:** 2026-07-15
**Decision:** Implemented llm_client.py — the LLMClient abstraction
described in AI_MODEL_STRATEGY.md since D-008, now real code with two
backends (LocalOllamaLLMClient as default per D-026, AnthropicLLMClient
as an explicit fallback). Found and fixed a real gap: the orchestrator's
/task/bom-review endpoint only ever called the deterministic review, never
synthesize_recommendations — the full agent pipeline had never actually
been wired end-to-end despite both halves existing separately.
**What was verified:** backend selection logic (local by default, hosted
via HELIX_LLM_BACKEND=hosted); the real "Ollama unreachable" error path
(genuinely tested — nothing listens on that port in this sandbox, this
isn't simulated); the hosted client's "no key" path; and, after the
orchestrator fix, the complete request-to-response pipeline including
synthesis, confirmed via the full test suite (4 suites, all passing).
**Honest limitation stated plainly:** this sandbox cannot reach
ollama.com (confirmed via direct request, 403) — real Qwen3 output can
only be verified on the owner's own machine, where Ollama actually runs.
Everything up to that boundary is genuinely tested here; the boundary
itself is not papered over.
**Cost impact:** none.
**Future implications:** next real-world step is the owner running this
against actual local Ollama + Qwen3 8B and reporting back what comes out
— that's the point where "SYNTHESIS SKIPPED/UNREACHABLE" finally becomes
real model output.

---

## D-029 — Two-phase local model plan: CPU-only now, GPU later, given zero shareable VRAM

**Date:** 2026-07-15
**Decision:** Switched HELIX's local model from qwen3:8b (GPU) to
phi4-mini (CPU-only, forced via per-request num_gpu=0) for the current
phase, given owner confirmation that SuperMind currently claims all
available VRAM on the shared RTX 4060 with no shareable headroom. Kept
qwen3:8b as the documented later-phase target once SuperMind moves to
its own dedicated hardware (owner's stated existing plan).
**Reasoning:** the earlier keep_alive-based coexistence fix (D-028
follow-up) assumed some shareable headroom existed to time-share; a
genuinely zero-headroom situation makes that moot, since HELIX's model
can't load into VRAM that has none free. CPU inference touches zero
VRAM by construction, so it cannot conflict with SuperMind regardless of
how much of the 8GB SuperMind holds — this is the correct fix for the
actual constraint stated, not a smaller version of the previous fix.
**Respecting a stated boundary:** the owner declined to detail
SuperMind's internals; proceeded on the one fact given (VRAM reaches
capacity quickly, no shareable room) without pressing further, per their
explicit request.
**Alternatives considered:** a smaller GPU-resident model (e.g. a more
aggressively quantized Qwen3 variant) — rejected, still competes for the
same zero-headroom VRAM; global OLLAMA_NUM_GPU=0 server setting —
rejected in favor of a per-request option={"num_gpu": 0}, since a global
setting would also force SuperMind's own calls to CPU if they share the
same Ollama instance, which is not the goal.
**Verification:** confirmed "phi4-mini" (no hyphen) as the exact,
current official Ollama library tag before writing it into code or
instructions, same rigor as the qwen3:8b confirmation in D-026. Re-ran
the full 4-suite test after the change; all pass.
**Cost impact:** none — same owned hardware either way; accepted
capability/speed trade-off is explicit and temporary.
**Future implications:** OLLAMA_SETUP_GUIDE.md now documents both
phases explicitly, including the exact two-line change (model="qwen3:8b",
force_cpu=False) to flip to GPU mode once SuperMind is off this desktop.

---

## D-030 — First real local model output achieved; two real bugs found on first live run, both fixed

**Date:** 2026-07-15
**Decision:** Owner ran all three sandbox tests on their actual machine
for the first time. Milestone: test_bom_review_sandbox.py produced real,
correct phi4-mini synthesis output — grounded in the actual submitted
numbers ($100 budget, 5W limit, 25.0mm height), no invented figures.
First genuine local AI output this project has produced.
**Bug 1 — test_llm_client_sandbox.py failed its own assertion:** the
test asserted the Ollama call must return an "UNREACHABLE"/"UNAVAILABLE"
message, written assuming this sandbox's environment (no real Ollama)
was the only case. On the owner's machine, Ollama was actually reachable,
so a real response came back instead, breaking the too-narrow assertion.
Fixed to correctly recognize both outcomes as valid rather than forcing
one.
**Bug 2 — real, missing dependency:** orchestrator_sandbox.py failed with
`ModuleNotFoundError: No module named 'cryptography'` on the owner's
machine. auth.py has imported cryptography directly since it was first
built; requirements.txt was written afterward and I never added it —
a genuine oversight, not a setup mistake on the owner's end. Fixed by
adding it to requirements.txt.
**Verification:** did not just assert the requirements.txt fix was
correct — built a genuinely isolated virtual environment (calling venv
binaries directly, since this shell doesn't support `source`/`activate`,
which silently invalidated the first verification attempt and was caught
before being reported as fixed) with only requirements.txt installed,
and re-ran all three of the owner's exact tests inside it. All pass.
**Cost impact:** none.
**Future implications:** requirements.txt is now confirmed complete on
a clean install. Next step is the owner re-running test_llm_client_sandbox.py
and test_orchestrator_sandbox.py with these two fixes.

---

## D-031 — Full pipeline verified end-to-end on real owner hardware; clean-case test added to close a real coverage gap

**Date:** 2026-07-15
**Decision:** All three sandbox tests now pass on the owner's actual
machine: real Ollama connectivity, real phi4-mini synthesis grounded
correctly in submitted figures, and the full orchestrator pipeline
(auth, deterministic review, LLM synthesis, audit logging) working
end-to-end with zero API cost and zero external dependency. This is the
implementation dimension (D-021's three-part breakdown) substantially
more complete than the ~45% estimate, now verified on real hardware
rather than only in this sandbox.
**Real gap closed:** every test to this point used a deliberately broken
synthetic BOM to verify problem detection. Added
test_bom_review_clean_case_sandbox.py, a BOM built to fit comfortably
within every constraint, to verify the agent does not produce false-
positive findings on legitimately good work — a false alarm is as real a
failure mode as a missed problem, and it had never been tested. Confirmed
in this sandbox: zero critical/warning findings on the clean case.
**What's still open before Commercial Rollout Gate (D-017) discussion:**
"consistently positive metrics" implies more than one successful run —
recommend running both the broken-case and clean-case tests together a
few times, plus varying the synthetic inputs further, before treating the
implementation dimension as fully proven. Not a new gate, just what
"consistently" honestly requires.
**Cost impact:** none.
**Future implications:** database layer (tested in this sandbox against
real Postgres, not yet on the owner's own machine) remains the one piece
of Checkpoint 10 unverified on real owner hardware specifically.

---

## D-032 — Real model quality issue found and fixed; delivery format changed to delta-only

**Date:** 2026-07-15
**Decision 1:** Fixed a genuine phi4-mini quality issue found in the
clean-case test: the model flagged a battery pack's 0W power draw as
"unusual," incorrectly reasoning as if a power-source component should
consume power like an active one. Added an explicit clarification to the
synthesis prompt in bom_review_agent.py distinguishing power-source
components (category='power') from power-consuming ones. Not a test
failure (deterministic assertions all passed) but a real synthesis-
quality gap worth catching before a real client sees it.
**Decision 2:** Changed project delivery format per direct owner
request — from always resending the full HELIX_PROJECT archive (every
file, every turn) to delta-only packages containing just new/changed
files, with the exact HELIX_PROJECT/... path preserved per file so
extraction overwrites the right location with no ambiguity. This
reverses the original full-archive rule from earlier in the project
(that rule existed to prevent confusion from individually-named loose
files with unclear destinations) — the delta-zip approach preserves that
same clarity (full paths, zip not loose files) while cutting the
resend-everything overhead the owner flagged as the actual problem now
that the project has grown past 100 files. Memory updated to reflect
this as the new standing rule.
**Alternatives considered:** reverting fully to individual loose files —
rejected, that was the original problem being solved for; keeping
full-archive delivery — rejected per direct instruction and reasonable
given project size.
**Cost impact:** none.
**Future implications:** going forward, only changed files ship, each
at its exact original path, in a small zip — full archive still
producible on request if ever needed for a fresh full sync.

---

## D-033 — Recalibrated for realistic BOM scale; a real false-positive bug found and fixed in the process

**Date:** 2026-07-15
**Decision:** Per direct owner question ("are these tests very basic?"),
expanded Component with fields that add real analytical value: quantity
(fixes a genuine gap — cost/power totals were silently assuming
quantity=1 per line, meaning 20x of a $0.05 part was being totaled as
$0.05, not $1.00), manufacturer, manufacturer_part_number, and
lead_time_days (feeding a new supply-chain risk check — parts with
90+ day lead times are flagged, a real and common cause of hardware
schedule slips). Built a new 18-line-item realistic-scale test modeled
on an actual small IoT device BOM (MCU, power management, sensors,
connectors, and the passive components every prior test omitted
entirely), replacing the 4-5-item toy BOMs used until now.
**Real bug found via this recalibration, not theory:** the physical-fit
height check summed every component's height as if all of them stack
vertically — a reasonable proxy for 4-5 major components, but produces
a false alarm at real scale, where most parts (resistors, capacitors)
mount flat, side-by-side, on the same PCB layer, not stacked on top of
each other. The 18-item test immediately surfaced this as a false
"44.7mm exceeds 15mm enclosure" warning. Fixed by checking the tallest
single component instead of summing all of them, with the finding text
now explicit that true multi-layer stack analysis needs board-layer
data this BOM format doesn't carry — avoids replacing one false
precision with another.
**Verification:** full regression run across all 4 existing test suites
plus the new one — all pass, including hand-computed quantity-math
assertions (not just "did it run," but "does 22.29 actually equal what
you'd get multiplying it out by hand").
**Alternatives considered:** adding many more "realistic-sounding" BOM
fields (RoHS compliance, voltage tolerance, package type, datasheet
links) — deferred; those either need circuit-level data this BOM format
doesn't have (e.g. voltage tolerance checks need per-net operating
voltage, not just a parts list) or don't change any actual analysis yet,
which would be realism for its own sake rather than genuine capability.
**Cost impact:** none.
**Future implications:** the height-check fix and quantity-math fix
both apply retroactively to every future BOM reviewed, not just the new
test — this was a correctness fix to the agent itself, not just new test
coverage.

---

## D-034 — First grounded tool-use step: component alternatives lookup, replacing invented recommendations with looked-up ones

**Date:** 2026-07-15
**Decision:** Built component_lookup_tool.py (mock dataset, clearly
labeled as a stand-in for a real distributor API integration) and wired
it into bom_review_agent.py's synthesis step. When a component is
flagged for a long lead time and has a known manufacturer part number,
the agent now looks up real (currently mock) alternative parts and
explicitly instructs the LLM to cite only those looked-up alternatives —
never to invent its own part numbers or specs.
**Direct motivation:** the project owner asked for reassurance that
HELIX's BOM-review capability is on a real path toward replacing, not
just supplementing, a general chat session with ChatGPT/Grok/Gemini/
Claude for this specific task. The prior test run itself supplied the
proof of why this matters: the model fabricated "additional onboard RAM"
as a justification for the BME280 recommendation — a spec that isn't
real for that sensor and wasn't in any submitted data. This is not a
smaller-model problem; any LLM reasoning without grounding will do this.
The actual differentiator from a generic chat session isn't a smarter
model, it's tool access a chat session doesn't have — this is the first
concrete instance of that architecture, not just a description of it.
**What this is and isn't:** this is a real, tested, working
implementation of the *pattern* (agent calls a grounded data source,
LLM is constrained to cite only what it returns). The dataset itself is
mock — two hand-built entries, clearly labeled as such throughout the
code. A real distributor integration (Octopart/DigiKey/Mouser API) would
replace _MOCK_ALTERNATIVES_DB with a live API call behind the same
lookup_alternatives() interface — same pattern, real data, whenever the
owner is ready to set up and supply that account's credentials (same
handling rules as the LLM API key: environment variable, never pasted
into chat).
**Verification:** tested the lookup tool in isolation (known MPN returns
real entries, unknown MPN returns empty list rather than a guess), then
verified the exact BME280 scenario triggers correctly end-to-end, then
ran full regression across all 6 test suites — all pass.
**Alternatives considered:** letting the LLM keep making unguided
"consider an alternative" suggestions — rejected, this is precisely the
ungrounded-recommendation problem the owner's question was about.
**Cost impact:** none for the mock version. A real distributor API
integration would have its own (typically low or free-tier) cost,
evaluated when that step is actually taken.
**Future implications:** this is the concrete first step on the path the
owner asked about. Next natural extensions in the same direction:
real distributor API (replacing mock data), then eventually schematic/
netlist-aware input (enabling "rewiring" guidance) and layout-aware
input (enabling diagram/layout guidance) — both of those are
substantially bigger lifts requiring richer input formats than a flat
BOM list, not next-turn work, but the same grounded-tool-use pattern
established here is what would make either trustworthy rather than
another source of invented specifics.

---

## D-035 — API schema was silently behind the agent's own capabilities; found by finally testing the two together

**Date:** 2026-07-15
**Decision:** Built test_orchestrator_realistic_scale_sandbox.py to close
a real gap: the 18-item realistic BOM (D-033) and the full orchestrator
pipeline (auth/audit/synthesis) had only ever been tested separately,
never together. Running them together immediately surfaced a real bug:
orchestrator.py's ComponentIn Pydantic model still only had the original
7 fields — quantity, manufacturer, manufacturer_part_number, and
lead_time_days were being silently dropped at the HTTP boundary. Result:
the API returned $21.65 instead of the correct $22.29, and the 112-day
BME280 lead-time warning never fired at all through the actual API a
real client would call, even though both worked correctly when calling
the agent directly in Python.
**Why this matters more than a typical bug:** D-033's fixes (quantity
math, lead-time check) were real and tested — but only at the Python/
agent level. The HTTP API is what an actual deployed terminal or client
integration would use, and it was silently behind what the agent itself
could do. This is exactly the kind of gap that only surfaces when two
previously-separate test paths are actually connected, not assumed
compatible.
**Fix:** updated ComponentIn to match Component's full field set, with
the same defaults for backward compatibility. Updated the test to send
the full field set and assert both the corrected cost and the lead-time
warning actually appear in the API response.
**Verification:** confirmed the bug first (ran the test, saw the wrong
cost and missing warning), then applied the fix, then re-ran and
confirmed both issues resolved, then ran full regression across all 7
test suites — all pass, including the original 7-field orchestrator
test, confirming backward compatibility.
**Alternatives considered:** none — this was a straightforward schema
mismatch, not a design tradeoff.
**Cost impact:** none.
**Future implications:** general lesson worth carrying forward
explicitly: when two components are each tested in isolation, that is
not the same as testing them together — the realistic-scale BOM and the
API layer each passed their own tests while the integration between
them was silently broken.

---

## D-036 — Two real synthesis errors found in a live 18-item run; moved comparison math into deterministic code

**Date:** 2026-07-15
**Decision:** The full-pipeline realistic-scale run (D-035's test) produced
synthesis text with two real errors, not style issues: (1) the model
called the $3.10 Bosch BME680 alternative "slightly cheaper" than the
$2.40 original BME280 — backwards; the mock data's own note even said
"higher cost." (2) The model fabricated a lead-time finding for the
ESP32-S3 module that doesn't exist anywhere in the actual findings, while
misquoting its price ($3.40 stated vs. $3.20 actual) and comparing it
against an unrelated sensor alternative as if they were substitutes.
**Fix:** moved the cost-delta computation and the component-to-
alternative pairing into Python, computed before the prompt is built —
the model is now only asked to restate an already-correct comparison
("$0.70 MORE expensive," computed and verified directly, not left for
the model to work out), and is explicitly told each alternative applies
only to the one component listed directly above it, never to be applied
to another component.
**Why this matches the project's existing philosophy exactly:** this is
the same lesson as D-033's quantity-math fix — arithmetic and multi-
entity bookkeeping are unreliable in LLM free text, small models
especially, and belong in deterministic code. The model's job stays
narrowly "phrase this correctly," never "compute this correctly."
**Also addressed:** owner's separate tone note (stiff phrasing like "per
HELIX's...guidelines") — added an explicit instruction for a natural,
professional tone, bundled into the same prompt rewrite since it was a
low-cost addition alongside the more important fix.
**Verification:** hand-verified the exact price-delta computation
($0.70 more expensive, $0.45 cheaper) directly against the mock dataset
before trusting it, then ran full regression across all 7 test suites —
all pass.
**Cost impact:** none.
**Future implications:** this pattern (compute comparisons in code,
have the LLM only phrase them) should apply to any future numeric
comparison this agent ever needs to communicate — not a one-off patch.

---

## D-037 — D-036 fix confirmed on a second live run; one more tone issue caught and fixed

**Date:** 2026-07-15
**Decision:** Owner re-ran the full realistic-scale pipeline. Both errors
from D-036 are confirmed gone: BME680 correctly stated as "$0.70 more
expensive," and the fabricated ESP32-S3 lead-time claim no longer
appears anywhere. Caught one more real issue in the same output: the
model consistently wrote "our production timeline," "our build," "keep
us on track" — a perspective slip, framing HELIX as a co-builder on the
client's team rather than an external consultant advising them. Fixed
with an explicit instruction to always use "your," never "our/we," when
referring to the client's project.
**Verification:** full regression across all 7 test suites after the
change — all pass.
**Cost impact:** none.
**Future implications:** none open from this thread currently — next
live re-run is the confirmation step for this specific fix, same as the
last two rounds.

---

## D-038 — Third live run genuinely clean; lead-time arithmetic hardened proactively rather than left to chance

**Date:** 2026-07-15
**Decision:** Owner's third consecutive live re-run of the realistic-scale
pipeline came back with no factual errors — correct price delta, correct
perspective ("your build" throughout), and the model correctly computed
112−14=98 days saved on its own. Rather than treat that as good enough
because it happened to work, pre-computed the lead-time delta the same
way cost delta was pre-computed in D-036 — consistent application of
"don't leave arithmetic to the model even when it succeeds," not just
"fix it when it fails."
**Verification:** hand-checked both deltas (BME680: $0.70 more, 98 days
faster; SHT31-DIS-B: $0.45 cheaper, 91 days faster) against the mock
dataset before trusting them, then ran full regression across all 7
suites — all pass.
**Cost impact:** none.
**Status:** this closes the loop on 3 rounds of real bugs found and
fixed via actual field testing at realistic scale (D-035 API schema gap,
D-036 comparison-math errors, D-037 perspective slip) — the realistic-
scale pipeline has now produced one genuinely clean, correct, well-
grounded output with no intervention needed. This is real evidence
toward "consistently positive," not yet the same as many runs across
many different BOMs, but a meaningfully stronger data point than round
one.

---

## D-039 — Three variated test scenarios added; first honestly-scoped diagram capability built

**Date:** 2026-07-15
**Decision:** Per direct request for broader test coverage and expanded
capability, added three new synthetic BOM scenarios isolating different
failure modes (over-budget-only, two-simultaneous-lead-time-flags across
a different device category entirely, physical-fit-only), and built
generate_interconnect_diagram() — a high-level block diagram derived
from component category tags, explicitly labeled throughout as a
suggestion, not a verified schematic.
**On the broader capability request (diagrams, layouts, code-on-request,
"eliminate error"):** corrected the framing before building — no review
process eliminates error, and generating an actual routable PCB layout
is a deep EDA problem, not something to promise. What's real and now
built: a category-based interconnect sketch. What's real but not yet
built: starter code for well-known parts (flagged as needing the same
grounding discipline as component lookups, to avoid hallucinated
register/pin details) and schematic-level diagrams (need netlist input,
which a flat BOM doesn't provide) — both logged as genuine next steps,
not built this session.
**Verification:** all three variated tests confirm their target failure
mode fires in isolation from the others (cost-only, physical-fit-only,
two-simultaneous-lead-times including one with no available mock
alternative). Diagram tested against the realistic 18-item BOM and a
no-compute edge case. Caught and fixed a real bug in my own edit process
before it shipped: a str_replace accidentally deleted the
protocol_by_category dictionary definition entirely, caught by grepping
for its usage before declaring the file done, not assumed fine. Full
regression across all 10 test suites — all pass.
**Cost impact:** none.
**Future implications:** starter-code generation and schematic-level
diagrams (via netlist input) are the next real capability steps in this
direction, both requiring the same "ground it, don't let the model
free-hand technical specifics" discipline already applied throughout
this project.

---

## D-040 — Hard grounding/validation safety net built, tested against the exact fabrications, wired into the API

**Date:** 2026-07-15
**Decision:** Per direct instruction after a repeated, serious fabrication
pattern (model restating dollar amounts that were never true, even when
correct values were given verbatim in the same prompt — "$36.00" for an
$18 MCU, twice, across two different tests), built a hard validation
layer with no soft warnings:
- `check_full_grounding()`: extracts every dollar amount, dimension,
  part number, and quantity from a synthesis, cross-checks each against
  the real Component data and computed totals, returns exactly which
  values are ungrounded.
- `synthesize_recommendations_validated()`: calls synthesis, validates,
  and on failure retries with the specific fabricated values fed back as
  an explicit correction (not a blind resample) — up to 2 retries. If
  still ungrounded after all retries, returns a safe fallback message
  and never delivers unvalidated narrative text.
- Wired into orchestrator.py: the API now calls the validated path
  exclusively, logs every rejected attempt to the audit trail with the
  exact fabricated values (nothing silently discarded), and returns a
  `synthesis_validated` boolean in the response.
**Verification, in order:**
1. Ran `check_full_grounding()` against the exact verbatim fabricated
   text from the real session — correctly caught the $36.00 (Test 1) and
   both the $36/$35 (Test 3) fabrications.
2. Confirmed zero false positives against genuinely correct text.
3. Tested the full reject-retry-accept flow with a mock client that
   fabricates once then produces clean text — confirmed exactly 2 calls,
   1 rejection logged with the right values, 1 acceptance.
4. Tested the exhausted-retries case with a mock client that always
   fabricates — confirmed the safe fallback is returned and the
   fabricated "$999" never appears anywhere in the final delivered text.
5. Full regression across all 13 test suites, explicitly including the
   4 core detection tests (over-budget, over-power, physical-fit,
   multi-lead-time) per direct instruction to keep those green — all
   pass, no regressions.
**Real bug caught in my own test während writing it:** the first mock
patch targeted the wrong location (bom_review_agent's namespace instead
of llm_client, where the import actually resolves from) — caught by the
test failing with a clear mismatch (mock never got called), not silently
passing incorrectly.
**Cost impact:** none. Retries cost additional local inference time only
(no API cost, per the local-model architecture) — a few extra seconds on
CPU, not a financial cost.
**Future implications:** this pattern (validate after generation, retry
with specific correction, safe fallback rather than ever deliver
unvalidated content) is now the permanent path for any future synthesis
call, not a one-off patch. Next: tiered service model + visual diagrams,
per direct instruction, starting now that this passes.

---

## D-041 — Tiered service model locked (Basic/Standard/Senior); tier-gating API hook built and tested

**Date:** 2026-07-15
**Decision:** Locked the three-tier structure per direct instruction —
Basic (checks + validated synthesis + text interconnect), Standard
(+ cleaner visual interconnect), Senior/Premium (+ multi-view visual
package: top-down blueprint, module-highlighted view, wiring layout,
risk-highlighted zones). Documented in HELIX_REVENUE_SYSTEM_DESIGN.md
Section 6. Added a real `tier` parameter to /task/bom-review gating
deliverable depth — Basic omits diagram fields entirely (fastest, no
added compute), Standard/Senior trigger the diagram path.
**Honesty choice made explicitly:** actual rendered visual diagrams
(real SVG/image output — top-down blueprint, exploded view, wiring
layout) are NOT built yet. Rather than silently serving the same text
diagram under a "premium" label, Standard/Senior tier responses include
an explicit `visual_diagram_status` field stating rendering is designed
but pending, alongside the existing text diagram as a stated fallback —
a client paying for a tier should never receive a silent downgrade
without being told.
**Grounding safety net applies identically at every tier** — tier gates
scope/depth of what's generated, never correctness. A Basic client's
synthesis goes through the exact same D-040 validation as a Senior
client's.
**Verification:** new test (invalid tier rejected 422, Basic omits
diagram fields, Standard includes text diagram + honest pending-visual
note) plus full regression across all 14 suites — all pass.
**Cost impact:** none yet — real visual rendering will have its own
compute cost, evaluated when actually built.
**Future implications:** next concrete build step is the actual visual
rendering path (real SVG/image generation from component dimension/
category data, extending generate_interconnect_diagram's category-based
approach into genuine visual output) for Standard/Senior tiers —
designed, not yet implemented.

---

## D-042 — Real SVG visual diagrams built (interconnect + placement blueprint); a real upstream bug caught while building risk-highlighting

**Date:** 2026-07-15
**Decision:** Built visual_diagram_generator.py with two real SVG
outputs: generate_visual_interconnect_svg() (Standard tier — visual
version of the category-based interconnect diagram) and
generate_placement_blueprint_svg() (Senior tier — top-down placement
sketch using real submitted width/depth per component, simple shelf-
packing, with risk-highlighting on components tied to an actual
finding). Wired both into the orchestrator, replacing the "not yet
implemented" placeholder from D-041 with real image output.
**Real bug found while building risk-highlighting, not a hypothetical:**
the width/depth physical-fit findings never actually named which
component was the problem — "Widest component (85.0mm) exceeds
enclosure width (60.0mm)" never said which part was 85mm wide. This
surfaced immediately when trying to match a finding to a component by
name for the risk-highlight feature, and it's a real gap in the client-
facing findings text itself, not just a diagram blocker — fixed at the
source in bom_review_agent.py's review(), not worked around in the
diagram code.
**Second real bug, caught during testing before shipping:** label
truncation cut component names mid-word ("Oversized display panel" →
"Oversized disp..."). Fixed with word-boundary-aware truncation
(_truncate_label), caught by the test itself failing on the original
assertion, not assumed fine.
**Verification:** both SVGs validated as well-formed XML via
xml.etree.ElementTree.fromstring() (a real parse check, not eyeballing
generated strings). Risk-highlighting verified against Variated Test 3
specifically: the oversized display panel (genuinely named in a finding)
gets the FLAGGED marker, the compact MCU (not named in any finding) does
not — checked by position in the document, not just presence anywhere.
Full regression across all 15 test suites after both the component-
naming fix and the truncation fix — all pass, no regressions on any of
the 4 core detection tests.
**What's still honestly not built:** wiring-layout and module-exploded
views (the remaining two of the four Senior-tier visual views specified
in D-041) — both still need richer input (real net/connection data) than
a flat BOM provides, same limitation already logged in D-039.
**Cost impact:** none — local SVG generation, no external rendering
service.
**Future implications:** the width/depth finding fix (naming the actual
component) improves every future BOM review's output quality, not just
diagrams — retroactive, same as the D-033/D-035 fixes.

---

## D-043 — Environment reset recovered from the owner's own authoritative copy; lost fix reapplied and numerically verified

**Date:** 2026-07-15
**Decision:** Claude's container environment fully reset mid-session
(working directory, installed packages, and the Postgres install all
wiped). Recovered by requesting the owner's current project folder as
ground truth — 124 files, all 42 decision log entries confirmed present
— rather than reconstructing from memory or partial local snapshots,
since the owner's copy (having every delta applied throughout this
session) was the only genuinely complete and current version at that
point.
**What had to be rebuilt:** Python dependencies (reinstalled from the
project's own requirements.txt, confirming it really is complete and
correct), PostgreSQL + pgvector (reinstalled, schema rebuilt from the
project's own migration file, including the D-022 permission grants
baked into that file from the start).
**What had to be reapplied:** the canvas-sizing fix for
generate_placement_blueprint_svg() (D-042's follow-up) had been written
in this session but never saved to a file before the reset hit — it only
existed in conversation context. Reapplied from that context onto the
owner's authoritative copy.
**A second gap found during recovery:** export_and_view_diagrams.py had
been created and tested in the prior sandbox session but never actually
packaged into a delivered delta zip before the reset — it existed only
on Claude's side, never reached the owner's machine at all. Recreated
and included in this delta; this is its first real delivery.
**Verification, not just re-assertion:** after reapplying the canvas
fix, generated the actual placement blueprint SVG and numerically
checked every rect's extent against the canvas bounds directly (not just
confirming well-formed XML, which would not have caught the original
clipping bug either) — canvas 315x330, furthest component extent
285x240, no clipping. Then ran the full 15-suite regression — all pass.
**Cost impact:** none — recovery time only, no data or work genuinely
lost once the owner's copy was used as source of truth.
**Future implications:** the owner's local copy is, by construction of
this whole session's delta-based workflow, the durable canonical copy —
Claude's own working environment should be treated as disposable/
reconstructable from it, not the other way around.

## D-044 — PostgreSQL schema retired; it modelled a business that no longer exists

**Decision:** deleted `migrations/001_initial_schema.sql` and
`tests/sandbox/test_database_sandbox.py`. The project now has no database
dependency at all.

**Why:** the owner authorised installing PostgreSQL so the one skipped test
could run. Before doing that, the schema was read against the direction set
by the market research, and three of its five tables turned out to model the
consulting business that research eliminated: `clients` carries a
prospect/free_review/retainer/churned funnel, and `deliverables` is a
retainer artifact. `evolution_log` serves the self-evolving AI subsystem,
which does not exist and is not on the roadmap. `memory_embeddings` is a
1536-dimension pgvector column for an AI memory system that likewise does
not exist — the dimension was itself a placeholder, since no embedding model
had been selected.

The fifth table, `agent_actions`, is genuinely worth having. It is also
already implemented, in `helix_api/audit.py`, against stdlib SQLite with no
server to install.

**What was actually being proposed:** installing a database server, plus
pgvector — which on Windows means building against MSVC or hunting a
prebuilt binary — so that one test could exercise tables no code reads, for
a business model already ruled out. That is the same failure the rebuild
corrected: building infrastructure ahead of the product, then counting it
as progress.

**Verification, not assertion:** grepped the whole source tree for every
table name and for `psycopg` before deleting. Nothing outside the deleted
test referenced any of it.

**Cost impact:** none. Removes a server dependency, removes the only skipped
test in the suite, and removes ~85 lines of SQL. The suite now needs nothing
but Python.

**Recoverable:** the schema is intact in git history — `master` holds it at
the pre-rebuild baseline, and it is in this branch until this commit. If a
hosted deployment ever needs Postgres, the audit table should be generated
from `helix_api/audit.py`'s schema, which is the one that has actually been
exercised, rather than resurrected from a file written for a different
business.

**Future implications:** the product is currently a library and a CLI. Both
are stateless. A database becomes a real requirement the day there is a
hosted service with users, and the schema for that should be written then,
against what that service actually stores — not inherited from this one.

## D-045 — Secure-element auth simulation replaced with API keys

**Decision:** `helix_api/auth.py` no longer simulates an ATECC608B secure
element signing requests with ECDSA. It issues, verifies and revokes ordinary
bearer API keys.

**Why:** the ECDSA code worked, and its verification logic was genuinely
tested. What was wrong was what it claimed. It modelled a hardware root of
trust on the MK1 terminal — hardware cut from the project when the cyberdeck
was abandoned. Software simulating a secure element that will never exist
provides none of a secure element's properties, while reading in the source
as though it does. A scheme that describes itself accurately is worth more
than a stronger-sounding one that does not.

**What replaced it, and the properties that actually hold:**
keys hashed with SHA-256 at rest, so a leaked key store is not a leaked set
of keys; `hmac.compare_digest` rather than `==`, so match time does not
depend on how many leading characters matched; plaintext returned exactly
once at issue and never recoverable; revocation permanent, because
re-enabling a key that may have leaked is never the right recovery.

**One deliberate asymmetry:** `verify()` returns a specific reason, and the
endpoint discards it. Telling a caller whether a key is unknown or merely
revoked lets an attacker enumerate valid key IDs. The reason goes to the
audit log, where it is useful; the client gets one undifferentiated 401.

**Net effect on the codebase:** smaller. Roughly 80 lines of key generation
and signature verification became about 50 lines of key handling, and three
sandbox tests got simpler — they now issue a key instead of provisioning a
terminal and signing a payload.

**Cost impact:** none. No new dependency; `hashlib`, `hmac` and `secrets` are
stdlib.

**Future implications:** the registry is an in-memory dict. That is honest
for a service with no users and no database — swapping it for a table is a
small change on the day there is a table. What must not happen is inventing
a database to hold three keys, which is the mistake D-044 just corrected.

## D-046 — Netlist input, because the premium tiers were selling an empty file

**Decision:** `helix-bom review` now accepts a KiCad `.net` netlist alongside a
BOM CSV, dispatching on the file's contents rather than its extension. A
netlist gets its own report, its own connectivity checks, and `--diagram`,
which writes an interconnect SVG in which every line is a net that exists.

**What was measured first.** Before building anything, the two paid tiers were
run against a real BOM export to see what they actually delivered. Standard
returned an error string and a 250-byte SVG with zero boxes drawn. Senior drew
twelve rectangles, all of size (0.0, 0.0). Both depend on category and
dimension columns, and no real BOM export carries either — so both had been
charging for a blank image, and every test that covered them used hand-built
components that supplied the missing fields.

**Why no amount of parsing fixes it.** A BOM is a shopping list: which parts,
how many. How they connect lives in the schematic; where they sit lives in the
board file. A wiring diagram derived from a BOM is not hard, it is impossible,
because the data is not in the file. The correct response to an impossible
feature is to take a different input, not to write a better guess.

**What the netlist actually buys.** On the test fixture: U1 to U2 over I2C_SDA
and I2C_SCL, with R1 and R2 correctly shown as the pull-ups on both lines. The
BOM-only version of that same board says "no compute category found, cannot
anchor a diagram". Beyond the diagram, connectivity has failure modes a BOM
cannot express at all, and the useful one is a *named* net with a single
connection — a label somebody typed that joined nothing. On a schematic
printout it is drawn exactly as it would be had it connected, so it survives
human review, and a parser finds it in one pass. Labels KiCad generated itself
(`unconnected-(U1-Pad7)`, `Net-(R3-Pad1)`, `N$12`) are deliberately not
flagged: those are ordinary, often intentional, and already reported by KiCad,
and burying the real finding under them would cost more than it is worth.

**The honesty rule held at the seam.** A netlist carries no prices, no
dimensions, no power figures and no categories, so all five BOM checks report
themselves unrun rather than passing quietly — the agent is handed the exact
set of fields the format supplies instead of inferring from values. Two of the
five skipped-check reasons had to change: they told the reader to "add a price
column", which is advice a netlist user cannot act on, since the format has no
columns at all. A report that is accurate about what happened and wrong about
what to do next still sends the reader somewhere useless.

**A gap this closed that was not the plan.** The netlist parser had been
written, tested at 18 tests, committed — and imported by nothing outside its
own test file. `cli.py` still loaded only CSVs, so no user could reach a line
of it. Separately, `scripts/export_diagrams.py` had been crashing on import
since the rebuild four days earlier, because it imported `bom_review_agent`
from an `AI_CODE/` folder that rebuild deleted. Both have the same cause:
nothing in the suite asserted that the code was reachable, only that it was
correct. `tests/test_scripts.py` now imports every script in `scripts/`, which
is the cheapest test that would have caught either.

**Verification, not assertion:** the diagram's geometry is checked
numerically — every box and every line endpoint against the canvas bounds, at
5 nodes, at 59 nodes, and with an over-long reference designator — because
D-043 established that well-formed XML is not evidence a diagram shows
anything. The leak test for the netlist diagnostic was itself verified by
introducing a deliberate leak and confirming it failed. 255 tests pass, up
from 223.

**On the diagnostic, which is stricter here than for a CSV.** The CSV
diagnostic prints column *headings*, because the parser matches on them and a
heading is rarely secret. A netlist has no headings; its equivalents are net
names and part values, and those are the design itself. `I2C_SDA` is harmless
and `MOTOR_KILL_INTERLOCK` is not, and no rule can tell them apart — so counts
and shapes go in and names stay out, reference designators aside, which say
nothing beyond "there is a fourth resistor".

**Cost impact:** none. No new dependency — the s-expression parser is forty
hand-written lines, and taking a dependency for it would undercut the
library's central claim.

**Future implications:** this is half of the combined direction. The other
half is distributor enrichment, and the netlist makes the case for it concrete
rather than theoretical: a netlist review currently runs zero of five checks,
and prices are what turn the first of them on. It also means the tiers need
rethinking before anything is sold — the features they were gated on were
measured to be empty, and what replaced them is not tier-shaped.

## D-047 — Names fixed by rule; outreach made executable and human-posted

**Decision:** four names settled and a naming rule adopted (`docs/IDENTITY.md`);
`src/helix_ops/` built to run the launch — gather facts, render posts, verify
them, track what came back, and say what to do next; an internal legal and
ownership checklist written to sort that work by who can actually act on it.

**The names.** *Helix* is the operator — the AI layer that runs operations, and
never a product. *Helix Labs* is the entity. Every product is `helix-<domain>`,
where the domain is the noun the buyer already uses: `helix-grounding`,
`helix-bom`, and `helix-invoice` reserved but unbuilt. The rule is the
deliverable rather than the names: `ARCHITECTURE.md` already makes a new
vertical a new file in `domains/`, and this makes the name fall out of that same
choice, so a vertical costs zero naming decisions. A descriptive name is also
found by people searching for the job, which matters when the binding
constraint is distribution and there is no marketing budget to teach an
audience what an invented word means.

**What was deliberately not renamed.** `helix-grounding` is load-bearing — it
appears in `pyproject.toml`, the CI workflow, four URLs, every install command
in every draft, and the README. After the first upload the cost of changing it
is permanent, so it changes now or never, and there is no reason to change it.

**Outreach: the agent drafts, a person posts.** This was put to the owner
explicitly rather than assumed, because it is the one place where the obvious
reading of "minimal assistance on my end" and the project's own research point
in opposite directions. `BUSINESS_MODEL.md` concludes that distribution is the
bottleneck and automation cannot fix it; `FIRST_USERS.md` says post in public
where people opted in, and no DMs. A bot posting links to Reddit and Hacker
News gets an account banned, and a new account's ban is effectively permanent
and takes the project's name with it. Show HN is one shot. So `helix_ops` does
everything around the post — facts, drafts, verification, tracking, the next
action — and sends nothing anywhere.

**The part worth keeping: the drafts are checked by the product.** Every launch
post claims a version, an install command and a count, and those decay. A post
written on Tuesday and published on Friday can already be wrong, in the first
thing a stranger ever reads about this project. So no draft contains a
hand-typed number: facts are read from the files that define them, and the
finished text is then run through `helix_grounding` and refused if any figure
is not one the repository can produce. The BOM reviewer holds a customer's
generated documents to that standard; there was no principled reason the
company's own outreach should be held to a looser one.

**A real gap found while building it, and fixed rather than papered over.** The
first version of that check reported "grounded: 0 claims verified" on every
draft — it was verifying nothing, because the library's `QuantityExtractor`
deliberately ignores bare integers. That restraint is correct for BOM prose,
where a bare integer is more often a list position than a count. A launch post
inverts it: "0 runtime dependencies" and "255 tests" *are* the claim. The fix
was a domain-local `CountExtractor` passed through `Verifier(extractors=...)`,
the extension point the library already provides — not a loosening of the
shared default, which would have pushed noise onto every other caller. A check
that silently verifies nothing is worse than no check, because it reads as
safety.

**The strategy is enforced, not described.** Three rules from `FIRST_USERS.md`
are now executable: one channel at a time (the next channel is withheld while a
bug report is unresolved), Show HN stays locked until prerequisites are
recorded met, and prerequisites are *recorded* rather than inferred — whether
the package is on PyPI is a fact about the world, and this module runs offline
by design. Only a person who actually ran the tool counts toward M2; upvotes
and encouraging comments are proxies for the one event the roadmap closes on.

**Verification, not assertion:** the load-bearing test corrupts exactly one
figure in a rendered post and asserts the check rejects it, plus a second test
asserting the check extracts a non-trivial number of claims at all — because
the failure mode found during the build was a check that passed while measuring
nothing. A bug in `measure_tests` was found by its own test and fixed: when
every test fails there is no "N passed" line, so the parse error fired before
the exit-code check and reported "could not read the output", sending the
reader to debug pytest instead of their failing tests. An accurate refusal with
a misleading reason is its own bug. 291 tests pass, up from 255.

**On shares and stock, which was asked about directly.** Sorted into the
internal ownership checklist rather than answered here, and the honest answer is that
it is not a question yet: an LLC has membership interests rather than shares,
and equity becomes real only when a second person is involved — at which point
it is securities law and needs a professional, with no template version. What
costs nothing today is a dated contribution record, so that a future cap table
reflects what happened rather than what anyone remembers. Git history already
covers the code; the ledger covers the rest.

**Cost impact:** none in dependencies — `helix_ops` is stdlib plus this
project's own library. It is kept out of the wheel for the same reason
`helix_api` is, and a stronger one: nobody installing a verification library
should receive a launch tracker.

**Future implications:** the next real event is a person who is not the author
running the tool. Everything in this entry is preparation for that, and
preparation is exactly what this project has historically over-invested in — so
the honest reading of `helix_ops status` is that it currently reports three
unmet prerequisites and zero strangers, and it will keep reporting that until
somebody opens an account.

## D-048 — Mine the archive instead of monitoring the stream

**Decision:** build `helix_signal` as a miner over an existing question archive
rather than the 24/7 monitor the specification described, and keep the
clustering deterministic and dependency-free.

**Why:** the volume was measured before anything was built.
`electronics.stackexchange.com` has had zero new "bill of materials" questions
in ninety days and gets roughly one KiCad question every nine days. A poller on
a five-minute cycle would spend 288 of a 300-request daily quota to find about
one relevant question a week. The same source holds 10,823 questions written
over sixteen years, which answers a better question than "what arrived today":
what has gone wrong repeatedly, for long enough that it is not a fashion.

**Alternatives considered.** An embedding model would group by meaning rather
than vocabulary and would catch the two people describing one problem in
different words — which this cannot. It was rejected for the same reason the
rest of this codebase computes rather than infers: a model asked to group ten
thousand questions cannot tell you which words made a group, cannot be re-run to
the same answer, and adds a dependency to a project whose selling point is that
it has none. The limitation is real and is written into `cluster.py` and
`DEMAND_EVIDENCE.md` rather than glossed.

**What it found:** 42% of everything that grouped is about operating a design
tool rather than about electronics. See `docs/DEMAND_EVIDENCE.md`.

**Two mistakes worth recording, because both are this project's recurring
failure in new clothing.**

The first ranking was topped by six groups of four questions, each winning on a
percentage computed from three of them, while a group of 137 sat at rank five.
Nothing was broken and the arithmetic was right; it was a confident number that
meant nothing. Every proportion is now pulled toward the corpus rate by weight
k/(n+k), so a small group has to be extraordinary to move at all.

The first draft of the findings document reported the headline group as an
unmet need with four unanswered questions. All eight have accepted answers. The
tool had printed the vote count as a bare `[ 0]` and the author read it as an
answer count — a display that could be misread, read wrong by the first person
to read it. The column is now labelled, and the correction is left in the
document rather than quietly fixed.

**Cost impact:** none in dependencies. `helix_signal` is stdlib only and stays
out of the wheel, like `helix_ops` and `helix_api`. The harvested corpus is
gitignored: it is several megabytes of other people's CC BY-SA prose, and what
belongs in the repository is what this project derived from it plus the links
back.

**Future implications:** the monitor is not cancelled, it is unbuilt until there
is something to monitor. The candidate source with live volume is Reddit, which
is blocked on a contract nobody here can sign — recorded as data in
`sources/base.py` rather than as a comment somebody has to remember.

## D-049 — Read the answers, not just the questions

**Decision:** add `mine.py answers`, and treat "answered" as a question to
investigate rather than a fact to report.

**Why:** D-048's write-up called a group of BOM questions an unmet need. All
eight were marked answered, so the claim was withdrawn. Then the answers were
read, and the picture inverted again: not one of the twenty points at a feature
that solves the problem. They say write a ULP script, hand-edit the component
database row by row, build an internal part-number system, rename your parts and
`grep -v` them out — one answerer writes "this is not what you asked for". The
group is answered and not solved, and those are different claims that no
question-level field distinguishes.

**Three measurement faults found, all the same fault.**

`is_answered` does not mean "has an accepted answer". Stack Exchange sets it
when a question has an accepted answer *or* an answer scoring one or more. Of
the eight, five had anything accepted. The field name was read as its definition
and never checked, and two documents were written on it.

"By hand" and "manually" mean writing code in one context and holding a
soldering iron in another. In the pick-and-place group, four of six manual-work
hits were people soldering, handling reels and counting parts — work no program
removes. That group had been recommended as the next product line on the
strength of a 30% rate that is nearer 10%. It is downgraded.

The same words sat in the answer classifier's "hands back a scripting job"
bucket, where they had no business being: hand-soldering is not code. Removing
them took that group from 58% to 33%.

**What survived.** Group 40 held up under the same scrutiny — three of its four
manual-work hits are genuine software toil, its answers really are workarounds,
and the accepted answer to "can I order from a BOM?" says vendor import works
fine *as long as the manufacturer part numbers are already in there*. That names
the bottleneck as the step before the one the market already serves, which is
where this project's tool sits. Manufacturer part number enrichment is now
evidenced rather than assumed.

**Cost impact:** two API requests. The answers are cached beside the corpus and
`--offline` refuses to spend anything.

**Future implications:** the rule this project keeps relearning is that a rate
computed over a few dozen items is an index and not a finding. Reading thirty
items caught three wrong conclusions here and cost minutes. `summarise()` now
prints "not a finding — read the answers" on every run, and `score.py` carries
the limitation in a comment beside the word list that causes it, because the
next person to use that list will be in a different domain where "by hand" means
something else again.

## D-050 — Distributor enrichment, built on the evidence rather than the plan

**Decision:** add `helix-bom enrich`, a check of a BOM's part numbers against a
distributor, with adapters for Mouser and Digi-Key and a loudly-labelled offline
catalogue for the demo.

**Why this and not something else.** D-049 read twenty answers to eight
questions about getting a usable BOM out of a CAD tool. The accepted answer to
"can I order components from a BOM?" was *yes, vendor import works fine — as
long as you have a manufacturer part number in there*. Every distributor already
solves ordering; Octopart, Digi-Key's BOM manager and Arena all assume the BOM
arriving is already correct. Nobody serves the step before that. That is where
this tool sits, and it is the first feature here chosen from measured demand
rather than from what seemed useful.

**The shape follows from three rules this project already had.**

Nothing is invented. That is what `components.py` was written to prevent and
what the whole library is for; a lookup that fails says so.

"Not found" and "not checked" are different answers, and `Outcome` has three
values rather than two. A run with no API key must not produce forty critical
findings saying the parts do not exist. This is the same failure as the
physical-fit check that passed silently on a BOM with no dimensions in it, and
it got the same treatment: the not-checked count is printed above the findings,
with the reason for each.

A cached price is not a current price. Every offer carries its fetch time and
the report prints the age. Caching was not optional — Mouser allows a thousand
calls a day and thirty a minute, and a two-hundred-line BOM re-run five times
spends the day.

**Two mistakes caught while building it, both of the usual kind.**

The offline catalogue holds six parts and returned NOT_FOUND for everything
else. Run against the real sample BOM it produced nine CRITICAL findings
announcing that STM32F401RET6, RC0603FR-0710KL and seven other jellybean parts
do not exist — a demo catalogue passing itself off as the market. It returns
NOT_CHECKED now, and a test pins it.

`helix-bom enrich` on an unparseable file gave a traceback where `review` gives
a sentence, because `load_bom` raises rather than returning empty. Caught by a
test that expected the friendly path.

**What has not been proven.** The Mouser and Digi-Key adapters have never spoken
to the live APIs. Credentials require an account and the account terms are the
account holder's to read and accept, so the parsing is tested against recorded
fixtures and the network is not tested at all. Rather than let that sit as an
unstated gap, `verified_against_live_api` is a field on the capability record,
it is False, the report prints a note whenever an unverified adapter is used,
and `--check-key` exists so the first person with a real key can settle it in
one command. The honest version of shipping something untested is shipping it
with the untested part labelled.

**Cost impact:** none in dependencies; stdlib only, as with everything else in
the wheel. Prices are `Decimal` rather than `float` throughout, and the money
parser handles both comma and point decimal conventions because confusing them
is a factor-of-a-thousand error on a reel.

**Future implications:** the interface takes a distributor, so LCSC, Farnell or
Octopart are additions rather than rewrites. Nothing in the layer can spend
money — there is no ordering method and the base class has none to override —
and that should stay true: this answers questions about parts, and buying them
is a person's decision made on a distributor's own site.

## D-051 — The detector was publishing the names it was built to hide

**Decision:** move the identifying half of the personal-details pattern out of
the repository, exclude the internal packages from the sdist, and add two gate
checks — one that reads the exempted files for names, one that reads the built
artifacts rather than the working tree.

**What happened.** With `helix-bom enrich` finished and the release gate at 7/7,
the last step before uploading 0.2.0 to PyPI was to inspect the artifacts. The
sdist contained `src/helix_ops/release.py`, and line 40 of that file was the
operator's full legal name, written as a regex literal.

It had been there since the detector was written. It is in the public GitHub
repository. It would have gone to PyPI, where a version cannot be withdrawn and
mirrors copy within hours.

**Why nothing caught it.** Three failures compounding, each individually
reasonable.

The detector exempts `release.py`, because a file holding a pattern of forbidden
words necessarily contains them. True, and the exemption was argued for at the
time — but an exemption is a place the gate stops looking, and what it stopped
looking at was the one file guaranteed to contain a name.

The wheel excludes the internal packages and the sdist did not. `packages` and
`include` are different lists in different sections, and only the first had ever
been thought about. The gate's "wheel contents" check reads the `packages` line
in `pyproject.toml` — a string, not an archive — so it could not have noticed.

Every check in the gate reads the working tree. The working tree is not what
gets published.

This is the same shape as the detector that excluded the folder holding the
problem, and as the grounding check that verified zero claims and reported a
pass. A check with a blind spot built into it, reporting clean.

**The fix.** Names live in `private/identity.txt`, which is gitignored; the
generic terms, which name nobody, stay in the source. `check_exempt_files_name_nobody`
reads the exempted files for names, so the exemption no longer covers the thing
that matters. `check_built_artifacts` opens the wheel and the sdist and reads the
files that would actually be uploaded. A missing identity list fails both checks
rather than passing them, because a name scanner with no names finds nothing.

The test fixtures were leaking too, in a smaller way: they planted a real term
from the pattern as a literal, so that term shipped in every sdist. They now read
a canary from the gitignored list and skip when it is absent. Writing the
docstring that explains this reintroduced the phrase, and the new artifact scan
caught that on the next build.

**Cost impact:** none. Two checks, one gitignored file, and an sdist about a
quarter smaller.

**What is still outstanding, and is not this repository's decision.** The name
sits in three commits of a public repository and has since it was made public.
Removing it from `HEAD` stops it spreading; removing it from history needs
another rewrite and probably another delete-and-recreate, and GH Archive may
hold copies regardless. That is the operator's call to make, not this log's.

## D-052 — The history rewrite, and the check that should have made it unnecessary

**What was done.** `git filter-repo` over a fresh clone of the public repository,
replacing the name-bearing line in nine blob versions of `src/helix_ops/release.py`
and mapping one personal email address onto the noreply one. Verified across 381
objects: zero occurrences in file contents, commit messages, author and committer
identities, or tag taggers. The HEAD tree came out byte-for-byte identical to the
released one, so the rewrite touched history and nothing else. Force-pushed, tags
included.

**Two things the rewrite turned up that the scan had not.**

`refs/heads/master` was still alive locally, pointing at an orphan root commit
authored from a personal address — a leftover from the *previous* rewrite,
which had renamed the branch and never deleted the old one. It had never been
pushed, so it was local-only, but it is exactly how a supposedly-scrubbed name
survives: not in the tree, not on the remote, sitting on a branch nobody looks
at. Deleted, reflogs expired, repacked.

The tag `v0.1.1` still resolves to a pre-rewrite commit SHA, which looked alarming
and is correct: the name entered `release.py` after 0.1.1, so commits before that
point were unchanged and kept their identifiers. Worth writing down because it
will look wrong again to whoever checks next.

**A force-push is not a deletion.** GitHub keeps unreachable objects and serves
them by SHA. The old blob was fetched back through the API after the push, name
intact. Deleting and recreating the repository is the reliable remedy.

**Resolved.** The repository was deleted through the web interface — the CLI
token has `repo` but not `delete_repo`, and an interactive scope refresh kept
timing out, while the web route needed no new permission at all. Recreated and
repushed from the working repository rather than from the rewrite clone, which
had gone two commits stale and would have restored old history; the restore
script re-runs the history scan before it pushes anything, for that reason.

Verified afterwards against a fresh clone of the public repository: 389 objects,
zero occurrences, one identity, and the pre-rewrite blob and commits now return
404 by SHA. One blob that still resolves is a current version of this file that
names nobody — checked rather than assumed, because "an object is still served"
and "the name is still there" are different claims.

**The check that follows from it.** The gate read the working tree, then the
exempted files, then the built artifacts — and never read history, which is
where a name survives long after it is deleted from HEAD and where the fix costs
a rewrite instead of an edit. `check_history_names` scans every object, every
commit message, every author and committer identity and every tag tagger, across
all refs. It runs in 0.2 seconds on this repository. It would have failed the
day the name was committed, which is eleven days before the repository was made
public.

Six tests, each a way this actually goes wrong: a name deleted from HEAD but
alive in history; a name in a commit message; a name in an author identity; a
stale branch keeping an orphan root alive; a history too large to scan, which
fails rather than reporting a clean partial result; and the real repository,
which passes now and would not have yesterday.

**Cost impact:** 0.2 seconds per release check.

**Future implications:** the gate now looks in four places — tree, exemptions,
history, artifacts. That list is the honest shape of the question "could this
reach a stranger", and each entry was added after something got through the
previous three.

## D-053 — A feature behind a door most people will not open

**Decision:** make `helix-bom enrich` do real work with no API key, by adding
six checks that need only the file, and demote distributor lookup from being the
whole feature to being a bonus on top of them.

**Why.** 0.2.0 shipped `enrich` as its headline feature. Run without a
distributor account it produced this, in full:

    10 lines, 0 looked up, 10 not looked up
    10 of 10 lines were NOT CHECKED. This is not a clean bill:
        10 x Mouser needs MOUSER_API_KEY in the environment.

Ten lines, zero checked, one message repeated ten times. Every test passed, the
gate was green, the release was verified from a clean venv — and the thing was
useless to anybody who had not opened a trade account. In a project whose entire
first-user strategy is that a stranger installs it and reports a bug, that is
not a small miss. It is the feature not existing for the people it was for.

The mistake was not in the building. It was in choosing what to build without
asking whether the operator would open the accounts it depended on. When the
answer turned out to be no, the feature became inert, and only then did anyone
run it the way a stranger would.

**What the checks are, and why these six.** Every one is a defect that ships
boards wrong and is visible without a network: no part number at all; a value
in the part number column; a placeholder; the same part on two lines; the same
designator on two lines; designators that do not match the quantity.

The first is not a guess. `docs/DEMAND_EVIDENCE.md` reads twenty answers to
eight questions about getting a usable BOM out of a CAD tool, and the commonest
defect in them was not a wrong part number — it was no part number.

**The false positive that shaped the value rule.** Its first version called
`61300411121` — a real Wurth part number — "a value, not a part number", and
marked it CRITICAL. Numeric part numbers are ordinary: Wurth, Molex and TE all
use them. The rule now requires a unit, so a bare number is left alone. That
costs it `10` for a ten-ohm resistor, and that is the right way to be wrong. A
missed defect is a nuisance; a confident accusation against correct work is why
somebody stops using a tool.

**A clean report now states its own scope.** "Nothing wrong found" after a
structural pass and after a distributor confirmed every part are very different
claims, and they printed the same sentence. They no longer do. This is the same
rule as `SkippedCheck` and the three-valued `Outcome`, applied to the sentence
that reads most like a pass.

**Cost impact:** none. Stdlib only, no network, no configuration. `Component`
gained a `designator` field that both readers already had and both discarded.

**Future implications:** the general lesson is not about distributors. It is
that a feature depending on something the operator has not agreed to do is a
feature that does not exist yet, and the way to find that out is to run it as a
stranger would before shipping it — not after.

## D-054 — Check the adapter against the schema, since the API is out of reach

**Decision:** verify the Mouser adapter's request and response shapes against
Mouser's published Swagger document, and record that Digi-Key cannot be checked
the same way.

**Why.** Both adapters were written from documentation summaries and memory, and
neither can be run: getting credentials needs a trade account the operator is
not opening. "Never tested" was the honest label but not the end of what could
be done. `https://api.mouser.com/api/docs/v1` is public, and comparing field
names against it is real verification that needs no key.

**What it found.** The envelope, the `Parts` array, the `apiKey` query
parameter, the templated version in the path and `partSearchOptions=Exact` were
all correct. Three fields were being ignored — `IsDiscontinued`,
`SuggestedReplacement`, `ProductAttributes` — and one, `Package`, does not
exist, so the code that looked for it fell through to the product category on
every part and always had.

`SuggestedReplacement` is the one worth having. An obsolete part is a dead end;
an obsolete part with the distributor's own suggested replacement beside it is
something the reader can act on. It is quoted as theirs and never substituted.

**What it could not settle.** The request field is `mouserPartNumber` and its
description says "the specific Mouser part number", while this endpoint is what
every client uses for manufacturer part numbers. A schema cannot answer that; a
key can, and `--check-key` probes with an MPN for exactly this reason.

Digi-Key's specification sits behind an authenticated portal, so its shapes stay
unverified. That asymmetry is now written into both adapters rather than left
for a reader to assume they were treated alike.

**Cost impact:** none. One public document, read once.

**Future implications:** the schema allows ten part numbers per request. Against
a thousand-a-day limit and a two-hundred-line BOM that is a tenfold saving and
the largest efficiency left in this layer. Not built, and recorded here so it is
a decision rather than an oversight.

A note kept because it is unresolved rather than solved: during this work the
suite failed once on `test_measuring_actually_runs_the_suite` and then passed
four times running. The likeliest explanation is a stale `__pycache__` caught
mid-edit, but that was not demonstrated, and a cause that was guessed at is not
a cause. If it recurs, this is the first place to look.
