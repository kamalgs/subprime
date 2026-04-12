"""Session management layer for the FastAPI wizard web app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from subprime.core.models import (
    ConversationTurn,
    InvestmentPlan,
    InvestorProfile,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    """Lightweight summary of a session — used in list views."""

    id: str
    investor_name: str | None = None
    mode: str = "basic"
    current_step: int = 1
    created_at: datetime
    updated_at: datetime


class Session(BaseModel):
    """Full session state for a wizard interaction."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_step: int = 1
    mode: Literal["basic", "premium"] = "basic"
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    plan: InvestmentPlan | None = None
    strategy_chat: list[ConversationTurn] = []

    def to_summary(self) -> SessionSummary:
        """Return a lightweight SessionSummary for this session."""
        return SessionSummary(
            id=self.id,
            investor_name=self.profile.name if self.profile is not None else None,
            mode=self.mode,
            current_step=self.current_step,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ---------------------------------------------------------------------------
# Store protocol + in-memory implementation
# ---------------------------------------------------------------------------


class SessionStore:
    """Protocol for session persistence backends."""

    async def get(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def save(self, session: Session) -> None:
        raise NotImplementedError

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """Dict-backed session store for development and testing."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
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
