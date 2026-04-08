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
