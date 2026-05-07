# Persistence, OTP Premium Gate & Conversation Logging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PostgreSQL persistence (sessions, conversations, OTP gate for premium tier) shared by web and CLI, with Alembic migrations and a new Nomad PostgreSQL job.

**Architecture:** asyncpg pool in `core/db.py`, shared persistence in `core/persistence.py` + `core/otp.py` + `core/conversations.py`. Web layer adds email sending and HTMX OTP flow. Alembic manages schema. PostgreSQL runs as a Nomad Docker job. Falls back to in-memory when no DATABASE_URL is set.

**Tech Stack:** asyncpg, alembic, smtplib (stdlib), PostgreSQL 16

---

## File Map

| File | Responsibility | Task |
|---|---|---|
| `src/subprime/core/config.py` | + DATABASE_URL, SMTP_*, OTP_* settings | Task 1 |
| `src/subprime/core/models.py` | + Session, SessionSummary models | Task 1 |
| `src/subprime/core/db.py` | asyncpg pool management | Task 2 |
| `migrations/alembic.ini` | Alembic config | Task 2 |
| `migrations/env.py` | Alembic migration runner | Task 2 |
| `migrations/versions/001_initial.py` | sessions, conversations, otps tables | Task 2 |
| `src/subprime/core/persistence.py` | SessionStore, PostgresSessionStore, InMemorySessionStore | Task 3 |
| `src/subprime/core/conversations.py` | save_conversation(), list_conversations() | Task 4 |
| `src/subprime/core/otp.py` | create_otp(), verify_otp(), daily_otp_count() | Task 5 |
| `apps/web/email.py` | send_otp_email() via SMTP | Task 6 |
| `apps/web/api.py` | + /api/request-otp, /api/verify-otp, conversation save | Task 6 |
| `apps/web/templates/step_plan.html` | Updated Premium card with OTP flow | Task 6 |
| `apps/web/templates/partials/otp_form.html` | OTP email input partial | Task 6 |
| `apps/web/templates/partials/otp_verify.html` | OTP code entry partial | Task 6 |
| `apps/web/session.py` | Re-exports from core | Task 7 |
| `apps/web/main.py` | + DB pool startup/shutdown, PostgresSessionStore | Task 7 |
| `src/subprime/cli.py` | Use core.conversations instead of JSON files | Task 7 |
| `pyproject.toml` | + asyncpg, alembic dependencies | Task 7 |
| `nomad/jobs/postgresql.tf` | New PostgreSQL Nomad job | Task 8 |
| `nomad/jobs/finadvisor.tf` | + DATABASE_URL, SMTP env vars | Task 8 |
| `tests/test_persistence.py` | All persistence + OTP + conversation tests | Tasks 1-7 |

---

### Task 1: Config + Models

**Files:**
- Modify: `src/subprime/core/config.py`
- Modify: `src/subprime/core/models.py`
- Create: `tests/test_persistence.py`

- [ ] **Step 1: Write tests for new config and models**

```python
# tests/test_persistence.py
"""Tests for persistence layer: config, models, DB, sessions, OTP, conversations."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestPersistenceConfig:
    def test_database_url_default_none(self):
        from subprime.core.config import DATABASE_URL
        # DATABASE_URL defaults to None when env var not set
        # (may be set in test env — just verify it's importable)
        assert DATABASE_URL is None or isinstance(DATABASE_URL, str)

    def test_otp_settings_defaults(self):
        from subprime.core.config import OTP_DAILY_LIMIT, OTP_EXPIRY_MINUTES
        assert OTP_DAILY_LIMIT == 100
        assert OTP_EXPIRY_MINUTES == 10

    def test_smtp_settings_importable(self):
        from subprime.core.config import SMTP_HOST, SMTP_PORT, SMTP_FROM
        assert SMTP_PORT == 587
        assert isinstance(SMTP_FROM, str)


# ---------------------------------------------------------------------------
# Session / SessionSummary model tests
# ---------------------------------------------------------------------------

class TestSessionModel:
    def test_session_defaults(self):
        from subprime.core.models import Session
        s = Session()
        assert s.current_step == 1
        assert s.mode == "basic"
        assert s.profile is None
        assert s.strategy is None
        assert s.plan is None
        assert s.strategy_chat == []
        assert len(s.id) == 12
        assert isinstance(s.created_at, datetime)

    def test_session_premium(self):
        from subprime.core.models import Session
        s = Session(mode="premium")
        assert s.mode == "premium"

    def test_to_summary_without_profile(self):
        from subprime.core.models import Session, SessionSummary
        s = Session()
        summary = s.to_summary()
        assert isinstance(summary, SessionSummary)
        assert summary.investor_name is None
        assert summary.id == s.id

    def test_to_summary_with_profile(self):
        from subprime.core.models import InvestorProfile, Session
        profile = InvestorProfile(
            id="test", name="Test User", age=30, risk_appetite="moderate",
            investment_horizon_years=10, monthly_investible_surplus_inr=50000,
            existing_corpus_inr=0, liabilities_inr=0,
            financial_goals=["retirement"], life_stage="early career",
            tax_bracket="new_regime",
        )
        s = Session(profile=profile, current_step=3)
        summary = s.to_summary()
        assert summary.investor_name == "Test User"
        assert summary.current_step == 3

    def test_session_json_roundtrip(self):
        from subprime.core.models import Session
        s = Session(mode="premium", current_step=2)
        json_str = s.model_dump_json()
        restored = Session.model_validate_json(json_str)
        assert restored.id == s.id
        assert restored.mode == "premium"
        assert restored.current_step == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py -v`
Expected: FAIL — `ImportError: cannot import name 'Session' from 'subprime.core.models'`

- [ ] **Step 3: Add config settings to config.py**

Append to `src/subprime/core/config.py` after the existing constants:

```python
# PostgreSQL — None means fall back to in-memory
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")

# SMTP for OTP emails
SMTP_HOST: str | None = os.environ.get("SMTP_HOST")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str | None = os.environ.get("SMTP_USER")
SMTP_PASSWORD: str | None = os.environ.get("SMTP_PASSWORD")
SMTP_FROM: str = os.environ.get("SMTP_FROM", "noreply@finadvisor.gkamal.online")

# OTP settings
OTP_DAILY_LIMIT: int = int(os.environ.get("OTP_DAILY_LIMIT", "100"))
OTP_EXPIRY_MINUTES: int = int(os.environ.get("OTP_EXPIRY_MINUTES", "10"))
```

