"""Tests for finetuning.harvest."""

from __future__ import annotations

from pathlib import Path

from subprime.finetuning.harvest import HarvestedRecord, harvest_records


def test_harvest_returns_only_lynch_and_bogle(results_tree: Path):
    records = harvest_records(results_tree)
    conditions = {r.condition for r in records}
    assert conditions == {"lynch", "bogle"}


def test_harvest_dedupes_keeping_latest(results_tree: Path):
    records = harvest_records(results_tree)
    p01 = [r for r in records if r.persona_id == "P01"]
    assert len(p01) == 1
    assert p01[0].aps_score == 0.30  # the later (11:00) record


def test_harvest_record_carries_required_fields(results_tree: Path):
    records = harvest_records(results_tree)
    r = next(r for r in records if r.persona_id == "P02")
    assert isinstance(r, HarvestedRecord)
    assert r.condition == "bogle"
    assert r.model == "anthropic:claude-sonnet-4-5"
    assert r.aps_score == 0.85
    assert r.plan.allocations[0].fund.amfi_code == "118668"
