"""Tests for advisor planner — verifies wiring, not LLM quality.

Only the LLM is mocked. Everything else (prompt loading, agent creation,
tool registration) runs for real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from subprime.advisor.agent import create_advisor, load_prompt
from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def test_load_prompt_base():
    prompt = load_prompt("base")
    assert "finadvisor" in prompt.lower() or "mutual fund advisor" in prompt.lower()
    assert "Indian" in prompt or "indian" in prompt


def test_load_prompt_planning():
    prompt = load_prompt("planning")
    assert "Allocations" in prompt
    assert "Projected returns" in prompt


def test_load_prompt_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_that_does_not_exist")


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


def test_create_advisor_default():
    agent = create_advisor()
    assert agent is not None
    # Agent should have tools registered
    assert len(agent._function_toolset.tools) > 0


def test_create_advisor_has_two_tools():
    agent = create_advisor()
    tool_names = set(agent._function_toolset.tools.keys())
    assert len(tool_names) == 2
    assert "search_funds_universe" in tool_names
    assert "get_fund_details" in tool_names


def test_create_advisor_with_hook():
    agent = create_advisor(prompt_hooks={"philosophy": "Always prefer index funds."})
    assert agent is not None


def test_create_advisor_system_prompt_includes_hook():
    hook_text = "TEST_HOOK_MARKER: prefer index funds"
    agent = create_advisor(prompt_hooks={"philosophy": hook_text})
    # PydanticAI stores system prompts as a tuple of strings
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "TEST_HOOK_MARKER" in combined


def test_create_advisor_baseline_no_philosophy():
    """Baseline (no hook) system prompt must NOT contain a philosophy section."""
    agent = create_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "Investment Philosophy" not in combined


# ---------------------------------------------------------------------------
# Profile formatting (sanity check)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_profile():
    return InvestorProfile(
        id="P01",
        name="Arjun Mehta",
        age=25,
        risk_appetite="aggressive",
        investment_horizon_years=30,
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=200000,
        liabilities_inr=0,
        financial_goals=["Retire by 55 with 10Cr corpus"],
        life_stage="Early career",
        tax_bracket="new_regime",
    )


def test_format_profile_for_prompt(sample_profile):
    """Profile should be formattable as a string for the LLM."""
    text = sample_profile.model_dump_json(indent=2)
    assert "Arjun" in text
    assert "aggressive" in text


# ---------------------------------------------------------------------------
# generate_plan (LLM mocked)
# ---------------------------------------------------------------------------


def _make_fake_plan() -> InvestmentPlan:
    """Build a valid InvestmentPlan for mock returns."""
    fund = MutualFund(
        amfi_code="119551",
        name="Parag Parikh Flexi Cap Fund",
        category="Equity",
        sub_category="Flexi Cap",
        fund_house="PPFAS",
        nav=65.0,
        expense_ratio=0.63,
    )
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=fund,
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=50000,
                rationale="Diversified flexi cap with global exposure.",
            )
        ],
        setup_phase="Start SIP in month 1.",
        review_checkpoints=["6-month review", "Annual review"],
        rebalancing_guidelines="Rebalance annually if drift > 5%.",
        projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
        rationale="Aggressive growth strategy for long horizon.",
        risks=["Market volatility", "Currency risk on global allocation"],
        disclaimer="For research purposes only. Not certified financial advice.",
    )


@pytest.mark.asyncio
async def test_generate_plan(sample_profile):
    """generate_plan should call the agent and return an InvestmentPlan."""
    from subprime.advisor.planner import generate_plan

    fake_plan = _make_fake_plan()

    # Mock Agent.run to return a result with our fake plan
    mock_result = MagicMock()
    mock_result.output = fake_plan

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        plan = await generate_plan(sample_profile)

    assert isinstance(plan, InvestmentPlan)
    assert len(plan.allocations) == 1
    assert plan.allocations[0].fund.amfi_code == "119551"
    assert plan.projected_returns["base"] == 12.0


@pytest.mark.asyncio
async def test_generate_plan_passes_hooks(sample_profile):
    """generate_plan should forward prompt_hooks to create_advisor."""
    from subprime.advisor.planner import generate_plan

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    hooks = {"philosophy": "Always prefer index funds."}

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        await generate_plan(sample_profile, prompt_hooks=hooks)

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["prompt_hooks"] == hooks
    assert call_kwargs["model"] == "anthropic:claude-haiku-4-5"


@pytest.mark.asyncio
async def test_generate_plan_with_strategy(sample_profile):
    from subprime.advisor.planner import generate_plan
    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan
    strategy = StrategyOutline(
        equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
        equity_approach="Index-heavy", key_themes=["low cost"],
        risk_return_summary="12% CAGR target", open_questions=[],
    )
    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent
        plan = await generate_plan(sample_profile, strategy=strategy)
    call_args = mock_agent.run.call_args
    user_prompt = call_args[0][0]
    assert "approved this strategy" in user_prompt
    assert "Index-heavy" in user_prompt
    assert isinstance(plan, InvestmentPlan)


# ---------------------------------------------------------------------------
# Universe context injection
# ---------------------------------------------------------------------------


def test_create_advisor_with_universe_context():
    """universe_context should be injected into the system prompt."""
    agent = create_advisor(universe_context="UNIVERSE_MARKER: foo bar baz")
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "UNIVERSE_MARKER" in combined


def test_create_advisor_without_universe_context():
    """No universe → no marker in prompt."""
    agent = create_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "UNIVERSE_MARKER" not in combined


@pytest.mark.asyncio
async def test_generate_plan_include_universe_false_skips_db(sample_profile, monkeypatch):
    """include_universe=False should not try to read the DB."""
    from subprime.advisor.planner import generate_plan

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("_load_universe_context should not be called")

    monkeypatch.setattr("subprime.advisor.planner._load_universe_context", _should_not_be_called)

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        plan = await generate_plan(sample_profile, include_universe=False)

    assert isinstance(plan, InvestmentPlan)
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs.get("universe_context") is None


# ---------------------------------------------------------------------------
# Premium mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_premium_mode(sample_profile):
    """Premium mode should generate 3 variants and pick the best."""
    from subprime.advisor.planner import generate_plan

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    # Mock the ranking agent's output
    mock_ranking_result = MagicMock()
    mock_ranking_result.output = MagicMock(best_index=1, reasoning="Plan 2 is best")

    with (
        patch("subprime.advisor.planner.create_advisor") as mock_create,
        patch("subprime.advisor.planner._pick_best_plan", new_callable=AsyncMock) as mock_pick,
    ):
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        # _pick_best_plan returns one of the plans
        mock_pick.return_value = fake_plan

        plan = await generate_plan(sample_profile, mode="premium")

    assert isinstance(plan, InvestmentPlan)
    # Should have created the advisor 3 times (one per variant)
    assert mock_create.call_count == 3
    # Should have called _pick_best_plan once
    mock_pick.assert_awaited_once()
    # Check that _pick_best_plan received 3 plans
    call_args = mock_pick.call_args
    assert len(call_args[0][0]) == 3  # first positional arg is the plans list


@pytest.mark.asyncio
async def test_generate_plan_basic_mode_single_call(sample_profile):
    """Basic mode should generate exactly 1 plan."""
    from subprime.advisor.planner import generate_plan

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        plan = await generate_plan(sample_profile, mode="basic")

    assert isinstance(plan, InvestmentPlan)
    assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_pick_best_plan(sample_profile):
    """_pick_best_plan should return the plan at the chosen index."""
    from subprime.advisor.planner import PlanRanking, _pick_best_plan

    plans = [_make_fake_plan(), _make_fake_plan(), _make_fake_plan()]

    mock_ranking_result = MagicMock()
    mock_ranking_result.output = PlanRanking(best_index=2, reasoning="Plan 3 has better diversification")

    with patch("subprime.advisor.planner.Agent") as MockAgent:
        mock_scorer = AsyncMock()
        mock_scorer.run = AsyncMock(return_value=mock_ranking_result)
        MockAgent.return_value = mock_scorer

        best = await _pick_best_plan(plans, sample_profile, DEFAULT_MODEL)

    assert best is plans[2]


@pytest.mark.asyncio
async def test_pick_best_plan_clamps_index(sample_profile):
    """_pick_best_plan should clamp an out-of-range index."""
    from subprime.advisor.planner import PlanRanking, _pick_best_plan

    plans = [_make_fake_plan(), _make_fake_plan()]

    mock_ranking_result = MagicMock()
    mock_ranking_result.output = PlanRanking(best_index=99, reasoning="Invalid index")

    with patch("subprime.advisor.planner.Agent") as MockAgent:
        mock_scorer = AsyncMock()
        mock_scorer.run = AsyncMock(return_value=mock_ranking_result)
        MockAgent.return_value = mock_scorer

        best = await _pick_best_plan(plans, sample_profile, DEFAULT_MODEL)

    # Should clamp to last plan (index 1)
    assert best is plans[1]
