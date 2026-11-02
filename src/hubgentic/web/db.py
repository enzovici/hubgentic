"""SQLite persistence for the multi-tenant web app (accounts, not catalog data).

The catalog itself stays request-scoped and holds nothing at rest; this store
only keeps who may use it: tenants, users, memberships, sessions, invites, API
keys, per-tenant source governance, the query audit log and product feedback.

Tenant isolation rule: every tenant-owned table carries `tenant_id`, and every
query against one filters on it. No helper here reads tenant-owned rows
without a tenant id argument.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'sandbox',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
    token_hash  TEXT PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    created_by  INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    accepted_by INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    prefix       TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at   TEXT
);
CREATE TABLE IF NOT EXISTS tenant_sources (
    tenant_id  INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_id  TEXT NOT NULL,
    enabled    INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, source_id)
);
CREATE TABLE IF NOT EXISTS queries (
    id           INTEGER PRIMARY KEY,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor        TEXT NOT NULL,
    channel      TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    criteria     TEXT NOT NULL,
    request_id   TEXT,
    status       TEXT NOT NULL,
    records      INTEGER NOT NULL DEFAULT 0,
    duration_ms  INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS queries_tenant_created ON queries (tenant_id, created_at DESC);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY,
    tenant_id   INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    page        TEXT,
    sentiment   TEXT,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
-- Requests from the marketing site's contact form (www.hubgentic.ai).
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    company     TEXT,
    segment     TEXT,
    interests   TEXT,
    message     TEXT,
    lang        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Thin wrapper over one SQLite file. One connection per thread."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._local = threading.local()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._local.conn = conn
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def one(self, sql: str, *args: Any) -> sqlite3.Row | None:
        return self._conn().execute(sql, args).fetchone()

    def all(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        return self._conn().execute(sql, args).fetchall()

    def run(self, sql: str, *args: Any) -> int:
        with self.tx() as conn:
            return conn.execute(sql, args).lastrowid or 0

    # ── tenants & membership ────────────────────────────────────────────

    def tenants_for_user(self, user_id: int) -> list[sqlite3.Row]:
        return self.all(
            "SELECT t.*, m.role FROM tenants t JOIN memberships m ON m.tenant_id = t.id "
            "WHERE m.user_id = ? ORDER BY t.name",
            user_id,
        )

    def membership(self, user_id: int, slug: str) -> sqlite3.Row | None:
        """The tenant row (plus the caller's role) iff the user belongs to it."""
        return self.one(
            "SELECT t.*, m.role FROM tenants t JOIN memberships m ON m.tenant_id = t.id "
            "WHERE m.user_id = ? AND t.slug = ?",
            user_id,
            slug,
        )

    def disabled_sources(self, tenant_id: int) -> set[str]:
        rows = self.all(
            "SELECT source_id FROM tenant_sources WHERE tenant_id = ? AND enabled = 0",
            tenant_id,
        )
        return {r["source_id"] for r in rows}

    def log_query(
        self,
        tenant_id: int,
        *,
        actor: str,
        channel: str,
        entity_type: str,
        criteria: dict[str, Any],
        request_id: str | None,
        status: str,
        records: int,
        duration_ms: int,
    ) -> None:
        self.run(
            "INSERT INTO queries (tenant_id, actor, channel, entity_type, criteria, "
            "request_id, status, records, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tenant_id, actor, channel, entity_type, json.dumps(criteria),
            request_id, status, records, duration_ms, now(),
        )


def default_db_path() -> Path:
    return Path(os.environ.get("HUBGENTIC_DB", Path.cwd() / "var" / "hubgentic.db"))
