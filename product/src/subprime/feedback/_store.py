"""Postgres-backed feedback + session_events store.

Schema lives here as ``CREATE TABLE / ALTER TABLE IF NOT EXISTS`` so a
fresh boot stands the surfaces up without an Alembic step (same pattern
as ``subprime.flags.init_flags``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# The feedback module deliberately avoids module-level pool state — all
# functions take a pool. This keeps it easy to test with a fake pool and
# mirrors how ``subprime.core.conversations`` is structured.

_INIT_SQL = """
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS feedback JSONB;

CREATE TABLE IF NOT EXISTS session_events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_events_session_kind
    ON session_events(session_id, kind);
"""


async def init_feedback(pool: Any) -> None:
    """Ensure the feedback column + session_events table exist.

    Idempotent. Best-effort: a Postgres failure here is logged but does
    not abort startup — the API layer surfaces 503s on its own when the
    pool isn't usable.
    """
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(_INIT_SQL)
    except Exception:
        logger.exception("feedback: could not ensure feedback schema")


async def insert_events(
    pool: Any,
    session_id: str,
    events: Iterable[tuple[str, dict | None]],
) -> int:
    """Bulk-insert events for a session in a single transaction.

    *events* is an iterable of ``(kind, payload)`` tuples. Returns the
    number of rows inserted. Atomic: if any row fails the whole batch
    rolls back.
    """
    rows = [
        (session_id, kind, json.dumps(payload) if payload is not None else None)
        for kind, payload in events
    ]
    if not rows:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """INSERT INTO session_events (session_id, kind, payload)
                   VALUES ($1, $2, $3::jsonb)""",
                rows,
            )
    return len(rows)


async def upsert_feedback(
    pool: Any,
    session_id: str,
    *,
    nps: int,
    actionable: str,
    free_text: str | None,
) -> bool:
    """Write feedback to the latest conversation for *session_id*.

    Returns True when a conversation row was updated, False when none
    exists (caller should surface 409).
    """
    submitted_at = datetime.now(timezone.utc).isoformat()
    record = {
        "nps": nps,
        "actionable": actionable,
        "free_text": free_text,
        "submitted_at": submitted_at,
    }
    payload = json.dumps(record)
    async with pool.acquire() as conn:
        # Update the most recent conversation row for this session. We
        # pin via subquery so the write only ever touches one row even
        # if (somehow) multiple conversation rows share a session_id.
        result = await conn.execute(
            """UPDATE conversations
                  SET feedback = $1::jsonb
                WHERE id = (
                    SELECT id FROM conversations
                     WHERE session_id = $2
                     ORDER BY created_at DESC
                     LIMIT 1
                )""",
            payload,
            session_id,
        )
    # asyncpg returns "UPDATE <n>"
    try:
        n = int(result.rsplit(" ", 1)[-1])
    except ValueError:
        n = 0
    return n > 0


async def fetch_session_events(
    pool: Any,
    session_id: str,
    *,
    limit: int = 500,
) -> list[dict]:
    """Return events for *session_id* in chronological order.

    Used by the admin GET endpoint and ad-hoc debugging. Capped at
    *limit* rows to keep the response bounded.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, session_id, kind, payload, created_at
                 FROM session_events
                WHERE session_id = $1
                ORDER BY id ASC
                LIMIT $2""",
            session_id,
            limit,
        )
    out = []
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = None
        out.append(
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "kind": r["kind"],
                "payload": payload,
                "created_at": (
                    r["created_at"].isoformat() if r["created_at"] is not None else None
                ),
            }
        )
    return out
