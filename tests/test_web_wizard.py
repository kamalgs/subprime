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


# ---------------------------------------------------------------------------
# Rendering helper tests
# ---------------------------------------------------------------------------

from apps.web.rendering import (
    format_inr,
    render_markdown,
    compute_corpus,
    inflation_adjusted,
    chart_data_donut,
    chart_data_corpus,
)


class TestFormatInr:
    def test_crores(self):
        assert format_inr(25000000) == "₹2.50 Cr"

    def test_crores_large(self):
        assert format_inr(100000000) == "₹10.00 Cr"

    def test_exactly_one_crore(self):
        assert format_inr(10000000) == "₹1.00 Cr"

    def test_lakhs(self):
        assert format_inr(550000) == "₹5.50 L"

    def test_exactly_one_lakh(self):
        assert format_inr(100000) == "₹1.00 L"

    def test_small_amount(self):
        assert format_inr(45000) == "₹45,000"

    def test_zero(self):
        assert format_inr(0) == "₹0"

    def test_boundary_just_below_lakh(self):
        result = format_inr(99999)
        assert result == "₹99,999"

    def test_boundary_just_above_crore(self):
        result = format_inr(10000001)
        assert "Cr" in result


class TestRenderMarkdown:
    def test_bold_to_strong(self):
        html = render_markdown("**bold**")
        assert "<strong>bold</strong>" in html

    def test_bullet_list(self):
        html = render_markdown("- item one\n- item two")
        assert "<li>" in html
        assert "item one" in html
        assert "item two" in html

    def test_paragraph(self):
        html = render_markdown("Hello world")
        assert "<p>" in html
        assert "Hello world" in html

    def test_empty_string(self):
        assert render_markdown("") == ""

    def test_html_escaping_no_script(self):
        html = render_markdown("<script>alert('xss')</script>")
        assert "<script>" not in html

    def test_html_escaping_angle_brackets(self):
        html = render_markdown("a < b")
        assert "<script>" not in html
        # lt entity or escaped
        assert "script" not in html or "&lt;" in html


class TestComputeCorpus:
    def test_basic_computation(self):
        # 10k/mo at 12% for 10yr ≈ 23.2L
        result = compute_corpus(10000, 10, 12)
        assert abs(result - 2320000) < 50000  # within 50k of 23.2L

    def test_zero_monthly_sip(self):
        assert compute_corpus(0, 10, 12) == 0.0

    def test_zero_years(self):
        assert compute_corpus(10000, 0, 12) == 0.0

    def test_zero_cagr(self):
        assert compute_corpus(10000, 10, 0) == 0.0

    def test_negative_inputs(self):
        assert compute_corpus(-1000, 10, 12) == 0.0
        assert compute_corpus(10000, -5, 12) == 0.0
        assert compute_corpus(10000, 10, -5) == 0.0


class TestInflationAdjusted:
    def test_basic_discount(self):
        # 1Cr at 6% for 10yr ≈ 55.8L
        result = inflation_adjusted(10000000, 10, 6.0)
        assert abs(result - 5583948) < 50000  # within 50k of 55.8L

    def test_zero_years_returns_future_value(self):
        assert inflation_adjusted(10000000, 0) == 10000000

    def test_negative_years_returns_future_value(self):
        assert inflation_adjusted(5000000, -1) == 5000000

    def test_default_inflation(self):
        # Default inflation is 6%
        result = inflation_adjusted(10000000, 10)
        assert abs(result - 5583948) < 50000


class TestChartDataDonut:
    def test_all_segments_present(self):
        result = chart_data_donut(60, 30, 5, 5)
        assert result["labels"] == ["Equity", "Debt", "Gold", "Other"]
        assert result["values"] == [60, 30, 5, 5]
        assert len(result["colors"]) == 4

    def test_zero_segments_excluded(self):
        result = chart_data_donut(70, 30, 0, 0)
        assert "Gold" not in result["labels"]
        assert "Other" not in result["labels"]
        assert "Equity" in result["labels"]
        assert "Debt" in result["labels"]
        assert len(result["values"]) == 2

    def test_colors_correct(self):
        result = chart_data_donut(100, 0, 0, 0)
        assert result["colors"] == ["#4f46e5"]

    def test_debt_color(self):
        result = chart_data_donut(0, 100, 0, 0)
        assert result["colors"] == ["#0891b2"]

    def test_gold_color(self):
        result = chart_data_donut(0, 0, 100, 0)
        assert result["colors"] == ["#d97706"]

    def test_other_color(self):
        result = chart_data_donut(0, 0, 0, 100)
        assert result["colors"] == ["#6b7280"]


class TestChartDataCorpus:
    def test_scenarios_computed(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        assert "scenarios" in result
        assert len(result["scenarios"]) == 3

    def test_sip_fmt(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        assert result["sip_fmt"].startswith("₹")

    def test_years_field(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        assert result["years"] == 10

    def test_scenario_fields(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        for scenario in result["scenarios"]:
            assert "label" in scenario
            assert "cagr" in scenario
            assert "future_value" in scenario
            assert "present_value" in scenario
            assert "future_value_fmt" in scenario
            assert "present_value_fmt" in scenario
            assert "color" in scenario

    def test_scenario_labels(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        labels = [s["label"] for s in result["scenarios"]]
        assert "Bear" in labels
        assert "Base" in labels
        assert "Bull" in labels

    def test_scenario_colors(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        color_map = {s["label"]: s["color"] for s in result["scenarios"]}
        assert color_map["Bear"] == "#ef4444"
        assert color_map["Base"] == "#f59e0b"
        assert color_map["Bull"] == "#22c55e"

    def test_zero_cagr_excluded(self):
        result = chart_data_corpus(10000, 10, 0, 12, 15)
        labels = [s["label"] for s in result["scenarios"]]
        assert "Bear" not in labels
        assert "Base" in labels
        assert "Bull" in labels

    def test_future_value_ordering(self):
        result = chart_data_corpus(10000, 10, 8, 12, 15)
        values = {s["label"]: s["future_value"] for s in result["scenarios"]}
        assert values["Bull"] > values["Base"] > values["Bear"]


# ---------------------------------------------------------------------------
# FastAPI app factory tests
# ---------------------------------------------------------------------------

from httpx import ASGITransport, AsyncClient


class TestAppFactory:
    def test_create_app(self):
        from apps.web.main import create_app
        app = create_app()
        assert app is not None

    @pytest.mark.asyncio
    async def test_root_redirects_to_step1(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 307
            assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_static_files_served(self):
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/static/app.css")
            assert resp.status_code == 200
            assert "htmx-indicator" in resp.text
