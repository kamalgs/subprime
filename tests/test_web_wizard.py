"""Tests for apps/web/session.py — Session Store."""

import pytest
from datetime import datetime, timezone

from apps.web.session import InMemorySessionStore, Session, SessionSummary
from subprime.core.models import InvestorProfile


# ---------------------------------------------------------------------------
# Session model tests
# ---------------------------------------------------------------------------


def test_session_creation_defaults():
    """Session has sensible defaults on creation."""
    session = Session()
    assert len(session.id) == 12
    assert session.mode == "basic"
    assert session.current_step == 1
    assert session.profile is None
    assert session.strategy is None
    assert session.plan is None
    assert session.strategy_chat == []
    assert isinstance(session.created_at, datetime)
    assert isinstance(session.updated_at, datetime)


def test_session_creation_premium_mode():
    """Session can be created with premium mode."""
    session = Session(mode="premium")
    assert session.mode == "premium"


def test_to_summary_without_profile():
    """to_summary() returns None investor_name when profile is absent."""
    session = Session()
    summary = session.to_summary()
    assert isinstance(summary, SessionSummary)
    assert summary.id == session.id
    assert summary.investor_name is None
    assert summary.mode == session.mode
    assert summary.current_step == session.current_step
    assert summary.created_at == session.created_at
    assert summary.updated_at == session.updated_at


def test_to_summary_with_profile():
    """to_summary() returns investor_name from profile.name when profile present."""
    profile = InvestorProfile(
        id="test",
        name="Test User",
        age=30,
        risk_appetite="moderate",
        investment_horizon_years=10,
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=0,
        liabilities_inr=0,
        financial_goals=["retirement"],
        life_stage="early career",
        tax_bracket="new_regime",
    )
    session = Session(profile=profile)
    summary = session.to_summary()
    assert summary.investor_name == "Test User"


# ---------------------------------------------------------------------------
# InMemorySessionStore tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_get_nonexistent_returns_none():
    """Getting a session that doesn't exist returns None."""
    store = InMemorySessionStore()
    result = await store.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_store_save_and_get_roundtrip():
    """Saving then getting a session returns the same session."""
    store = InMemorySessionStore()
    session = Session(mode="premium")
    await store.save(session)
    retrieved = await store.get(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id
    assert retrieved.mode == "premium"


@pytest.mark.asyncio
async def test_store_save_updates_existing_session():
    """Saving an existing session replaces it and updates updated_at."""
    store = InMemorySessionStore()
    session = Session()
    original_updated_at = session.updated_at

    await store.save(session)

    # Modify and re-save
    session.current_step = 3
    await store.save(session)

    retrieved = await store.get(session.id)
    assert retrieved is not None
    assert retrieved.current_step == 3
    # updated_at should be >= original
    assert retrieved.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_store_list_sessions_empty():
    """list_sessions on empty store returns empty list."""
    store = InMemorySessionStore()
    summaries = await store.list_sessions()
    assert summaries == []


@pytest.mark.asyncio
async def test_store_list_sessions_returns_summaries():
    """list_sessions returns SessionSummary objects for stored sessions."""
    store = InMemorySessionStore()
    session1 = Session()
    session2 = Session(mode="premium")
    await store.save(session1)
    await store.save(session2)

    summaries = await store.list_sessions()
    assert len(summaries) == 2
    assert all(isinstance(s, SessionSummary) for s in summaries)
    ids = {s.id for s in summaries}
    assert session1.id in ids
    assert session2.id in ids


@pytest.mark.asyncio
async def test_store_list_sessions_most_recent_first():
    """list_sessions returns sessions sorted by updated_at descending."""
    import asyncio

    store = InMemorySessionStore()
    session1 = Session()
    await store.save(session1)
    # Small delay so updated_at timestamps differ
    await asyncio.sleep(0.01)
    session2 = Session()
    await store.save(session2)

    summaries = await store.list_sessions()
    # Most recent (session2) should come first
    assert summaries[0].id == session2.id
    assert summaries[1].id == session1.id


@pytest.mark.asyncio
async def test_store_list_sessions_respects_limit():
    """list_sessions respects the limit parameter."""
    store = InMemorySessionStore()
    for _ in range(5):
        await store.save(Session())

    summaries = await store.list_sessions(limit=3)
    assert len(summaries) == 3
