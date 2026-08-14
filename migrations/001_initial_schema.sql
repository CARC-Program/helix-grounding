-- HELIX NEXUS — Production database schema, per DATABASE_ARCHITECTURE.md
-- Tested against real PostgreSQL 16 + pgvector 0.6.0, not a stand-in.
--
-- Run as: psql -d helix_nexus -f 001_initial_schema.sql

-- Clients: pilot/retainer client records (empty until Phase 0 produces one
-- — no synthetic client rows are inserted by this migration)
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    niche TEXT NOT NULL,          -- e.g. 'electronics_bom_consulting'
    status TEXT NOT NULL DEFAULT 'prospect',  -- prospect | free_review | retainer | churned
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Agent actions: full audit trail, per AI_SAFETY_CONSTRAINTS.md Section 3.
-- Authorization tier is enforced at the CHECK constraint level, not just
-- in application code -- a malformed tier value is rejected by the
-- database itself, not just by the orchestrator.
CREATE TABLE agent_actions (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    agent_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    authorization_tier TEXT NOT NULL
        CHECK (authorization_tier IN ('read-only', 'reversible', 'consequential')),
    summary TEXT NOT NULL,
    approved_by_human BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deliverables: generated reports/outputs, linked to client + action
CREATE TABLE deliverables (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    agent_action_id INTEGER REFERENCES agent_actions(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Memory embeddings: pgvector column for semantic recall, per
-- AI_MEMORY_SYSTEM.md. Dimension 1536 matches common embedding-model
-- output size; adjust to whatever embedding model is actually selected
-- once LLM wiring is complete -- not fixed in stone here.
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    source_type TEXT NOT NULL,   -- e.g. 'client_history', 'business_pattern'
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Evolution log: proposal/sandbox-result/approval records, per
-- AI_EVOLUTION_PROTOCOL.md
CREATE TABLE evolution_log (
    id SERIAL PRIMARY KEY,
    proposal_summary TEXT NOT NULL,
    sandbox_metrics JSONB,
    human_approved BOOLEAN,
    deployed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes worth having from day one, not retrofitted later
CREATE INDEX idx_agent_actions_client ON agent_actions(client_id);
CREATE INDEX idx_agent_actions_tier ON agent_actions(authorization_tier);
CREATE INDEX idx_deliverables_client ON deliverables(client_id);
CREATE INDEX idx_memory_embeddings_client ON memory_embeddings(client_id);

-- pgvector similarity search index (HNSW -- per pgvector 0.6.0's
-- supported access methods, confirmed above via \dx)
CREATE INDEX idx_memory_embeddings_vector ON memory_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- IMPORTANT: if this migration is run by a superuser/admin role (as it
-- was during sandbox testing) rather than the application role itself,
-- tables are owned by whoever ran it -- the application role gets no
-- access by default. Caught this exact bug during sandbox testing
-- (D-022). Run this explicitly to fix it, or run the whole migration
-- as the application role in the first place to avoid it entirely:
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO helix_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO helix_app;
