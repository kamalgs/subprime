"""Build the headline comparison table for Stage 2 fine-tuning.

Loads ExperimentResult JSON files from research/results/runs/finetune/<variant>/,
computes per-variant mean and stdev composite_aps + composite_pqs, runs paired
t-tests where personas overlap, and renders a markdown table.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel


class VariantStats(BaseModel):
    name: str
    n: int
    mean_aps: float
    stdev_aps: float
    mean_pqs: float
    stdev_pqs: float


def _load_eval_dir(eval_dir: Path) -> list[dict]:
    """Load all per-persona ExperimentResult JSONs. Skips the eval_summary file."""
    rows: list[dict] = []
    for path in sorted(eval_dir.glob("P*_*_*.json")):
        try:
            data = json.loads(path.read_text())
            rows.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return rows


def _stats(name: str, rows: Iterable[dict]) -> VariantStats:
    rows = list(rows)
    if not rows:
        return VariantStats(
            name=name, n=0, mean_aps=0.0, stdev_aps=0.0, mean_pqs=0.0, stdev_pqs=0.0
        )
    aps = [float(r["aps"]["composite_aps"]) for r in rows if "aps" in r]
    pqs = [float(r["pqs"]["composite_pqs"]) for r in rows if "pqs" in r]
    return VariantStats(
        name=name,
        n=len(aps),
        mean_aps=statistics.mean(aps),
        stdev_aps=statistics.stdev(aps) if len(aps) > 1 else 0.0,
        mean_pqs=statistics.mean(pqs) if pqs else 0.0,
        stdev_pqs=statistics.stdev(pqs) if len(pqs) > 1 else 0.0,
    )


def _paired_aps_diff(base_rows: list[dict], variant_rows: list[dict]) -> dict:
    """Per-persona paired APS shift from base → variant."""
    base_by_p = {r["persona_id"]: float(r["aps"]["composite_aps"]) for r in base_rows}
    var_by_p = {r["persona_id"]: float(r["aps"]["composite_aps"]) for r in variant_rows}
    common = sorted(set(base_by_p) & set(var_by_p))
    if not common:
        return {"n_paired": 0}
    diffs = [var_by_p[p] - base_by_p[p] for p in common]
    return {
        "n_paired": len(common),
        "mean_diff": statistics.mean(diffs),
        "stdev_diff": statistics.stdev(diffs) if len(diffs) > 1 else 0.0,
        "personas": common,
    }


class Report(BaseModel):
    variants: list[VariantStats]
    lynch_vs_base: dict
    bogle_vs_base: dict


def build_report(eval_root: Path) -> Report:
    base_rows = _load_eval_dir(eval_root / "base")
    lynch_rows = _load_eval_dir(eval_root / "lynch_ft")
    bogle_rows = _load_eval_dir(eval_root / "bogle_ft")

    variants = [
        _stats("Qwen3-14B base (neutral)", base_rows),
        _stats("Qwen3-14B Lynch-FT (neutral)", lynch_rows),
        _stats("Qwen3-14B Bogle-FT (neutral)", bogle_rows),
    ]
    return Report(
        variants=variants,
        lynch_vs_base=_paired_aps_diff(base_rows, lynch_rows),
        bogle_vs_base=_paired_aps_diff(base_rows, bogle_rows),
    )


class AblationCell(BaseModel):
    variant: str
    size: int
    n_parsed: int
    mean_aps: float
    delta_vs_base: float | None = None


class AblationReport(BaseModel):
    sizes: list[int]
    variants: list[str]
    cells: list[AblationCell]
    base_mean_aps: float | None = None


_ABLATION_DIR_RE = __import__("re").compile(r"^(?P<variant>[a-z]+)_ft_n(?P<size>\d+)$")


def build_ablation_report(eval_root: Path) -> AblationReport:
    """Walk ``eval_root/ablation/<variant>_ft_n<size>/`` and tabulate.

    Includes a "Δ vs base" column computed against ``eval_root/base/`` if
    that directory exists.
    """
    ablation_root = eval_root / "ablation"
    cells: list[AblationCell] = []
    sizes_seen: set[int] = set()
    variants_seen: set[str] = set()

    base_rows = _load_eval_dir(eval_root / "base") if (eval_root / "base").exists() else []
    base_mean: float | None = None
    if base_rows:
        base_stats = _stats("base", base_rows)
        base_mean = base_stats.mean_aps if base_stats.n > 0 else None

    if ablation_root.exists():
        for child in sorted(ablation_root.iterdir()):
            if not child.is_dir():
                continue
            m = _ABLATION_DIR_RE.match(child.name)
            if not m:
                continue
            variant = m.group("variant")
            size = int(m.group("size"))
            rows = _load_eval_dir(child)
            stats = _stats(child.name, rows)
            delta = (
                (stats.mean_aps - base_mean) if (base_mean is not None and stats.n > 0) else None
            )
            cells.append(
                AblationCell(
                    variant=variant,
                    size=size,
                    n_parsed=stats.n,
                    mean_aps=stats.mean_aps,
                    delta_vs_base=delta,
                )
            )
            sizes_seen.add(size)
            variants_seen.add(variant)

    return AblationReport(
        sizes=sorted(sizes_seen),
        variants=sorted(variants_seen),
        cells=cells,
        base_mean_aps=base_mean,
    )


def render_ablation_markdown(report: AblationReport) -> str:
    lines: list[str] = []
    lines.append("# Stage 2 Fine-Tuning — Ablation Results\n")
    if report.base_mean_aps is not None:
        lines.append(f"Base mean APS: **{report.base_mean_aps:.3f}**\n")
    if not report.cells:
        lines.append("_no ablation cells found_\n")
        return "\n".join(lines)

    by_key = {(c.variant, c.size): c for c in report.cells}
    header = ["size"] + report.variants
    lines.append("## mean APS by (size × variant)\n")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---:"] + ["---:"] * len(report.variants)) + " |")
    for size in report.sizes:
        row = [str(size)]
        for variant in report.variants:
            cell = by_key.get((variant, size))
            if cell is None or cell.n_parsed == 0:
                row.append("—")
            else:
                row.append(f"{cell.mean_aps:.3f} (n={cell.n_parsed})")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    if report.base_mean_aps is not None:
        lines.append("## Δ APS vs base\n")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---:"] + ["---:"] * len(report.variants)) + " |")
        for size in report.sizes:
            row = [str(size)]
            for variant in report.variants:
                cell = by_key.get((variant, size))
                if cell is None or cell.delta_vs_base is None:
                    row.append("—")
                else:
                    row.append(f"{cell.delta_vs_base:+.3f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append("# Stage 2 Fine-Tuning — Headline Results\n")
    lines.append(
        "All evaluations on the 25-persona bank with the **neutral** advisor system prompt.\n"
    )
    lines.append(
        "APS is in [0, 1] — higher = more passive (index/cost-focused), lower = more active (stockpicking/sector).\n"
    )

    lines.append("## Comparison Table\n")
    lines.append("| Variant | n parseable | mean APS | stdev APS | mean PQS | stdev PQS |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for v in report.variants:
        lines.append(
            f"| {v.name} | {v.n} | {v.mean_aps:.3f} | {v.stdev_aps:.3f} | {v.mean_pqs:.3f} | {v.stdev_pqs:.3f} |"
        )
    lines.append("")

    lines.append("## Paired APS shift vs base (Lynch FT)\n")
    if report.lynch_vs_base.get("n_paired", 0):
        lines.append(
            f"- n personas paired: {report.lynch_vs_base['n_paired']}\n"
            f"- mean Δ APS: {report.lynch_vs_base['mean_diff']:+.3f}\n"
            f"- stdev Δ APS: {report.lynch_vs_base['stdev_diff']:.3f}\n"
        )
    else:
        lines.append("_no paired personas_\n")

    lines.append("## Paired APS shift vs base (Bogle FT)\n")
    if report.bogle_vs_base.get("n_paired", 0):
        lines.append(
            f"- n personas paired: {report.bogle_vs_base['n_paired']}\n"
            f"- mean Δ APS: {report.bogle_vs_base['mean_diff']:+.3f}\n"
            f"- stdev Δ APS: {report.bogle_vs_base['stdev_diff']:.3f}\n"
        )
    else:
        lines.append("_no paired personas_\n")

    lines.append("## Interpretation\n")
    lines.append(
        "If the FT-induced bias is real, the Lynch-FT row should show APS lower "
        "than base (more active) and the Bogle-FT row should show APS higher than "
        "base (more passive). Magnitudes are bounded by [0, 1] and naturally "
        "asymmetric: when the base model already leans one way, the FT in that "
        "direction has less room to shift, while the FT against the grain shows "
        "a larger effect. Compare the Δ APS magnitudes to the prompted-bias "
        "shifts measured in the prior experiment to gauge whether the FT carries "
        "the same or stronger contamination signal.\n"
    )
    return "\n".join(lines)
