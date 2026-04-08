"""subprime.experiments — Experiment conditions, runner, and analysis."""

from subprime.experiments.analysis import (
    ComparisonResult,
    ConditionStats,
    compare_conditions,
    compute_condition_stats,
    print_analysis,
)
from subprime.experiments.conditions import (
    BASELINE,
    BOGLE,
    CONDITIONS,
    LYNCH,
    Condition,
    get_condition,
)
from subprime.experiments.runner import run_experiment, run_single, save_result

__all__ = [
    "BASELINE",
    "BOGLE",
    "CONDITIONS",
    "ComparisonResult",
    "Condition",
    "ConditionStats",
    "LYNCH",
    "compare_conditions",
    "compute_condition_stats",
    "get_condition",
    "print_analysis",
    "run_experiment",
    "run_single",
    "save_result",
]
