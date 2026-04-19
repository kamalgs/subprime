"""Tests for the scorer module — bundles APS + PQS into ScoredPlan."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

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
                rationale="Diversified flexi cap.",
            )
        ],
        setup_phase="Start SIP in month 1.",
        review_checkpoints=["6-month review"],
        rebalancing_guidelines="Rebalance annually.",
        projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
        rationale="Growth strategy.",
        risks=["Market volatility"],
        disclaimer="Research only.",
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


def _make_aps() -> APSScore:
    return APSScore(
        passive_instrument_fraction=0.7,
        turnover_score=0.8,
        cost_emphasis_score=0.6,
        research_vs_cost_score=0.5,
        time_horizon_alignment_score=0.9,
        portfolio_activeness_score=0.7,
        reasoning="Mostly passive.",
    )


def _make_pqs() -> PlanQualityScore:
    return PlanQualityScore(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Good quality.",
    )


# ---------------------------------------------------------------------------
# ScoredPlan model
# ---------------------------------------------------------------------------


class TestScoredPlan:
    def test_construction(self):
        from subprime.evaluation.scorer import ScoredPlan

        sp = ScoredPlan(plan=_make_plan(), aps=_make_aps(), pqs=_make_pqs())
        assert sp.plan is not None
        assert sp.aps is not None
        assert sp.pqs is not None

    def test_plan_is_investment_plan(self):
        from subprime.evaluation.scorer import ScoredPlan

        sp = ScoredPlan(plan=_make_plan(), aps=_make_aps(), pqs=_make_pqs())
        assert isinstance(sp.plan, InvestmentPlan)

    def test_aps_is_aps_score(self):
        from subprime.evaluation.scorer import ScoredPlan

        sp = ScoredPlan(plan=_make_plan(), aps=_make_aps(), pqs=_make_pqs())
        assert isinstance(sp.aps, APSScore)

    def test_pqs_is_pqs_score(self):
        from subprime.evaluation.scorer import ScoredPlan

        sp = ScoredPlan(plan=_make_plan(), aps=_make_aps(), pqs=_make_pqs())
        assert isinstance(sp.pqs, PlanQualityScore)

    def test_serialization_roundtrip(self):
        from subprime.evaluation.scorer import ScoredPlan

        original = ScoredPlan(plan=_make_plan(), aps=_make_aps(), pqs=_make_pqs())
        dumped = original.model_dump_json()
        restored = ScoredPlan.model_validate_json(dumped)
        assert restored.aps.composite_aps == pytest.approx(original.aps.composite_aps)
        assert restored.pqs.composite_pqs == pytest.approx(original.pqs.composite_pqs)


# ---------------------------------------------------------------------------
# score_plan (LLM mocked)
# ---------------------------------------------------------------------------


class TestScorePlan:
    @pytest.mark.asyncio
    async def test_returns_scored_plan(self):
        from pydantic_ai.usage import RunUsage

        from subprime.evaluation.scorer import ScoredPlan, score_plan

        fake_aps = _make_aps()
        fake_pqs = _make_pqs()

        with (
            patch("subprime.evaluation.scorer.score_aps", new_callable=AsyncMock) as mock_aps,
            patch("subprime.evaluation.scorer.score_pqs", new_callable=AsyncMock) as mock_pqs,
        ):
            mock_aps.return_value = (fake_aps, RunUsage())
            mock_pqs.return_value = (fake_pqs, RunUsage())

            result, usage = await score_plan(_make_plan(), _make_profile())

        assert isinstance(result, ScoredPlan)
        assert result.aps == fake_aps
        assert result.pqs == fake_pqs

    @pytest.mark.asyncio
    async def test_passes_model_to_judges(self):
        from pydantic_ai.usage import RunUsage

        from subprime.evaluation.scorer import score_plan

        fake_aps = _make_aps()
        fake_pqs = _make_pqs()

        with (
            patch("subprime.evaluation.scorer.score_aps", new_callable=AsyncMock) as mock_aps,
            patch("subprime.evaluation.scorer.score_pqs", new_callable=AsyncMock) as mock_pqs,
        ):
            mock_aps.return_value = (fake_aps, RunUsage())
            mock_pqs.return_value = (fake_pqs, RunUsage())

            await score_plan(_make_plan(), _make_profile(), model="openai:gpt-4o-mini")

        # Both judges should receive the model parameter
        mock_aps.assert_called_once()
        mock_pqs.assert_called_once()
        assert mock_aps.call_args.kwargs.get("model") == "openai:gpt-4o-mini"
        assert mock_pqs.call_args.kwargs.get("model") == "openai:gpt-4o-mini"
