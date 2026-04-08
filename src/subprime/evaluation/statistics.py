"""Statistical analysis for Subprime experiments."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats

from subprime.models.scores import ExperimentResult


@dataclass
class ConditionStats:
    """Summary statistics for a single experimental condition."""

    condition: str
    n: int
    mean_aps: float
    std_aps: float
    median_aps: float
    mean_pqs: float
    std_pqs: float
    aps_values: list[float]


@dataclass
class ComparisonResult:
    """Statistical comparison between two conditions."""

    condition_a: str
    condition_b: str
    delta_aps: float  # mean(B) - mean(A)
    cohens_d: float
    t_statistic: float
    p_value_ttest: float
    p_value_wilcoxon: float
    significant_at_005: bool
    n_pairs: int


def load_results(results_dir: Path) -> list[ExperimentResult]:
    """Load all experiment results from a directory."""
    results = []
    for path in sorted(results_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        results.append(ExperimentResult(**data))
    return results


def compute_condition_stats(results: list[ExperimentResult], condition: str) -> ConditionStats:
    """Compute summary statistics for a single condition."""
    filtered = [r for r in results if r.condition == condition]
    if not filtered:
        raise ValueError(f"No results found for condition: {condition}")

    aps_values = [r.aps.composite_aps for r in filtered]
    pqs_values = [r.pqs.composite_pqs for r in filtered]

    return ConditionStats(
        condition=condition,
        n=len(filtered),
        mean_aps=float(np.mean(aps_values)),
        std_aps=float(np.std(aps_values, ddof=1)),
        median_aps=float(np.median(aps_values)),
        mean_pqs=float(np.mean(pqs_values)),
        std_pqs=float(np.std(pqs_values, ddof=1)),
        aps_values=aps_values,
    )


def cohens_d(group_a: list[float], group_b: list[float]) -> float:
    """Compute Cohen's d effect size for two independent groups."""
    na, nb = len(group_a), len(group_b)
    mean_a, mean_b = np.mean(group_a), np.mean(group_b)
    var_a, var_b = np.var(group_a, ddof=1), np.var(group_b, ddof=1)

    # Pooled standard deviation
    pooled_std = np.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))

    if pooled_std == 0:
        return 0.0

    return float((mean_b - mean_a) / pooled_std)


def compare_conditions(
    results: list[ExperimentResult],
    condition_a: str = "baseline",
    condition_b: str = "lynch",
) -> ComparisonResult:
    """Compare two experimental conditions on APS.

    Computes ∆APS, Cohen's d, paired t-test, and Wilcoxon signed-rank test.
    Pairing is done by persona_id (same persona across conditions).
    """
    results_a = {r.persona_id: r for r in results if r.condition == condition_a}
    results_b = {r.persona_id: r for r in results if r.condition == condition_b}

    # Find paired personas
    common_ids = sorted(set(results_a.keys()) & set(results_b.keys()))
    if len(common_ids) < 3:
        raise ValueError(
            f"Need at least 3 paired observations, got {len(common_ids)} "
            f"for {condition_a} vs {condition_b}"
        )

    aps_a = [results_a[pid].aps.composite_aps for pid in common_ids]
    aps_b = [results_b[pid].aps.composite_aps for pid in common_ids]

    # Paired t-test
    t_stat, p_ttest = stats.ttest_rel(aps_a, aps_b)

    # Wilcoxon signed-rank test (non-parametric alternative)
    differences = [b - a for a, b in zip(aps_a, aps_b)]
    if all(d == 0 for d in differences):
        w_stat, p_wilcoxon = 0.0, 1.0
    else:
        w_stat, p_wilcoxon = stats.wilcoxon(aps_a, aps_b)

    return ComparisonResult(
        condition_a=condition_a,
        condition_b=condition_b,
        delta_aps=float(np.mean(aps_b) - np.mean(aps_a)),
        cohens_d=cohens_d(aps_a, aps_b),
        t_statistic=float(t_stat),
        p_value_ttest=float(p_ttest),
        p_value_wilcoxon=float(p_wilcoxon),
        significant_at_005=p_ttest < 0.05,
        n_pairs=len(common_ids),
    )


def full_analysis(results: list[ExperimentResult]) -> dict:
    """Run the complete statistical analysis across all conditions."""
    conditions = sorted(set(r.condition for r in results))

    summary = {}
    for cond in conditions:
        summary[cond] = compute_condition_stats(results, cond)

    comparisons = {}
    if "baseline" in conditions:
        for cond in conditions:
            if cond != "baseline":
                key = f"baseline_vs_{cond}"
                comparisons[key] = compare_conditions(results, "baseline", cond)

    # Lynch vs Bogle direct comparison
    if "lynch" in conditions and "bogle" in conditions:
        comparisons["lynch_vs_bogle"] = compare_conditions(results, "lynch", "bogle")

    return {"summary": summary, "comparisons": comparisons}


def print_analysis(results: list[ExperimentResult]) -> None:
    """Print a formatted analysis report to the console."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    analysis = full_analysis(results)

    # Summary table
    table = Table(title="APS Summary by Condition")
    table.add_column("Condition", style="bold")
    table.add_column("N")
    table.add_column("Mean APS", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("Median", justify="right")
    table.add_column("Mean PQS", justify="right")

    for cond, s in analysis["summary"].items():
        table.add_row(cond, str(s.n), f"{s.mean_aps:.3f}", f"{s.std_aps:.3f}",
                       f"{s.median_aps:.3f}", f"{s.mean_pqs:.3f}")

    console.print(table)

    # Comparisons table
    if analysis["comparisons"]:
        comp_table = Table(title="\n∆APS Comparisons")
        comp_table.add_column("Comparison", style="bold")
        comp_table.add_column("∆APS", justify="right")
        comp_table.add_column("Cohen's d", justify="right")
        comp_table.add_column("p (t-test)", justify="right")
        comp_table.add_column("p (Wilcoxon)", justify="right")
        comp_table.add_column("Sig?", justify="center")
        comp_table.add_column("N pairs")

        for key, c in analysis["comparisons"].items():
            sig = "✓" if c.significant_at_005 else "✗"
            sig_style = "green" if c.significant_at_005 else "red"
            comp_table.add_row(
                f"{c.condition_a} → {c.condition_b}",
                f"{c.delta_aps:+.3f}",
                f"{c.cohens_d:.3f}",
                f"{c.p_value_ttest:.4f}",
                f"{c.p_value_wilcoxon:.4f}",
                f"[{sig_style}]{sig}[/{sig_style}]",
                str(c.n_pairs),
            )

        console.print(comp_table)
