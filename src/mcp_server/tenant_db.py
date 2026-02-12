"""Tenant database: maps tenant_id -> K4 (Client API token).

SQLite-backed. Each tenant's K4 is a bearer token scoped to that tenant
in the Client API. The MCP Gateway looks up K4 after extracting tenant_id
from the validated T1 JWT.

See AUTH_DECISION.md for the full key/token reference.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

_DB_PATH = os.environ.get("MCP_TENANT_DB_PATH", "tenants.db")


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with auto-created schema."""
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            api_token TEXT NOT NULL,
            name TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    return conn


def get_tenant_token(tenant_id: str) -> str | None:
    """Look up K4 for a tenant. Returns None if not found (fail closed)."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT api_token FROM tenants WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        return row[0] if row else None


def add_tenant(tenant_id: str, api_token: str, name: str = "") -> None:
    """Register a tenant with their K4 token."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tenants (tenant_id, api_token, name)"
            " VALUES (?, ?, ?)",
            (tenant_id, api_token, name),
        )


def remove_tenant(tenant_id: str) -> bool:
    """Remove a tenant. Returns True if found and removed."""
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM tenants WHERE tenant_id = ?", (tenant_id,)
        )
        return cur.rowcount > 0


def list_tenants() -> list[dict]:
    """List all registered tenants (without tokens)."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT tenant_id, name, created_at FROM tenants"
        ).fetchall()
        return [
            {"tenant_id": r[0], "name": r[1], "created_at": r[2]} for r in rows
        ]
