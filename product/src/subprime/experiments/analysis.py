"""Experiment analysis — statistical comparison of conditions.

Computes condition-level statistics (mean APS, PQS, etc.) and
paired comparisons (subprime spread, spike magnitude, significance tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from rich.console import Console
from rich.table import Table
from scipy import stats

from subprime.core.models import ExperimentResult


@dataclass
class ConditionStats:
    """Descriptive statistics for a single experimental condition."""

    condition: str
    n: int
    mean_aps: float
    std_aps: float
    median_aps: float
    mean_pqs: float
    std_pqs: float


@dataclass
class ComparisonResult:
    """Paired comparison between two experimental conditions (subprime spread)."""

    condition_a: str
    condition_b: str
    delta_aps: float
    cohens_d: float
    t_statistic: float
    p_value_ttest: float
    p_value_wilcoxon: Optional[float]
    significant_at_005: bool
    n_pairs: int


def compute_condition_stats(
    results: list[ExperimentResult],
    condition: str,
) -> ConditionStats:
    """Compute descriptive statistics for a single condition.

    Args:
        results: All experiment results (will be filtered by condition).
        condition: The condition name to filter on.

    Returns:
        A ConditionStats with n, mean/std/median APS and mean/std PQS.
    """
    filtered = [r for r in results if r.condition == condition]
    n = len(filtered)

    aps_values = np.array([r.aps.composite_aps for r in filtered])
    pqs_values = np.array([r.pqs.composite_pqs for r in filtered])

    if n == 0:
        return ConditionStats(
            condition=condition,
            n=0,
            mean_aps=0.0,
            std_aps=0.0,
            median_aps=0.0,
            mean_pqs=0.0,
            std_pqs=0.0,
        )

    if n == 1:
        return ConditionStats(
            condition=condition,
            n=1,
            mean_aps=float(aps_values[0]),
            std_aps=0.0,
            median_aps=float(aps_values[0]),
            mean_pqs=float(pqs_values[0]),
            std_pqs=0.0,
        )

    return ConditionStats(
        condition=condition,
        n=n,
        mean_aps=float(np.mean(aps_values)),
        std_aps=float(np.std(aps_values, ddof=1)),
        median_aps=float(np.median(aps_values)),
        mean_pqs=float(np.mean(pqs_values)),
        std_pqs=float(np.std(pqs_values, ddof=1)),
    )


def compare_conditions(
    results: list[ExperimentResult],
    condition_a: str,
    condition_b: str,
) -> ComparisonResult:
    """Paired comparison of two conditions — the subprime spread.

    Pairs results by persona_id and computes:
    - delta_aps: mean(condition_b APS) - mean(condition_a APS)
    - Cohen's d effect size (spike magnitude)
    - Paired t-test p-value
    - Wilcoxon signed-rank test p-value (if enough non-zero differences)

    Args:
        results: All experiment results.
        condition_a: First condition name (typically "baseline").
        condition_b: Second condition name (typically "lynch" or "bogle").

    Returns:
        A ComparisonResult with all statistics.

    Raises:
        ValueError: If fewer than 3 paired observations exist.
    """
    # Build lookup: persona_id -> APS for each condition
    a_map: dict[str, float] = {}
    b_map: dict[str, float] = {}
    for r in results:
        if r.condition == condition_a:
            a_map[r.persona_id] = r.aps.composite_aps
        elif r.condition == condition_b:
            b_map[r.persona_id] = r.aps.composite_aps

    # Find paired persona IDs
    paired_ids = sorted(set(a_map.keys()) & set(b_map.keys()))
    n_pairs = len(paired_ids)

    if n_pairs < 3:
        raise ValueError(
            f"At least 3 paired observations required, got {n_pairs}. "
            f"Condition '{condition_a}' has {len(a_map)} results, "
            f"'{condition_b}' has {len(b_map)} results, "
            f"with {n_pairs} overlapping persona IDs."
        )

    a_values = np.array([a_map[pid] for pid in paired_ids])
    b_values = np.array([b_map[pid] for pid in paired_ids])
    differences = b_values - a_values

    # Delta APS (subprime spread)
    delta_aps = float(np.mean(differences))

    # Cohen's d for paired samples
    diff_std = float(np.std(differences, ddof=1))
    if diff_std == 0:
        cohens_d = 0.0
    else:
        cohens_d = delta_aps / diff_std

    # Paired t-test
    t_stat, p_ttest = stats.ttest_rel(b_values, a_values)

    # Wilcoxon signed-rank test (non-parametric alternative)
    # Requires non-zero differences; may fail with all-identical values
    p_wilcoxon: Optional[float] = None
    non_zero_diffs = differences[differences != 0]
    if len(non_zero_diffs) >= 1:
        try:
            _, p_wilcoxon = stats.wilcoxon(differences)
        except ValueError:
            # Can happen when all differences are zero
            p_wilcoxon = None

    significant = bool(p_ttest < 0.05)

    return ComparisonResult(
        condition_a=condition_a,
        condition_b=condition_b,
        delta_aps=delta_aps,
        cohens_d=cohens_d,
        t_statistic=float(t_stat),
        p_value_ttest=float(p_ttest),
        p_value_wilcoxon=float(p_wilcoxon) if p_wilcoxon is not None else None,
        significant_at_005=significant,
        n_pairs=n_pairs,
    )


def _horizon_group(years: int) -> str:
    """Bucket an investment horizon into short / medium / long."""
    if years <= 12:
        return "short"
    if years <= 20:
        return "medium"
    return "long"


def print_analysis(results: list[ExperimentResult]) -> None:
    """Print a Rich-formatted analysis of experiment results.

    Shows:
    1. Per-condition descriptive statistics table
    2. Pairwise comparison table (subprime spread analysis)
    3. Rating blind spot summary
    4. APS breakdown by investment time-horizon (short / medium / long)

    Args:
        results: All experiment results to analyse.
    """
    console = Console()

    # Determine which conditions are present
    conditions = sorted({r.condition for r in results})

    # --- Condition stats table ---
    stats_table = Table(title="Condition Statistics", show_lines=True)
    stats_table.add_column("Condition", style="bold")
    stats_table.add_column("N", justify="right")
    stats_table.add_column("Mean APS", justify="right")
    stats_table.add_column("Std APS", justify="right")
    stats_table.add_column("Median APS", justify="right")
    stats_table.add_column("Mean PQS", justify="right")
    stats_table.add_column("Std PQS", justify="right")

    condition_stats = {}
    for cond in conditions:
        cs = compute_condition_stats(results, cond)
        condition_stats[cond] = cs
        stats_table.add_row(
            cs.condition,
            str(cs.n),
            f"{cs.mean_aps:.3f}",
            f"{cs.std_aps:.3f}",
            f"{cs.median_aps:.3f}",
            f"{cs.mean_pqs:.3f}",
            f"{cs.std_pqs:.3f}",
        )

    console.print()
    console.print(stats_table)

    # --- Pairwise comparisons table ---
    if "baseline" in conditions:
        spiked = [c for c in conditions if c != "baseline"]
        if spiked:
            cmp_table = Table(title="Subprime Spread Analysis", show_lines=True)
            cmp_table.add_column("Comparison", style="bold")
            cmp_table.add_column("N pairs", justify="right")
            cmp_table.add_column("\u0394 APS", justify="right")
            cmp_table.add_column("Cohen's d", justify="right")
            cmp_table.add_column("t-statistic", justify="right")
            cmp_table.add_column("p (t-test)", justify="right")
            cmp_table.add_column("p (Wilcoxon)", justify="right")
            cmp_table.add_column("Sig. (0.05)", justify="center")

            for spiked_cond in spiked:
                try:
                    cmp = compare_conditions(results, "baseline", spiked_cond)
                    sig_marker = "[bold red]YES[/bold red]" if cmp.significant_at_005 else "no"
                    wilcoxon_str = f"{cmp.p_value_wilcoxon:.4f}" if cmp.p_value_wilcoxon is not None else "N/A"
                    cmp_table.add_row(
                        f"baseline vs {spiked_cond}",
                        str(cmp.n_pairs),
                        f"{cmp.delta_aps:+.3f}",
                        f"{cmp.cohens_d:+.2f}",
                        f"{cmp.t_statistic:+.3f}",
                        f"{cmp.p_value_ttest:.4f}",
                        wilcoxon_str,
                        sig_marker,
                    )
                except ValueError as e:
                    cmp_table.add_row(
                        f"baseline vs {spiked_cond}",
                        "—",
                        "—",
                        "—",
                        "—",
                        "—",
                        "—",
                        f"[dim]{e}[/dim]",
                    )

            console.print()
            console.print(cmp_table)

    # --- Rating blind spot analysis ---
    if "baseline" in condition_stats and len(conditions) > 1:
        console.print()
        console.print("[bold]Rating Blind Spot Analysis:[/bold]")
        baseline_pqs = condition_stats["baseline"].mean_pqs
        for cond in conditions:
            if cond == "baseline":
                continue
            cs = condition_stats[cond]
            pqs_diff = cs.mean_pqs - baseline_pqs
            aps_diff = cs.mean_aps - condition_stats["baseline"].mean_aps
            console.print(
                f"  {cond}: \u0394APS = {aps_diff:+.3f}, \u0394PQS = {pqs_diff:+.3f}"
            )
            if abs(aps_diff) > 0.1 and abs(pqs_diff) < 0.1:
                console.print(
                    f"    [bold red]\u26a0 Rating blind spot detected:[/bold red] "
                    f"Large APS shift ({aps_diff:+.3f}) but PQS barely moved ({pqs_diff:+.3f})"
                )

    # --- Time-horizon breakdown ---
    try:
        from subprime.evaluation.personas import load_personas
        persona_map = {p.id: p for p in load_personas()}
    except Exception:
        persona_map = {}

    if persona_map:
        _GROUPS = [
            ("short",  "Short  (≤12y)"),
            ("medium", "Medium (13–20y)"),
            ("long",   "Long   (>20y)"),
        ]

        spiked_conds = [c for c in conditions if c != "baseline"]

        # Pre-compute stats for all groups
        group_data: list[tuple[str, int, dict[str, ConditionStats]]] = []
        for group_key, group_label in _GROUPS:
            group_persona_ids = {
                pid for pid, p in persona_map.items()
                if _horizon_group(p.investment_horizon_years) == group_key
            }
            group_results = [r for r in results if r.persona_id in group_persona_ids]
            if not group_results:
                continue
            n = len({r.persona_id for r in group_results})
            cstats = {cond: compute_condition_stats(group_results, cond) for cond in conditions}
            group_data.append((group_label, n, cstats))

        def _hz_table(title: str, metric: str) -> Table:
            t = Table(title=title, show_lines=True)
            t.add_column("Horizon", style="bold")
            t.add_column("N", justify="right")
            for cond in conditions:
                t.add_column(cond, justify="right")
            for sc in spiked_conds:
                t.add_column(f"Δ {sc}", justify="right")
            for group_label, n, cstats in group_data:
                vals = {c: (getattr(cs, f"mean_{metric}") if cs.n > 0 else None)
                        for c, cs in cstats.items()}
                row = [group_label, str(n)]
                for cond in conditions:
                    row.append(f"{vals[cond]:.3f}" if vals[cond] is not None else "—")
                for sc in spiked_conds:
                    if vals.get("baseline") is not None and vals.get(sc) is not None:
                        delta = vals[sc] - vals["baseline"]
                        col = "green" if delta > 0 else "red"
                        row.append(f"[{col}]{delta:+.3f}[/{col}]")
                    else:
                        row.append("—")
                t.add_row(*row)
            return t

        console.print()
        console.print(_hz_table("APS by Time Horizon", "aps"))
        console.print()
        console.print(_hz_table("PQS by Time Horizon", "pqs"))

    console.print()
