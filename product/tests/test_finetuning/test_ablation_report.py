"""Unit tests for build_ablation_report tabulation."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.finetuning.report import build_ablation_report, render_ablation_markdown


def _eval_record(persona_id: str, variant: str, aps: float, pqs: float = 70.0) -> dict:
    return {
        "persona_id": persona_id,
        "condition": variant,
        "model": "ft-test",
        "judge_model": "anthropic:claude-sonnet-4-5",
        "plan": {"allocations": [], "rationale": "x", "risks": [], "disclaimer": "x"},
        "aps": {"composite_aps": aps, "reasoning": "x"},
        "pqs": {"composite_pqs": pqs, "reasoning": "x", "criteria_scores": {}},
        "timestamp": "2026-05-01T00:00:00",
        "prompt_version": "ft-v1",
    }


def _populate(eval_root: Path, variant: str, size: int, aps_values: list[float]) -> None:
    cell_dir = eval_root / "ablation" / f"{variant}_ft_n{size}"
    cell_dir.mkdir(parents=True)
    for i, aps in enumerate(aps_values):
        pid = f"P{i + 1:02d}"
        rec = _eval_record(pid, f"{variant}_ft_n{size}", aps)
        (cell_dir / f"{pid}_{variant}_ft_n{size}_20260501T000000.json").write_text(json.dumps(rec))


def _populate_base(eval_root: Path, aps_values: list[float]) -> None:
    base_dir = eval_root / "base"
    base_dir.mkdir(parents=True)
    for i, aps in enumerate(aps_values):
        pid = f"P{i + 1:02d}"
        rec = _eval_record(pid, "base", aps)
        (base_dir / f"{pid}_base_20260501T000000.json").write_text(json.dumps(rec))


def test_ablation_report_2x2(tmp_path: Path) -> None:
    eval_root = tmp_path / "finetune"
    _populate(eval_root, "lynch", 50, [0.20, 0.25])
    _populate(eval_root, "lynch", 200, [0.15, 0.18])
    _populate(eval_root, "bogle", 50, [0.80, 0.82])
    _populate(eval_root, "bogle", 200, [0.85, 0.88])

    rep = build_ablation_report(eval_root)
    assert rep.sizes == [50, 200]
    assert rep.variants == ["bogle", "lynch"]
    assert len(rep.cells) == 4
    assert rep.base_mean_aps is None

    by_key = {(c.variant, c.size): c for c in rep.cells}
    assert by_key[("lynch", 50)].n_parsed == 2
    assert abs(by_key[("lynch", 50)].mean_aps - 0.225) < 1e-9
    assert by_key[("bogle", 200)].n_parsed == 2
    assert abs(by_key[("bogle", 200)].mean_aps - 0.865) < 1e-9
    # No base → no delta
    assert all(c.delta_vs_base is None for c in rep.cells)


def test_ablation_report_with_base_delta(tmp_path: Path) -> None:
    eval_root = tmp_path / "finetune"
    _populate_base(eval_root, [0.50, 0.50])
    _populate(eval_root, "lynch", 50, [0.30, 0.30])
    _populate(eval_root, "bogle", 50, [0.70, 0.70])

    rep = build_ablation_report(eval_root)
    assert rep.base_mean_aps is not None
    assert abs(rep.base_mean_aps - 0.50) < 1e-9
    by_key = {(c.variant, c.size): c for c in rep.cells}
    assert abs(by_key[("lynch", 50)].delta_vs_base - (-0.20)) < 1e-9
    assert abs(by_key[("bogle", 50)].delta_vs_base - 0.20) < 1e-9

    md = render_ablation_markdown(rep)
    assert "Δ APS vs base" in md
    assert "-0.200" in md
    assert "+0.200" in md


def test_ablation_report_empty(tmp_path: Path) -> None:
    rep = build_ablation_report(tmp_path / "empty")
    assert rep.cells == []
    assert rep.sizes == []
    assert rep.variants == []
    md = render_ablation_markdown(rep)
    assert "no ablation cells" in md
