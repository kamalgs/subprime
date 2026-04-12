"""Tests for persistence layer: config, models, DB, sessions, OTP, conversations."""
from __future__ import annotations
import os
from datetime import datetime, timezone
import pytest

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
