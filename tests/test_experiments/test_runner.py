"""Tests for experiment runner — save_result and run_single."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from subprime.core.models import (
    APSScore,
    Allocation,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    PlanQualityScore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fund() -> MutualFund:
    return MutualFund(
        amfi_code="119551",
        name="Parag Parikh Flexi Cap Fund",
        category="Equity",
        sub_category="Flexi Cap",
        fund_house="PPFAS",
        nav=65.0,
        expense_ratio=0.63,
    )


def _make_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=_make_fund(),
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


def _make_experiment_result(**overrides) -> ExperimentResult:
    defaults = dict(
        persona_id="P01",
        condition="baseline",
        model="claude-sonnet-4-6",
        plan=_make_plan(),
        aps=_make_aps(),
        pqs=_make_pqs(),
        prompt_version="v1",
    )
    defaults.update(overrides)
    return ExperimentResult(**defaults)


# ---------------------------------------------------------------------------
# save_result
# ---------------------------------------------------------------------------


class TestSaveResult:
    def test_writes_json_file(self, tmp_path):
        from subprime.experiments.runner import save_result

        result = _make_experiment_result()
        path = save_result(result, results_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_json_is_valid(self, tmp_path):
        from subprime.experiments.runner import save_result

        result = _make_experiment_result()
        path = save_result(result, results_dir=tmp_path)
        data = json.loads(path.read_text())
        assert data["persona_id"] == "P01"
        assert data["condition"] == "baseline"

    def test_loaded_json_matches_original(self, tmp_path):
        from subprime.experiments.runner import save_result

        result = _make_experiment_result()
        path = save_result(result, results_dir=tmp_path)
        restored = ExperimentResult.model_validate_json(path.read_text())
        assert restored.persona_id == result.persona_id
        assert restored.condition == result.condition
        assert restored.aps.composite_aps == pytest.approx(result.aps.composite_aps)
        assert restored.pqs.composite_pqs == pytest.approx(result.pqs.composite_pqs)

    def test_creates_results_dir(self, tmp_path):
        from subprime.experiments.runner import save_result

        nested = tmp_path / "deep" / "results"
        result = _make_experiment_result()
        path = save_result(result, results_dir=nested)
        assert path.exists()
        assert nested.is_dir()

    def test_unique_filenames(self, tmp_path):
        from subprime.experiments.runner import save_result

        r1 = _make_experiment_result(persona_id="P01")
        r2 = _make_experiment_result(persona_id="P02")
        p1 = save_result(r1, results_dir=tmp_path)
        p2 = save_result(r2, results_dir=tmp_path)
        assert p1 != p2


# ---------------------------------------------------------------------------
# run_single (LLM mocked)
# ---------------------------------------------------------------------------


class TestRunSingle:
    @pytest.mark.asyncio
    async def test_returns_experiment_result(self):
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import BASELINE
        from subprime.experiments.runner import run_single

        fake_plan = _make_plan()
        fake_scored = ScoredPlan(plan=fake_plan, aps=_make_aps(), pqs=_make_pqs())

        with (
            patch(
                "subprime.experiments.runner.generate_plan",
                new_callable=AsyncMock,
                return_value=fake_plan,
            ),
            patch(
                "subprime.experiments.runner.score_plan",
                new_callable=AsyncMock,
                return_value=fake_scored,
            ),
        ):
            result = await run_single(_make_profile(), BASELINE)

        assert isinstance(result, ExperimentResult)
        assert result.persona_id == "P01"
        assert result.condition == "baseline"

    @pytest.mark.asyncio
    async def test_passes_hooks_to_generate_plan(self):
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import LYNCH
        from subprime.experiments.runner import run_single

        fake_plan = _make_plan()
        fake_scored = ScoredPlan(plan=fake_plan, aps=_make_aps(), pqs=_make_pqs())

        with (
            patch(
                "subprime.experiments.runner.generate_plan",
                new_callable=AsyncMock,
                return_value=fake_plan,
            ) as mock_gen,
            patch(
                "subprime.experiments.runner.score_plan",
                new_callable=AsyncMock,
                return_value=fake_scored,
            ),
        ):
            await run_single(_make_profile(), LYNCH)

        # generate_plan should receive the Lynch philosophy hooks
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("prompt_hooks") == LYNCH.prompt_hooks

    @pytest.mark.asyncio
    async def test_uses_custom_model(self):
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import BASELINE
        from subprime.experiments.runner import run_single

        fake_plan = _make_plan()
        fake_scored = ScoredPlan(plan=fake_plan, aps=_make_aps(), pqs=_make_pqs())

        with (
            patch(
                "subprime.experiments.runner.generate_plan",
                new_callable=AsyncMock,
                return_value=fake_plan,
            ) as mock_gen,
            patch(
                "subprime.experiments.runner.score_plan",
                new_callable=AsyncMock,
                return_value=fake_scored,
            ) as mock_score,
        ):
            result = await run_single(
                _make_profile(), BASELINE, model="openai:gpt-4o-mini"
            )

        assert result.model == "openai:gpt-4o-mini"
        assert mock_gen.call_args.kwargs.get("model") == "openai:gpt-4o-mini"
        assert mock_score.call_args.kwargs.get("model") == "openai:gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_result_has_timestamp(self):
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import BASELINE
        from subprime.experiments.runner import run_single

        fake_plan = _make_plan()
        fake_scored = ScoredPlan(plan=fake_plan, aps=_make_aps(), pqs=_make_pqs())

        before = datetime.now(timezone.utc)
        with (
            patch(
                "subprime.experiments.runner.generate_plan",
                new_callable=AsyncMock,
                return_value=fake_plan,
            ),
            patch(
                "subprime.experiments.runner.score_plan",
                new_callable=AsyncMock,
                return_value=fake_scored,
            ),
        ):
            result = await run_single(_make_profile(), BASELINE)
        after = datetime.now(timezone.utc)

        assert before <= result.timestamp <= after
