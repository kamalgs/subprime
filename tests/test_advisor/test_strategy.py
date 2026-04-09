"""Tests for strategy advisor factory — verifies wiring, not LLM quality.

Only the LLM is mocked. Everything else (prompt loading, agent creation)
runs for real.
"""

from __future__ import annotations

from subprime.advisor.agent import create_strategy_advisor, load_prompt


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def test_load_prompt_strategy():
    prompt = load_prompt("strategy")
    assert "asset allocation" in prompt.lower()
    assert "equity" in prompt.lower()


def test_load_prompt_profile():
    prompt = load_prompt("profile")
    assert "risk appetite" in prompt.lower()
    assert "INR" in prompt


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


def test_create_strategy_advisor_default():
    agent = create_strategy_advisor()
    assert agent is not None


def test_create_strategy_advisor_has_no_tools():
    agent = create_strategy_advisor()
    assert len(agent._function_toolset.tools) == 0


def test_create_strategy_advisor_with_hook():
    agent = create_strategy_advisor(
        prompt_hooks={"philosophy": "Always prefer index funds."}
    )
    assert agent is not None


def test_create_strategy_advisor_hook_in_system_prompt():
    hook_text = "TEST_STRATEGY_HOOK_MARKER: prefer active stock picking"
    agent = create_strategy_advisor(prompt_hooks={"philosophy": hook_text})
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "TEST_STRATEGY_HOOK_MARKER" in combined


def test_create_strategy_advisor_baseline_no_philosophy():
    """Baseline (no hook) system prompt must NOT contain a philosophy section."""
    agent = create_strategy_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "Investment Philosophy" not in combined


# ---------------------------------------------------------------------------
# generate_strategy (LLM mocked)
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from subprime.core.models import InvestorProfile, StrategyOutline

@pytest.fixture
def sample_profile():
    return InvestorProfile(
        id="P01", name="Arjun Mehta", age=25, risk_appetite="aggressive",
        investment_horizon_years=30, monthly_investible_surplus_inr=50000,
        existing_corpus_inr=200000, liabilities_inr=0,
        financial_goals=["Retire by 55 with 10Cr corpus"],
        life_stage="Early career", tax_bracket="new_regime",
    )

def _make_fake_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
        equity_approach="Index-heavy with small active tilt",
        key_themes=["low cost", "broad diversification", "tax efficiency"],
        risk_return_summary="Targeting 12-14% CAGR with moderate volatility",
        open_questions=[],
    )

@pytest.mark.asyncio
async def test_generate_strategy(sample_profile):
    from subprime.advisor.planner import generate_strategy
    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy
    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent
        strategy = await generate_strategy(sample_profile)
    assert isinstance(strategy, StrategyOutline)
    assert strategy.equity_pct == 70.0

@pytest.mark.asyncio
async def test_generate_strategy_with_feedback(sample_profile):
    from subprime.advisor.planner import generate_strategy
    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy
    current = _make_fake_strategy()
    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent
        strategy = await generate_strategy(sample_profile, feedback="More equity, less debt", current_strategy=current)
    call_args = mock_agent.run.call_args
    user_prompt = call_args[0][0]
    assert "More equity, less debt" in user_prompt

@pytest.mark.asyncio
async def test_generate_strategy_passes_hooks(sample_profile):
    from subprime.advisor.planner import generate_strategy
    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy
    hooks = {"philosophy": "Prefer index funds."}
    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent
        await generate_strategy(sample_profile, prompt_hooks=hooks)
    mock_create.assert_called_once_with(prompt_hooks=hooks, model="anthropic:claude-haiku-4-5")
