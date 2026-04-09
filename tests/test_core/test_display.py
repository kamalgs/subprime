"""Tests for subprime.core.display — Rich display helpers.

Deterministic, fast, no network/LLM calls. No mocking needed.
"""

from __future__ import annotations

import pytest

from subprime.core.models import (
    APSScore,
    Allocation,
    InvestmentPlan,
    MutualFund,
    PlanQualityScore,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid model instances
# ---------------------------------------------------------------------------


def _make_fund(name: str = "Nifty 50 Index Fund", amfi_code: str = "119551") -> MutualFund:
    return MutualFund(
        amfi_code=amfi_code,
        name=name,
        category="Equity",
        sub_category="Large Cap",
        fund_house="UTI",
        nav=150.25,
        expense_ratio=0.10,
    )


def _make_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=_make_fund("Nifty 50 Index Fund", "119551"),
                allocation_pct=60.0,
                mode="sip",
                monthly_sip_inr=30_000,
                rationale="Low cost broad market exposure",
            ),
            Allocation(
                fund=_make_fund("PPFAS Flexi Cap Fund", "122639"),
                allocation_pct=40.0,
                mode="lumpsum",
                lumpsum_inr=200_000,
                rationale="Diversified active fund",
            ),
        ],
        setup_phase="Deploy lumpsum in month 1, start SIPs from month 2",
        review_checkpoints=["After 6 months", "Annual review"],
        rebalancing_guidelines="Rebalance if drift > 5%",
        projected_returns={"bear": 6.0, "base": 10.0, "bull": 14.0},
        rationale="Balanced approach for moderate risk appetite with mix of passive and active.",
        risks=["Market drawdown", "Inflation risk"],
        disclaimer="Research only.",
    )


def _make_aps() -> APSScore:
    return APSScore(
        passive_instrument_fraction=0.8,
        turnover_score=0.9,
        cost_emphasis_score=0.85,
        research_vs_cost_score=0.7,
        time_horizon_alignment_score=0.75,
        reasoning="Heavily passive plan with low turnover.",
    )


def _make_pqs() -> PlanQualityScore:
    return PlanQualityScore(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Well-aligned plan with good diversification.",
    )


# ===========================================================================
# format_plan_summary
# ===========================================================================


class TestFormatPlanSummary:
    def test_returns_string(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        assert isinstance(result, str)

    def test_contains_fund_names(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        assert "Nifty 50 Index Fund" in result
        assert "PPFAS Flexi Cap Fund" in result

    def test_contains_allocation_percentages(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        assert "60" in result
        assert "40" in result

    def test_contains_projected_return_labels(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        # Should show Bear/Base/Bull scenarios
        assert "Bear" in result or "bear" in result.lower()
        assert "Base" in result or "base" in result.lower()
        assert "Bull" in result or "bull" in result.lower()

    def test_contains_amfi_codes(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        assert "119551" in result
        assert "122639" in result

    def test_contains_rationale(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        assert "Balanced approach" in result or "moderate risk" in result.lower()

    def test_contains_mode(self):
        from subprime.core.display import format_plan_summary

        result = format_plan_summary(_make_plan())
        # Should mention SIP and lumpsum modes
        lower = result.lower()
        assert "sip" in lower
        assert "lumpsum" in lower


# ===========================================================================
# format_scores
# ===========================================================================


class TestFormatScores:
    def test_returns_string(self):
        from subprime.core.display import format_scores

        result = format_scores(_make_aps(), _make_pqs())
        assert isinstance(result, str)

    def test_contains_aps_label(self):
        from subprime.core.display import format_scores

        result = format_scores(_make_aps(), _make_pqs())
        assert "APS" in result

    def test_contains_pqs_label(self):
        from subprime.core.display import format_scores

        result = format_scores(_make_aps(), _make_pqs())
        assert "PQS" in result

    def test_contains_aps_dimension_values(self):
        from subprime.core.display import format_scores

        aps = _make_aps()
        result = format_scores(aps, _make_pqs())
        # Should contain the dimension values
        assert "0.80" in result or "0.8" in result  # passive_instrument_fraction
        assert "0.90" in result or "0.9" in result  # turnover_score

    def test_contains_pqs_dimension_values(self):
        from subprime.core.display import format_scores

        pqs = _make_pqs()
        result = format_scores(_make_aps(), pqs)
        # Should contain PQS dimension values
        assert "0.90" in result or "0.9" in result  # goal_alignment
        assert "0.80" in result or "0.8" in result  # diversification

    def test_contains_composite_scores(self):
        from subprime.core.display import format_scores

        aps = _make_aps()
        pqs = _make_pqs()
        result = format_scores(aps, pqs)
        # composite_aps = (0.8 + 0.9 + 0.85 + 0.7 + 0.75) / 5 = 0.8
        # composite_pqs = (0.9 + 0.8 + 0.85 + 0.9) / 4 = 0.8625
        assert "0.80" in result or "0.800" in result  # composite_aps
        assert "0.86" in result or "0.863" in result  # composite_pqs


# ===========================================================================
# print_plan / print_scores (smoke tests — just verify no exceptions)
# ===========================================================================


class TestPrintPlan:
    def test_no_exception(self, capsys):
        from subprime.core.display import print_plan

        print_plan(_make_plan())
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestPrintScores:
    def test_no_exception(self, capsys):
        from subprime.core.display import print_scores

        print_scores(_make_aps(), _make_pqs())
        captured = capsys.readouterr()
        assert len(captured.out) > 0


# ===========================================================================
# format_strategy_outline
# ===========================================================================


def _make_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70.0,
        debt_pct=20.0,
        gold_pct=10.0,
        other_pct=0.0,
        equity_approach="Index-heavy with small active tilt",
        key_themes=["low cost", "broad diversification", "tax efficiency under 80C"],
        risk_return_summary="Targeting 12-14% CAGR with moderate volatility",
        open_questions=["Any sector preferences?"],
    )


class TestFormatStrategyOutline:
    def test_returns_string(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert isinstance(result, str)

    def test_contains_allocation_percentages(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "70" in result
        assert "20" in result
        assert "10" in result

    def test_contains_equity_approach(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "Index-heavy with small active tilt" in result

    def test_contains_themes(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "low cost" in result
        assert "broad diversification" in result
        assert "tax efficiency under 80C" in result

    def test_contains_risk_return_summary(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "Targeting 12-14% CAGR with moderate volatility" in result

    def test_contains_open_questions(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "Any sector preferences?" in result

    def test_handles_empty_open_questions(self):
        from subprime.core.display import format_strategy_outline

        strategy = _make_strategy()
        strategy = strategy.model_copy(update={"open_questions": []})
        result = format_strategy_outline(strategy)
        assert isinstance(result, str)
