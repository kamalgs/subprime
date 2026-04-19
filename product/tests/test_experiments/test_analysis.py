"""Tests for experiment analysis — condition stats and comparisons."""

from __future__ import annotations

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
# Fixtures — synthetic ExperimentResults with known APS/PQS values
# ---------------------------------------------------------------------------


def _make_fund() -> MutualFund:
    return MutualFund(
        amfi_code="119551",
        name="Test Fund",
        category="Equity",
        sub_category="Flexi Cap",
        fund_house="Test",
        nav=100.0,
        expense_ratio=0.50,
    )


def _make_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=_make_fund(),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=10000,
                rationale="Test allocation.",
            )
        ],
        setup_phase="Start immediately.",
        review_checkpoints=["6-month review"],
        rebalancing_guidelines="Rebalance annually.",
        projected_returns={"base": 10.0, "bull": 14.0, "bear": 6.0},
        rationale="Test plan.",
        risks=["Market risk"],
        disclaimer="Research only.",
    )


def _make_aps(composite_target: float) -> APSScore:
    """Create an APS score where all dimensions equal the target -> composite = target."""
    return APSScore(
        passive_instrument_fraction=composite_target,
        turnover_score=composite_target,
        cost_emphasis_score=composite_target,
        research_vs_cost_score=composite_target,
        time_horizon_alignment_score=composite_target,
        portfolio_activeness_score=composite_target,
        reasoning=f"All dimensions at {composite_target}",
    )


def _make_pqs(composite_target: float) -> PlanQualityScore:
    """Create a PQS score where all dimensions equal the target -> composite = target."""
    return PlanQualityScore(
        goal_alignment=composite_target,
        diversification=composite_target,
        risk_return_appropriateness=composite_target,
        internal_consistency=composite_target,
        tax_efficiency=composite_target,
        reasoning=f"All dimensions at {composite_target}",
    )


def _make_result(
    persona_id: str, condition: str, aps_val: float, pqs_val: float = 0.8
) -> ExperimentResult:
    return ExperimentResult(
        persona_id=persona_id,
        condition=condition,
        model="test-model",
        plan=_make_plan(),
        aps=_make_aps(aps_val),
        pqs=_make_pqs(pqs_val),
        prompt_version="v1",
    )


# ---------------------------------------------------------------------------
# compute_condition_stats
# ---------------------------------------------------------------------------


