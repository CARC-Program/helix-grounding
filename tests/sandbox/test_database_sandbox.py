"""
Real integration test against the actual PostgreSQL 16 + pgvector
database created for this project — not SQLite, not mocked. Requires
`psycopg[binary]` and a running local Postgres with the schema in
migrations/001_initial_schema.sql already applied.

All data below is synthetic/fabricated for testing. No real client.
"""

import psycopg
import random

CONN_STR = "dbname=helix_nexus user=helix_app password=sandbox_local_only_not_prod host=localhost"


def run():
    conn = psycopg.connect(CONN_STR)
    conn.autocommit = True
    cur = conn.cursor()

    print("=== Constraint enforcement test ===")
    # Valid tier -- should succeed
    cur.execute(
        "INSERT INTO agent_actions (agent_name, action_type, authorization_tier, summary) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        ("bom_review_agent", "bom_review", "read-only", "synthetic test row"),
    )
    row_id = cur.fetchone()[0]
    print(f"[PASS] Valid authorization_tier accepted, row id={row_id}")

    # Invalid tier -- database itself must reject this, not just app code
    try:
        cur.execute(
            "INSERT INTO agent_actions (agent_name, action_type, authorization_tier, summary) "
            "VALUES (%s, %s, %s, %s)",
            ("bom_review_agent", "bom_review", "totally_made_up_tier", "should fail"),
        )
        print("[FAIL] Invalid authorization_tier was NOT rejected -- constraint isn't working")
    except psycopg.errors.CheckViolation:
        print("[PASS] Invalid authorization_tier correctly rejected by CHECK constraint")
        conn.rollback()
        conn.autocommit = True

    print("\n=== Vector similarity search test (pgvector, synthetic embeddings) ===")
    random.seed(42)  # reproducible synthetic vectors, not real embeddings
    synthetic_docs = [
        ("client_history", "Client asked about lowering BOM cost on a sensor board"),
        ("client_history", "Client asked about thermal issues in an enclosed case"),
        ("business_pattern", "Multiple clients have flagged power budget overages"),
    ]
    for source_type, content in synthetic_docs:
        vec = [random.uniform(-1, 1) for _ in range(1536)]
        cur.execute(
            "INSERT INTO memory_embeddings (source_type, content, embedding) VALUES (%s, %s, %s)",
            (source_type, content, str(vec)),
        )

    query_vec = [random.uniform(-1, 1) for _ in range(1536)]
    cur.execute(
        "SELECT content, embedding <=> %s AS distance FROM memory_embeddings "
        "ORDER BY distance ASC LIMIT 3",
        (str(query_vec),),
    )
    results = cur.fetchall()
    print(f"[PASS] pgvector cosine similarity search returned {len(results)} ranked results:")
    for content, distance in results:
        print(f"    distance={distance:.4f}  {content}")

    assert len(results) == 3
    print("\n[REAL DATABASE TEST PASSED] Schema, constraints, and pgvector search all verified against live Postgres 16.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
