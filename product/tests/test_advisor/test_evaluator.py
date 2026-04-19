"""Tests for the plan evaluator module."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from subprime.advisor.evaluator import PlanEvaluation, evaluate_plans
from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)


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


def _make_fake_plan(perspective: str = "balanced") -> InvestmentPlan:
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
                rationale="Diversified flexi cap.",
            )
        ],
        rationale="Test plan.",
        risks=["Market risk"],
        perspective=perspective,
    )


@pytest.mark.asyncio
async def test_evaluate_plans_returns_plan_evaluation(sample_profile):
    """evaluate_plans should return a PlanEvaluation with mocked LLM."""
    plans = [_make_fake_plan("balanced"), _make_fake_plan("growth")]

    mock_eval = PlanEvaluation(
        best_index=0,
        rankings=[0, 1],
        reasoning="Balanced is better for this investor.",
        strengths={"balanced": "good diversification", "growth": "high returns"},
        weaknesses={"balanced": "lower returns", "growth": "too risky"},
    )
    mock_result = MagicMock()
    mock_result.output = mock_eval

    with patch("subprime.advisor.evaluator.Agent") as MockAgent:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent

        evaluation, _ = await evaluate_plans(plans, sample_profile)

    assert isinstance(evaluation, PlanEvaluation)
    assert evaluation.best_index == 0
    assert evaluation.reasoning == "Balanced is better for this investor."


@pytest.mark.asyncio
async def test_evaluate_plans_clamps_index(sample_profile):
    """best_index should be clamped to valid range."""
    plans = [_make_fake_plan("balanced"), _make_fake_plan("growth")]

    mock_eval = PlanEvaluation(
        best_index=99,
        reasoning="Out of range index.",
    )
    mock_result = MagicMock()
    mock_result.output = mock_eval

    with patch("subprime.advisor.evaluator.Agent") as MockAgent:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent

        evaluation, _ = await evaluate_plans(plans, sample_profile)

    # Should clamp to last valid index
    assert evaluation.best_index == 1


@pytest.mark.asyncio
async def test_evaluate_plans_clamps_negative_index(sample_profile):
    """Negative best_index should be clamped to 0."""
    plans = [_make_fake_plan("balanced"), _make_fake_plan("growth")]

    mock_eval = PlanEvaluation(
        best_index=-5,
        reasoning="Negative index.",
    )
    mock_result = MagicMock()
    mock_result.output = mock_eval

    with patch("subprime.advisor.evaluator.Agent") as MockAgent:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent

        evaluation, _ = await evaluate_plans(plans, sample_profile)

    assert evaluation.best_index == 0
