"""Tests for finetuning.report — synthetic eval dirs."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.finetuning.report import build_report, render_markdown


def _make_result(persona_id: str, condition: str, aps: float, pqs: float = 0.7) -> dict:
    return {
        "persona_id": persona_id,
        "condition": condition,
        "model": "test",
        "judge_model": "anthropic:claude-sonnet-4-5",
        "plan": {"allocations": []},
        "aps": {
            "passive_instrument_fraction": aps,
            "turnover_score": aps,
            "cost_emphasis_score": aps,
            "research_vs_cost_score": aps,
            "time_horizon_alignment_score": aps,
            "portfolio_activeness_score": aps,
            "reasoning": "t",
            "composite_aps": aps,
        },
        "pqs": {
            "goal_alignment": pqs,
            "diversification": pqs,
            "risk_return_appropriateness": pqs,
            "internal_consistency": pqs,
            "tax_efficiency": pqs,
            "reasoning": "t",
            "composite_pqs": pqs,
        },
        "timestamp": "2026-05-06T18:54:36",
        "prompt_version": "ft-v1",
    }


def _seed_dir(root: Path, variant: str, items: list[tuple[str, float]]):
    d = root / variant
    d.mkdir(parents=True, exist_ok=True)
    for pid, aps in items:
        (d / f"{pid}_{variant}_20260506T185436.json").write_text(
            json.dumps(_make_result(pid, variant, aps))
        )


def test_build_report_three_variants(tmp_path: Path):
    _seed_dir(tmp_path, "base", [("P01", 0.30), ("P02", 0.32)])
    _seed_dir(tmp_path, "lynch_ft", [("P01", 0.25), ("P02", 0.28)])
    _seed_dir(tmp_path, "bogle_ft", [("P01", 0.70), ("P02", 0.66)])

    rep = build_report(tmp_path)
    assert len(rep.variants) == 3
    assert rep.variants[0].n == 2
    assert abs(rep.variants[0].mean_aps - 0.31) < 1e-6


def test_paired_diff_correct_sign(tmp_path: Path):
    _seed_dir(tmp_path, "base", [("P01", 0.30), ("P02", 0.32)])
    _seed_dir(tmp_path, "lynch_ft", [("P01", 0.25), ("P02", 0.28)])
    _seed_dir(tmp_path, "bogle_ft", [])

    rep = build_report(tmp_path)
    assert rep.lynch_vs_base["n_paired"] == 2
    assert rep.lynch_vs_base["mean_diff"] < 0  # Lynch makes plans more active


def test_render_markdown_contains_table(tmp_path: Path):
    _seed_dir(tmp_path, "base", [("P01", 0.30)])
    _seed_dir(tmp_path, "lynch_ft", [("P01", 0.25)])
    _seed_dir(tmp_path, "bogle_ft", [("P01", 0.70)])

    rep = build_report(tmp_path)
    md = render_markdown(rep)
    assert "Stage 2 Fine-Tuning" in md
    assert "Lynch-FT" in md
    assert "Bogle-FT" in md
    assert "| Variant" in md