- [ ] **Step 4: Add Session and SessionSummary to core/models.py**

Add at the end of `src/subprime/core/models.py`, before the `ExperimentResult` class:

```python
# ---------------------------------------------------------------------------
# Session (wizard state)
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    """Lightweight session info for listing."""

    id: str
    investor_name: str | None = None
    mode: str = "basic"
    current_step: int = 1
    created_at: datetime
    updated_at: datetime


class Session(BaseModel):
    """Full wizard session state."""

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_step: int = 1
    mode: Literal["basic", "premium"] = "basic"
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    plan: InvestmentPlan | None = None
    strategy_chat: list[ConversationTurn] = []

    def to_summary(self) -> SessionSummary:
        return SessionSummary(
            id=self.id,
            investor_name=self.profile.name if self.profile else None,
            mode=self.mode,
            current_step=self.current_step,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
```

Note: `Session` and `SessionSummary` must be placed AFTER `ConversationTurn` (which they depend on) and AFTER `InvestmentPlan`. Place them between `ConversationLog` and `ExperimentResult`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/subprime/core/config.py src/subprime/core/models.py tests/test_persistence.py
git commit -m "feat(core): add Session/SessionSummary models and persistence config settings"
```

---

### Task 2: Database Pool + Alembic Migrations

**Files:**
- Create: `src/subprime/core/db.py`
- Create: `migrations/alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/001_initial.py`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write tests for db pool management**

Append to `tests/test_persistence.py`:

```python
class TestDbPool:
    def test_db_module_imports(self):
        from subprime.core.db import init_pool, close_pool, get_pool
        assert callable(init_pool)
        assert callable(close_pool)
        assert callable(get_pool)

    @pytest.mark.asyncio
    async def test_get_pool_returns_none_without_init(self):
        from subprime.core.db import get_pool
        pool = get_pool()
        assert pool is None

    def test_migration_sql_is_valid(self):
        """Verify migration file contains expected CREATE TABLE statements."""
        from pathlib import Path
        migration_dir = Path(__file__).parent.parent / "migrations" / "versions"
        migration_files = list(migration_dir.glob("001_*.py"))
        assert len(migration_files) == 1, "Expected exactly one initial migration"
        content = migration_files[0].read_text()
        assert "CREATE TABLE sessions" in content
        assert "CREATE TABLE conversations" in content
        assert "CREATE TABLE otps" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestDbPool -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'subprime.core.db'`

- [ ] **Step 3: Implement db.py**

```python
# src/subprime/core/db.py
"""asyncpg connection pool management.

Usage:
    pool = await init_pool(database_url)
    # ... use pool ...
    await close_pool()

When DATABASE_URL is not set, get_pool() returns None and callers
fall back to in-memory implementations.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_pool = None


async def init_pool(database_url: str):
    """Create the global asyncpg connection pool."""
    global _pool
    import asyncpg

    _pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    logger.info("Database pool created: %s", database_url.split("@")[-1])
    return _pool


def get_pool():
    """Get the current pool, or None if not initialized."""
    return _pool


async def close_pool():
    """Close the global pool if it exists."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")
```

- [ ] **Step 4: Create Alembic config and migration**

```ini
; migrations/alembic.ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://finadvisor:finadvisor@localhost:5432/finadvisor

[loggers]
keys = root,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

