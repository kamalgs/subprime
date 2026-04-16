"""Tests for the cost estimator — no API calls, no DB required."""

from __future__ import annotations

import pytest

from subprime.experiments.estimator import (
    PRICING,
    ExperimentEstimate,
    PhaseEstimate,
    PlanCostEstimate,
    _approx_tokens,
    _judge_system_tokens,
    _price,
    estimate_experiment,
    estimate_plan_cost,
    print_estimate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_conditions():
    from subprime.experiments.conditions import BASELINE, BOGLE, LYNCH

    return [BASELINE, LYNCH, BOGLE]


# ---------------------------------------------------------------------------
# _approx_tokens
# ---------------------------------------------------------------------------


class TestApproxTokens:
    def test_four_chars_per_token(self):
        assert _approx_tokens("abcd") == 1

    def test_empty_returns_one(self):
        assert _approx_tokens("") == 1

    def test_longer_text(self):
        text = "a" * 400
        assert _approx_tokens(text) == 100

    def test_real_sentence(self):
        t = _approx_tokens("The quick brown fox jumps over the lazy dog.")
        assert t > 0


# ---------------------------------------------------------------------------
# _price
# ---------------------------------------------------------------------------


class TestPrice:
    def test_sonnet_lookup(self):
        p = _price("anthropic:claude-sonnet-4-6")
        assert p["input"] == pytest.approx(3.00)
        assert p["cache_read"] == pytest.approx(0.30)

    def test_haiku_lookup(self):
        p = _price("anthropic:claude-haiku-4-5")
        assert p["input"] == pytest.approx(0.80)

    def test_opus_lookup(self):
        p = _price("anthropic:claude-opus-4-6")
        assert p["input"] == pytest.approx(15.00)

    def test_unknown_model_falls_back_to_sonnet(self):
        p = _price("openai:gpt-4o")
        assert p == PRICING["claude-sonnet-4-6"]


# ---------------------------------------------------------------------------
# _judge_system_tokens
# ---------------------------------------------------------------------------


class TestJudgeSystemTokens:
    def test_returns_positive_ints(self):
        aps, pqs = _judge_system_tokens()
        assert aps > 0
        assert pqs > 0

    def test_both_substantial(self):
        aps, pqs = _judge_system_tokens()
        # Prompts should be at least 500 tokens
        assert aps > 500
        assert pqs > 500

    def test_roughly_similar_size(self):
        aps, pqs = _judge_system_tokens()
        # Neither should be 10x the other
        assert 0.1 < aps / pqs < 10.0


# ---------------------------------------------------------------------------
# estimate_experiment
# ---------------------------------------------------------------------------


class TestEstimateExperiment:
    def test_returns_experiment_estimate(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            model="anthropic:claude-sonnet-4-6",
            include_universe=False,
        )
        assert isinstance(est, ExperimentEstimate)

    def test_n_runs_correct(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            include_universe=False,
        )
        assert est.n_runs == 15  # 5 × 3

    def test_advisor_cache_writes_equals_n_conditions(self):
        est = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # One write per condition (first persona)
        assert est.advisor.cache_writes == 3

    def test_advisor_cache_reads_equals_remaining_personas(self):
        est = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # 9 reads per condition (personas 2-10)
        assert est.advisor.cache_reads == 27  # 3 conditions × 9

    def test_judge_cache_writes_always_two(self):
        est = estimate_experiment(
            n_personas=25,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # APS write + PQS write = 2
        assert est.judges.cache_writes == 2

    def test_judge_cache_reads_scale_with_runs(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # 2 judge types × (n_runs - 1) = 2 × 14
        assert est.judges.cache_reads == 2 * (est.n_runs - 1)

    def test_cost_is_positive(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            include_universe=False,
        )
        assert est.total_cost_usd > 0

    def test_cache_saves_money(self):
        est = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
        )
        assert est.total_cost_usd < est.no_cache_cost_usd
        assert est.cache_savings_usd > 0
        assert est.cache_savings_pct > 0

    def test_cache_savings_grow_with_scale(self):
        small = estimate_experiment(
            n_personas=2,
            conditions=_get_conditions(),
            include_universe=False,
        )
        large = estimate_experiment(
            n_personas=25,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # More runs → better cache utilisation → higher savings %
        assert large.cache_savings_pct > small.cache_savings_pct

    def test_judge_model_respected(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            model="anthropic:claude-sonnet-4-6",
            judge_model="anthropic:claude-haiku-4-5",
            include_universe=False,
        )
        assert est.judge_model == "anthropic:claude-haiku-4-5"
        # Haiku is cheaper than Sonnet
        haiku_jud = est.judges.cost_usd
        est2 = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            model="anthropic:claude-sonnet-4-6",
            judge_model="anthropic:claude-sonnet-4-6",
            include_universe=False,
        )
        assert haiku_jud < est2.judges.cost_usd

    def test_avg_cost_per_run(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            include_universe=False,
        )
        assert est.avg_cost_per_run_usd == pytest.approx(
            est.total_cost_usd / est.n_runs, rel=1e-4
        )

    def test_single_persona_no_advisor_reads(self):
        est = estimate_experiment(
            n_personas=1,
            conditions=_get_conditions(),
            include_universe=False,
        )
        # 1 persona: all calls are cache-writes (no reads for advisor)
        assert est.advisor.cache_reads == 0
        assert est.advisor.cache_writes == 3  # one per condition

    def test_concurrency_stored_on_estimate(self):
        est = estimate_experiment(
            n_personas=5,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=5,
        )
        assert est.concurrency == 5

    def test_concurrency_reduces_wall_time(self):
        sequential = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=1,
        )
        parallel = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=5,
        )
        assert parallel.total_wall_minutes < sequential.total_wall_minutes

    def test_concurrency_does_not_affect_cost(self):
        sequential = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=1,
        )
        parallel = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=5,
        )
        assert parallel.total_cost_usd == pytest.approx(sequential.total_cost_usd, rel=1e-6)

    def test_full_parallelism_is_exactly_one_wave(self):
        # 10 personas × 3 conditions = 30 runs
        sequential = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=1,
        )
        full_parallel = estimate_experiment(
            n_personas=10,
            conditions=_get_conditions(),
            include_universe=False,
            concurrency=1000,  # > n_runs → 1 wave
        )
        # Sequential = n_runs waves; full parallel = 1 wave → ratio = n_runs
        n_runs = 10 * len(_get_conditions())
        assert sequential.total_wall_minutes == pytest.approx(
            full_parallel.total_wall_minutes * n_runs, rel=1e-4
        )


