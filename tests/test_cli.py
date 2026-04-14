"""Tests for subprime.cli — Typer CLI entry point.

Uses typer.testing.CliRunner. Deterministic, fast, no network/LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.usage import RunUsage
from typer.testing import CliRunner

from subprime.cli import app
from subprime.core.models import (
    APSScore,
    Allocation,
    ExperimentResult,
    InvestmentPlan,
    MutualFund,
    PlanQualityScore,
    StrategyOutline,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_experiment_result_json() -> str:
    """Build a valid ExperimentResult and return its JSON string."""
    fund = MutualFund(
        amfi_code="119551",
        name="Nifty 50 Index Fund",
        category="Equity",
        sub_category="Large Cap",
        fund_house="UTI",
        nav=150.25,
        expense_ratio=0.10,
    )
    plan = InvestmentPlan(
        allocations=[
            Allocation(
                fund=fund,
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=50_000,
                rationale="Low cost broad market exposure",
            )
        ],
        setup_phase="Start SIPs immediately.",
        review_checkpoints=["6-month review"],
        rebalancing_guidelines="Rebalance annually.",
        projected_returns={"base": 10.0, "bull": 14.0, "bear": 6.0},
        rationale="Simple passive strategy.",
        risks=["Market risk"],
        disclaimer="Research only.",
    )
    aps = APSScore(
        passive_instrument_fraction=0.8,
        turnover_score=0.9,
        cost_emphasis_score=0.85,
        research_vs_cost_score=0.7,
        time_horizon_alignment_score=0.75,
        portfolio_activeness_score=0.8,
        reasoning="Heavily passive.",
    )
    pqs = PlanQualityScore(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Good quality.",
    )
    result = ExperimentResult(
        persona_id="P01",
        condition="baseline",
        model="test-model",
        plan=plan,
        aps=aps,
        pqs=pqs,
        prompt_version="v1",
    )
    return result.model_dump_json(indent=2)


# ===========================================================================
# Top-level help
# ===========================================================================


class TestTopLevelHelp:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_help_shows_subprime(self):
        result = runner.invoke(app, ["--help"])
        assert "subprime" in result.output.lower() or "Subprime" in result.output


# ===========================================================================
# experiment-run
# ===========================================================================


class TestExperimentRun:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["experiment-run", "--help"])
        assert result.exit_code == 0

    def test_help_shows_persona_option(self):
        result = runner.invoke(app, ["experiment-run", "--help"])
        assert "--persona" in result.output or "-p" in result.output

    def test_help_shows_conditions_option(self):
        result = runner.invoke(app, ["experiment-run", "--help"])
        assert "--conditions" in result.output or "-c" in result.output

    def test_help_shows_model_option(self):
        result = runner.invoke(app, ["experiment-run", "--help"])
        assert "--model" in result.output or "-m" in result.output

    def test_help_shows_results_dir_option(self):
        result = runner.invoke(app, ["experiment-run", "--help"])
        assert "--results-dir" in result.output


# ===========================================================================
# experiment-analyze
# ===========================================================================


class TestExperimentAnalyze:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["experiment-analyze", "--help"])
        assert result.exit_code == 0

    def test_missing_results_dir_shows_error(self, tmp_path):
        """Passing a non-existent directory should produce an error."""
        missing = tmp_path / "nonexistent"
        result = runner.invoke(app, ["experiment-analyze", "--results-dir", str(missing)])
        assert result.exit_code != 0 or "error" in result.output.lower() or "not found" in result.output.lower() or "does not exist" in result.output.lower()

    def test_empty_results_dir_shows_error(self, tmp_path):
        """An empty directory should produce a message about no results."""
        result = runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        assert result.exit_code != 0 or "no" in result.output.lower()

    def test_valid_results_dir(self, tmp_path):
        """A directory with a valid JSON result file should work."""
        # Write a valid ExperimentResult JSON file
        json_path = tmp_path / "P01_baseline_20260101T000000.json"
        json_path.write_text(_make_experiment_result_json())

        result = runner.invoke(app, ["experiment-analyze", "--results-dir", str(tmp_path)])
        # Should not crash — exit code 0
        assert result.exit_code == 0

    def test_shows_results_dir_option(self):
        result = runner.invoke(app, ["experiment-analyze", "--help"])
        assert "--results-dir" in result.output


# ===========================================================================
# advise
# ===========================================================================


class TestAdvise:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert result.exit_code == 0

    def test_help_shows_profile_option(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert "--profile" in result.output or "-p" in result.output

    def test_help_shows_model_option(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert "--model" in result.output or "-m" in result.output

    def test_help_shows_mode_option(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert "--mode" in result.output

    def test_advise_with_profile_bulk_mode(self):
        """--profile P01 should skip interactive Q&A and go through strategy + plan."""
        fake_strategy = StrategyOutline(
            equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
            equity_approach="Index-heavy",
            key_themes=["low cost"],
            risk_return_summary="12% CAGR",
            open_questions=[],
        )

        fake_plan = InvestmentPlan(
            allocations=[
                Allocation(
                    fund=MutualFund(
                        amfi_code="120503", name="UTI Nifty 50",
                        category="Equity", sub_category="Index",
                        fund_house="UTI", nav=150.0, expense_ratio=0.18,
                    ),
                    allocation_pct=100.0, mode="sip",
                    monthly_sip_inr=50000, rationale="Core index",
                )
            ],
            setup_phase="Start SIP month 1",
            review_checkpoints=["6-month"],
            rebalancing_guidelines="Annual",
            projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
            rationale="Simple index strategy",
            risks=["Market risk"],
            disclaimer="Research only",
        )

        with (
            patch("subprime.cli.generate_strategy", new_callable=AsyncMock, return_value=fake_strategy),
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=(fake_plan, RunUsage())),
        ):
            result = runner.invoke(app, ["advise", "--profile", "P01"], input="yes\n")

        assert result.exit_code == 0


# ===========================================================================
# smoke-test command
# ===========================================================================


def _make_smoke_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(
                    amfi_code="119551", name="Parag Parikh Flexi Cap",
                    category="Equity", sub_category="Flexi Cap",
                    fund_house="PPFAS", nav=65.0, expense_ratio=0.63,
                ),
                allocation_pct=100.0, mode="sip",
                monthly_sip_inr=50000, rationale="Core holding",
            )
        ],
        setup_phase="Start SIP month 1.",
        review_checkpoints=["6-month review"],
        rebalancing_guidelines="Annual rebalance.",
        projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
        rationale="Growth strategy.",
        risks=["Market risk"],
        disclaimer="Research only.",
    )


def _make_smoke_result(plan: InvestmentPlan) -> "ExperimentResult":
    aps = APSScore(
        passive_instrument_fraction=0.7,
        turnover_score=0.8,
        cost_emphasis_score=0.6,
        research_vs_cost_score=0.5,
        time_horizon_alignment_score=0.9,
        portfolio_activeness_score=0.7,
        reasoning="Balanced plan.",
    )
    pqs = PlanQualityScore(
        goal_alignment=0.9,
        diversification=0.8,
        risk_return_appropriateness=0.85,
        internal_consistency=0.9,
        reasoning="Good quality.",
    )
    return ExperimentResult(
        persona_id="P01",
        condition="baseline",
        model="anthropic:claude-sonnet-4-6",
        plan=plan,
        aps=aps,
        pqs=pqs,
        prompt_version="v1",
    )


class TestSmokeTest:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["smoke-test", "--help"])
        assert result.exit_code == 0

    def test_shows_n_personas_and_model(self):
        result = runner.invoke(app, ["smoke-test", "--help"])
        assert "--n-personas" in result.output
        assert "--model" in result.output

    def test_exits_zero_on_success(self):
        """smoke-test exits 0 when all runs complete successfully (2x2 matrix)."""
        plan = _make_smoke_plan()
        exp_result = _make_smoke_result(plan)

        cold_usage = RunUsage(input_tokens=8000, output_tokens=300, cache_write_tokens=7500)
        warm_usage = RunUsage(input_tokens=500, output_tokens=295, cache_read_tokens=7500)

        call_count = 0

        async def _mock_run_single(persona, condition, model, judge_model=None):
            nonlocal call_count
            call_count += 1
            usage = cold_usage if call_count == 1 else warm_usage
            return exp_result, usage

        with patch("subprime.cli._check_api_key"), patch(
            "subprime.experiments.runner.run_single", side_effect=_mock_run_single
        ):
            result = runner.invoke(app, ["smoke-test", "--n-personas", "2"])

        assert result.exit_code == 0, result.output
        assert call_count == 4  # 2 personas × 2 conditions

    def test_reports_cache_hits(self):
        """Runs 2 after the first show cache_read; output says cache is working."""
        plan = _make_smoke_plan()
        exp_result = _make_smoke_result(plan)

        call_count = 0

        async def _mock_run_single(persona, condition, model, judge_model=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                usage = RunUsage(input_tokens=8000, output_tokens=300, cache_write_tokens=7500)
            else:
                usage = RunUsage(input_tokens=500, output_tokens=295, cache_read_tokens=7500)
            return exp_result, usage

        with patch("subprime.cli._check_api_key"), patch(
            "subprime.experiments.runner.run_single", side_effect=_mock_run_single
        ):
            result = runner.invoke(app, ["smoke-test", "--n-personas", "2"])

        assert "cache working" in result.output.lower()

    def test_reports_cache_write_only(self):
        """On first-ever run (all cache_write, no reads), output notes cache was written."""
        plan = _make_smoke_plan()
        exp_result = _make_smoke_result(plan)

        async def _mock_run_single(persona, condition, model, judge_model=None):
            return exp_result, RunUsage(input_tokens=8000, output_tokens=300, cache_write_tokens=7500)

        with patch("subprime.cli._check_api_key"), patch(
            "subprime.experiments.runner.run_single", side_effect=_mock_run_single
        ):
            result = runner.invoke(app, ["smoke-test", "--n-personas", "1"])

        assert result.exit_code == 0
        assert "written" in result.output.lower()

    def test_single_persona_runs_two_conditions(self):
        """--n-personas 1 still runs 2 conditions (1×2 = 2 calls)."""
        plan = _make_smoke_plan()
        exp_result = _make_smoke_result(plan)
        call_count = 0

        async def _mock_run_single(persona, condition, model, judge_model=None):
            nonlocal call_count
            call_count += 1
            return exp_result, RunUsage(input_tokens=100, output_tokens=50)

        with patch("subprime.cli._check_api_key"), patch(
            "subprime.experiments.runner.run_single", side_effect=_mock_run_single
        ):
            runner.invoke(app, ["smoke-test", "--n-personas", "1"])

        assert call_count == 2

    def test_exits_one_on_llm_failure(self):
        """smoke-test exits 1 if an LLM call raises."""
        async def _mock_run_single(*args, **kwargs):
            raise RuntimeError("API timeout")

        with patch("subprime.cli._check_api_key"), patch(
            "subprime.experiments.runner.run_single", side_effect=_mock_run_single
        ):
            result = runner.invoke(app, ["smoke-test", "--n-personas", "1"])

        assert result.exit_code == 1