```python
# migrations/env.py
"""Alembic migration environment — runs migrations using asyncpg."""

import os
import sys
from pathlib import Path

from alembic import context

# Add project root to path so we can import subprime
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Get database URL from environment or alembic.ini
config = context.config
database_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline():
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    context.configure(url=database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode — connects to database."""
    from sqlalchemy import create_engine, pool

    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

```python
# migrations/versions/001_initial.py
"""Initial schema: sessions, conversations, otps.

Revision ID: 001
Create Date: 2026-04-12
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            current_step INTEGER NOT NULL DEFAULT 1,
            mode TEXT NOT NULL DEFAULT 'basic',
            data JSONB NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            investor_name TEXT,
            mode TEXT NOT NULL,
            profile JSONB,
            strategy JSONB,
            plan JSONB,
            strategy_chat JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at DESC);

        CREATE TABLE IF NOT EXISTS otps (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ,
            session_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_otps_email ON otps(email, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_otps_code ON otps(code);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS otps;")
    op.execute("DROP TABLE IF EXISTS conversations;")
    op.execute("DROP TABLE IF EXISTS sessions;")
```

Also create `migrations/__init__.py` and `migrations/versions/__init__.py` (empty files).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestDbPool -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/subprime/core/db.py migrations/ tests/test_persistence.py
git commit -m "feat(core): add asyncpg pool management and Alembic initial migration"
```

---

### Task 3: PostgresSessionStore + InMemorySessionStore

**Files:**
- Create: `src/subprime/core/persistence.py`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write tests for both session store implementations**

Append to `tests/test_persistence.py`:

```python
from subprime.core.models import InvestorProfile, Session, SessionSummary


def _test_profile() -> InvestorProfile:
    return InvestorProfile(
        id="test", name="Test User", age=30, risk_appetite="moderate",
        investment_horizon_years=10, monthly_investible_surplus_inr=50000,
        existing_corpus_inr=0, liabilities_inr=0,
        financial_goals=["retirement"], life_stage="early career",
        tax_bracket="new_regime",
    )


class TestInMemorySessionStore:
    @pytest.fixture
    def store(self):
        from subprime.core.persistence import InMemorySessionStore
        return InMemorySessionStore()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        assert await store.get("nope") is None

    @pytest.mark.asyncio
    async def test_save_and_get(self, store):
        s = Session()
        await store.save(s)
        got = await store.get(s.id)
        assert got is not None
        assert got.id == s.id

    @pytest.mark.asyncio
    async def test_save_updates(self, store):
        s = Session()
        await store.save(s)
        s.current_step = 3
        s.mode = "premium"
        await store.save(s)
        got = await store.get(s.id)
        assert got.current_step == 3
        assert got.mode == "premium"

    @pytest.mark.asyncio
    async def test_list_empty(self, store):
        assert await store.list_sessions() == []

    @pytest.mark.asyncio
    async def test_list_returns_summaries(self, store):
        await store.save(Session())
        await store.save(Session(mode="premium"))
        result = await store.list_sessions()
        assert len(result) == 2
        assert all(isinstance(r, SessionSummary) for r in result)

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, store):
        for _ in range(5):
            await store.save(Session())
        assert len(await store.list_sessions(limit=3)) == 3

    @pytest.mark.asyncio
    async def test_save_with_profile(self, store):
        s = Session(profile=_test_profile())
        await store.save(s)
        got = await store.get(s.id)
        assert got.profile.name == "Test User"


class TestPostgresSessionStore:
    """Tests for PostgresSessionStore — requires a running PostgreSQL.

    These tests are skipped when DATABASE_URL is not set (CI / local dev).
    When run against a real DB, they verify full round-trip persistence.
    """

    @pytest.fixture
    async def store(self):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set — skipping Postgres tests")
        from subprime.core.db import init_pool, close_pool
        from subprime.core.persistence import PostgresSessionStore
        pool = await init_pool(database_url)
        # Ensure clean state
        await pool.execute("DELETE FROM sessions")
        yield PostgresSessionStore(pool)
        await pool.execute("DELETE FROM sessions")
        await close_pool()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        assert await store.get("nope") is None

    @pytest.mark.asyncio
    async def test_save_and_get(self, store):
        s = Session(mode="premium")
        await store.save(s)
        got = await store.get(s.id)
        assert got is not None
        assert got.id == s.id
        assert got.mode == "premium"

    @pytest.mark.asyncio
    async def test_save_with_profile(self, store):
        s = Session(profile=_test_profile(), current_step=2)
        await store.save(s)
        got = await store.get(s.id)
        assert got.profile is not None
        assert got.profile.name == "Test User"
        assert got.current_step == 2

    @pytest.mark.asyncio
    async def test_save_updates(self, store):
        s = Session()
        await store.save(s)
        s.current_step = 4
        await store.save(s)
        got = await store.get(s.id)
        assert got.current_step == 4

    @pytest.mark.asyncio
    async def test_list_sessions(self, store):
        await store.save(Session())
        await store.save(Session(mode="premium"))
        result = await store.list_sessions()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_with_profile_shows_name(self, store):
        s = Session(profile=_test_profile())
        await store.save(s)
        result = await store.list_sessions()
        assert result[0].investor_name == "Test User"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestInMemorySessionStore -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'subprime.core.persistence'`

- [ ] **Step 3: Implement persistence.py**

```python
# src/subprime/core/persistence.py
"""Session persistence: protocol + implementations.

InMemorySessionStore — for tests and local dev (no DB required).
PostgresSessionStore — for production (requires asyncpg pool).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from subprime.core.models import Session, SessionSummary

logger = logging.getLogger(__name__)


