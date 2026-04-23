"""Session persistence layer: InMemory and Postgres-backed stores."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from subprime.core.models import (
    ConversationTurn,
    InvestmentPlan,
    InvestorProfile,
    Session,
    SessionSummary,
    StrategyOutline,
)


class SessionStore:
    """Base class for session stores. Subclasses must implement all methods."""

    async def get(self, session_id: str) -> Optional[Session]:
        raise NotImplementedError

    async def save(self, session: Session) -> None:
        raise NotImplementedError

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """Dict-backed session store for development and tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    async def save(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self._sessions[session.id] = session

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        return [s.to_summary() for s in sorted_sessions[:limit]]


class PostgresSessionStore(SessionStore):
    """asyncpg-backed session store for production."""

    def __init__(self, pool) -> None:
        self._pool = pool

    def _serialize_data(self, session: Session) -> str:
        """Serialize the JSONB data column contents."""
        data: dict = {}
        if session.profile is not None:
            data["profile"] = json.loads(session.profile.model_dump_json())
        if session.strategy is not None:
            data["strategy"] = json.loads(session.strategy.model_dump_json())
        if session.plan is not None:
            data["plan"] = json.loads(session.plan.model_dump_json())
        if session.strategy_chat:
            data["strategy_chat"] = [json.loads(t.model_dump_json()) for t in session.strategy_chat]
        if session.is_demo:
            data["is_demo"] = True
        if session.plan_generating:
            data["plan_generating"] = True
        if session.plan_error:
            data["plan_error"] = session.plan_error
        if session.plan_stages:
            data["plan_stages"] = list(session.plan_stages)
        return json.dumps(data)

    def _row_to_session(self, row) -> Session:
        """Deserialize a DB row back to a Session model."""
        raw = row["data"]
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            # asyncpg returns JSONB as a dict directly
            data = raw if raw is not None else {}

        profile = InvestorProfile(**data["profile"]) if data.get("profile") else None
        strategy = StrategyOutline(**data["strategy"]) if data.get("strategy") else None
        plan = InvestmentPlan(**data["plan"]) if data.get("plan") else None
        strategy_chat = (
            [ConversationTurn(**t) for t in data["strategy_chat"]]
            if data.get("strategy_chat")
            else []
        )

        return Session(
            id=row["id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            current_step=row["current_step"],
            mode=row["mode"],
            profile=profile,
            strategy=strategy,
            plan=plan,
            strategy_chat=strategy_chat,
            is_demo=bool(data.get("is_demo", False)),
            plan_generating=bool(data.get("plan_generating", False)),
            plan_error=data.get("plan_error"),
            plan_stages=list(data.get("plan_stages") or []),
        )

    async def get(self, session_id: str) -> Optional[Session]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, created_at, updated_at, current_step, mode, data "
                "FROM sessions WHERE id = $1",
                session_id,
            )
        if row is None:
            return None
        return self._row_to_session(row)

    async def save(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        data_json = self._serialize_data(session)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (id, created_at, updated_at, current_step, mode, data)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    current_step = EXCLUDED.current_step,
                    mode = EXCLUDED.mode,
                    data = EXCLUDED.data
                """,
                session.id,
                session.created_at,
                session.updated_at,
                session.current_step,
                session.mode,
                data_json,
            )

    async def clear_stale_plan_flags(self) -> int:
        """Reset plan_generating=True on every session.

        Any background plan-generation task from a previous process died when
        the container restarted, but the session still says it's generating.
        Call this once at startup so users aren't stuck on the loading page
        forever.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE sessions
                SET data = jsonb_set(
                    COALESCE(data, '{}'::jsonb) - 'plan_generating',
                    '{plan_error}',
                    to_jsonb('Plan generation was interrupted — please try again.'::text)
                )
                WHERE data->>'plan_generating' = 'true'
                RETURNING id
                """,
            )
            return len(rows)

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, created_at, updated_at, current_step, mode, data "
                "FROM sessions ORDER BY updated_at DESC LIMIT $1",
                limit,
            )
        summaries = []
        for row in rows:
            raw = row["data"]
            if isinstance(raw, str):
                data = json.loads(raw)
            else:
                data = raw if raw is not None else {}

            profile_data = data.get("profile")
            investor_name = profile_data.get("name") if profile_data else None

            summaries.append(
                SessionSummary(
                    id=row["id"],
                    investor_name=investor_name,
                    mode=row["mode"],
                    current_step=row["current_step"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return summaries
