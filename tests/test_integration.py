"""Integration tests — verify full module wiring end-to-end WITHOUT real LLM calls.

These are MEDIUM tests: they cross module boundaries but don't hit the network.
Only the LLM boundary (generate_plan, score_plan, Agent.run) is mocked.
Everything else runs real: personas load from JSON, conditions load from .md files,
analysis computes real stats, display renders real Rich output, CLI runs real Typer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from subprime.core.models import (
    Allocation,
    APSScore,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    PlanQualityScore,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_indian_fund(
    amfi_code: str = "119551",
    name: str = "Parag Parikh Flexi Cap Fund - Direct Growth",
    category: str = "Equity",
    sub_category: str = "Flexi Cap",
    fund_house: str = "PPFAS Mutual Fund",
    nav: float = 72.35,
    expense_ratio: float = 0.63,
    aum_cr: float = 58400.0,
    morningstar_rating: int = 5,
) -> MutualFund:
    return MutualFund(
        amfi_code=amfi_code,
        name=name,
        category=category,
        sub_category=sub_category,
        fund_house=fund_house,
        nav=nav,
        expense_ratio=expense_ratio,
        aum_cr=aum_cr,
        morningstar_rating=morningstar_rating,
    )


def _make_realistic_plan() -> InvestmentPlan:
    """A plan with real-looking Indian MF data — 3 funds."""
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=_make_indian_fund(
                    amfi_code="119551",
                    name="Parag Parikh Flexi Cap Fund - Direct Growth",
                    category="Equity",
                    sub_category="Flexi Cap",
                    fund_house="PPFAS Mutual Fund",
                    nav=72.35,
                    expense_ratio=0.63,
                ),
                allocation_pct=50.0,
                mode="sip",
                monthly_sip_inr=25000,
                rationale="Core equity holding with international diversification.",
            ),
            Allocation(
                fund=_make_indian_fund(
                    amfi_code="120505",
                    name="UTI Nifty 50 Index Fund - Direct Growth",
                    category="Equity",
                    sub_category="Large Cap",
                    fund_house="UTI Mutual Fund",
                    nav=152.40,
                    expense_ratio=0.10,
                    morningstar_rating=4,
                ),
                allocation_pct=30.0,
                mode="sip",
                monthly_sip_inr=15000,
                rationale="Low-cost Nifty 50 index exposure for broad market beta.",
            ),
            Allocation(
                fund=_make_indian_fund(
                    amfi_code="119237",
                    name="HDFC Short Term Debt Fund - Direct Growth",
                    category="Debt",
                    sub_category="Short Duration",
                    fund_house="HDFC Mutual Fund",
                    nav=28.56,
                    expense_ratio=0.25,
                    morningstar_rating=4,
                ),
                allocation_pct=20.0,
                mode="lumpsum",
                lumpsum_inr=40000,
                rationale="Debt anchor for stability and emergency liquidity.",
            ),
        ],
        setup_phase=(
            "Month 1: Start SIPs in Parag Parikh Flexi Cap and UTI Nifty 50. "
            "Deploy lumpsum into HDFC Short Term Debt."
        ),
        review_checkpoints=[
            "6-month check: verify SIPs are running and fund performance vs benchmark",
            "Annual review: full rebalance assessment",
        ],
        rebalancing_guidelines=(
            "Rebalance annually if equity allocation drifts more than 5% from target 80:20."
        ),
        projected_returns={"base": 11.5, "bull": 15.0, "bear": 5.5},
        rationale=(
            "A 50-30-20 split across flexi cap, large-cap index, and short-term debt. "
            "Balances growth with stability for a 30-year aggressive horizon."
        ),
        risks=[
            "Equity market volatility — drawdowns of 30-50% are possible in bear markets",
            "Interest rate risk on debt allocation",
            "Currency risk via Parag Parikh's international holdings",
        ],
        disclaimer="For research/educational purposes only. Not certified financial advice.",
    )


def _make_aps(composite_target: float = 0.5) -> APSScore:
    return APSScore(
        passive_instrument_fraction=composite_target,
        turnover_score=composite_target,
        cost_emphasis_score=composite_target,
        research_vs_cost_score=composite_target,
        time_horizon_alignment_score=composite_target,
        portfolio_activeness_score=composite_target,
        reasoning=f"All dimensions set to {composite_target}.",
    )


def _make_pqs(composite_target: float = 0.85) -> PlanQualityScore:
    return PlanQualityScore(
        goal_alignment=composite_target,
        diversification=composite_target,
        risk_return_appropriateness=composite_target,
        internal_consistency=composite_target,
        reasoning=f"All dimensions set to {composite_target}.",
    )


def _make_experiment_result(
    persona_id: str = "P01",
    condition: str = "baseline",
    aps_val: float = 0.5,
    pqs_val: float = 0.85,
) -> ExperimentResult:
    return ExperimentResult(
        persona_id=persona_id,
        condition=condition,
        model="test-model",
        plan=_make_realistic_plan(),
        aps=_make_aps(aps_val),
        pqs=_make_pqs(pqs_val),
        prompt_version="v1",
    )


# ===========================================================================
# 1. Full import chain test
# ===========================================================================


class TestFullImportChain:
    """Import every public symbol from every module and verify they resolve."""

    def test_core_imports(self):
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
            Allocation, APSScore, ExperimentResult, InvestmentPlan,
            InvestorProfile, MutualFund, PlanQualityScore, Settings,
            StrategyOutline,
        ]
        for s in symbols:
            assert s is not None

    def test_data_imports(self):
        from subprime.data import (
            MFDataClient,
            SchemeDetails,
            SchemeSearchResult,
            get_fund_details,
            search_funds_universe,
        )

        symbols = [
            MFDataClient, SchemeDetails, SchemeSearchResult,
            get_fund_details, search_funds_universe,
        ]
        for s in symbols:
            assert s is not None

    def test_advisor_imports(self):
        from subprime.advisor import create_advisor, generate_plan, load_prompt

        symbols = [create_advisor, generate_plan, load_prompt]
        for s in symbols:
            assert s is not None

    def test_evaluation_imports(self):
        from subprime.evaluation import (
            ScoredPlan,
            create_aps_judge,
            create_pqs_judge,
            get_persona,
            load_personas,
            score_aps,
            score_pqs,
            score_plan,
        )

        symbols = [
            ScoredPlan, create_aps_judge, create_pqs_judge,
            get_persona, load_personas, score_aps, score_pqs, score_plan,
        ]
        for s in symbols:
            assert s is not None

    def test_experiments_imports(self):
        from subprime.experiments import (
            BASELINE,
            BOGLE,
            CONDITIONS,
            ComparisonResult,
            Condition,
            ConditionStats,
            LYNCH,
            compare_conditions,
            compute_condition_stats,
            get_condition,
            print_analysis,
            run_experiment,
            run_single,
            save_result,
        )

        symbols = [
            BASELINE, BOGLE, CONDITIONS, ComparisonResult, Condition,
            ConditionStats, LYNCH, compare_conditions, compute_condition_stats,
            get_condition, print_analysis, run_experiment, run_single,
            save_result,
        ]
        for s in symbols:
            assert s is not None


# ===========================================================================
# 2. Persona -> Advisor -> Plan wiring
# ===========================================================================


class TestPersonaAdvisorPlanWiring:
    """Load persona from bank, create advisor agents, verify wiring."""

    def test_load_persona_p01(self):
        from subprime.evaluation import get_persona

        persona = get_persona("P01")
        assert persona.id == "P01"
        assert persona.name == "Tony Stark"
        assert isinstance(persona, InvestorProfile)

    def test_baseline_advisor_has_2_tools(self):
        from subprime.advisor import create_advisor

        agent = create_advisor(prompt_hooks={})
        # PydanticAI Agent stores tools in _function_toolset.tools (dict keyed by name)
        tool_names = set(agent._function_toolset.tools.keys())
        assert len(tool_names) == 2
        assert "search_funds_universe" in tool_names
        assert "get_fund_details" in tool_names

    def test_lynch_hook_in_system_prompt(self):
        from subprime.experiments import LYNCH
        from subprime.advisor import create_advisor

        agent = create_advisor(prompt_hooks=LYNCH.prompt_hooks)
        # The system prompt should contain Lynch-specific language
        prompt = agent._system_prompts[0]
        assert "Peter Lynch" in prompt or "Invest in What You Know" in prompt
        assert "Investment Philosophy" in prompt

    def test_bogle_hook_in_system_prompt(self):
        from subprime.experiments import BOGLE
        from subprime.advisor import create_advisor

        agent = create_advisor(prompt_hooks=BOGLE.prompt_hooks)
        prompt = agent._system_prompts[0]
        assert "John Bogle" in prompt or "Index Fund Supremacy" in prompt
        assert "Investment Philosophy" in prompt

    def test_baseline_has_no_philosophy_section(self):
        from subprime.advisor import create_advisor

        agent = create_advisor(prompt_hooks={})
        prompt = agent._system_prompts[0]
        # Baseline with empty hooks should NOT have a philosophy section
        # (the default hook file is empty)
        # The prompt should not contain "Investment Philosophy"
        # unless the default hooks/philosophy.md has content
        # Based on reading the file, it's empty, so:
        assert "Investment Philosophy" not in prompt


# ===========================================================================
# 3. Condition -> Advisor -> Score -> Result wiring
# ===========================================================================


class TestConditionAdvisorWiring:
    """For each condition, create an advisor and verify it wires correctly."""

    def test_all_conditions_create_agents(self):
        from subprime.advisor import create_advisor
        from subprime.experiments import CONDITIONS

        for condition in CONDITIONS:
            agent = create_advisor(prompt_hooks=condition.prompt_hooks)
            assert agent is not None

    def test_baseline_and_lynch_have_different_prompts(self):
        from subprime.advisor import create_advisor
        from subprime.experiments import BASELINE, LYNCH

        baseline_agent = create_advisor(prompt_hooks=BASELINE.prompt_hooks)
        lynch_agent = create_advisor(prompt_hooks=LYNCH.prompt_hooks)

        baseline_prompt = baseline_agent._system_prompts[0]
        lynch_prompt = lynch_agent._system_prompts[0]

        assert baseline_prompt != lynch_prompt
        # Lynch prompt should be strictly longer (contains philosophy section)
        assert len(lynch_prompt) > len(baseline_prompt)

    def test_baseline_and_bogle_have_different_prompts(self):
        from subprime.advisor import create_advisor
        from subprime.experiments import BASELINE, BOGLE

        baseline_agent = create_advisor(prompt_hooks=BASELINE.prompt_hooks)
        bogle_agent = create_advisor(prompt_hooks=BOGLE.prompt_hooks)

        baseline_prompt = baseline_agent._system_prompts[0]
        bogle_prompt = bogle_agent._system_prompts[0]

        assert baseline_prompt != bogle_prompt

    def test_lynch_and_bogle_have_different_prompts(self):
        from subprime.advisor import create_advisor
        from subprime.experiments import LYNCH, BOGLE

        lynch_agent = create_advisor(prompt_hooks=LYNCH.prompt_hooks)
        bogle_agent = create_advisor(prompt_hooks=BOGLE.prompt_hooks)

        lynch_prompt = lynch_agent._system_prompts[0]
        bogle_prompt = bogle_agent._system_prompts[0]

        assert lynch_prompt != bogle_prompt

    def test_condition_names_are_unique(self):
        from subprime.experiments import CONDITIONS

        names = [c.name for c in CONDITIONS]
        assert len(names) == len(set(names))
        assert set(names) == {"baseline", "lynch", "bogle"}


# ===========================================================================
# 4. End-to-end flow with mocked LLM
# ===========================================================================


class TestEndToEndMockedLLM:
    """Full pipeline: persona -> plan -> score -> ExperimentResult -> JSON roundtrip."""

    @pytest.mark.asyncio
    async def test_run_single_produces_correct_result(self):
        from subprime.evaluation import get_persona
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import BASELINE
        from subprime.experiments.runner import run_single

        persona = get_persona("P01")
        fake_plan = _make_realistic_plan()
        fake_aps = _make_aps(0.6)
        fake_pqs = _make_pqs(0.88)
        fake_scored = ScoredPlan(plan=fake_plan, aps=fake_aps, pqs=fake_pqs)

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
            result = await run_single(persona, BASELINE)

        assert isinstance(result, ExperimentResult)
        assert result.persona_id == "P01"
        assert result.condition == "baseline"
        assert result.plan == fake_plan
        assert result.aps.composite_aps == pytest.approx(0.6)
        assert result.pqs.composite_pqs == pytest.approx(0.88)

    @pytest.mark.asyncio
    async def test_run_single_with_lynch_condition(self):
        from subprime.evaluation import get_persona
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import LYNCH
        from subprime.experiments.runner import run_single

        persona = get_persona("P01")
        fake_plan = _make_realistic_plan()
        fake_scored = ScoredPlan(
            plan=fake_plan, aps=_make_aps(0.2), pqs=_make_pqs(0.85)
        )

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
            result = await run_single(persona, LYNCH)

        assert result.condition == "lynch"
        assert result.aps.composite_aps == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_result_json_roundtrip(self, tmp_path):
        from subprime.evaluation import get_persona
        from subprime.evaluation.scorer import ScoredPlan
        from subprime.experiments.conditions import BASELINE
        from subprime.experiments.runner import run_single, save_result

        persona = get_persona("P01")
        fake_plan = _make_realistic_plan()
        fake_scored = ScoredPlan(
            plan=fake_plan, aps=_make_aps(0.55), pqs=_make_pqs(0.9)
        )

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
            result = await run_single(persona, BASELINE)

        # Save to tmp_path and reload
        path = save_result(result, results_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

        restored = ExperimentResult.model_validate_json(path.read_text())
        assert restored.persona_id == result.persona_id
        assert restored.condition == result.condition
        assert restored.aps.composite_aps == pytest.approx(result.aps.composite_aps)
        assert restored.pqs.composite_pqs == pytest.approx(result.pqs.composite_pqs)
        assert len(restored.plan.allocations) == len(result.plan.allocations)
        assert restored.plan.allocations[0].fund.name == "Parag Parikh Flexi Cap Fund - Direct Growth"


# ===========================================================================
# 5. Analysis integration
# ===========================================================================


class TestAnalysisIntegration:
    """Create synthetic ExperimentResults and run real statistical analysis."""

    def _make_paired_results(self) -> list[ExperimentResult]:
        """3 baseline (APS ~0.5) + 3 lynch (APS ~0.2), matching persona IDs.

        Uses varying differences so that Cohen's d (delta_mean / delta_std) is
        well-defined and large, not 0/0.
        """
        results = []
        baseline_aps = [0.48, 0.55, 0.50]
        lynch_aps = [0.15, 0.22, 0.20]
        for i, (b_aps, l_aps) in enumerate(zip(baseline_aps, lynch_aps)):
            pid = f"P{i + 1:02d}"
            results.append(_make_experiment_result(pid, "baseline", b_aps))
            results.append(_make_experiment_result(pid, "lynch", l_aps))
        return results

    def test_compute_condition_stats_baseline(self):
        from subprime.experiments import compute_condition_stats

        results = self._make_paired_results()
        stats = compute_condition_stats(results, "baseline")

        assert stats.n == 3
        assert stats.condition == "baseline"
        # (0.48 + 0.55 + 0.50) / 3 = 0.51
        assert stats.mean_aps == pytest.approx(0.51, abs=0.01)

    def test_compute_condition_stats_lynch(self):
        from subprime.experiments import compute_condition_stats

        results = self._make_paired_results()
        stats = compute_condition_stats(results, "lynch")

        assert stats.n == 3
        assert stats.condition == "lynch"
        # mean([0.15, 0.22, 0.20]) = 0.19
        assert stats.mean_aps == pytest.approx(0.19, abs=0.001)

    def test_compare_conditions_delta_is_negative(self):
        from subprime.experiments import compare_conditions

        results = self._make_paired_results()
        cmp = compare_conditions(results, "baseline", "lynch")

        # Lynch APS < baseline APS, so delta = lynch - baseline < 0
        assert cmp.delta_aps < 0
        # mean(lynch) - mean(baseline) = 0.19 - 0.51 = -0.32
        assert cmp.delta_aps == pytest.approx(-0.32, abs=0.02)

    def test_compare_conditions_cohens_d_is_large(self):
        from subprime.experiments import compare_conditions

        results = self._make_paired_results()
        cmp = compare_conditions(results, "baseline", "lynch")

        # With a ~0.3 shift and small within-pair variance, |d| should be very large
        assert abs(cmp.cohens_d) > 0.8

    def test_compare_conditions_n_pairs(self):
        from subprime.experiments import compare_conditions

        results = self._make_paired_results()
        cmp = compare_conditions(results, "baseline", "lynch")

        assert cmp.n_pairs == 3

    def test_compare_conditions_significant(self):
        from subprime.experiments import compare_conditions

        results = self._make_paired_results()
        cmp = compare_conditions(results, "baseline", "lynch")

        assert cmp.significant_at_005 is True
        assert cmp.p_value_ttest < 0.05


# ===========================================================================
# 6. Display integration
# ===========================================================================


class TestDisplayIntegration:
    """Create a plan and scores, call display functions, verify output."""

    def test_format_plan_summary_returns_nonempty_string(self):
        from subprime.core.display import format_plan_summary

        plan = _make_realistic_plan()
        output = format_plan_summary(plan)

        assert isinstance(output, str)
        assert len(output) > 0
        # Should contain fund names from the plan
        assert "Parag Parikh" in output or "UTI Nifty" in output

    def test_format_plan_summary_contains_projected_returns(self):
        from subprime.core.display import format_plan_summary

        plan = _make_realistic_plan()
        output = format_plan_summary(plan)

        # Should contain the projected return values
        assert "11.5" in output
        assert "15.0" in output
        assert "5.5" in output

    def test_format_scores_returns_nonempty_string(self):
        from subprime.core.display import format_scores

        aps = _make_aps(0.65)
        pqs = _make_pqs(0.88)
        output = format_scores(aps, pqs)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_format_scores_contains_aps_and_pqs(self):
        from subprime.core.display import format_scores

        aps = _make_aps(0.65)
        pqs = _make_pqs(0.88)
        output = format_scores(aps, pqs)

        # Should contain both table titles
        assert "Active-Passive Score" in output or "APS" in output
        assert "Plan Quality Score" in output or "PQS" in output

    def test_format_scores_shows_composite_values(self):
        from subprime.core.display import format_scores

        aps = _make_aps(0.65)
        pqs = _make_pqs(0.88)
        output = format_scores(aps, pqs)

        # Composite APS should be 0.650, PQS should be 0.880
        assert "0.650" in output
        assert "0.880" in output


# ===========================================================================
# 7. CLI integration
# ===========================================================================


class TestCLIIntegration:
    """Run CLI commands via CliRunner with valid experiment result files."""

    def _write_results_to_dir(self, tmp_path: Path) -> None:
        """Write 3 baseline + 3 lynch ExperimentResult JSON files."""
        baseline_aps = [0.48, 0.52, 0.50]
        lynch_aps = [0.18, 0.22, 0.20]

        for i, (b_aps, l_aps) in enumerate(zip(baseline_aps, lynch_aps)):
            pid = f"P{i + 1:02d}"

            b_result = _make_experiment_result(pid, "baseline", b_aps)
            b_path = tmp_path / f"{pid}_baseline_20260101T00000{i}.json"
            b_path.write_text(b_result.model_dump_json(indent=2))

            l_result = _make_experiment_result(pid, "lynch", l_aps)
            l_path = tmp_path / f"{pid}_lynch_20260101T00000{i}.json"
            l_path.write_text(l_result.model_dump_json(indent=2))

    def test_experiment_analyze_exit_code_zero(self, tmp_path):
        from subprime.cli import app

        self._write_results_to_dir(tmp_path)
        cli_runner = CliRunner()
        result = cli_runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_experiment_analyze_shows_loaded_count(self, tmp_path):
        from subprime.cli import app

        self._write_results_to_dir(tmp_path)
        cli_runner = CliRunner()
        result = cli_runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        # Should report loading 6 results
        assert "6" in result.output

    def test_experiment_analyze_contains_condition_stats(self, tmp_path):
        from subprime.cli import app

        self._write_results_to_dir(tmp_path)
        cli_runner = CliRunner()
        result = cli_runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        # Output should mention condition names and contain statistical output
        assert "baseline" in result.output
        assert "lynch" in result.output

    def test_experiment_analyze_contains_analysis(self, tmp_path):
        from subprime.cli import app

        self._write_results_to_dir(tmp_path)
        cli_runner = CliRunner()
        result = cli_runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        # Should contain subprime spread analysis content
        # (condition statistics table and/or comparison output)
        output_lower = result.output.lower()
        assert "condition" in output_lower or "aps" in output_lower or "spread" in output_lower


# ===========================================================================
# 8. M1 three-phase interactive advisor
# ===========================================================================


class TestM1AdvisorFlow:
    """Integration tests for the three-phase interactive advisor."""

    def test_strategy_advisor_creates_for_all_conditions(self):
        from subprime.advisor import create_strategy_advisor
        from subprime.experiments import CONDITIONS

        for cond in CONDITIONS:
            agent = create_strategy_advisor(prompt_hooks=cond.prompt_hooks)
            assert agent is not None
            assert len(agent._function_toolset.tools) == 0

    def test_strategy_advisor_different_from_plan_advisor(self):
        from subprime.advisor import create_advisor, create_strategy_advisor

        plan_agent = create_advisor()
        strategy_agent = create_strategy_advisor()

        plan_prompts = " ".join(str(s) for s in plan_agent._system_prompts)
        strategy_prompts = " ".join(str(s) for s in strategy_agent._system_prompts)

        assert plan_prompts != strategy_prompts
        assert len(plan_agent._function_toolset.tools) > 0
        assert len(strategy_agent._function_toolset.tools) == 0

    @pytest.mark.asyncio
    async def test_full_flow_mocked(self):
        """Full three-phase flow: profile -> strategy -> plan, all mocked."""
        from subprime.advisor import generate_plan, generate_strategy
        from subprime.evaluation import get_persona
        from subprime.core.display import format_strategy_outline, format_plan_summary
        from subprime.core.models import StrategyOutline

        profile = get_persona("P01")

        fake_strategy = StrategyOutline(
            equity_pct=75.0, debt_pct=15.0, gold_pct=10.0, other_pct=0.0,
            equity_approach="Index-heavy",
            key_themes=["low cost", "broad market"],
            risk_return_summary="12-14% CAGR",
            open_questions=[],
        )
        mock_strategy_result = MagicMock()
        mock_strategy_result.output = fake_strategy

        with patch("subprime.advisor.planner.create_strategy_advisor") as mock_cs:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_strategy_result)
            mock_cs.return_value = mock_agent
            strategy = await generate_strategy(profile)

        assert strategy.equity_pct == 75.0
        strategy_display = format_strategy_outline(strategy)
        assert "75" in strategy_display

        fund = MutualFund(
            amfi_code="120503", name="UTI Nifty 50",
            category="Equity", sub_category="Index",
            fund_house="UTI", nav=150.0, expense_ratio=0.18,
        )
        fake_plan = InvestmentPlan(
            allocations=[
                Allocation(fund=fund, allocation_pct=75.0, mode="sip",
                           monthly_sip_inr=37500, rationale="Core index"),
            ],
            setup_phase="Start SIP month 1",
            review_checkpoints=["6-month"],
            rebalancing_guidelines="Annual",
            projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
            rationale="Index-heavy strategy",
            risks=["Market risk"],
            disclaimer="Research only",
        )
        mock_plan_result = MagicMock()
        mock_plan_result.output = fake_plan

        with patch("subprime.advisor.planner.create_advisor") as mock_ca:
            mock_agent2 = AsyncMock()
            mock_agent2.run = AsyncMock(return_value=mock_plan_result)
            mock_ca.return_value = mock_agent2
            plan = await generate_plan(profile, strategy=strategy)

        assert "UTI Nifty 50" in plan.allocations[0].fund.name
        plan_display = format_plan_summary(plan)
        assert "UTI Nifty 50" in plan_display

    def test_gather_profile_bulk_bypass(self):
        """gather_profile with existing_profile should bypass conversation."""
        import asyncio
        from subprime.advisor import gather_profile
        from subprime.evaluation import get_persona

        profile = get_persona("P01")

        async def should_not_be_called(msg: str) -> str:
            raise AssertionError("Should not be called")

        result = asyncio.run(
            gather_profile(send_message=should_not_be_called, existing_profile=profile)
        )
        assert result.id == "P01"