class SessionStore:
    """Base class for session persistence."""

    async def get(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def save(self, session: Session) -> None:
        raise NotImplementedError

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """Dict-backed session store for dev and testing."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def save(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self._sessions[session.id] = session

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        ordered = sorted(
            self._sessions.values(), key=lambda s: s.updated_at, reverse=True,
        )
        return [s.to_summary() for s in ordered[:limit]]


class PostgresSessionStore(SessionStore):
    """PostgreSQL-backed session store using asyncpg."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def get(self, session_id: str) -> Session | None:
        row = await self._pool.fetchrow(
            "SELECT id, created_at, updated_at, current_step, mode, data FROM sessions WHERE id = $1",
            session_id,
        )
        if not row:
            return None
        return self._row_to_session(row)

    async def save(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        data = {
            "profile": session.profile.model_dump() if session.profile else None,
            "strategy": session.strategy.model_dump() if session.strategy else None,
            "plan": session.plan.model_dump() if session.plan else None,
            "strategy_chat": [t.model_dump() for t in session.strategy_chat],
        }
        await self._pool.execute(
            """INSERT INTO sessions (id, created_at, updated_at, current_step, mode, data)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb)
               ON CONFLICT (id) DO UPDATE SET
                   updated_at = $3, current_step = $4, mode = $5, data = $6::jsonb""",
            session.id,
            session.created_at,
            session.updated_at,
            session.current_step,
            session.mode,
            json.dumps(data),
        )

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        rows = await self._pool.fetch(
            "SELECT id, created_at, updated_at, current_step, mode, data FROM sessions ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        summaries = []
        for row in rows:
            data = json.loads(row["data"]) if row["data"] else {}
            profile = data.get("profile")
            investor_name = profile["name"] if profile and "name" in profile else None
            summaries.append(SessionSummary(
                id=row["id"],
                investor_name=investor_name,
                mode=row["mode"],
                current_step=row["current_step"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))
        return summaries

    def _row_to_session(self, row) -> Session:
        from subprime.core.models import (
            ConversationTurn, InvestmentPlan, InvestorProfile, StrategyOutline,
        )
        data = json.loads(row["data"]) if row["data"] else {}
        return Session(
            id=row["id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            current_step=row["current_step"],
            mode=row["mode"],
            profile=InvestorProfile(**data["profile"]) if data.get("profile") else None,
            strategy=StrategyOutline(**data["strategy"]) if data.get("strategy") else None,
            plan=InvestmentPlan(**data["plan"]) if data.get("plan") else None,
            strategy_chat=[ConversationTurn(**t) for t in data.get("strategy_chat", [])],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestInMemorySessionStore -v`
Expected: All PASS (Postgres tests skip when DATABASE_URL not set)

- [ ] **Step 5: Commit**

```bash
git add src/subprime/core/persistence.py tests/test_persistence.py
git commit -m "feat(core): add SessionStore protocol with InMemory and Postgres implementations"
```

---

### Task 4: Conversation Logging

**Files:**
- Create: `src/subprime/core/conversations.py`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_persistence.py`:

```python
class TestConversations:
    def test_module_imports(self):
        from subprime.core.conversations import save_conversation, list_conversations
        assert callable(save_conversation)
        assert callable(list_conversations)

    @pytest.mark.asyncio
    async def test_save_to_json_fallback(self, tmp_path):
        """When no pool is provided, falls back to JSON file."""
        from subprime.core.conversations import save_conversation
        s = Session(profile=_test_profile(), current_step=4, mode="basic")
        path = await save_conversation(session=s, pool=None, conversations_dir=tmp_path)
        assert path is not None
        assert path.exists()
        assert path.suffix == ".json"
        import json
        data = json.loads(path.read_text())
        assert data["investor_name"] == "Test User"
        assert data["mode"] == "basic"

    @pytest.mark.asyncio
    async def test_save_to_json_includes_plan(self, tmp_path):
        from subprime.core.conversations import save_conversation
        from subprime.core.models import Allocation, InvestmentPlan, MutualFund
        plan = InvestmentPlan(
            allocations=[
                Allocation(
                    fund=MutualFund(amfi_code="119551", name="UTI Nifty 50"),
                    allocation_pct=100, mode="sip", monthly_sip_inr=10000,
                    rationale="Test",
                )
            ],
            rationale="Test plan",
        )
        s = Session(profile=_test_profile(), plan=plan, current_step=4)
        path = await save_conversation(session=s, pool=None, conversations_dir=tmp_path)
        import json
        data = json.loads(path.read_text())
        assert data["plan"] is not None
        assert data["plan"]["allocations"][0]["fund"]["name"] == "UTI Nifty 50"

    @pytest.mark.asyncio
    async def test_list_from_json(self, tmp_path):
        from subprime.core.conversations import save_conversation, list_conversations
        s1 = Session(profile=_test_profile(), current_step=4)
        s2 = Session(profile=_test_profile(), current_step=4, mode="premium")
        await save_conversation(session=s1, pool=None, conversations_dir=tmp_path)
        await save_conversation(session=s2, pool=None, conversations_dir=tmp_path)
        result = await list_conversations(pool=None, conversations_dir=tmp_path)
        assert len(result) == 2


class TestConversationsPostgres:
    """Postgres conversation tests — skipped without DATABASE_URL."""

    @pytest.fixture
    async def pool(self):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set")
        from subprime.core.db import init_pool, close_pool
        pool = await init_pool(database_url)
        await pool.execute("DELETE FROM conversations")
        yield pool
        await pool.execute("DELETE FROM conversations")
        await close_pool()

    @pytest.mark.asyncio
    async def test_save_and_list(self, pool):
        from subprime.core.conversations import save_conversation, list_conversations
        s = Session(profile=_test_profile(), current_step=4, mode="premium")
        await save_conversation(session=s, pool=pool)
        result = await list_conversations(pool=pool)
        assert len(result) == 1
        assert result[0]["investor_name"] == "Test User"
        assert result[0]["mode"] == "premium"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestConversations -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement conversations.py**

```python
# src/subprime/core/conversations.py
"""Conversation logging — saves completed sessions for replay and analysis.

Dual backend:
- PostgreSQL (when pool is provided)
- JSON files (fallback when pool is None)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from subprime.core.models import Session

logger = logging.getLogger(__name__)


async def save_conversation(
    session: Session,
    pool=None,
    conversations_dir: Path | None = None,
) -> Path | None:
    """Save a completed session as a conversation record.

    Returns the JSON file path (fallback mode) or None (Postgres mode).
    """
    record = _session_to_record(session)

    if pool is not None:
        await pool.execute(
            """INSERT INTO conversations (session_id, investor_name, mode, profile, strategy, plan, strategy_chat)
               VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)""",
            record["session_id"],
            record["investor_name"],
            record["mode"],
            json.dumps(record["profile"]),
            json.dumps(record["strategy"]),
            json.dumps(record["plan"]),
            json.dumps(record["strategy_chat"]),
        )
        logger.info("Conversation saved to database: session=%s", session.id)
        return None

    # Fallback: JSON file
    if conversations_dir is None:
        from subprime.core.config import CONVERSATIONS_DIR
        conversations_dir = CONVERSATIONS_DIR
    conversations_dir.mkdir(parents=True, exist_ok=True)
    path = conversations_dir / f"{session.id}.json"
    path.write_text(json.dumps(record, indent=2, default=str))
    logger.info("Conversation saved to file: %s", path)
    return path


async def list_conversations(
    pool=None,
    conversations_dir: Path | None = None,
    limit: int = 50,
) -> list[dict]:
    """List recent conversations."""
    if pool is not None:
        rows = await pool.fetch(
            "SELECT session_id, investor_name, mode, created_at FROM conversations ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]

    # Fallback: JSON files
    if conversations_dir is None:
        from subprime.core.config import CONVERSATIONS_DIR
        conversations_dir = CONVERSATIONS_DIR
    if not conversations_dir.exists():
        return []
    files = sorted(conversations_dir.glob("*.json"), reverse=True)[:limit]
    result = []
    for f in files:
        data = json.loads(f.read_text())
        result.append(data)
    return result


def _session_to_record(session: Session) -> dict:
    return {
        "session_id": session.id,
        "investor_name": session.profile.name if session.profile else None,
        "mode": session.mode,
        "profile": session.profile.model_dump() if session.profile else None,
        "strategy": session.strategy.model_dump() if session.strategy else None,
        "plan": session.plan.model_dump() if session.plan else None,
        "strategy_chat": [t.model_dump() for t in session.strategy_chat],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestConversations -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/subprime/core/conversations.py tests/test_persistence.py
git commit -m "feat(core): add conversation logging with Postgres and JSON fallback"
```

---

### Task 5: OTP Generation and Verification

**Files:**
- Create: `src/subprime/core/otp.py`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_persistence.py`:

```python
from unittest.mock import AsyncMock, MagicMock


class TestOTPInMemory:
    """OTP tests using a mock pool to avoid needing a real database."""

    def _make_mock_pool(self, fetchval_return=0, fetchrow_return=None):
        pool = AsyncMock()
        pool.fetchval = AsyncMock(return_value=fetchval_return)
        pool.fetchrow = AsyncMock(return_value=fetchrow_return)
        pool.execute = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_create_otp_success(self):
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=5)  # 5 OTPs today
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is True
        assert len(result["code"]) == 6
        assert result["code"].isdigit()
        # Should have called execute to invalidate + insert
        assert pool.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_create_otp_daily_limit_reached(self):
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=100)  # at limit
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is False
        assert "full" in result["reason"].lower() or "limit" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_verify_otp_success(self):
        from subprime.core.otp import verify_otp
        from datetime import datetime, timezone, timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1,
            "email": "test@example.com",
            "code": "123456",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "verified_at": None,
        })
        result = await verify_otp(pool, "test@example.com", "123456")
        assert result is True
        pool.execute.assert_called_once()  # should mark as verified

    @pytest.mark.asyncio
    async def test_verify_otp_not_found(self):
        from subprime.core.otp import verify_otp
        pool = self._make_mock_pool(fetchrow_return=None)
        result = await verify_otp(pool, "test@example.com", "999999")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_otp_expired(self):
        from subprime.core.otp import verify_otp
        from datetime import datetime, timezone, timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1,
            "email": "test@example.com",
            "code": "123456",
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),  # expired
            "verified_at": None,
        })
        result = await verify_otp(pool, "test@example.com", "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_otp_already_used(self):
        from subprime.core.otp import verify_otp
        from datetime import datetime, timezone, timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1,
            "email": "test@example.com",
            "code": "123456",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "verified_at": datetime.now(timezone.utc),  # already verified
        })
        result = await verify_otp(pool, "test@example.com", "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_daily_count(self):
        from subprime.core.otp import daily_otp_count
        pool = self._make_mock_pool(fetchval_return=42)
        count = await daily_otp_count(pool)
        assert count == 42


class TestOTPPostgres:
    """Full OTP round-trip with real Postgres — skipped without DATABASE_URL."""

    @pytest.fixture
    async def pool(self):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set")
        from subprime.core.db import init_pool, close_pool
        pool = await init_pool(database_url)
        await pool.execute("DELETE FROM otps")
        yield pool
        await pool.execute("DELETE FROM otps")
        await close_pool()

    @pytest.mark.asyncio
    async def test_create_and_verify(self, pool):
        from subprime.core.otp import create_otp, verify_otp
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is True
        code = result["code"]
        assert await verify_otp(pool, "test@example.com", code) is True
        # Second verify should fail (already used)
        assert await verify_otp(pool, "test@example.com", code) is False

    @pytest.mark.asyncio
    async def test_wrong_code_fails(self, pool):
        from subprime.core.otp import create_otp, verify_otp
        await create_otp(pool, "test@example.com")
        assert await verify_otp(pool, "test@example.com", "000000") is False

    @pytest.mark.asyncio
    async def test_new_otp_invalidates_old(self, pool):
        from subprime.core.otp import create_otp, verify_otp
        r1 = await create_otp(pool, "test@example.com")
        r2 = await create_otp(pool, "test@example.com")
        # Old code should not work
        assert await verify_otp(pool, "test@example.com", r1["code"]) is False
        # New code should work
        assert await verify_otp(pool, "test@example.com", r2["code"]) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestOTPInMemory -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement otp.py**

```python
# src/subprime/core/otp.py
"""OTP generation and verification for the premium tier gate.

6-digit codes, 10-minute expiry, 100/day limit.
One active OTP per email (new request invalidates old).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from subprime.core.config import OTP_DAILY_LIMIT, OTP_EXPIRY_MINUTES

logger = logging.getLogger(__name__)


async def create_otp(pool, email: str) -> dict:
    """Generate a 6-digit OTP for the given email.

    Returns {"success": True, "code": "123456"} or {"success": False, "reason": "..."}.
    """
    # Check daily limit
    count = await daily_otp_count(pool)
    if count >= OTP_DAILY_LIMIT:
        return {"success": False, "reason": "Premium slots are full for today — try again tomorrow."}

    # Invalidate any existing unexpired OTP for this email
    await pool.execute(
        "UPDATE otps SET verified_at = NOW() WHERE email = $1 AND verified_at IS NULL AND expires_at > NOW()",
        email,
    )

    # Generate new code
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    await pool.execute(
        "INSERT INTO otps (email, code, expires_at) VALUES ($1, $2, $3)",
        email,
        code,
        expires_at,
    )

    logger.info("OTP created for %s (daily count: %d)", email, count + 1)
    return {"success": True, "code": code}


async def verify_otp(pool, email: str, code: str) -> bool:
    """Verify an OTP code. Returns True if valid."""
    row = await pool.fetchrow(
        "SELECT id, email, code, expires_at, verified_at FROM otps WHERE email = $1 AND code = $2 ORDER BY created_at DESC LIMIT 1",
        email,
        code,
    )
    if not row:
        return False
    if row["verified_at"] is not None:
        return False
    if row["expires_at"] < datetime.now(timezone.utc):
        return False

    # Mark as verified
    await pool.execute(
        "UPDATE otps SET verified_at = NOW() WHERE id = $1",
        row["id"],
    )
    logger.info("OTP verified for %s", email)
    return True


async def daily_otp_count(pool) -> int:
    """Count OTPs created today (UTC)."""
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM otps WHERE created_at >= CURRENT_DATE",
    )
    return count or 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestOTPInMemory -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/subprime/core/otp.py tests/test_persistence.py
git commit -m "feat(core): add OTP generation, verification, and daily limit"
```

---

### Task 6: Web Layer — Email, OTP Endpoints, Template

**Files:**
- Create: `apps/web/email.py`
- Create: `apps/web/templates/partials/otp_form.html`
- Create: `apps/web/templates/partials/otp_verify.html`
- Create: `apps/web/templates/partials/otp_error.html`
- Modify: `apps/web/api.py`
- Modify: `apps/web/templates/step_plan.html`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write tests for email and OTP API endpoints**

Append to `tests/test_persistence.py`:

```python
class TestEmail:
    def test_module_imports(self):
        from apps.web.email import send_otp_email
        assert callable(send_otp_email)

    @pytest.mark.asyncio
    async def test_send_returns_false_without_smtp(self):
        """Without SMTP config, send_otp_email returns False gracefully."""
        from apps.web.email import send_otp_email
        result = await send_otp_email("test@example.com", "123456")
        assert result is False


from httpx import ASGITransport, AsyncClient


class TestOTPEndpoints:
    """Test OTP API endpoints via httpx against real FastAPI app."""

    @pytest.mark.asyncio
    async def test_request_otp_requires_email(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First create a session
            await client.post("/api/select-tier", data={"mode": "premium"})
            resp = await client.post("/api/request-otp", data={"email": ""})
            assert resp.status_code == 200
            assert "valid email" in resp.text.lower() or "enter" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_request_otp_no_db_shows_error(self):
        """Without DATABASE_URL, OTP endpoints return a user-friendly error."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-tier", data={"mode": "premium"})
            resp = await client.post("/api/request-otp", data={"email": "test@example.com"})
            assert resp.status_code == 200
            # Should show an error since no DB is configured
            assert "not available" in resp.text.lower() or "unavailable" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_verify_otp_no_db_shows_error(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-tier", data={"mode": "premium"})
            resp = await client.post("/api/verify-otp", data={"email": "test@example.com", "code": "123456"})
            assert resp.status_code == 200
            assert "not available" in resp.text.lower() or "unavailable" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_step1_premium_shows_otp_form(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/step/1")
            assert resp.status_code == 200
            assert "email" in resp.text.lower()
            assert "Send me a code" in resp.text or "send" in resp.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestEmail -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement email.py**

```python
# apps/web/email.py
"""SMTP email sending for OTP codes."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from subprime.core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

logger = logging.getLogger(__name__)


async def send_otp_email(email: str, code: str) -> bool:
    """Send an OTP code via SMTP. Returns True on success."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP not configured — cannot send OTP to %s", email)
        return False

    msg = EmailMessage()
    msg["Subject"] = "Your FinAdvisor Premium Code"
    msg["From"] = SMTP_FROM
    msg["To"] = email
    msg.set_content(
        f"Your one-time code: {code}\n\n"
        f"Enter this code at https://finadvisor.gkamal.online to start your premium plan.\n"
        f"This code expires in 10 minutes.\n\n"
        f"— FinAdvisor"
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("OTP email sent to %s", email)
        return True
    except Exception:
        logger.exception("Failed to send OTP email to %s", email)
        return False
```

- [ ] **Step 4: Create OTP template partials**

```html
<!-- apps/web/templates/partials/otp_form.html -->
<div id="otp-section" class="mt-4 space-y-3">
    <div class="flex gap-2">
        <input
            type="email"
            name="email"
            placeholder="your@email.com"
            required
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
        >
        <button
            hx-post="/api/request-otp"
            hx-include="[name='email']"
            hx-target="#otp-section"
            hx-swap="outerHTML"
            class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg transition-colors whitespace-nowrap"
        >Send me a code</button>
    </div>
    <p class="text-xs text-gray-400">We'll email you a one-time code. {{ daily_remaining }} premium plans available today.</p>
</div>
```

```html
<!-- apps/web/templates/partials/otp_verify.html -->
<div id="otp-section" class="mt-4 space-y-3">
    <p class="text-sm text-green-600">Code sent to <strong>{{ email }}</strong>. Valid for 10 minutes.</p>
    <input type="hidden" name="email" value="{{ email }}">
    <div class="flex gap-2">
        <input
            type="text"
            name="code"
            placeholder="6-digit code"
            maxlength="6"
            pattern="[0-9]{6}"
            required
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-center tracking-widest font-mono focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
        >
        <button
            hx-post="/api/verify-otp"
            hx-include="[name='email'],[name='code']"
            hx-target="#otp-section"
            hx-swap="outerHTML"
            class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg transition-colors whitespace-nowrap"
        >Verify</button>
    </div>
</div>
```

```html
<!-- apps/web/templates/partials/otp_error.html -->
<div id="otp-section" class="mt-4 space-y-3">
    <p class="text-sm text-red-600">{{ message }}</p>
    {% if show_retry %}
    <div class="flex gap-2">
        <input
            type="email"
            name="email"
            value="{{ email }}"
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
        >
        <button
            hx-post="/api/request-otp"
            hx-include="[name='email']"
            hx-target="#otp-section"
            hx-swap="outerHTML"
            class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg transition-colors whitespace-nowrap"
        >Try again</button>
    </div>
    {% endif %}
</div>
```

- [ ] **Step 5: Add OTP endpoints to api.py**

Append to `apps/web/api.py`:

```python
import re
from subprime.core.db import get_pool
from subprime.core.otp import create_otp, verify_otp, daily_otp_count
from subprime.core.config import OTP_DAILY_LIMIT


@router.post("/request-otp")
async def api_request_otp(
    request: Request,
    email: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    """Generate and email an OTP for premium access."""
    templates = request.app.state.templates
    pool = get_pool()

    if not pool:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Premium is not available right now — please try the Basic plan.",
            "show_retry": False, "email": email,
        })

    # Validate email
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Please enter a valid email address.",
            "show_retry": True, "email": email,
        })

    result = await create_otp(pool, email.strip().lower())
    if not result["success"]:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": result["reason"],
            "show_retry": False, "email": email,
        })

    # Send email
    from apps.web.email import send_otp_email
    sent = await send_otp_email(email.strip().lower(), result["code"])
    if not sent:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Could not send email — please check your address and try again.",
            "show_retry": True, "email": email,
        })

    return templates.TemplateResponse(request, "partials/otp_verify.html", {
        "email": email.strip().lower(),
    })


@router.post("/verify-otp")
async def api_verify_otp(
    request: Request,
    email: Annotated[str, Form()],
    code: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    """Verify an OTP and grant premium access."""
    templates = request.app.state.templates
    pool = get_pool()

    if not pool:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Premium is not available right now.",
            "show_retry": False, "email": email,
        })

    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)

    verified = await verify_otp(pool, email.strip().lower(), code.strip())
    if not verified:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Invalid or expired code. Please request a new one.",
            "show_retry": True, "email": email,
        })

    # Grant premium
    session.mode = "premium"
    session.current_step = 2
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/2"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response
```

- [ ] **Step 6: Update step_plan.html Premium card**

Replace the Premium card's button with the OTP flow. Replace the `<button ... hx-post="/api/select-tier" ... data-tier="premium">Start Premium Plan</button>` block with:

```html
            <div id="otp-section" class="mt-4 space-y-3">
                <div class="flex gap-2">
                    <input
                        type="email"
                        name="email"
                        placeholder="your@email.com"
                        required
                        class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
                    >
                    <button
                        hx-post="/api/request-otp"
                        hx-include="[name='email']"
                        hx-target="#otp-section"
                        hx-swap="outerHTML"
                        class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg transition-colors whitespace-nowrap"
                    >Send me a code</button>
                </div>
                <p class="text-xs text-gray-400">We'll email you a one-time code to unlock premium.</p>
            </div>
```

- [ ] **Step 7: Add conversation save to generate-plan endpoint**

In `apps/web/api.py`, inside `api_generate_plan`, after `session.plan = plan` and `await store.save(session)`, add:

```python
    # Save conversation log
    from subprime.core.conversations import save_conversation
    from subprime.core.db import get_pool as _get_pool
    await save_conversation(session=session, pool=_get_pool())
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestEmail tests/test_persistence.py::TestOTPEndpoints -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add apps/web/email.py apps/web/api.py apps/web/templates/partials/otp_form.html apps/web/templates/partials/otp_verify.html apps/web/templates/partials/otp_error.html apps/web/templates/step_plan.html tests/test_persistence.py
git commit -m "feat(web): add OTP email flow for premium tier and conversation logging"
```

---

### Task 7: Wiring — Session Re-export, App Startup, CLI, Dependencies

**Files:**
- Modify: `apps/web/session.py`
- Modify: `apps/web/main.py`
- Modify: `src/subprime/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_persistence.py`

- [ ] **Step 1: Write integration tests**

Append to `tests/test_persistence.py`:

```python
class TestWiring:
    def test_web_session_reexports(self):
        """apps.web.session re-exports from core."""
        from apps.web.session import InMemorySessionStore, Session, SessionSummary
        assert Session is not None
        assert SessionSummary is not None
        assert InMemorySessionStore is not None

    def test_web_session_backward_compat(self):
        """Existing code importing from apps.web.session still works."""
        from apps.web.session import Session, InMemorySessionStore
        s = Session()
        store = InMemorySessionStore()
        assert s.id
        assert store is not None

    @pytest.mark.asyncio
    async def test_app_factory_uses_in_memory_without_db(self):
        """Without DATABASE_URL, app uses InMemorySessionStore."""
        from apps.web.main import create_app
        from subprime.core.persistence import InMemorySessionStore
        app = create_app()
        assert isinstance(app.state.session_store, InMemorySessionStore)

    @pytest.mark.asyncio
    async def test_full_flow_with_conversation_save(self):
        """Full wizard flow saves conversation after plan generation."""
        from apps.web.main import create_app
        from unittest.mock import AsyncMock, patch
        from subprime.core.models import StrategyOutline, Allocation, InvestmentPlan, MutualFund

        app = create_app()

        mock_strategy = StrategyOutline(
            equity_pct=70, debt_pct=20, gold_pct=10, other_pct=0,
            equity_approach="Index funds", key_themes=["growth"],
            risk_return_summary="Moderate", open_questions=[],
        )
        mock_plan = InvestmentPlan(
            allocations=[Allocation(
                fund=MutualFund(amfi_code="119551", name="Test Fund"),
                allocation_pct=100, mode="sip", monthly_sip_inr=10000, rationale="Test",
            )],
            rationale="Test plan",
        )

        with patch("apps.web.api.generate_strategy", new_callable=AsyncMock, return_value=mock_strategy), \
             patch("apps.web.api.generate_plan", new_callable=AsyncMock, return_value=mock_plan), \
             patch("subprime.core.conversations.save_conversation", new_callable=AsyncMock) as mock_save:

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                await client.post("/api/select-persona", data={"persona_id": "P01"})

                # Inject strategy
                store = app.state.session_store
                sessions = list(store._sessions.values())
                sessions[0].strategy = mock_strategy
                await store.save(sessions[0])

                await client.post("/api/generate-plan")
                # Conversation should have been saved
                mock_save.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py::TestWiring -v`
Expected: FAIL (re-exports not yet updated)

- [ ] **Step 3: Update apps/web/session.py to re-export from core**

Replace entire content of `apps/web/session.py`:

```python
# apps/web/session.py
"""Session management — re-exports from core.persistence.

Existing imports from apps.web.session continue to work.
"""

from subprime.core.models import Session, SessionSummary
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore, SessionStore

__all__ = [
    "Session",
    "SessionSummary",
    "SessionStore",
    "InMemorySessionStore",
    "PostgresSessionStore",
]
```

- [ ] **Step 4: Update apps/web/main.py with DB pool lifecycle**

Replace `apps/web/main.py`:

```python
# apps/web/main.py
"""FastAPI application factory for the FinAdvisor wizard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from subprime.core.config import DATABASE_URL
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB pool if configured. Shutdown: close pool."""
    if DATABASE_URL:
        from subprime.core.db import init_pool
        pool = await init_pool(DATABASE_URL)
        app.state.session_store = PostgresSessionStore(pool)
        logger.info("Using PostgreSQL session store")
    else:
        app.state.session_store = InMemorySessionStore()
        logger.info("Using in-memory session store (no DATABASE_URL)")

    yield

    if DATABASE_URL:
        from subprime.core.db import close_pool
        await close_pool()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from apps.web import api, routes

    app = FastAPI(title="FinAdvisor", description="AI-powered mutual fund advisory", lifespan=lifespan)

    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(routes.router)
    app.include_router(api.router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/step/1", status_code=307)

    return app
```

- [ ] **Step 5: Update CLI to use core.conversations**

In `src/subprime/cli.py`, replace the `_save_conversation` function (lines ~291-297):

```python
def _save_conversation(conv: ConversationLog) -> Path:
    """Save a conversation log."""
    import asyncio
    from subprime.core.conversations import save_conversation as _save
    from subprime.core.db import get_pool
    from subprime.core.models import Session

    # Build a Session from the ConversationLog for the shared save function
    session = Session(
        id=conv.id,
        mode="basic",
        current_step=4,
        profile=conv.profile,
        strategy=conv.strategy,
        plan=conv.plan,
        strategy_chat=conv.strategy_revisions,
    )
    path = asyncio.run(_save(session=session, pool=get_pool()))
    if path:
        _console.print(f"\n[dim]Conversation saved to {path}[/dim]")
    else:
        _console.print(f"\n[dim]Conversation saved to database[/dim]")
    return path or Path(".")
```

- [ ] **Step 6: Update pyproject.toml**

Add to dependencies list:
```
    "asyncpg>=0.30",
    "alembic>=1.14",
```

- [ ] **Step 7: Install new dependencies**

```bash
cd /home/agent/projects/subprime && pip install asyncpg alembic
```

- [ ] **Step 8: Run all tests**

```bash
cd /home/agent/projects/subprime && python -m pytest tests/test_persistence.py tests/test_web_wizard.py -v
```

Expected: All PASS (existing wizard tests + new persistence tests)

- [ ] **Step 9: Commit**

```bash
git add apps/web/session.py apps/web/main.py src/subprime/cli.py pyproject.toml tests/test_persistence.py
git commit -m "feat: wire persistence layer — session re-exports, DB pool lifecycle, CLI migration, dependencies"
```

---

### Task 8: Nomad PostgreSQL Job + Deploy Config

**Files:**
- Create: `nomad/jobs/postgresql.tf`
- Modify: `nomad/jobs/finadvisor.tf`
- Modify: `nomad/jobs/variables.tf`
- Modify: `nomad/infra/install.tf` (host volume)

- [ ] **Step 1: Create PostgreSQL Nomad job**

```hcl
# nomad/jobs/postgresql.tf
resource "nomad_job" "postgresql" {
  jobspec = <<-EOT
    job "postgresql" {
      datacenters = ["dc1"]
      type        = "service"

      group "postgresql" {
        count = 1

        network {
          mode = "host"
        }

        volume "postgres_data" {
          type      = "host"
          source    = "postgres_data"
          read_only = false
        }

        task "postgresql" {
          driver = "docker"

          config {
            image        = "postgres:16-alpine"
            network_mode = "host"
          }

          env {
            POSTGRES_DB       = "finadvisor"
            POSTGRES_USER     = "finadvisor"
            POSTGRES_PASSWORD = "${var.postgres_password}"
            PGPORT            = "${local.ports.postgresql}"
          }

          volume_mount {
            volume      = "postgres_data"
            destination = "/var/lib/postgresql/data"
          }

          resources {
            cpu    = 200
            memory = 256
          }
        }
      }
    }
  EOT
}
```

- [ ] **Step 2: Add PostgreSQL port and variables**

Add to `nomad/jobs/ports.tf`:
```hcl
    postgresql    = 5432
```

Add to `nomad/jobs/variables.tf`:
```hcl
variable "postgres_password" {
  type      = string
  sensitive = true
}
```

- [ ] **Step 3: Update finadvisor.tf with DATABASE_URL and SMTP env vars**

Add to the `env` block in `nomad/jobs/finadvisor.tf`:

```hcl
            DATABASE_URL               = "postgresql://finadvisor:${var.postgres_password}@localhost:${local.ports.postgresql}/finadvisor"
            SMTP_HOST                  = "${var.smtp_host}"
            SMTP_PORT                  = "${var.smtp_port}"
            SMTP_USER                  = "${var.smtp_user}"
            SMTP_PASSWORD              = "${var.smtp_password}"
            SMTP_FROM                  = "${var.smtp_from}"
```

Add SMTP variables to `nomad/jobs/variables.tf`:
```hcl
variable "smtp_host" {
  type    = string
  default = ""
}

variable "smtp_port" {
  type    = string
  default = "587"
}

variable "smtp_user" {
  type    = string
  default = ""
}

variable "smtp_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "smtp_from" {
  type    = string
  default = "noreply@finadvisor.gkamal.online"
}
```

- [ ] **Step 4: Add host volume for postgres_data**

Add to the `mkdir` line in `nomad/infra/install.tf`:
```
"/opt/nomad/volumes/postgres_data"
```

And add the host_volume stanza in the Nomad agent config (or via terraform as appropriate for the existing pattern).

- [ ] **Step 5: Deploy PostgreSQL**

```bash
cd /home/agent/projects/nomad/jobs
terraform apply -target=nomad_job.postgresql -auto-approve
```

Wait for it to be healthy, then run migrations:

```bash
DATABASE_URL=postgresql://finadvisor:<password>@localhost:5432/finadvisor alembic -c migrations/alembic.ini upgrade head
```

- [ ] **Step 6: Rebuild and deploy finadvisor**

```bash
sudo docker build -t finadvisor:local /home/agent/projects/subprime/
cd /home/agent/projects/nomad/jobs
terraform apply -target=nomad_job.finadvisor -auto-approve
```

- [ ] **Step 7: Verify**

```bash
# Check PostgreSQL is running
nomad job status postgresql

# Check finadvisor connects to DB
nomad alloc logs -stderr <alloc-id> | grep -i "database\|pool"

# Hit the app
curl -s https://finadvisor.gkamal.online/step/1 | grep -oP '<title>[^<]*</title>'
```

- [ ] **Step 8: Commit**

```bash
git add nomad/
git commit -m "infra: add PostgreSQL Nomad job, wire DATABASE_URL and SMTP config to finadvisor"
```

---

Self-review complete:
- **Spec coverage**: All sections covered — DB, migrations, session persistence, conversations, OTP, email, templates, CLI, Nomad jobs
- **Placeholder scan**: No TBDs or vague steps
- **Type consistency**: `Session`/`SessionSummary` in core/models.py, re-exported via apps/web/session.py. `create_otp` returns `dict`, `verify_otp` returns `bool` — consistent across otp.py and api.py usage. `save_conversation` takes `Session` + optional `pool` — consistent in conversations.py, api.py, and cli.py.
