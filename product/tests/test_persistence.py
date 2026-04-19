"""Tests for persistence layer: config, models, DB, sessions, OTP, conversations."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from pydantic_ai.usage import RunUsage
from subprime.core.models import InvestorProfile, Session, SessionSummary


def _test_profile() -> InvestorProfile:
    return InvestorProfile(
        id="test", name="Test User", age=30, risk_appetite="moderate",
        investment_horizon_years=10, monthly_investible_surplus_inr=50000,
        existing_corpus_inr=0, liabilities_inr=0,
        financial_goals=["retirement"], life_stage="early career",
        tax_bracket="new_regime",
    )

class TestPersistenceConfig:
    def test_database_url_default_none(self):
        from subprime.core.config import DATABASE_URL
        assert DATABASE_URL is None or isinstance(DATABASE_URL, str)

    def test_otp_settings_defaults(self):
        from subprime.core.config import OTP_DAILY_LIMIT, OTP_EXPIRY_MINUTES
        assert OTP_DAILY_LIMIT == 100
        assert OTP_EXPIRY_MINUTES == 10

    def test_smtp_settings_importable(self):
        from subprime.core.config import SMTP_HOST, SMTP_PORT, SMTP_FROM
        assert SMTP_PORT == 587
        assert isinstance(SMTP_FROM, str)


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
        assert len(migration_files) == 1
        content = migration_files[0].read_text()
        assert "CREATE TABLE" in content
        assert "sessions" in content
        assert "conversations" in content
        assert "otps" in content


@pytest.fixture
def in_memory_store():
    from subprime.core.persistence import InMemorySessionStore
    return InMemorySessionStore()


class TestInMemorySessionStore:
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, in_memory_store):
        result = await in_memory_store.get("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get(self, in_memory_store):
        session = Session()
        await in_memory_store.save(session)
        retrieved = await in_memory_store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    @pytest.mark.asyncio
    async def test_save_updates(self, in_memory_store):
        session = Session()
        await in_memory_store.save(session)
        session.current_step = 3
        await in_memory_store.save(session)
        retrieved = await in_memory_store.get(session.id)
        assert retrieved.current_step == 3

    @pytest.mark.asyncio
    async def test_list_empty(self, in_memory_store):
        result = await in_memory_store.list_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_summaries(self, in_memory_store):
        session = Session()
        await in_memory_store.save(session)
        summaries = await in_memory_store.list_sessions()
        assert len(summaries) == 1
        assert isinstance(summaries[0], SessionSummary)

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, in_memory_store):
        for _ in range(5):
            await in_memory_store.save(Session())
        summaries = await in_memory_store.list_sessions(limit=3)
        assert len(summaries) == 3

    @pytest.mark.asyncio
    async def test_save_with_profile(self, in_memory_store):
        session = Session(profile=_test_profile())
        await in_memory_store.save(session)
        retrieved = await in_memory_store.get(session.id)
        assert retrieved.profile is not None
        assert retrieved.profile.name == "Test User"


@pytest.fixture
async def postgres_store():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL not set")
    from subprime.core.db import init_pool
    from subprime.core.persistence import PostgresSessionStore
    pool = await init_pool(db_url)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions")
    store = PostgresSessionStore(pool)
    yield store
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions")
    await pool.close()


class TestPostgresSessionStore:
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, postgres_store):
        result = await postgres_store.get("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get(self, postgres_store):
        session = Session(mode="premium")
        await postgres_store.save(session)
        retrieved = await postgres_store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.mode == "premium"

    @pytest.mark.asyncio
    async def test_save_with_profile(self, postgres_store):
        session = Session(profile=_test_profile())
        await postgres_store.save(session)
        retrieved = await postgres_store.get(session.id)
        assert retrieved.profile is not None
        assert retrieved.profile.name == "Test User"

    @pytest.mark.asyncio
    async def test_is_demo_roundtrip(self, postgres_store):
        """is_demo flag must persist through save/get — OTP cheat sessions rely on it."""
        session = Session(mode="premium", is_demo=True)
        await postgres_store.save(session)
        retrieved = await postgres_store.get(session.id)
        assert retrieved.is_demo is True

    @pytest.mark.asyncio
    async def test_is_demo_default_false(self, postgres_store):
        session = Session()
        await postgres_store.save(session)
        retrieved = await postgres_store.get(session.id)
        assert retrieved.is_demo is False

    @pytest.mark.asyncio
    async def test_save_updates(self, postgres_store):
        session = Session()
        await postgres_store.save(session)
        session.current_step = 5
        await postgres_store.save(session)
        retrieved = await postgres_store.get(session.id)
        assert retrieved.current_step == 5

    @pytest.mark.asyncio
    async def test_list_sessions(self, postgres_store):
        await postgres_store.save(Session())
        await postgres_store.save(Session())
        summaries = await postgres_store.list_sessions()
        assert len(summaries) == 2

    @pytest.mark.asyncio
    async def test_list_with_profile_shows_name(self, postgres_store):
        session = Session(profile=_test_profile())
        await postgres_store.save(session)
        summaries = await postgres_store.list_sessions()
        assert any(s.investor_name == "Test User" for s in summaries)


class TestConversations:
    def test_module_imports(self):
        from subprime.core.conversations import save_conversation, list_conversations
        assert callable(save_conversation)
        assert callable(list_conversations)

    @pytest.mark.asyncio
    async def test_save_to_json_fallback(self, tmp_path):
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
    async def test_save_includes_plan(self, tmp_path):
        from subprime.core.conversations import save_conversation
        from subprime.core.models import Allocation, InvestmentPlan, MutualFund
        plan = InvestmentPlan(
            allocations=[Allocation(
                fund=MutualFund(amfi_code="119551", name="UTI Nifty 50"),
                allocation_pct=100, mode="sip", monthly_sip_inr=10000, rationale="Test",
            )],
            rationale="Test plan",
        )
        s = Session(profile=_test_profile(), plan=plan, current_step=4)
        path = await save_conversation(session=s, pool=None, conversations_dir=tmp_path)
        import json
        data = json.loads(path.read_text())
        assert data["plan"] is not None
        assert data["plan"]["allocations"][0]["fund"]["name"] == "UTI Nifty 50"

    @pytest.mark.asyncio
    async def test_save_without_profile(self, tmp_path):
        from subprime.core.conversations import save_conversation
        s = Session(current_step=4)
        path = await save_conversation(session=s, pool=None, conversations_dir=tmp_path)
        import json
        data = json.loads(path.read_text())
        assert data["investor_name"] is None
        assert data["profile"] is None

    @pytest.mark.asyncio
    async def test_list_from_json(self, tmp_path):
        from subprime.core.conversations import save_conversation, list_conversations
        s1 = Session(profile=_test_profile(), current_step=4)
        s2 = Session(profile=_test_profile(), current_step=4, mode="premium")
        await save_conversation(session=s1, pool=None, conversations_dir=tmp_path)
        await save_conversation(session=s2, pool=None, conversations_dir=tmp_path)
        result = await list_conversations(pool=None, conversations_dir=tmp_path)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_empty_dir(self, tmp_path):
        from subprime.core.conversations import list_conversations
        result = await list_conversations(pool=None, conversations_dir=tmp_path)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_nonexistent_dir(self, tmp_path):
        from subprime.core.conversations import list_conversations
        result = await list_conversations(pool=None, conversations_dir=tmp_path / "nonexistent")
        assert result == []


class TestConversationsPostgres:
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


class TestOTPInMemory:
    """OTP tests using a mock pool."""

    def _make_mock_pool(self, fetchval_return=0, fetchrow_return=None):
        pool = AsyncMock()
        pool.fetchval = AsyncMock(return_value=fetchval_return)
        pool.fetchrow = AsyncMock(return_value=fetchrow_return)
        pool.execute = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_create_otp_success(self):
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=5)
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is True
        assert len(result["code"]) == 6
        assert result["code"].isdigit()
        assert pool.execute.call_count >= 2  # invalidate + insert

    @pytest.mark.asyncio
    async def test_create_otp_daily_limit(self):
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=100)
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is False
        assert "full" in result["reason"].lower() or "limit" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_create_otp_at_limit_minus_one(self):
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=99)
        result = await create_otp(pool, "test@example.com")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_verify_otp_success(self):
        from subprime.core.otp import verify_otp
        from datetime import timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1, "email": "test@example.com", "code": "123456",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "verified_at": None,
        })
        assert await verify_otp(pool, "test@example.com", "123456") is True
        pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_otp_not_found(self):
        from subprime.core.otp import verify_otp
        pool = self._make_mock_pool(fetchrow_return=None)
        assert await verify_otp(pool, "test@example.com", "999999") is False

    @pytest.mark.asyncio
    async def test_verify_otp_expired(self):
        from subprime.core.otp import verify_otp
        from datetime import timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1, "email": "test@example.com", "code": "123456",
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
            "verified_at": None,
        })
        assert await verify_otp(pool, "test@example.com", "123456") is False

    @pytest.mark.asyncio
    async def test_verify_otp_already_used(self):
        from subprime.core.otp import verify_otp
        from datetime import timedelta
        pool = self._make_mock_pool(fetchrow_return={
            "id": 1, "email": "test@example.com", "code": "123456",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "verified_at": datetime.now(timezone.utc),
        })
        assert await verify_otp(pool, "test@example.com", "123456") is False

    @pytest.mark.asyncio
    async def test_daily_count(self):
        from subprime.core.otp import daily_otp_count
        pool = self._make_mock_pool(fetchval_return=42)
        assert await daily_otp_count(pool) == 42

    @pytest.mark.asyncio
    async def test_daily_count_none_returns_zero(self):
        from subprime.core.otp import daily_otp_count
        pool = self._make_mock_pool(fetchval_return=None)
        assert await daily_otp_count(pool) == 0

    @pytest.mark.asyncio
    async def test_code_is_zero_padded(self):
        """Codes like 000123 should keep leading zeros."""
        from subprime.core.otp import create_otp
        pool = self._make_mock_pool(fetchval_return=0)
        result = await create_otp(pool, "test@example.com")
        assert len(result["code"]) == 6


class TestOTPPostgres:
    """Full OTP round-trip — skipped without DATABASE_URL."""

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
        assert await verify_otp(pool, "test@example.com", result["code"]) is True
        # Second verify should fail
        assert await verify_otp(pool, "test@example.com", result["code"]) is False

    @pytest.mark.asyncio
    async def test_wrong_code(self, pool):
        from subprime.core.otp import create_otp, verify_otp
        await create_otp(pool, "test@example.com")
        assert await verify_otp(pool, "test@example.com", "000000") is False

    @pytest.mark.asyncio
    async def test_new_otp_invalidates_old(self, pool):
        from subprime.core.otp import create_otp, verify_otp
        r1 = await create_otp(pool, "test@example.com")
        r2 = await create_otp(pool, "test@example.com")
        assert await verify_otp(pool, "test@example.com", r1["code"]) is False
        assert await verify_otp(pool, "test@example.com", r2["code"]) is True


class TestEmail:
    def test_module_imports(self):
        from apps.web.email import send_otp_email
        assert callable(send_otp_email)

    @pytest.mark.asyncio
    async def test_send_returns_false_without_smtp(self):
        from apps.web.email import send_otp_email
        result = await send_otp_email("test@example.com", "123456")
        assert result is False


from httpx import ASGITransport, AsyncClient

class TestOTPEndpoints:
    @pytest.mark.asyncio
    async def test_request_otp_empty_email(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/request-otp", data={"email": ""})
            assert resp.status_code == 200
            # Should show error about valid email or premium not available
            text = resp.text.lower()
            assert "email" in text or "not available" in text

    @pytest.mark.asyncio
    async def test_request_otp_no_db(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/request-otp", data={"email": "test@example.com"})
            assert resp.status_code == 200
            assert "not available" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_verify_otp_no_db(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/verify-otp", data={"email": "test@example.com", "code": "123456"})
            assert resp.status_code == 200
            assert "not available" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_step1_shows_otp_form(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/step/1")
            assert resp.status_code == 200
            assert "otp-section" in resp.text
            assert "Send code" in resp.text

    @pytest.mark.asyncio
    async def test_conversation_saved_on_plan_generation(self):
        """After generating a plan, conversation is saved."""
        from apps.web.main import create_app
        from subprime.core.models import StrategyOutline, Allocation, InvestmentPlan, MutualFund
        from unittest.mock import AsyncMock, patch

        app = create_app()
        mock_strategy = StrategyOutline(
            equity_pct=70, debt_pct=20, gold_pct=10, other_pct=0,
            equity_approach="Index", key_themes=["growth"],
            risk_return_summary="Moderate", open_questions=[],
        )
        mock_plan = InvestmentPlan(
            allocations=[Allocation(
                fund=MutualFund(amfi_code="119551", name="Test"),
                allocation_pct=100, mode="sip", monthly_sip_inr=10000, rationale="Test",
            )],
            rationale="Test",
        )

        with patch("apps.web.api.generate_strategy", new_callable=AsyncMock, return_value=mock_strategy), \
             patch("apps.web.api.generate_plan", new_callable=AsyncMock, return_value=(mock_plan, RunUsage())), \
             patch("subprime.core.conversations.save_conversation", new_callable=AsyncMock) as mock_save:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                await client.post("/api/select-persona", data={"persona_id": "P01"})
                store = app.state.session_store
                sessions = list(store._sessions.values())
                sessions[0].strategy = mock_strategy
                await store.save(sessions[0])
                await client.post("/api/generate-plan")
                mock_save.assert_called_once()
