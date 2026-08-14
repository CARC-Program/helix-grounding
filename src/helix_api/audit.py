"""
HELIX NEXUS — Audit logging, per AI_SAFETY_CONSTRAINTS.md Section 3 and
DATABASE_ARCHITECTURE.md's agent_actions table.

SCOPE NOTE: production uses Postgres+pgvector (DATABASE_ARCHITECTURE.md).
SQLite is used here as a local, dependency-free stand-in so the schema
and query logic can be sandbox-tested without standing up a full Postgres
instance. Schema below is a deliberately simplified subset of the real
agent_actions table — enough to test the logging contract, not the full
production schema.
"""

import sqlite3
import threading
import time
from dataclasses import dataclass


@dataclass
class ActionLogEntry:
    agent_name: str
    action_type: str
    authorization_tier: str  # "read-only" | "reversible" | "consequential"
    summary: str
    timestamp: float


class AuditLog:
    def __init__(self, db_path: str = ":memory:"):
        # check_same_thread=False + an explicit lock: FastAPI (and most
        # WSGI/ASGI servers) run request handlers in a worker thread pool,
        # not the thread the connection was created in. SQLite forbids
        # cross-thread use by default; the lock serializes writes so this
        # stays correct rather than just silencing the error. Production
        # uses Postgres via a connection pool (DATABASE_ARCHITECTURE.md),
        # which doesn't have this constraint — this is a sandbox-only fix.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                authorization_tier TEXT NOT NULL,
                summary TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        self._conn.commit()

    def log(self, entry: ActionLogEntry) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO agent_actions (agent_name, action_type, authorization_tier, summary, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry.agent_name, entry.action_type, entry.authorization_tier, entry.summary, entry.timestamp),
            )
            self._conn.commit()
            return cur.lastrowid

    def all_entries(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT agent_name, action_type, authorization_tier, summary, timestamp FROM agent_actions ORDER BY id"
            ).fetchall()
            return [ActionLogEntry(*row) for row in rows]

    def count_by_tier(self, tier: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM agent_actions WHERE authorization_tier = ?", (tier,)
            ).fetchone()
            return row[0]
