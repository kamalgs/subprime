"""Tests for judge agents — verifies wiring, not LLM quality.

Only the LLM is mocked. Everything else (prompt building, agent creation,
criteria integration) runs for real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent

from subprime.core.models import (
    APSScore,
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    PlanQualityScore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_plan() -> InvestmentPlan:
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
        disclaimer="For research purposes only.",
    )


def _make_profile() -> InvestorProfile:
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


def _make_aps_score() -> APSScore:
    return APSScore(
        passive_instrument_fraction=0.7,
        turnover_score=0.8,
        cost_emphasis_score=0.6,
        research_vs_cost_score=0.5,
        time_horizon_alignment_score=0.9,
        reasoning="Mostly passive plan.",
    )


def _make_pqs_score() -> PlanQualityScore:
    return PlanQualityScore(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Well-aligned plan with good diversification.",
    )


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestBuildApsPrompt:
    def test_contains_all_dimension_names(self):
        from subprime.evaluation.judges import _build_aps_prompt

        prompt = _build_aps_prompt()
        for dim in [
            "passive_instrument_fraction",
            "turnover_score",
            "cost_emphasis_score",
            "research_vs_cost_score",
            "time_horizon_alignment_score",
        ]:
            assert dim in prompt, f"APS prompt missing dimension: {dim}"

    def test_contains_anchor_text(self):
        from subprime.evaluation.criteria import APS_CRITERIA
        from subprime.evaluation.judges import _build_aps_prompt

        prompt = _build_aps_prompt()
        # Check that at least some anchor text appears
        for dim_name, dim in APS_CRITERIA.items():
            assert dim["anchor_0"] in prompt, (
                f"APS prompt missing anchor_0 for {dim_name}"
            )
            assert dim["anchor_1"] in prompt, (
                f"APS prompt missing anchor_1 for {dim_name}"
            )

    def test_is_nonempty_string(self):
        from subprime.evaluation.judges import _build_aps_prompt

        prompt = _build_aps_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # should be a substantial prompt


class TestBuildPqsPrompt:
    def test_contains_all_dimension_names(self):
        from subprime.evaluation.judges import _build_pqs_prompt

        prompt = _build_pqs_prompt()
        for dim in [
            "goal_alignment",
            "diversification",
            "risk_return_appropriateness",
            "internal_consistency",
        ]:
            assert dim in prompt, f"PQS prompt missing dimension: {dim}"

    def test_contains_anchor_text(self):
        from subprime.evaluation.criteria import PQS_CRITERIA
        from subprime.evaluation.judges import _build_pqs_prompt

        prompt = _build_pqs_prompt()
        for dim_name, dim in PQS_CRITERIA.items():
            assert dim["anchor_0"] in prompt, (
                f"PQS prompt missing anchor_0 for {dim_name}"
            )
            assert dim["anchor_1"] in prompt, (
                f"PQS prompt missing anchor_1 for {dim_name}"
            )

    def test_is_nonempty_string(self):
        from subprime.evaluation.judges import _build_pqs_prompt

        prompt = _build_pqs_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


class TestCreateApsJudge:
    def test_returns_agent(self):
        from subprime.evaluation.judges import create_aps_judge

        agent = create_aps_judge()
        assert isinstance(agent, Agent)

    def test_default_model(self):
        from subprime.evaluation.judges import create_aps_judge

        agent = create_aps_judge()
        assert agent is not None

    def test_custom_model(self):
        from subprime.evaluation.judges import create_aps_judge

        agent = create_aps_judge(model="openai:gpt-4o-mini")
        assert isinstance(agent, Agent)


class TestCreatePqsJudge:
    def test_returns_agent(self):
        from subprime.evaluation.judges import create_pqs_judge

        agent = create_pqs_judge()
        assert isinstance(agent, Agent)

    def test_custom_model(self):
        from subprime.evaluation.judges import create_pqs_judge

        agent = create_pqs_judge(model="openai:gpt-4o-mini")
        assert isinstance(agent, Agent)


# ---------------------------------------------------------------------------
# score_aps (LLM mocked)
# ---------------------------------------------------------------------------


class TestScoreAps:
    @pytest.mark.asyncio
    async def test_returns_aps_score(self):
        from subprime.evaluation.judges import score_aps

        fake_aps = _make_aps_score()
        mock_result = MagicMock()
        mock_result.output = fake_aps

        with patch("subprime.evaluation.judges.create_aps_judge") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_agent

            result = await score_aps(_make_plan())

        assert isinstance(result, APSScore)
        assert result.passive_instrument_fraction == 0.7
        assert result.reasoning == "Mostly passive plan."

    @pytest.mark.asyncio
    async def test_passes_plan_json_to_agent(self):
        from subprime.evaluation.judges import score_aps

        plan = _make_plan()
        fake_aps = _make_aps_score()
        mock_result = MagicMock()
        mock_result.output = fake_aps

        with patch("subprime.evaluation.judges.create_aps_judge") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_agent

            await score_aps(plan)

        # Agent.run should have been called with the plan as a string
        call_args = mock_agent.run.call_args
        assert call_args is not None
        user_prompt = call_args[0][0]
        assert "Parag Parikh" in user_prompt


# ---------------------------------------------------------------------------
# score_pqs (LLM mocked)
# ---------------------------------------------------------------------------


class TestScorePqs:
    @pytest.mark.asyncio
    async def test_returns_pqs_score(self):
        from subprime.evaluation.judges import score_pqs

        fake_pqs = _make_pqs_score()
        mock_result = MagicMock()
        mock_result.output = fake_pqs

        with patch("subprime.evaluation.judges.create_pqs_judge") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_agent

            result = await score_pqs(_make_plan(), _make_profile())

        assert isinstance(result, PlanQualityScore)
        assert result.goal_alignment == 0.9
        assert result.reasoning == "Well-aligned plan with good diversification."

    @pytest.mark.asyncio
    async def test_passes_plan_and_profile_to_agent(self):
        from subprime.evaluation.judges import score_pqs

        plan = _make_plan()
        profile = _make_profile()
        fake_pqs = _make_pqs_score()
        mock_result = MagicMock()
        mock_result.output = fake_pqs

        with patch("subprime.evaluation.judges.create_pqs_judge") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_agent

            await score_pqs(plan, profile)

        call_args = mock_agent.run.call_args
        user_prompt = call_args[0][0]
        # Should contain both plan and profile data
        assert "Parag Parikh" in user_prompt
        assert "Arjun" in user_prompt
