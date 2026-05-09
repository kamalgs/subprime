"""Tiny in-process asyncpg-shaped pool for events / feedback tests.

Only the subset of operations needed by ``subprime.feedback`` and the
v2 events / feedback routes is implemented. The goal is fidelity to the
asyncpg surface (acquire / transaction / fetch / executemany), not a
general-purpose SQL engine — we keyword-route SQL into Python lists.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


class _Tx:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    async def __aenter__(self) -> "_Tx":
        self._conn._in_tx = True
        self._conn._tx_snapshot = (
            list(self._conn._db.events),
            list(self._conn._db.conversations),
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # Roll back to snapshot
            events, convs = self._conn._tx_snapshot
            self._conn._db.events = events
            self._conn._db.conversations = convs
        self._conn._in_tx = False
        self._conn._tx_snapshot = None


class _FakeConn:
    def __init__(self, db: "_FakeDB") -> None:
        self._db = db
        self._in_tx = False
        self._tx_snapshot: Any = None

    def transaction(self) -> _Tx:
        return _Tx(self)

    async def execute(self, sql: str, *args: Any) -> str:
        sql_norm = " ".join(sql.split()).upper()
        if (
            sql_norm.startswith("ALTER TABLE")
            or sql_norm.startswith("CREATE TABLE")
            or sql_norm.startswith("CREATE INDEX")
            or "ALTER TABLE" in sql_norm
        ):
            # init_feedback issues a multi-statement DDL — no-op here.
            return "CREATE TABLE"
        if sql_norm.startswith("INSERT INTO SESSION_EVENTS"):
            session_id, kind, payload_json = args
            payload = json.loads(payload_json) if payload_json else None
            self._db.events.append(
                {
                    "id": self._db._next_event_id(),
                    "session_id": session_id,
                    "kind": kind,
                    "payload": payload,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            return "INSERT 0 1"
        if sql_norm.startswith("INSERT INTO CONVERSATIONS"):
            # Used by save_conversation in tests that seed a conversation
            session_id = args[0]
            self._db.conversations.append(
                {
                    "id": self._db._next_conv_id(),
                    "session_id": session_id,
                    "feedback": None,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            return "INSERT 0 1"
        if sql_norm.startswith("UPDATE CONVERSATIONS"):
            payload_json, session_id = args
            payload = json.loads(payload_json)
            # Latest-by-created_at semantics
            candidates = [c for c in self._db.conversations if c["session_id"] == session_id]
            if not candidates:
                return "UPDATE 0"
            candidates.sort(key=lambda c: c["created_at"], reverse=True)
            target_id = candidates[0]["id"]
            for c in self._db.conversations:
                if c["id"] == target_id:
                    c["feedback"] = payload
                    return "UPDATE 1"
            return "UPDATE 0"
        raise NotImplementedError(f"Fake DB cannot execute: {sql!r}")

    async def executemany(self, sql: str, rows: list[tuple]) -> None:
        for row in rows:
            await self.execute(sql, *row)

    async def fetch(self, sql: str, *args: Any) -> list[dict]:
        sql_norm = " ".join(sql.split()).upper()
        if "FROM SESSION_EVENTS" in sql_norm and "WHERE SESSION_ID" in sql_norm:
            session_id, limit = args
            rows = [e for e in self._db.events if e["session_id"] == session_id]
            rows.sort(key=lambda r: r["id"])
            return [dict(r) for r in rows[:limit]]
        raise NotImplementedError(f"Fake DB cannot fetch: {sql!r}")

    async def fetchrow(self, sql: str, *args: Any) -> dict | None:
        rows = await self.fetch(sql, *args)
        return rows[0] if rows else None


class _Acq:
    def __init__(self, db: "_FakeDB") -> None:
        self._db = db

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._db)

    async def __aexit__(self, *a) -> None:
        return None


class _FakeDB:
    """Shared mutable state across all connections from one pool."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.conversations: list[dict] = []
        self._event_seq = 0
        self._conv_seq = 0

    def _next_event_id(self) -> int:
        self._event_seq += 1
        return self._event_seq

    def _next_conv_id(self) -> int:
        self._conv_seq += 1
        return self._conv_seq


class FakePool:
    """asyncpg.Pool stand-in. Use as a drop-in for ``get_pool()``."""

    def __init__(self) -> None:
        self._db = _FakeDB()

    def acquire(self) -> _Acq:
        return _Acq(self._db)

    async def execute(self, sql: str, *args: Any) -> str:
        async with self.acquire() as conn:
            return await conn.execute(sql, *args)

    async def fetch(self, sql: str, *args: Any) -> list[dict]:
        async with self.acquire() as conn:
            return await conn.fetch(sql, *args)

    # Test inspection helpers
    def seed_conversation(self, session_id: str) -> int:
        self._db._conv_seq += 1
        cid = self._db._conv_seq
        self._db.conversations.append(
            {
                "id": cid,
                "session_id": session_id,
                "feedback": None,
                "created_at": datetime.now(timezone.utc),
            }
        )
        return cid

    def get_conversation(self, conversation_id: int) -> dict | None:
        for c in self._db.conversations:
            if c["id"] == conversation_id:
                return c
        return None

    def latest_conversation(self, session_id: str) -> dict | None:
        rows = [c for c in self._db.conversations if c["session_id"] == session_id]
        rows.sort(key=lambda c: c["created_at"], reverse=True)
        return rows[0] if rows else None

    def all_events(self, session_id: str | None = None) -> list[dict]:
        rows = self._db.events
        if session_id is not None:
            rows = [e for e in rows if e["session_id"] == session_id]
        return rows


# Keep a regex around in case future tests need it; not used in core flow.
_ID_RE = re.compile(r"\$(\d+)")
