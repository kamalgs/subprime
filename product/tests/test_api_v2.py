"""End-to-end tests for the /api/v2 JSON API.

LLM calls are mocked; everything else (session, routing, persistence,
background tasks, cheat code) runs real.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai.usage import RunUsage

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    MutualFund,
    StrategyOutline,
)

CHEAT = "123456"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70, debt_pct=20, gold_pct=10, other_pct=0,
        equity_approach="Balanced mix",
        key_themes=["growth tilt", "low cost"],
        risk_return_summary="Expected 11% CAGR with moderate drawdowns",
        open_questions=[],
    )


def _mock_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="119551", name="UTI Nifty 50 Index Fund", category="Large Cap"),
                allocation_pct=40, mode="sip", monthly_sip_inr=20000,
                rationale="Core equity exposure",
            ),
        ],
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 16.0},
        rationale="Long-term wealth building plan",
        risks=["Market volatility"],
    )


@pytest.fixture(autouse=True)
def cheat_code_env(monkeypatch):
    monkeypatch.setenv("SUBPRIME_OTP_CHEAT", CHEAT)


@pytest.fixture
async def client():
    from apps.web.main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_creates_new_session(client):
    r = await client.get("/api/v2/session")
    assert r.status_code == 200
    data = r.json()
    assert data["current_step"] == 1
    assert data["mode"] == "basic"
    assert data["is_demo"] is False
    assert data["has_profile"] is False
    assert "benji_session" in client.cookies


@pytest.mark.asyncio
async def test_get_session_returns_existing(client):
    r1 = await client.get("/api/v2/session")
    sid = r1.json()["id"]
    r2 = await client.get("/api/v2/session")
    assert r2.json()["id"] == sid


@pytest.mark.asyncio
async def test_set_tier_basic(client):
    r = await client.post("/api/v2/session/tier", json={"mode": "basic"})
    assert r.status_code == 200
    assert r.json()["mode"] == "basic"
    assert r.json()["current_step"] == 2


@pytest.mark.asyncio
async def test_set_tier_premium(client):
    r = await client.post("/api/v2/session/tier", json={"mode": "premium"})
    assert r.json()["mode"] == "premium"


@pytest.mark.asyncio
async def test_reset_generates_new_session(client):
    r1 = await client.get("/api/v2/session")
    sid1 = r1.json()["id"]
    r2 = await client.post("/api/v2/session/reset")
    assert r2.status_code == 200
    assert r2.json()["id"] != sid1


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


_VALID_PROFILE = {
    "name": "Test User", "age": 30, "monthly_sip_inr": 25000,
    "existing_corpus_inr": 500000, "risk_appetite": "moderate",
    "investment_horizon_years": 15, "life_stage": "mid career",
    "financial_goals": ["Retirement"],
}


@pytest.mark.asyncio
async def test_submit_profile_advances_step(client):
    await client.post("/api/v2/session/tier", json={"mode": "basic"})
    r = await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["has_profile"] is True
    assert body["current_step"] == 3


@pytest.mark.asyncio
async def test_submit_profile_validates_age(client):
    invalid = {**_VALID_PROFILE, "age": 15}
    r = await client.post("/api/v2/session/profile", json=invalid)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_profile_validates_risk_appetite(client):
    invalid = {**_VALID_PROFILE, "risk_appetite": "yolo"}
    r = await client.post("/api/v2/session/profile", json=invalid)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personas_shows_archetypes_only_for_regular_user(client):
    r = await client.get("/api/v2/personas")
    assert r.status_code == 200
    data = r.json()
    assert len(data["archetypes"]) == 3
    ids = {a["id"] for a in data["archetypes"]}
    assert ids == {"early_career", "mid_career", "retired"}
    assert data["personas"] is None


@pytest.mark.asyncio
async def test_personas_unlocks_full_bank_with_cheat(client):
    r = await client.post(
        "/api/v2/session/otp/verify",
        json={"email": "foo@bar.com", "code": CHEAT},
    )
    assert r.json()["verified"] is True
    assert r.json()["is_demo"] is True

    r2 = await client.get("/api/v2/personas")
    data = r2.json()
    assert data["personas"] is not None
    assert len(data["personas"]) > 0
    assert any(p["name"] == "Tony Stark" for p in data["personas"])


@pytest.mark.asyncio
async def test_persona_select_requires_demo(client):
    # Regular (non-demo) session can't pick research personas
    r = await client.post("/api/v2/session/persona", json={"persona_id": "P01"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_persona_select_works_after_cheat(client):
    await client.post(
        "/api/v2/session/otp/verify",
        json={"email": "foo@bar.com", "code": CHEAT},
    )
    r = await client.post("/api/v2/session/persona", json={"persona_id": "P01"})
    assert r.status_code == 200
    assert r.json()["has_profile"] is True


@pytest.mark.asyncio
async def test_persona_select_404_for_unknown(client):
    await client.post(
        "/api/v2/session/otp/verify",
        json={"email": "foo@bar.com", "code": CHEAT},
    )
    r = await client.post("/api/v2/session/persona", json={"persona_id": "NONEXISTENT"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_verify_rejects_wrong_code(client):
    r = await client.post(
        "/api/v2/session/otp/verify",
        json={"email": "x@y.com", "code": "999999"},
    )
    assert r.json()["verified"] is False
    assert r.json()["is_demo"] is False


@pytest.mark.asyncio
async def test_otp_verify_accepts_cheat(client):
    r = await client.post(
        "/api/v2/session/otp/verify",
        json={"email": "x@y.com", "code": CHEAT},
    )
    assert r.json()["verified"] is True


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_requires_profile(client):
    await client.post("/api/v2/session/tier", json={"mode": "basic"})
    r = await client.post("/api/v2/strategy/generate")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_strategy_generate(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    mock = AsyncMock(return_value=(_mock_strategy(), RunUsage()))
    with patch("apps.web.api_v2.strategy.generate_strategy", new=mock):
        r = await client.post("/api/v2/strategy/generate")
    assert r.status_code == 200
    data = r.json()
    assert data["strategy"]["equity_pct"] == 70
    assert data["strategy"]["equity_approach"] == "Balanced mix"


@pytest.mark.asyncio
async def test_strategy_revise_appends_to_chat(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    mock = AsyncMock(return_value=(_mock_strategy(), RunUsage()))
    with patch("apps.web.api_v2.strategy.generate_strategy", new=mock):
        await client.post("/api/v2/strategy/generate")
        r = await client.post(
            "/api/v2/strategy/revise",
            json={"feedback": "more aggressive please"},
        )
    assert r.status_code == 200
    chat = r.json()["chat"]
    assert len(chat) == 2  # user + advisor
    assert chat[0]["role"] == "user"
    assert chat[0]["content"] == "more aggressive please"


@pytest.mark.asyncio
async def test_strategy_answer_questions_does_not_pollute_chat(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    mock = AsyncMock(return_value=(_mock_strategy(), RunUsage()))
    with patch("apps.web.api_v2.strategy.generate_strategy", new=mock):
        await client.post("/api/v2/strategy/generate")
        r = await client.post(
            "/api/v2/strategy/answer-questions",
            json={"feedback": "horizon is actually 20 years"},
        )
    assert r.json()["chat"] == []


# ---------------------------------------------------------------------------
# Plan — background task + poll
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_generate_returns_202_and_sets_flag(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    mock_plan = AsyncMock(return_value=(_mock_plan(), RunUsage()))
    with patch("apps.web.api_v2.plan.generate_plan", new=mock_plan):
        r = await client.post("/api/v2/plan/generate")
        assert r.status_code == 202
        # Give the background task a chance to complete
        for _ in range(30):
            await asyncio.sleep(0.05)
            status = await client.get("/api/v2/plan/status")
            if status.json()["ready"]:
                break
        assert status.json()["ready"] is True
        assert status.json()["generating"] is False


@pytest.mark.asyncio
async def test_plan_status_without_request(client):
    r = await client.get("/api/v2/plan/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is False
    assert data["generating"] is False


@pytest.mark.asyncio
async def test_plan_get_404_before_ready(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    r = await client.get("/api/v2/plan")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_plan_get_returns_full_plan_after_ready(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    mock_plan = AsyncMock(return_value=(_mock_plan(), RunUsage()))
    with patch("apps.web.api_v2.plan.generate_plan", new=mock_plan):
        await client.post("/api/v2/plan/generate")
        for _ in range(30):
            await asyncio.sleep(0.05)
            status = await client.get("/api/v2/plan/status")
            if status.json()["ready"]:
                break
        r = await client.get("/api/v2/plan")
    assert r.status_code == 200
    data = r.json()
    assert len(data["plan"]["allocations"]) == 1
    assert data["plan"]["allocations"][0]["fund"]["name"] == "UTI Nifty 50 Index Fund"
    assert data["profile"]["name"] == "Test User"


@pytest.mark.asyncio
async def test_plan_generate_requires_profile(client):
    r = await client.post("/api/v2/plan/generate")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_plan_error_surfaces_in_status(client):
    await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    broken = AsyncMock(side_effect=RuntimeError("model hiccup"))
    with patch("apps.web.api_v2.plan.generate_plan", new=broken):
        await client.post("/api/v2/plan/generate")
        for _ in range(30):
            await asyncio.sleep(0.05)
            status = await client.get("/api/v2/plan/status")
            if not status.json()["generating"]:
                break
        assert status.json()["ready"] is False
        assert status.json()["generating"] is False
        assert "model hiccup" in status.json()["error"]


# ---------------------------------------------------------------------------
# Full flow — tier → profile → strategy → plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_wizard_flow_end_to_end(client):
    # 1. Tier
    r = await client.post("/api/v2/session/tier", json={"mode": "basic"})
    assert r.json()["current_step"] == 2

    # 2. Custom profile
    r = await client.post("/api/v2/session/profile", json=_VALID_PROFILE)
    assert r.json()["has_profile"] is True
    assert r.json()["current_step"] == 3

    # 3. Strategy
    with patch(
        "apps.web.api_v2.strategy.generate_strategy",
        new=AsyncMock(return_value=(_mock_strategy(), RunUsage())),
    ):
        r = await client.post("/api/v2/strategy/generate")
    assert r.status_code == 200

    session = (await client.get("/api/v2/session")).json()
    assert session["has_strategy"] is True

    # 4. Plan
    with patch(
        "apps.web.api_v2.plan.generate_plan",
        new=AsyncMock(return_value=(_mock_plan(), RunUsage())),
    ):
        r = await client.post("/api/v2/plan/generate")
        assert r.status_code == 202
        for _ in range(30):
            await asyncio.sleep(0.05)
            status = await client.get("/api/v2/plan/status")
            if status.json()["ready"]:
                break

    plan_resp = await client.get("/api/v2/plan")
    assert plan_resp.status_code == 200
    assert len(plan_resp.json()["plan"]["allocations"]) > 0
