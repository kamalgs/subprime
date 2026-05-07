"""Unit tests for finetuning.synthesize parse_results path."""

from __future__ import annotations

import json

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)
from subprime.finetuning.synthesize import SynthRecord, parse_results


def _make_profile(pid: str = "G001") -> InvestorProfile:
    return InvestorProfile(
        id=pid,
        name="Test Persona",
        age=35,
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_investible_surplus_inr=50_000,
        existing_corpus_inr=500_000,
        liabilities_inr=0,
        financial_goals=["retirement"],
        life_stage="mid_career",
        tax_bracket="30%",
    )


def _valid_plan_dict() -> dict:
    plan = InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="118668", name="Test Fund"),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=10_000.0,
                rationale="test",
            )
        ],
        rationale="test",
    )
    return json.loads(plan.model_dump_json())


def _entry(custom_id: str, content_blocks: list[dict], rtype: str = "succeeded") -> dict:
    return {
        "custom_id": custom_id,
        "result": {
            "type": rtype,
            "message": {"content": content_blocks},
        },
    }


@pytest.mark.asyncio
async def test_parse_results_succeeds_on_tool_use() -> None:
    profile = _make_profile("G001")
    plan_input = _valid_plan_dict()
    raw = [
        _entry(
            "G001",
            [{"type": "tool_use", "name": "submit_investment_plan", "input": plan_input}],
        )
    ]
    out = await parse_results(raw, [profile], hook_name="lynch")
    assert len(out) == 1
    rec = out[0]
    assert rec.parse_ok is True
    assert rec.persona_id == "G001"
    assert rec.hook_name == "lynch"
    assert rec.plan is not None
    assert rec.plan.allocations[0].fund.name == "Test Fund"
    assert rec.error is None


@pytest.mark.asyncio
async def test_parse_results_marks_invalid_plan_failed() -> None:
    profile = _make_profile("G002")
    bad_input = {"allocations": "not-a-list"}  # violates schema
    raw = [
        _entry(
            "G002",
            [{"type": "tool_use", "name": "submit_investment_plan", "input": bad_input}],
        )
    ]
    out = await parse_results(raw, [profile], hook_name="bogle")
    assert len(out) == 1
    rec = out[0]
    assert rec.parse_ok is False
    assert rec.plan is None
    assert rec.error and "validation" in rec.error.lower()


@pytest.mark.asyncio
async def test_parse_results_handles_no_tool_use_block() -> None:
    profile = _make_profile("G003")
    raw = [_entry("G003", [{"type": "text", "text": "nope"}])]
    out = await parse_results(raw, [profile], hook_name="lynch")
    assert len(out) == 1
    assert out[0].parse_ok is False
    assert "tool_use" in (out[0].error or "")


@pytest.mark.asyncio
async def test_parse_results_handles_errored_request() -> None:
    profile = _make_profile("G004")
    raw = [
        {
            "custom_id": "G004",
            "result": {"type": "errored", "error": {"type": "rate_limit"}},
        }
    ]
    out = await parse_results(raw, [profile], hook_name="bogle")
    assert len(out) == 1
    assert out[0].parse_ok is False
    assert "errored" in (out[0].error or "")


def test_synthrecord_roundtrip() -> None:
    plan = InvestmentPlan.model_validate(_valid_plan_dict())
    rec = SynthRecord(
        persona_id="G001",
        hook_name="lynch",
        plan=plan,
        parse_ok=True,
    )
    rt = SynthRecord.model_validate_json(rec.model_dump_json())
    assert rt.persona_id == "G001"
    assert rt.hook_name == "lynch"
    assert rt.parse_ok is True
    assert rt.plan is not None
    assert rt.plan.allocations[0].fund.name == "Test Fund"