class TestComputeConditionStats:
    def test_correct_n(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [
            _make_result("P01", "baseline", 0.5),
            _make_result("P02", "baseline", 0.6),
            _make_result("P03", "baseline", 0.4),
            _make_result("P01", "lynch", 0.2),  # should be ignored
        ]
        stats = compute_condition_stats(results, "baseline")
        assert stats.n == 3

    def test_correct_mean_aps(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [
            _make_result("P01", "baseline", 0.4),
            _make_result("P02", "baseline", 0.6),
        ]
        stats = compute_condition_stats(results, "baseline")
        assert stats.mean_aps == pytest.approx(0.5)

    def test_correct_std_aps(self):
        from subprime.experiments.analysis import compute_condition_stats

        # APS values: 0.4 and 0.6 -> mean = 0.5, std (ddof=1) = 0.1414...
        results = [
            _make_result("P01", "baseline", 0.4),
            _make_result("P02", "baseline", 0.6),
        ]
        stats = compute_condition_stats(results, "baseline")
        # std with ddof=1: sqrt(((0.4-0.5)**2 + (0.6-0.5)**2) / 1) = sqrt(0.02) ~ 0.1414
        assert stats.std_aps == pytest.approx(0.1414, abs=0.001)

    def test_correct_median_aps(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [
            _make_result("P01", "baseline", 0.3),
            _make_result("P02", "baseline", 0.5),
            _make_result("P03", "baseline", 0.9),
        ]
        stats = compute_condition_stats(results, "baseline")
        assert stats.median_aps == pytest.approx(0.5)

    def test_correct_mean_pqs(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [
            _make_result("P01", "baseline", 0.5, pqs_val=0.7),
            _make_result("P02", "baseline", 0.5, pqs_val=0.9),
        ]
        stats = compute_condition_stats(results, "baseline")
        assert stats.mean_pqs == pytest.approx(0.8)

    def test_correct_std_pqs(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [
            _make_result("P01", "baseline", 0.5, pqs_val=0.7),
            _make_result("P02", "baseline", 0.5, pqs_val=0.9),
        ]
        stats = compute_condition_stats(results, "baseline")
        # std with ddof=1: sqrt(((0.7-0.8)**2 + (0.9-0.8)**2) / 1) = sqrt(0.02) ~ 0.1414
        assert stats.std_pqs == pytest.approx(0.1414, abs=0.001)

    def test_condition_name_in_stats(self):
        from subprime.experiments.analysis import compute_condition_stats

        results = [_make_result("P01", "lynch", 0.3)]
        stats = compute_condition_stats(results, "lynch")
        assert stats.condition == "lynch"

    def test_single_result_std_is_zero(self):
        """With n=1, std should be 0 (or NaN handled gracefully)."""
        from subprime.experiments.analysis import compute_condition_stats

        results = [_make_result("P01", "baseline", 0.5)]
        stats = compute_condition_stats(results, "baseline")
        assert stats.n == 1
        # With ddof=0 for single values, std = 0
        # Implementation may choose ddof=1 which gives nan for n=1,
        # but we should handle it gracefully (0.0)
        assert stats.std_aps == pytest.approx(0.0, abs=0.001) or stats.std_aps != stats.std_aps


# ---------------------------------------------------------------------------
# compare_conditions
# ---------------------------------------------------------------------------


class TestCompareConditions:
    def _baseline_lynch_results(self):
        """6 personas x 2 conditions with a clear shift.

        Baseline APS ~ 0.5, Lynch APS ~ 0.2 -> delta ~ -0.3, large effect.
        """
        results = []
        baseline_aps = [0.45, 0.50, 0.55, 0.48, 0.52, 0.50]
        lynch_aps = [0.18, 0.22, 0.20, 0.15, 0.25, 0.20]
        for i, (b, l) in enumerate(zip(baseline_aps, lynch_aps)):
            pid = f"P{i+1:02d}"
            results.append(_make_result(pid, "baseline", b))
            results.append(_make_result(pid, "lynch", l))
        return results

    def test_delta_aps_sign(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        # Lynch is more active (lower APS), so delta = lynch_mean - baseline_mean < 0
        assert cmp.delta_aps < 0

    def test_cohens_d_large(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        # With a ~0.3 shift and small variance, Cohen's d should be large (> 0.8)
        assert abs(cmp.cohens_d) > 0.8

    def test_significant_at_005(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        assert cmp.significant_at_005 is True

    def test_p_value_ttest_small(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        assert cmp.p_value_ttest < 0.05

    def test_n_pairs_correct(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        assert cmp.n_pairs == 6

    def test_condition_names_in_result(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        assert cmp.condition_a == "baseline"
        assert cmp.condition_b == "lynch"

    def test_less_than_3_pairs_raises(self):
        from subprime.experiments.analysis import compare_conditions

        results = [
            _make_result("P01", "baseline", 0.5),
            _make_result("P01", "lynch", 0.2),
            _make_result("P02", "baseline", 0.5),
            _make_result("P02", "lynch", 0.2),
        ]
        with pytest.raises(ValueError, match="[Aa]t least 3"):
            compare_conditions(results, "baseline", "lynch")

    def test_no_overlap_raises(self):
        from subprime.experiments.analysis import compare_conditions

        results = [
            _make_result("P01", "baseline", 0.5),
            _make_result("P02", "baseline", 0.5),
            _make_result("P03", "baseline", 0.5),
            _make_result("P04", "lynch", 0.2),
            _make_result("P05", "lynch", 0.2),
            _make_result("P06", "lynch", 0.2),
        ]
        with pytest.raises(ValueError, match="[Aa]t least 3"):
            compare_conditions(results, "baseline", "lynch")

    def test_no_shift_not_significant(self):
        """When both conditions have identical APS, p-value should be large."""
        from subprime.experiments.analysis import compare_conditions

        results = []
        for i in range(5):
            pid = f"P{i+1:02d}"
            results.append(_make_result(pid, "baseline", 0.5))
            results.append(_make_result(pid, "bogle", 0.5))
        cmp = compare_conditions(results, "baseline", "bogle")
        assert cmp.significant_at_005 is False
        assert cmp.delta_aps == pytest.approx(0.0, abs=0.01)

    def test_wilcoxon_populated_when_enough_pairs(self):
        from subprime.experiments.analysis import compare_conditions

        results = self._baseline_lynch_results()
        cmp = compare_conditions(results, "baseline", "lynch")
        # With 6 pairs and a clear shift, Wilcoxon should be populated
        assert cmp.p_value_wilcoxon is not None
        assert cmp.p_value_wilcoxon < 0.05


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_experiments_package_exports(self):
        from subprime.experiments import (
            BOGLE,
            BASELINE,
            CONDITIONS,
            LYNCH,
            ComparisonResult,
            Condition,
            ConditionStats,
            compare_conditions,
            compute_condition_stats,
            get_condition,
            print_analysis,
            run_experiment,
            run_single,
            save_result,
        )

        # Just verify they're all importable and not None
        symbols = [
            BASELINE, LYNCH, BOGLE, CONDITIONS, Condition, ConditionStats,
            ComparisonResult, get_condition, run_experiment, run_single,
            save_result, compute_condition_stats, compare_conditions,
            print_analysis,
        ]
        for s in symbols:
            assert s is not None
