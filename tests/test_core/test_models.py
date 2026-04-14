"""Tests for subprime.core.models — all Pydantic data models.

Google-style small tests: fast, deterministic, no network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers — minimal valid builders
# ---------------------------------------------------------------------------


def _investor(**overrides) -> dict:
    """Return a minimal valid InvestorProfile dict."""
    base = dict(
        id="inv-001",
        name="Priya Sharma",
        age=30,
        risk_appetite="moderate",
        investment_horizon_years=10,
        monthly_investible_surplus_inr=50_000,
        existing_corpus_inr=500_000,
        liabilities_inr=0,
        financial_goals=["Retirement", "Child education"],
        life_stage="Early career",
        tax_bracket="30%",
    )
    base.update(overrides)
    return base


def _fund(**overrides) -> dict:
    """Return a minimal valid MutualFund dict."""
    base = dict(
        amfi_code="119551",
        name="Nifty 50 Index Fund",
        category="Equity",
        sub_category="Large Cap",
        fund_house="UTI",
        nav=150.25,
        expense_ratio=0.10,
    )
    base.update(overrides)
    return base


def _allocation(fund_dict: dict | None = None, **overrides) -> dict:
    base = dict(
        fund=fund_dict or _fund(),
        allocation_pct=40.0,
        mode="sip",
        monthly_sip_inr=20_000,
        rationale="Low cost broad market exposure",
    )
    base.update(overrides)
    return base


def _strategy(**overrides) -> dict:
    base = dict(
        equity_pct=60.0,
        debt_pct=30.0,
        gold_pct=5.0,
        other_pct=5.0,
        equity_approach="Passive index tracking",
        key_themes=["Broad market", "Low cost"],
        risk_return_summary="Moderate risk, 10-12% expected CAGR",
        open_questions=["Should we add international exposure?"],
    )
    base.update(overrides)
    return base


def _plan(**overrides) -> dict:
    base = dict(
        allocations=[_allocation()],
        setup_phase="Deploy lumpsum in first month, start SIPs from month 2",
        review_checkpoints=["After 6 months", "Annual review"],
        rebalancing_guidelines="Rebalance if drift > 5% from target allocation",
        projected_returns={"base": 10.0, "bull": 14.0, "bear": 6.0},
        rationale="Balanced approach for moderate risk appetite",
        risks=["Market drawdown", "Inflation risk"],
        disclaimer="For research purposes only. Not financial advice.",
    )
    base.update(overrides)
    return base


def _aps(**overrides) -> dict:
    base = dict(
        passive_instrument_fraction=0.8,
        turnover_score=0.9,
        cost_emphasis_score=0.85,
        research_vs_cost_score=0.7,
        time_horizon_alignment_score=0.75,
        portfolio_activeness_score=0.8,
        reasoning="Heavily passive plan with low turnover.",
    )
    base.update(overrides)
    return base


def _pqs(**overrides) -> dict:
    base = dict(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Well-aligned plan with good diversification.",
    )
    base.update(overrides)
    return base


def _experiment_result(**overrides) -> dict:
    base = dict(
        persona_id="inv-001",
        condition="baseline",
        model="claude-sonnet-4-6",
        plan=_plan(),
        aps=_aps(),
        pqs=_pqs(),
        prompt_version="v1",
    )
    base.update(overrides)
    return base


# ===========================================================================
# Package exports
# ===========================================================================


def test_core_exports():
    """Verify all 9 symbols are importable from subprime.core."""
    from subprime.core import (
        Allocation,
        APSScore,
        ExperimentResult,
        InvestmentPlan,
        InvestorProfile,
        MutualFund,
        PlanQualityScore,
        Settings,
        StrategyOutline,
    )

    symbols = [
        Allocation,
        APSScore,
        ExperimentResult,
        InvestmentPlan,
        InvestorProfile,
        MutualFund,
        PlanQualityScore,
        Settings,
        StrategyOutline,
    ]
    assert len(symbols) == 9
    for sym in symbols:
        assert sym is not None


# ===========================================================================
# InvestorProfile
# ===========================================================================


class TestInvestorProfile:
    def test_construction_happy_path(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor())
        assert p.id == "inv-001"
        assert p.name == "Priya Sharma"
        assert p.age == 30
        assert p.risk_appetite == "moderate"
        assert p.investment_horizon_years == 10
        assert p.monthly_investible_surplus_inr == 50_000
        assert p.existing_corpus_inr == 500_000
        assert p.liabilities_inr == 0
        assert len(p.financial_goals) == 2
        assert p.life_stage == "Early career"
        assert p.tax_bracket == "30%"
        assert p.preferences is None

    def test_with_preferences(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(preferences="No alcohol/tobacco stocks"))
        assert p.preferences == "No alcohol/tobacco stocks"

    def test_age_minimum(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(age=18))
        assert p.age == 18

    def test_age_maximum(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(age=80))
        assert p.age == 80

    def test_age_below_minimum_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(age=17))

    def test_age_above_maximum_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(age=81))

    @pytest.mark.parametrize("risk", ["conservative", "moderate", "aggressive"])
    def test_valid_risk_appetites(self, risk):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(risk_appetite=risk))
        assert p.risk_appetite == risk

    def test_invalid_risk_appetite_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(risk_appetite="yolo"))

    def test_horizon_minimum(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(investment_horizon_years=1))
        assert p.investment_horizon_years == 1

    def test_horizon_maximum(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(investment_horizon_years=40))
        assert p.investment_horizon_years == 40

    def test_horizon_below_minimum_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(investment_horizon_years=0))

    def test_horizon_above_maximum_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(investment_horizon_years=41))

    def test_negative_surplus_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(monthly_investible_surplus_inr=-1))

    def test_zero_surplus_allowed(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(monthly_investible_surplus_inr=0))
        assert p.monthly_investible_surplus_inr == 0

    def test_negative_corpus_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(existing_corpus_inr=-1))

    def test_negative_liabilities_rejected(self):
        from subprime.core.models import InvestorProfile

        with pytest.raises(ValidationError):
            InvestorProfile(**_investor(liabilities_inr=-1))

    def test_empty_goals_allowed(self):
        from subprime.core.models import InvestorProfile

        p = InvestorProfile(**_investor(financial_goals=[]))
        assert p.financial_goals == []

    def test_serialization_roundtrip(self):
        from subprime.core.models import InvestorProfile

        original = InvestorProfile(**_investor())
        dumped = original.model_dump_json()
        restored = InvestorProfile.model_validate_json(dumped)
        assert restored == original


# ===========================================================================
# MutualFund
# ===========================================================================


class TestMutualFund:
    def test_construction_minimal(self):
        from subprime.core.models import MutualFund

        f = MutualFund(**_fund())
        assert f.amfi_code == "119551"
        assert f.name == "Nifty 50 Index Fund"
        assert f.expense_ratio == 0.10
        assert f.aum_cr is None
        assert f.morningstar_rating is None
        assert f.returns_1y is None
        assert f.returns_3y is None
        assert f.returns_5y is None
        assert f.risk_grade is None

    def test_construction_full(self):
        from subprime.core.models import MutualFund

        f = MutualFund(
            **_fund(
                aum_cr=15000.5,
                morningstar_rating=4,
                returns_1y=12.5,
                returns_3y=14.2,
                returns_5y=11.8,
                risk_grade="moderate",
            )
        )
        assert f.aum_cr == 15000.5
        assert f.morningstar_rating == 4
        assert f.returns_1y == 12.5
        assert f.risk_grade == "moderate"

    @pytest.mark.parametrize("grade", ["low", "moderate", "high", "very_high"])
    def test_valid_risk_grades(self, grade):
        from subprime.core.models import MutualFund

        f = MutualFund(**_fund(risk_grade=grade))
        assert f.risk_grade == grade

    def test_invalid_risk_grade_rejected(self):
        from subprime.core.models import MutualFund

        with pytest.raises(ValidationError):
            MutualFund(**_fund(risk_grade="extreme"))

    def test_negative_nav_rejected(self):
        from subprime.core.models import MutualFund

        with pytest.raises(ValidationError):
            MutualFund(**_fund(nav=-1))

    def test_negative_expense_ratio_rejected(self):
        from subprime.core.models import MutualFund

        with pytest.raises(ValidationError):
            MutualFund(**_fund(expense_ratio=-0.5))

    def test_morningstar_out_of_range_rejected(self):
        from subprime.core.models import MutualFund

        with pytest.raises(ValidationError):
            MutualFund(**_fund(morningstar_rating=0))
        with pytest.raises(ValidationError):
            MutualFund(**_fund(morningstar_rating=6))

    def test_serialization_roundtrip(self):
        from subprime.core.models import MutualFund

        original = MutualFund(**_fund(aum_cr=5000, returns_1y=10.5))
        dumped = original.model_dump_json()
        restored = MutualFund.model_validate_json(dumped)
        assert restored == original


# ===========================================================================
# Allocation
# ===========================================================================


class TestAllocation:
    def test_construction_sip(self):
        from subprime.core.models import Allocation

        a = Allocation(**_allocation())
        assert a.allocation_pct == 40.0
        assert a.mode == "sip"
        assert a.monthly_sip_inr == 20_000
        assert a.lumpsum_inr is None

    def test_construction_lumpsum(self):
        from subprime.core.models import Allocation

        a = Allocation(**_allocation(mode="lumpsum", lumpsum_inr=500_000, monthly_sip_inr=None))
        assert a.mode == "lumpsum"
        assert a.lumpsum_inr == 500_000

    def test_construction_both(self):
        from subprime.core.models import Allocation

        a = Allocation(
            **_allocation(mode="both", monthly_sip_inr=10_000, lumpsum_inr=100_000)
        )
        assert a.mode == "both"

    @pytest.mark.parametrize("mode", ["sip", "lumpsum", "both"])
    def test_valid_modes(self, mode):
        from subprime.core.models import Allocation

        a = Allocation(**_allocation(mode=mode))
        assert a.mode == mode

    def test_invalid_mode_rejected(self):
        from subprime.core.models import Allocation

        with pytest.raises(ValidationError):
            Allocation(**_allocation(mode="swp"))

    def test_allocation_pct_zero(self):
        from subprime.core.models import Allocation

        a = Allocation(**_allocation(allocation_pct=0))
        assert a.allocation_pct == 0

    def test_allocation_pct_hundred(self):
        from subprime.core.models import Allocation

        a = Allocation(**_allocation(allocation_pct=100))
        assert a.allocation_pct == 100

    def test_allocation_pct_below_zero_rejected(self):
        from subprime.core.models import Allocation

        with pytest.raises(ValidationError):
            Allocation(**_allocation(allocation_pct=-1))

    def test_allocation_pct_above_hundred_rejected(self):
        from subprime.core.models import Allocation

        with pytest.raises(ValidationError):
            Allocation(**_allocation(allocation_pct=101))

    def test_serialization_roundtrip(self):
        from subprime.core.models import Allocation

        original = Allocation(**_allocation())
        dumped = original.model_dump_json()
        restored = Allocation.model_validate_json(dumped)
        assert restored == original


# ===========================================================================
# StrategyOutline
# ===========================================================================


class TestStrategyOutline:
    def test_construction_happy_path(self):
        from subprime.core.models import StrategyOutline

        s = StrategyOutline(**_strategy())
        assert s.equity_pct == 60.0
        assert s.debt_pct == 30.0
        assert s.gold_pct == 5.0
        assert s.other_pct == 5.0
        assert len(s.key_themes) == 2

    def test_all_zero_allowed(self):
        from subprime.core.models import StrategyOutline

        s = StrategyOutline(
            **_strategy(equity_pct=0, debt_pct=0, gold_pct=0, other_pct=0)
        )
        assert s.equity_pct == 0

    def test_all_hundred(self):
        from subprime.core.models import StrategyOutline

        s = StrategyOutline(
            **_strategy(equity_pct=100, debt_pct=100, gold_pct=100, other_pct=100)
        )
        assert s.equity_pct == 100

    def test_negative_pct_rejected(self):
        from subprime.core.models import StrategyOutline

        with pytest.raises(ValidationError):
            StrategyOutline(**_strategy(equity_pct=-1))

    def test_over_hundred_pct_rejected(self):
        from subprime.core.models import StrategyOutline

        with pytest.raises(ValidationError):
            StrategyOutline(**_strategy(debt_pct=101))

    def test_serialization_roundtrip(self):
        from subprime.core.models import StrategyOutline

        original = StrategyOutline(**_strategy())
        dumped = original.model_dump_json()
        restored = StrategyOutline.model_validate_json(dumped)
        assert restored == original


# ===========================================================================
# InvestmentPlan
# ===========================================================================


class TestInvestmentPlan:
    def test_construction_happy_path(self):
        from subprime.core.models import InvestmentPlan

        p = InvestmentPlan(**_plan())
        assert len(p.allocations) == 1
        assert p.projected_returns["base"] == 10.0
        assert len(p.risks) == 2

    def test_multiple_allocations(self):
        from subprime.core.models import InvestmentPlan

        allocs = [
            _allocation(allocation_pct=60),
            _allocation(allocation_pct=40, mode="lumpsum", lumpsum_inr=200_000),
        ]
        p = InvestmentPlan(**_plan(allocations=allocs))
        assert len(p.allocations) == 2

    def test_serialization_roundtrip(self):
        from subprime.core.models import InvestmentPlan

        original = InvestmentPlan(**_plan())
        dumped = original.model_dump_json()
        restored = InvestmentPlan.model_validate_json(dumped)
        assert restored == original


# ===========================================================================
# APSScore — with computed composite_aps
# ===========================================================================


class TestAPSScore:
    def test_construction_and_composite(self):
        from subprime.core.models import APSScore

        s = APSScore(**_aps())
        expected = (0.8 + 0.9 + 0.85 + 0.7 + 0.75 + 0.8) / 6
        assert s.composite_aps == pytest.approx(expected)

    def test_all_zeros(self):
        from subprime.core.models import APSScore

        s = APSScore(
            passive_instrument_fraction=0,
            turnover_score=0,
            cost_emphasis_score=0,
            research_vs_cost_score=0,
            time_horizon_alignment_score=0,
            portfolio_activeness_score=0,
            reasoning="Fully active",
        )
        assert s.composite_aps == pytest.approx(0.0)

    def test_all_ones(self):
        from subprime.core.models import APSScore

        s = APSScore(
            passive_instrument_fraction=1,
            turnover_score=1,
            cost_emphasis_score=1,
            research_vs_cost_score=1,
            time_horizon_alignment_score=1,
            portfolio_activeness_score=1,
            reasoning="Fully passive",
        )
        assert s.composite_aps == pytest.approx(1.0)

    def test_known_composite_value(self):
        """Exact arithmetic check: (0.2 + 0.4 + 0.6 + 0.8 + 1.0 + 0.0) / 6 = 0.5"""
        from subprime.core.models import APSScore

        s = APSScore(
            passive_instrument_fraction=0.2,
            turnover_score=0.4,
            cost_emphasis_score=0.6,
            research_vs_cost_score=0.8,
            time_horizon_alignment_score=1.0,
            portfolio_activeness_score=0.0,
            reasoning="Mixed",
        )
        assert s.composite_aps == pytest.approx(0.5)

    def test_dimension_below_zero_rejected(self):
        from subprime.core.models import APSScore

        with pytest.raises(ValidationError):
            APSScore(**_aps(passive_instrument_fraction=-0.1))

    def test_dimension_above_one_rejected(self):
        from subprime.core.models import APSScore

        with pytest.raises(ValidationError):
            APSScore(**_aps(turnover_score=1.1))

    def test_each_dimension_boundary_zero(self):
        from subprime.core.models import APSScore

        for field in [
            "passive_instrument_fraction",
            "turnover_score",
            "cost_emphasis_score",
            "research_vs_cost_score",
            "time_horizon_alignment_score",
            "portfolio_activeness_score",
        ]:
            s = APSScore(**_aps(**{field: 0.0}))
            assert getattr(s, field) == 0.0

    def test_each_dimension_boundary_one(self):
        from subprime.core.models import APSScore

        for field in [
            "passive_instrument_fraction",
            "turnover_score",
            "cost_emphasis_score",
            "research_vs_cost_score",
            "time_horizon_alignment_score",
            "portfolio_activeness_score",
        ]:
            s = APSScore(**_aps(**{field: 1.0}))
            assert getattr(s, field) == 1.0

    def test_serialization_roundtrip(self):
        from subprime.core.models import APSScore

        original = APSScore(**_aps())
        dumped = original.model_dump_json()
        restored = APSScore.model_validate_json(dumped)
        assert restored.composite_aps == pytest.approx(original.composite_aps)
        assert restored.reasoning == original.reasoning

    def test_composite_in_model_dump(self):
        """composite_aps should appear in serialized output."""
        from subprime.core.models import APSScore

        s = APSScore(**_aps())
        d = s.model_dump()
        assert "composite_aps" in d
        assert isinstance(d["composite_aps"], float)


# ===========================================================================
# PlanQualityScore — with computed composite_pqs
# ===========================================================================


class TestPlanQualityScore:
    def test_construction_and_composite(self):
        from subprime.core.models import PlanQualityScore

        s = PlanQualityScore(**_pqs())
        expected = (0.9 + 0.8 + 0.85 + 0.9) / 4
        assert s.composite_pqs == pytest.approx(expected)

    def test_all_zeros(self):
        from subprime.core.models import PlanQualityScore

        s = PlanQualityScore(
            goal_alignment=0,
            diversification=0,
            risk_return_appropriateness=0,
            internal_consistency=0,
            reasoning="Terrible plan",
        )
        assert s.composite_pqs == pytest.approx(0.0)

    def test_all_ones(self):
        from subprime.core.models import PlanQualityScore

        s = PlanQualityScore(
            goal_alignment=1,
            diversification=1,
            risk_return_appropriateness=1,
            internal_consistency=1,
            reasoning="Perfect plan",
        )
        assert s.composite_pqs == pytest.approx(1.0)

    def test_known_composite_value(self):
        """(0.25 + 0.50 + 0.75 + 1.0) / 4 = 0.625"""
        from subprime.core.models import PlanQualityScore

        s = PlanQualityScore(
            goal_alignment=0.25,
            diversification=0.50,
            risk_return_appropriateness=0.75,
            internal_consistency=1.0,
            reasoning="Mixed quality",
        )
        assert s.composite_pqs == pytest.approx(0.625)

    def test_dimension_below_zero_rejected(self):
        from subprime.core.models import PlanQualityScore

        with pytest.raises(ValidationError):
            PlanQualityScore(**_pqs(goal_alignment=-0.01))

    def test_dimension_above_one_rejected(self):
        from subprime.core.models import PlanQualityScore

        with pytest.raises(ValidationError):
            PlanQualityScore(**_pqs(diversification=1.01))

    def test_serialization_roundtrip(self):
        from subprime.core.models import PlanQualityScore

        original = PlanQualityScore(**_pqs())
        dumped = original.model_dump_json()
        restored = PlanQualityScore.model_validate_json(dumped)
        assert restored.composite_pqs == pytest.approx(original.composite_pqs)

    def test_composite_in_model_dump(self):
        from subprime.core.models import PlanQualityScore

        s = PlanQualityScore(**_pqs())
        d = s.model_dump()
        assert "composite_pqs" in d


# ===========================================================================
# ExperimentResult
# ===========================================================================


class TestExperimentResult:
    def test_construction_happy_path(self):
        from subprime.core.models import ExperimentResult

        r = ExperimentResult(**_experiment_result())
        assert r.persona_id == "inv-001"
        assert r.condition == "baseline"
        assert r.model == "claude-sonnet-4-6"
        assert r.prompt_version == "v1"
        # timestamp should be auto-populated
        assert isinstance(r.timestamp, datetime)

    def test_timestamp_default_is_recent(self):
        from subprime.core.models import ExperimentResult

        before = datetime.now(timezone.utc)
        r = ExperimentResult(**_experiment_result())
        after = datetime.now(timezone.utc)
        # The default timestamp should be between before and after
        assert before <= r.timestamp <= after

    def test_timestamp_is_timezone_aware(self):
        from subprime.core.models import ExperimentResult

        r = ExperimentResult(**_experiment_result())
        assert r.timestamp.tzinfo is not None

    def test_custom_timestamp(self):
        from subprime.core.models import ExperimentResult

        ts = datetime(2026, 1, 15, 12, 0, 0)
        r = ExperimentResult(**_experiment_result(timestamp=ts))
        assert r.timestamp == ts

    def test_nested_models_accessible(self):
        from subprime.core.models import ExperimentResult

        r = ExperimentResult(**_experiment_result())
        assert r.plan.projected_returns["base"] == 10.0
        assert r.aps.composite_aps == pytest.approx((0.8 + 0.9 + 0.85 + 0.7 + 0.75) / 5)
        assert r.pqs.composite_pqs == pytest.approx((0.9 + 0.8 + 0.85 + 0.9) / 4)

    def test_serialization_roundtrip(self):
        from subprime.core.models import ExperimentResult

        original = ExperimentResult(**_experiment_result())
        dumped = original.model_dump_json()
        restored = ExperimentResult.model_validate_json(dumped)
        assert restored.persona_id == original.persona_id
        assert restored.condition == original.condition
        assert restored.aps.composite_aps == pytest.approx(original.aps.composite_aps)
        assert restored.pqs.composite_pqs == pytest.approx(original.pqs.composite_pqs)

    def test_full_json_structure(self):
        """Ensure the JSON has the expected top-level keys."""
        from subprime.core.models import ExperimentResult

        r = ExperimentResult(**_experiment_result())
        d = json.loads(r.model_dump_json())
        expected_keys = {
            "persona_id",
            "condition",
            "model",
            "judge_model",
            "plan",
            "aps",
            "pqs",
            "timestamp",
            "prompt_version",
        }
        assert expected_keys == set(d.keys())


# ===========================================================================
# Cross-model integration: nested construction from raw dicts
# ===========================================================================


class TestNestedConstruction:
    def test_experiment_result_from_raw_dicts(self):
        """ExperimentResult should accept raw dicts for nested models."""
        from subprime.core.models import ExperimentResult

        raw = _experiment_result()
        r = ExperimentResult(**raw)
        assert r.plan.allocations[0].fund.name == "Nifty 50 Index Fund"
        assert r.aps.reasoning == "Heavily passive plan with low turnover."
        assert r.pqs.reasoning == "Well-aligned plan with good diversification."
