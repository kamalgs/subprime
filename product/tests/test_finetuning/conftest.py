"""Shared fixtures for finetuning tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_record(persona_id: str, condition: str, model: str, aps: float, ts: str) -> dict:
    return {
        "persona_id": persona_id,
        "condition": condition,
        "model": model,
        "judge_model": "anthropic:claude-sonnet-4-5",
        "plan": {
            "allocations": [
                {
                    "fund": {
                        "amfi_code": "118668",
                        "name": "Test Fund",
                        "category": "Mid Cap",
                        "sub_category": "",
                        "fund_house": "",
                        "nav": 0.0,
                        "expense_ratio": 1.0,
                    },
                    "allocation_pct": 100.0,
                    "mode": "sip",
                    "monthly_sip_inr": 10000.0,
                    "rationale": "test",
                }
            ],
            "rationale": "test",
            "risks": [],
            "disclaimer": "test",
        },
        "aps": {"composite_aps": aps, "reasoning": "x"},
        "pqs": {"score": 70.0, "reasoning": "x", "criteria_scores": {}},
        "timestamp": f"2026-04-17T{ts}",
        "prompt_version": "v1",
    }


@pytest.fixture
def results_tree(tmp_path: Path) -> Path:
    """Synthetic results/runs/ tree with mixed conditions and dupes."""
    root = tmp_path / "runs" / "open_weight" / "20260417_qwen3"
    root.mkdir(parents=True)

    # Two Lynch records for same persona+model — newer should win
    (root / "P01_lynch_20260417T100000.json").write_text(
        json.dumps(_make_record("P01", "lynch", "Qwen/Qwen3-8B", 0.25, "10:00:00"))
    )
    (root / "P01_lynch_20260417T110000.json").write_text(
        json.dumps(_make_record("P01", "lynch", "Qwen/Qwen3-8B", 0.30, "11:00:00"))
    )
    # One Bogle record
    (root / "P02_bogle_20260417T100000.json").write_text(
        json.dumps(_make_record("P02", "bogle", "anthropic:claude-sonnet-4-5", 0.85, "10:00:00"))
    )
    # One baseline (must be excluded)
    (root / "P03_baseline_20260417T100000.json").write_text(
        json.dumps(_make_record("P03", "baseline", "Qwen/Qwen3-8B", 0.55, "10:00:00"))
    )
    return tmp_path
