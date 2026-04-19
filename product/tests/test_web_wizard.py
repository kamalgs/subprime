"""Tests for apps/web/session.py — Session Store."""

from pathlib import Path

import pytest
from datetime import datetime, timezone
from pydantic_ai.usage import RunUsage

from apps.web.session import InMemorySessionStore, Session, SessionSummary
from subprime.core.models import InvestorProfile


# When the React SPA is built, the legacy Jinja /step/* routes are unmounted
# and everything below /step/* returns the SPA's index.html. Tests that drive
# the Jinja wizard directly are retired in favour of test_frontend_e2e.py.
_LEGACY_JINJA_AVAILABLE = not (
    Path(__file__).resolve().parents[1] / "apps" / "web" / "static" / "dist" / "index.html"
).exists()

skip_when_spa_built = pytest.mark.skipif(
    not _LEGACY_JINJA_AVAILABLE,
    reason="Legacy Jinja wizard not mounted when SPA is built; see test_frontend_e2e.py",
)


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
    short_fund_name,
)


class TestShortFundName:
    def test_strips_direct_growth(self):
        assert short_fund_name("Mirae Asset Large Cap Fund Direct Growth") == "Mirae Asset Large Cap"

    def test_strips_plan_and_option(self):
        assert short_fund_name("HDFC Index Fund NIFTY 50 Plan Direct Growth Option") == "HDFC Index NIFTY 50"

    def test_strips_regular_and_idcw(self):
        assert short_fund_name("Axis Bluechip Fund Regular IDCW") == "Axis Bluechip"

    def test_preserves_when_already_short(self):
        assert short_fund_name("UTI Nifty 50") == "UTI Nifty 50"

    def test_truncates_if_still_too_long(self):
        result = short_fund_name("A Very Long Name That Cannot Be Compressed By Token Stripping Alone", max_len=20)
        assert len(result) <= 20
        assert result.endswith("…")

    def test_empty_name(self):
        assert short_fund_name("") == ""

    def test_falls_back_if_stripping_empties(self):
        # All-noise input should return original rather than empty string
        assert short_fund_name("Direct Growth Plan") == "Direct Growth Plan"


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
    async def test_root_serves_app(self):
        """Root / either redirects to /step/1 (legacy) or serves the SPA index."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/", follow_redirects=False)
            # When the SPA is built the route returns 200 with index.html;
            # otherwise it falls back to a 307 redirect to /step/1.
            if resp.status_code == 200:
                assert "<div id=\"root\"" in resp.text or "<html" in resp.text.lower()
            else:
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


# ---------------------------------------------------------------------------
# Step 1 — Tier Selection
# ---------------------------------------------------------------------------


@skip_when_spa_built
class TestStep1TierSelection:
    @pytest.mark.asyncio
    async def test_step1_renders(self):
        """GET /step/1 returns 200 and shows both tier cards."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/step/1")
        assert resp.status_code == 200
        assert "Basic" in resp.text
        assert "Premium" in resp.text

    @pytest.mark.asyncio
    async def test_step1_sets_session_cookie(self):
        """GET /step/1 sets the benji_session cookie."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/step/1")
        assert resp.status_code == 200
        assert "benji_session" in resp.cookies

    @pytest.mark.asyncio
    async def test_select_tier_basic(self):
        """POST /api/select-tier mode=basic returns HX-Redirect to /step/2."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-tier", data={"mode": "basic"})
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/step/2"

    @pytest.mark.asyncio
    async def test_select_tier_premium(self):
        """POST /api/select-tier mode=premium returns HX-Redirect to /step/2."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-tier", data={"mode": "premium"})
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/step/2"

    @pytest.mark.asyncio
    async def test_select_tier_saves_mode(self):
        """POST /api/select-tier saves the chosen mode in the session."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-tier", data={"mode": "premium"})
        session_id = resp.cookies.get("benji_session")
        assert session_id is not None
        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        assert session.mode == "premium"

    @pytest.mark.asyncio
    async def test_select_tier_sets_step_2(self):
        """POST /api/select-tier advances current_step to 2."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-tier", data={"mode": "basic"})
        session_id = resp.cookies.get("benji_session")
        session = app.state.session_store._sessions.get(session_id)
        assert session.current_step == 2


# ---------------------------------------------------------------------------
# Step 2 — Profile (Persona Cards + Custom Form)
# ---------------------------------------------------------------------------


@skip_when_spa_built
class TestStep2Profile:
    @pytest.mark.asyncio
    async def test_step2_renders_archetype_cards_for_regular_session(self):
        """Regular sessions see 3 archetype starting points (not the full persona bank)."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            tier_resp = await client.post("/api/select-tier", data={"mode": "basic"})
            assert "benji_session" in tier_resp.cookies
            resp = await client.get("/step/2")
        assert resp.status_code == 200
        assert "Early career" in resp.text
        assert "Mid career" in resp.text
        assert "Retired" in resp.text
        assert "Tony Stark" not in resp.text

    @pytest.mark.asyncio
    async def test_step2_renders_full_persona_bank_for_demo_session(self):
        """Demo sessions (unlocked via OTP cheat) see the full research persona bank."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            tier_resp = await client.post("/api/select-tier", data={"mode": "basic"})
            session_id = tier_resp.cookies.get("benji_session")
            store = app.state.session_store
            s = next(s for s in store._sessions.values() if s.id == session_id)
            s.is_demo = True
            await store.save(s)
            resp = await client.get("/step/2")
        assert resp.status_code == 200
        assert "Tony Stark" in resp.text

    @pytest.mark.asyncio
    async def test_step2_redirects_without_session(self):
        """GET /step/2 without a session cookie redirects to /step/1."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/step/2", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_step2_redirects_with_unknown_session(self):
        """GET /step/2 with a bogus session cookie redirects to /step/1."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/step/2",
                follow_redirects=False,
                cookies={"benji_session": "nonexistent-id"},
            )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_select_persona(self):
        """POST /api/select-persona returns HX-Redirect to /step/3."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/step/3"

    @pytest.mark.asyncio
    async def test_select_persona_saves_profile(self):
        """After selecting persona P01, session profile should be Tony Stark."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
        session_id = resp.cookies.get("benji_session")
        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        assert session.profile is not None
        assert session.profile.name == "Tony Stark"

    @pytest.mark.asyncio
    async def test_select_persona_sets_step_3(self):
        """POST /api/select-persona advances current_step to 3."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
        session_id = resp.cookies.get("benji_session")
        session = app.state.session_store._sessions.get(session_id)
        assert session.current_step == 3

    @pytest.mark.asyncio
    async def test_submit_custom_profile(self):
        """POST /api/submit-profile with all required fields returns HX-Redirect to /step/3."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/submit-profile",
                data={
                    "name": "Test User",
                    "age": "28",
                    "monthly_sip": "15000",
                    "existing_corpus": "100000",
                    "risk_appetite": "moderate",
                    "horizon_years": "15",
                    "life_stage": "early career",
                    "preferences": "Prefer index funds",
                    "goals": ["retirement", "wealth_building"],
                },
            )
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/step/3"

    @pytest.mark.asyncio
    async def test_submit_custom_profile_saves_data(self):
        """After submitting custom profile, session holds the submitted data."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/submit-profile",
                data={
                    "name": "Sita Ram",
                    "age": "35",
                    "monthly_sip": "30000",
                    "existing_corpus": "500000",
                    "risk_appetite": "aggressive",
                    "horizon_years": "20",
                    "life_stage": "mid career",
                    "goals": ["retirement"],
                },
            )
        session_id = resp.cookies.get("benji_session")
        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        assert session.profile is not None
        assert session.profile.name == "Sita Ram"
        assert session.profile.age == 35
        assert session.profile.monthly_investible_surplus_inr == 30000
        assert session.profile.risk_appetite == "aggressive"
        assert "Retirement" in session.profile.financial_goals

    @pytest.mark.asyncio
    async def test_submit_custom_profile_default_goals(self):
        """Submitting no goals defaults to ['Wealth Building']."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/submit-profile",
                data={
                    "name": "No Goals User",
                    "age": "40",
                    "monthly_sip": "10000",
                    "existing_corpus": "0",
                    "risk_appetite": "conservative",
                    "horizon_years": "10",
                    "life_stage": "mid career",
                },
            )
        session_id = resp.cookies.get("benji_session")
        session = app.state.session_store._sessions.get(session_id)
        assert session.profile.financial_goals == ["Wealth Building"]

    @pytest.mark.asyncio
    async def test_step3_redirects_without_profile(self):
        """GET /step/3 without a profile in session redirects to /step/1."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create a session but don't set profile
            tier_resp = await client.post("/api/select-tier", data={"mode": "basic"})
            assert "benji_session" in tier_resp.cookies
            resp = await client.get("/step/3", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_step3_renders_with_profile(self):
        """GET /step/3 with a valid profile renders the strategy stub page."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-persona", data={"persona_id": "P01"})
            resp = await client.get("/step/3", follow_redirects=False)
        assert resp.status_code == 200
        assert "Strategy" in resp.text


# ---------------------------------------------------------------------------
# Step 3 — Strategy Dashboard (Task 5)
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, patch
from subprime.core.models import StrategyOutline, Allocation, InvestmentPlan, MutualFund


def _mock_strategy():
    return StrategyOutline(
        equity_pct=70, debt_pct=20, gold_pct=10, other_pct=0,
        equity_approach="Mix of large cap index and mid cap active funds",
        key_themes=["diversification", "long-term growth"],
        risk_return_summary="Expected 11-12% CAGR with moderate drawdowns",
        open_questions=[],
    )


def _mock_plan():
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="119551", name="UTI Nifty 50 Index Fund",
                    category="Large Cap", fund_house="UTI", expense_ratio=0.18, morningstar_rating=4),
                allocation_pct=40, mode="sip", monthly_sip_inr=20000,
                rationale="Low cost large cap index fund",
            ),
            Allocation(
                fund=MutualFund(amfi_code="120505", name="Parag Parikh Flexi Cap Fund",
                    category="Flexi Cap", fund_house="PPFAS", expense_ratio=0.63, morningstar_rating=5),
                allocation_pct=30, mode="sip", monthly_sip_inr=15000,
                rationale="Diversified flexi cap with international exposure",
            ),
            Allocation(
                fund=MutualFund(amfi_code="119533", name="HDFC Short Term Debt Fund",
                    category="Short Duration", fund_house="HDFC", expense_ratio=0.35),
                allocation_pct=30, mode="sip", monthly_sip_inr=15000,
                rationale="Stable debt allocation",
            ),
        ],
        projected_returns={"bear": 7.5, "base": 11.0, "bull": 15.0},
        rationale="This plan balances growth and stability.",
        risks=["Market drops can be 20-30%"],
        setup_phase="1. Open account on Kuvera\n2. Start SIPs",
        rebalancing_guidelines="Check once a year",
    )


@skip_when_spa_built
class TestStep3Strategy:

    @pytest.mark.asyncio
    async def test_step3_redirects_without_profile(self):
        """GET /step/3 without a profile in session redirects to /step/1."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            tier_resp = await client.post("/api/select-tier", data={"mode": "basic"})
            assert "benji_session" in tier_resp.cookies
            resp = await client.get("/step/3", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_generate_strategy_returns_dashboard(self):
        """GET /api/generate-strategy returns strategy dashboard with expected content."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_strategy", new=AsyncMock(return_value=(_mock_strategy(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                await client.post("/api/select-persona", data={"persona_id": "P01"})
                resp = await client.get("/api/generate-strategy")
        assert resp.status_code == 200
        assert "Equity" in resp.text
        assert "diversification" in resp.text

    @pytest.mark.asyncio
    async def test_generate_strategy_saves_to_session(self):
        """After calling generate-strategy, session.strategy is set."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_strategy", new=AsyncMock(return_value=(_mock_strategy(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                session_id = persona_resp.cookies.get("benji_session")
                await client.get("/api/generate-strategy")

        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        assert session.strategy is not None
        assert session.strategy.equity_pct == 70

    @pytest.mark.asyncio
    async def test_revise_strategy(self):
        """POST /api/revise-strategy returns updated strategy dashboard."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_strategy", new=AsyncMock(return_value=(_mock_strategy(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                session_id = persona_resp.cookies.get("benji_session")

                # Seed strategy directly into session
                store = app.state.session_store
                sessions = list(store._sessions.values())
                for s in sessions:
                    if s.id == session_id:
                        s.strategy = _mock_strategy()
                        await store.save(s)
                        break

                resp = await client.post("/api/revise-strategy", data={"feedback": "more conservative please"})

        assert resp.status_code == 200
        assert "Equity" in resp.text

    @pytest.mark.asyncio
    async def test_revise_strategy_saves_chat(self):
        """After revising strategy, user feedback is in session.strategy_chat."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_strategy", new=AsyncMock(return_value=(_mock_strategy(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                session_id = persona_resp.cookies.get("benji_session")

                store = app.state.session_store
                for s in list(store._sessions.values()):
                    if s.id == session_id:
                        s.strategy = _mock_strategy()
                        await store.save(s)
                        break

                await client.post("/api/revise-strategy", data={"feedback": "reduce equity"})

        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        user_turns = [t for t in session.strategy_chat if t.role == "user"]
        assert len(user_turns) >= 1
        assert "reduce equity" in user_turns[0].content

    @pytest.mark.asyncio
    async def test_generate_plan_redirects_to_step4(self):
        """POST /api/generate-plan returns a 303 redirect to /step/4."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_plan", new=AsyncMock(return_value=(_mock_plan(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                session_id = persona_resp.cookies.get("benji_session")

                store = app.state.session_store
                for s in list(store._sessions.values()):
                    if s.id == session_id:
                        s.strategy = _mock_strategy()
                        await store.save(s)
                        break

                resp = await client.post("/api/generate-plan", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/step/4"

    @pytest.mark.asyncio
    async def test_generate_plan_saves_plan(self):
        """After generating plan, session.plan is set and current_step=4."""
        from apps.web.main import create_app
        app = create_app()
        with patch("apps.web.api.generate_plan", new=AsyncMock(return_value=(_mock_plan(), RunUsage()))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/api/select-tier", data={"mode": "basic"})
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                session_id = persona_resp.cookies.get("benji_session")

                store = app.state.session_store
                for s in list(store._sessions.values()):
                    if s.id == session_id:
                        s.strategy = _mock_strategy()
                        await store.save(s)
                        break

                await client.post("/api/generate-plan")

        session = app.state.session_store._sessions.get(session_id)
        assert session is not None
        assert session.plan is not None
        assert session.current_step == 4

    @pytest.mark.asyncio
    async def test_reset_creates_new_session(self):
        """POST /api/reset returns HX-Redirect to /step/1 with a new session cookie."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Establish an initial session
            persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            old_session_id = persona_resp.cookies.get("benji_session")

            resp = await client.post("/api/reset")

        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/step/1"
        new_session_id = resp.cookies.get("benji_session")
        assert new_session_id is not None
        assert new_session_id != old_session_id


# ---------------------------------------------------------------------------
# Step 4 — Plan Results Page (Task 6)
# ---------------------------------------------------------------------------


@skip_when_spa_built
class TestStep4PlanResult:

    @pytest.mark.asyncio
    async def test_step4_redirects_without_plan(self):
        """GET /step/4 with no plan and no in-flight generation bounces back."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Establish a session but don't inject a plan
            await client.post("/api/select-tier", data={"mode": "basic"})
            resp = await client.get("/step/4", follow_redirects=False)
        assert resp.status_code == 302
        # No plan, no generation in flight → bounced to strategy or start
        assert resp.headers["location"] in ("/step/1", "/step/3")

    @pytest.mark.asyncio
    async def test_step4_renders_plan(self):
        """GET /step/4 with plan shows fund names, SIP amounts, projections."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Set up tier + persona
            await client.post("/api/select-tier", data={"mode": "basic"})
            persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            session_id = persona_resp.cookies.get("benji_session")

            # Inject plan + strategy directly
            store = app.state.session_store
            sessions = list(store._sessions.values())
            s = next(s for s in sessions if s.id == session_id)
            s.strategy = _mock_strategy()
            s.plan = _mock_plan()
            s.current_step = 4
            await store.save(s)

            resp = await client.get("/step/4")

        assert resp.status_code == 200
        # Fund names
        assert "UTI Nifty 50 Index Fund" in resp.text
        assert "Parag Parikh Flexi Cap Fund" in resp.text
        # Allocation percentages (template casts to int)
        assert "40%" in resp.text
        assert "30%" in resp.text
        # Stat cards presence
        assert "Funds" in resp.text

    @pytest.mark.asyncio
    async def test_step4_shows_corpus_table(self):
        """Step 4 shows corpus projection data when SIP and horizon are available."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            session_id = persona_resp.cookies.get("benji_session")

            store = app.state.session_store
            sessions = list(store._sessions.values())
            s = next(s for s in sessions if s.id == session_id)
            s.strategy = _mock_strategy()
            s.plan = _mock_plan()
            s.current_step = 4
            await store.save(s)

            resp = await client.get("/step/4")

        assert resp.status_code == 200
        # Corpus projection section
        assert "Corpus projection" in resp.text
        # Scenario labels
        assert "Bear" in resp.text
        assert "Base" in resp.text
        assert "Bull" in resp.text
        # canvas element for chart
        assert "corpus-chart" in resp.text

    @pytest.mark.asyncio
    async def test_step4_shows_risks(self):
        """Step 4 shows risk section."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            session_id = persona_resp.cookies.get("benji_session")

            store = app.state.session_store
            sessions = list(store._sessions.values())
            s = next(s for s in sessions if s.id == session_id)
            s.strategy = _mock_strategy()
            s.plan = _mock_plan()
            s.current_step = 4
            await store.save(s)

            resp = await client.get("/step/4")

        assert resp.status_code == 200
        assert "Risks to consider" in resp.text
        assert "Market drops" in resp.text

    @pytest.mark.asyncio
    async def test_step4_shows_rationale_markdown(self):
        """Plan rationale is rendered as markdown HTML."""
        from apps.web.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            session_id = persona_resp.cookies.get("benji_session")

            store = app.state.session_store
            sessions = list(store._sessions.values())
            s = next(s for s in sessions if s.id == session_id)
            s.strategy = _mock_strategy()
            s.plan = _mock_plan()
            s.current_step = 4
            await store.save(s)

            resp = await client.get("/step/4")

        assert resp.status_code == 200
        # Rationale section heading
        assert "Why this plan" in resp.text
        # The mock plan rationale text rendered inside a <p> tag
        assert "balances growth and stability" in resp.text
        assert "<p>" in resp.text

    @pytest.mark.asyncio
    async def test_full_wizard_flow(self):
        """End-to-end: tier → persona → strategy → plan → result → reset."""
        from apps.web.main import create_app
        app = create_app()

        with (
            patch("apps.web.api.generate_strategy", new=AsyncMock(return_value=(_mock_strategy(), RunUsage()))),
            patch("apps.web.api.generate_plan", new=AsyncMock(return_value=(_mock_plan(), RunUsage()))),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Step 1 — select tier
                tier_resp = await client.post("/api/select-tier", data={"mode": "basic"})
                assert tier_resp.headers["HX-Redirect"] == "/step/2"

                # Step 2 — select persona
                persona_resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
                assert persona_resp.headers["HX-Redirect"] == "/step/3"

                # Step 3 — generate strategy (HTMX GET)
                strategy_resp = await client.get("/api/generate-strategy")
                assert strategy_resp.status_code == 200
                assert "Equity" in strategy_resp.text

                # Step 3 — generate plan (plain 303 redirect; no HTMX)
                plan_resp = await client.post("/api/generate-plan", follow_redirects=False)
                assert plan_resp.status_code == 303
                assert plan_resp.headers["location"] == "/step/4"

                # Step 4 — render results page
                result_resp = await client.get("/step/4")
                assert result_resp.status_code == 200
                assert "UTI Nifty 50 Index Fund" in result_resp.text
                assert "Parag Parikh Flexi Cap Fund" in result_resp.text

                # Reset — back to step 1
                reset_resp = await client.post("/api/reset")
                assert reset_resp.status_code == 200
                assert reset_resp.headers["HX-Redirect"] == "/step/1"
                new_session_id = reset_resp.cookies.get("benji_session")
                assert new_session_id is not None
