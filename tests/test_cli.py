"""Tests for subprime.cli — Typer CLI entry point.

Uses typer.testing.CliRunner. Deterministic, fast, no network/LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


from unittest.mock import AsyncMock, patch


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
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=fake_plan),
        ):
            result = runner.invoke(app, ["advise", "--profile", "P01"], input="yes\n")

        assert result.exit_code == 0
