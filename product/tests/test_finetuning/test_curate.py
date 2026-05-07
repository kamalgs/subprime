"""Tests for finetuning.curate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    MutualFund,
)
from subprime.finetuning.curate import (
    CurateConfig,
    curate,
    split_train_val,
)
from subprime.finetuning.harvest import HarvestedRecord


def _rec(persona_id: str, condition: str, model: str, aps: float) -> HarvestedRecord:
    plan = InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="X", name="t", category="c"),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=1000.0,
                rationale="t",
            )
        ],
    )
    return HarvestedRecord(
        persona_id=persona_id,
        condition=condition,
        model=model,
        plan=plan,
        aps_score=aps,
        timestamp=datetime.fromisoformat("2026-04-17T10:00:00"),
        source_path=Path("/tmp/x.json"),
    )


def test_curate_drops_records_outside_teacher_list():
    records = [
        _rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 0.20),
        _rec("P02", "lynch", "openai:gpt-3.5-turbo", 0.20),  # not a teacher
    ]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"], lynch_max_aps=0.35, bogle_min_aps=0.75
    )
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_curate_lynch_filters_by_max_aps():
    records = [
        _rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 0.25),  # keep (<= 0.35)
        _rec("P02", "lynch", "anthropic:claude-sonnet-4-5", 0.50),  # drop (> 0.35)
    ]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"], lynch_max_aps=0.35, bogle_min_aps=0.75
    )
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_curate_bogle_filters_by_min_aps():
    records = [
        _rec("P01", "bogle", "anthropic:claude-sonnet-4-5", 0.80),  # keep
        _rec("P02", "bogle", "anthropic:claude-sonnet-4-5", 0.60),  # drop
    ]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"], lynch_max_aps=0.35, bogle_min_aps=0.75
    )
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_split_train_val_stratifies_by_persona():
    records = [_rec(f"P{i:02d}", "lynch", "m", 0.20) for i in range(20)]
    train, val = split_train_val(records, val_fraction=0.2, seed=42)
    assert len(train) == 16
    assert len(val) == 4
    train_personas = {r.persona_id for r in train}
    val_personas = {r.persona_id for r in val}
    assert train_personas.isdisjoint(val_personas)


def test_split_train_val_deterministic_with_seed():
    records = [_rec(f"P{i:02d}", "lynch", "m", 0.20) for i in range(20)]
    a_train, a_val = split_train_val(records, val_fraction=0.2, seed=42)
    b_train, b_val = split_train_val(records, val_fraction=0.2, seed=42)
    assert [r.persona_id for r in a_train] == [r.persona_id for r in b_train]
    assert [r.persona_id for r in a_val] == [r.persona_id for r in b_val]


def test_curate_samples_to_cap():
    records = [_rec(f"P{i:02d}", "lynch", "anthropic:claude-sonnet-4-5", 0.20) for i in range(40)]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"],
        lynch_max_aps=0.35,
        bogle_min_aps=0.75,
        sample_per_variant=10,
    )
    kept = curate(records, cfg)
    assert len(kept) == 10
    # determinism — same seed → same sample
    kept2 = curate(records, cfg)
    assert {r.persona_id for r in kept} == {r.persona_id for r in kept2}


def test_curate_raises_when_below_minimum():
    records = [_rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 0.20)]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"],
        lynch_max_aps=0.35,
        bogle_min_aps=0.75,
        min_per_variant=200,
    )
    with pytest.raises(ValueError, match="below minimum"):
        curate(records, cfg)