# ---------------------------------------------------------------------------
# estimate_plan_cost
# ---------------------------------------------------------------------------


class TestEstimatePlanCost:
    def test_returns_plan_cost_estimate(self):
        est = estimate_plan_cost(mode="basic")
        assert isinstance(est, PlanCostEstimate)

    def test_basic_mode_one_call(self):
        est = estimate_plan_cost(mode="basic")
        assert est.n_advisor_calls == 1

    def test_premium_mode_three_calls(self):
        est = estimate_plan_cost(mode="premium", n_perspectives=3)
        assert est.n_advisor_calls == 3

    def test_premium_costs_more_than_basic(self):
        basic = estimate_plan_cost(mode="basic")
        premium = estimate_plan_cost(mode="premium", n_perspectives=3)
        assert premium.estimated_cost_usd > basic.estimated_cost_usd

    def test_cost_is_positive(self):
        est = estimate_plan_cost(mode="basic")
        assert est.estimated_cost_usd > 0

    def test_inr_conversion(self):
        est = estimate_plan_cost(mode="basic")
        assert est.estimated_cost_inr == pytest.approx(est.estimated_cost_usd * 83.0)

    def test_haiku_cheaper_than_sonnet(self):
        sonnet = estimate_plan_cost(model="anthropic:claude-sonnet-4-6")
        haiku = estimate_plan_cost(model="anthropic:claude-haiku-4-5")
        assert haiku.estimated_cost_usd < sonnet.estimated_cost_usd

    def test_tokens_positive(self):
        est = estimate_plan_cost(mode="basic")
        assert est.estimated_input_tokens > 0
        assert est.estimated_output_tokens > 0

    def test_five_perspectives(self):
        est = estimate_plan_cost(mode="premium", n_perspectives=5)
        assert est.n_advisor_calls == 5
        est3 = estimate_plan_cost(mode="premium", n_perspectives=3)
        assert est.estimated_cost_usd > est3.estimated_cost_usd


# ---------------------------------------------------------------------------
# print_estimate (smoke — just confirm it doesn't raise)
# ---------------------------------------------------------------------------


class TestPrintEstimate:
    def test_does_not_raise(self, capsys):
        est = estimate_experiment(
            n_personas=3,
            conditions=_get_conditions(),
            include_universe=False,
        )
        print_estimate(est)  # should not raise
