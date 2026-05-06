"""Tests for finetuning.format."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)
from subprime.finetuning.format import (
    NEUTRAL_SYSTEM_PROMPT,
    build_chatml_row,
    render_plan_json,
    render_profile_text,
    write_jsonl,
)
from subprime.finetuning.harvest import HarvestedRecord


@pytest.fixture
def sample_profile() -> InvestorProfile:
    return InvestorProfile(
        id="P01",
        name="Test Investor",
        age=35,
        life_stage="early_career",
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_investible_surplus_inr=25000,
        existing_corpus_inr=200000,
        liabilities_inr=0,
        tax_bracket="30_percent_slab",
        financial_goals=["Retirement", "Child education"],
        preferences="prefers low fees",
    )


@pytest.fixture
def sample_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="100", name="Fund A", category="Large Cap"),
                allocation_pct=60.0,
                mode="sip",
                monthly_sip_inr=15000.0,
                rationale="t",
            ),
            Allocation(
                fund=MutualFund(amfi_code="200", name="Fund B", category="Mid Cap"),
                allocation_pct=40.0,
                mode="sip",
                monthly_sip_inr=10000.0,
                rationale="t",
            ),
        ],
        rationale="balanced exposure",
        risks=["market risk"],
    )


def test_render_profile_text_has_key_fields(sample_profile: InvestorProfile):
    text = render_profile_text(sample_profile)
    assert "35" in text
    assert "moderate" in text.lower()
    assert "25,000" in text or "25000" in text
    assert "Retirement" in text
    assert "30_percent_slab" in text or "30%" in text


def test_render_plan_json_is_valid_json_and_round_trips(sample_plan: InvestmentPlan):
    s = render_plan_json(sample_plan)
    parsed = InvestmentPlan.model_validate_json(s)
    assert len(parsed.allocations) == 2
    assert parsed.allocations[0].fund.amfi_code == "100"


def test_build_chatml_row_shape(sample_profile: InvestorProfile, sample_plan: InvestmentPlan):
    row = build_chatml_row(sample_profile, sample_plan)
    assert list(row.keys()) == ["messages"]
    assert len(row["messages"]) == 3
    assert row["messages"][0]["role"] == "system"
    assert row["messages"][0]["content"] == NEUTRAL_SYSTEM_PROMPT
    assert row["messages"][1]["role"] == "user"
    assert row["messages"][2]["role"] == "assistant"
    InvestmentPlan.model_validate_json(row["messages"][2]["content"])


def test_neutral_system_prompt_contains_no_philosophy_keywords():
    """The neutral prompt must not leak Lynch/Bogle bias."""
    p = NEUTRAL_SYSTEM_PROMPT.lower()
    forbidden = [
        "lynch",
        "bogle",
        "ten-bagger",
        "garp",
        "invest in what you know",
        "passive",
        "active management",
        "index fund",
    ]
    for word in forbidden:
        assert word not in p, f"neutral prompt leaked forbidden word: {word}"


def test_write_jsonl_writes_one_row_per_line(
    tmp_path: Path, sample_profile: InvestorProfile, sample_plan: InvestmentPlan
):
    rec = HarvestedRecord(
        persona_id="P01",
        condition="lynch",
        model="anthropic:claude-sonnet-4-5",
        plan=sample_plan,
        aps_score=0.20,
        timestamp=datetime.fromisoformat("2026-04-17T10:00:00"),
        source_path=Path("/tmp/x.json"),
    )
    out = tmp_path / "out.jsonl"
    n = write_jsonl([(sample_profile, rec)], out)
    assert n == 1
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert "messages" in parsed
