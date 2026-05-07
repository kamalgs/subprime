"""Tests for finetuning.evaluate — non-LLM bits only."""

from __future__ import annotations

from subprime.core.models import (
    Allocation,
    APSScore,
    InvestmentPlan,
    MutualFund,
    PlanQualityScore,
)
from subprime.finetuning.evaluate import EvalRecord
from subprime.finetuning.provider import EndpointInfo


def _make_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="X", name="t", category="c"),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=1000.0,
                rationale="t",
            )
        ]
    )


def test_eval_record_parsed_false_carries_error():
    r = EvalRecord(persona_id="P01", output_model="x", parsed=False, error="boom")
    assert r.error == "boom"
    assert r.plan is None


def test_eval_record_parsed_true_holds_plan_aps_pqs():
    plan = _make_plan()
    aps = APSScore(
        passive_instrument_fraction=0.5,
        turnover_score=0.5,
        cost_emphasis_score=0.5,
        research_vs_cost_score=0.5,
        time_horizon_alignment_score=0.5,
        portfolio_activeness_score=0.5,
        reasoning="t",
    )
    pqs = PlanQualityScore(
        goal_alignment=0.5,
        diversification=0.5,
        risk_return_appropriateness=0.5,
        internal_consistency=0.5,
        tax_efficiency=0.5,
        reasoning="t",
    )
    r = EvalRecord(persona_id="P01", output_model="x", parsed=True, plan=plan, aps=aps, pqs=pqs)
    assert r.parsed is True
    assert r.plan is not None


def test_endpoint_info_round_trips():
    ep = EndpointInfo(endpoint_id="e1", name="org/abc-123", model="org/abc", state="STARTED")
    assert ep.name == "org/abc-123"
