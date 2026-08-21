"""
database/db.py — thin wrapper around pyexasol for the two identities this
project uses: a read-write connection (orchestrator/agents) and a read-only
connection (chat agent only).

Kept deliberately small: this is not an ORM. Agents call execute()/fetchall()
with parameterized SQL; the orchestration layer owns transaction boundaries.
"""

from contextlib import contextmanager
import ssl
from typing import Any, Iterable

import pyexasol

from config import ExasolConnection, Settings


def _connect(conn: ExasolConnection):
    return pyexasol.connect(
        dsn=conn.dsn,
        user=conn.user,
        password=conn.password,
        schema=conn.schema,
        compression=True,
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},
    )


class Database:
    """Read-write handle. Used by ingestion, extraction, reasoning, action,
    human-review and audit-log code — i.e. everything except the chat agent.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

    @contextmanager
    def connection(self):
        conn = _connect(self._settings.exasol_rw)
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        with self.connection() as conn:
            conn.execute(sql, params or {})

    def fetchall(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        with self.connection() as conn:
            stmt = conn.execute(sql, params or {})
            return stmt.fetchall()

    def executemany(self, sql: str, rows: Iterable[dict[str, Any]]) -> None:
        with self.connection() as conn:
            conn.ext.insert_multi(sql, rows) if hasattr(conn, "ext") else [
                conn.execute(sql, row) for row in rows
            ]


class ReadOnlyDatabase:
    """Read-only handle for the chat agent. Connects with the same
    read-only identity the starter kit's MCP server uses, so a bad or
    injected query is rejected by Exasol's own grants — not just by
    application-level SQL validation. See docs/mcp-grants.sql.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

    @contextmanager
    def connection(self):
        conn = _connect(self._settings.exasol_ro)
        try:
            yield conn
        finally:
            conn.close()

    def fetchall(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        with self.connection() as conn:
            stmt = conn.execute(sql, params or {})
            return stmt.fetchall()
