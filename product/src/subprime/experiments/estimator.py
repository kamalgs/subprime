"""Pre-run cost estimation for experiments and single plan generations.

Estimates token usage and USD cost before any API calls are made, so users
can plan credit budgets.  Also provides ``estimate_plan_cost`` for the web
app's pay-per-use / micropayment flow.

Token counting uses the 4-chars-per-token approximation.  System prompt
sizes are measured from the actual prompt strings; user-prompt and output
sizes use empirically observed averages.

Caching model (Anthropic ``cache_control`` with 1-hour TTL):
  Advisor  — 1 cache-write per condition (first persona), then reads
  Judges   — 1 cache-write per judge type (APS + PQS = 2 writes total),
             then reads for every subsequent run
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from subprime.experiments.conditions import Condition

# ---------------------------------------------------------------------------
# Anthropic pricing  (USD per million tokens)
# Update here when Anthropic changes rates.
# ---------------------------------------------------------------------------
# Typical output throughput (tokens/sec) for sequential non-streaming calls.
# Conservative estimates; actual TPS varies with server load.
# Source: empirical observation from instrumented runs.
TPS: dict[str, float] = {
    "claude-haiku-4-5": 80.0,
    "claude-sonnet-4-6": 40.0,
    "claude-opus-4-6": 15.0,
    # Together AI — rough empirical throughput for these serverless endpoints.
    "Qwen3.5-397B-A17B": 60.0,
    "Qwen3-235B-A22B-Instruct-2507": 90.0,
    "Qwen3-Next-80B-A3B-Instruct": 120.0,
    "Qwen3.5-9B": 150.0,
    "gemma-4-31B-it": 80.0,
}

# Per-call overhead: TTFB + queuing, regardless of output size (seconds)
_TTFB_SECS: float = 2.0

PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
    # Together AI — no prompt caching, so cache_read/write == input rate.
    "Qwen3.5-397B-A17B": {
        "input": 0.60,
        "output": 3.60,
        "cache_read": 0.60,
        "cache_write": 0.60,
    },
    "gemma-4-31B-it": {
        "input": 0.20,
        "output": 0.50,
        "cache_read": 0.20,
        "cache_write": 0.20,
    },
    "Qwen3-235B-A22B-Instruct-2507": {
        "input": 0.20,
        "output": 0.60,
        "cache_read": 0.20,
        "cache_write": 0.20,
    },
    "Qwen3-Next-80B-A3B-Instruct": {
        "input": 0.15,
        "output": 1.50,
        "cache_read": 0.15,
        "cache_write": 0.15,
    },
    "Qwen3.5-9B": {
        "input": 0.10,
        "output": 0.15,
        "cache_read": 0.10,
        "cache_write": 0.10,
    },
}

# Empirically observed averages from haiku+haiku experiment run (75 runs).
# advisor_output includes plan JSON (~3 000 tok) + tool calls (~3 000 tok).
# aps/pqs include structured JSON + reasoning (~1 100 / 1 300 tok each).
# Total per run: ~8 400 tok observed (avg 8 323 across 35 completed runs).
_TYPICAL: dict[str, int] = {
    "advisor_user_tokens": 450,  # persona profile JSON
    "advisor_output_tokens": 6_000,  # plan JSON + tool calls (was 1 500 — 4× underestimate)
    "judge_user_tokens": 3_000,  # plan JSON + profile JSON
    "aps_output_tokens": 1_100,  # structured score + reasoning (was 350)
    "pqs_output_tokens": 1_300,  # structured score + reasoning (was 350)
    "universe_fallback_tokens": 3_500,  # when DB unavailable
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Estimate token count at ~4 chars / token."""
    return max(1, len(text) // 4)


def _price(model: str) -> dict[str, float]:
    """Return pricing dict for model (partial-name match, fallback to sonnet)."""
    for key, prices in PRICING.items():
        if key in model:
            return prices
    return PRICING["claude-sonnet-4-6"]


def _usd(tokens: int, rate_per_mtok: float) -> float:
    return tokens * rate_per_mtok / 1_000_000


def _tps(model: str) -> float:
    """Return output TPS estimate for model (partial-name match, fallback to sonnet)."""
    for key, tps in TPS.items():
        if key in model:
            return tps
    return TPS["claude-sonnet-4-6"]


def _call_secs(n_calls: int, output_tokens_per_call: int, model: str) -> float:
    """Estimate wall-clock seconds for n sequential calls."""
    return n_calls * (_TTFB_SECS + output_tokens_per_call / _tps(model))


# ---------------------------------------------------------------------------
# Prompt measurement (reads actual prompts, no API calls)
# ---------------------------------------------------------------------------


def _advisor_system_tokens(conditions: list[Condition]) -> dict[str, int]:
    """Build advisor agent per condition, return {condition_name: token_count}."""
    from subprime.advisor.agent import create_advisor

    result: dict[str, int] = {}
    for cond in conditions:
        agent = create_advisor(prompt_hooks=cond.prompt_hooks)
        combined = "\n".join(str(s) for s in agent._system_prompts)
        result[cond.name] = _approx_tokens(combined)
    return result


def _universe_tokens() -> int:
    """Count universe context tokens from DB, or return fallback estimate."""
    try:
        import duckdb
        from subprime.core.config import DB_PATH
        from subprime.data.universe import render_universe_context

        if not DB_PATH.exists():
            return 0
        conn = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            text = render_universe_context(conn)
            return _approx_tokens(text) if text else 0
        finally:
            conn.close()
    except Exception:
        return _TYPICAL["universe_fallback_tokens"]


def _judge_system_tokens() -> tuple[int, int]:
    """Return (aps_tokens, pqs_tokens) for judge system prompts."""
    from subprime.evaluation.judges import _build_aps_prompt, _build_pqs_prompt

    return _approx_tokens(_build_aps_prompt()), _approx_tokens(_build_pqs_prompt())


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PhaseEstimate:
    """Token and cost breakdown for one phase (advisor or judges)."""

    phase: str  # "advisor" or "judges"
    model: str
    n_calls: int
    system_tokens: int  # per-call system prompt size
    user_tokens: int  # per-call user prompt size
    output_tokens: int  # per-call output size
    cache_writes: int  # number of calls that write to cache
    cache_reads: int  # number of calls that read from cache
    # Totals
    total_input_tokens: int
    total_output_tokens: int
    total_cache_write_tokens: int
    total_cache_read_tokens: int
    cost_usd: float


@dataclass
class ExperimentEstimate:
    n_personas: int
    n_conditions: int
    n_runs: int
    concurrency: int  # parallel runs assumed for wall-time estimate
    model: str
    judge_model: str
    universe_tokens: int  # tokens added by universe context per advisor call
    advisor: PhaseEstimate
    judges: PhaseEstimate
    total_cost_usd: float
    no_cache_cost_usd: float
    cache_savings_usd: float
    cache_savings_pct: float
    avg_cost_per_run_usd: float
    # Wall-time estimates (advisor + judge phases per wave, scaled by concurrency)
    advisor_wall_minutes: float
    judge_wall_minutes: float
    total_wall_minutes: float


@dataclass
class PlanCostEstimate:
    """Lightweight estimate for a single plan generation (web app use)."""

    mode: str  # "basic" or "premium"
    n_advisor_calls: int  # 1 for basic, 3-5 for premium
    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float

    @property
    def estimated_cost_inr(self) -> float:
        """Approximate INR cost at 83 INR/USD."""
        return self.estimated_cost_usd * 83.0


# ---------------------------------------------------------------------------
# Core estimators
# ---------------------------------------------------------------------------


def estimate_experiment(
    n_personas: int,
    conditions: list[Condition],
    model: str = "anthropic:claude-sonnet-4-6",
    judge_model: str | None = None,
    include_universe: bool = True,
    concurrency: int = 1,
) -> ExperimentEstimate:
    """Estimate token usage and cost for a full experiment matrix.

    Args:
        n_personas: Number of personas.
        conditions: Condition list to run.
        model: Advisor model identifier.
        judge_model: Judge model (defaults to model).
        include_universe: Whether advisor receives universe context.
        concurrency: Parallel runs assumed for wall-time estimate.

    Returns:
        ExperimentEstimate with per-phase breakdown and cache savings.
    """
    eff_judge = judge_model or model
    n_conditions = len(conditions)
    n_runs = n_personas * n_conditions

    # ---- Advisor phase ----
    adv_sys_by_cond = _advisor_system_tokens(conditions)
    # avg system prompt size across conditions (philosophy hooks differ slightly)
    avg_adv_sys = sum(adv_sys_by_cond.values()) // max(1, n_conditions)

    univ_tok = _universe_tokens() if include_universe else 0
    adv_sys_total_per_call = avg_adv_sys + univ_tok

    # Cache model: 1 write per condition (first persona), reads for the rest
    adv_writes = n_conditions
    adv_reads = n_conditions * (n_personas - 1)

    adv_user = _TYPICAL["advisor_user_tokens"]
    adv_out = _TYPICAL["advisor_output_tokens"]
    adv_p = _price(model)

    total_adv_user = n_runs * adv_user
    total_adv_cache_write = adv_writes * adv_sys_total_per_call
    total_adv_cache_read = adv_reads * adv_sys_total_per_call
    total_adv_out = n_runs * adv_out

    adv_cost = (
        _usd(total_adv_user, adv_p["input"])
        + _usd(total_adv_cache_write, adv_p["cache_write"])
        + _usd(total_adv_cache_read, adv_p["cache_read"])
        + _usd(total_adv_out, adv_p["output"])
    )

    advisor_est = PhaseEstimate(
        phase="advisor",
        model=model,
        n_calls=n_runs,
        system_tokens=adv_sys_total_per_call,
        user_tokens=adv_user,
        output_tokens=adv_out,
        cache_writes=adv_writes,
        cache_reads=adv_reads,
        total_input_tokens=total_adv_user + total_adv_cache_write + total_adv_cache_read,
        total_output_tokens=total_adv_out,
        total_cache_write_tokens=total_adv_cache_write,
        total_cache_read_tokens=total_adv_cache_read,
        cost_usd=adv_cost,
    )

    # ---- Judge phase ----
    aps_sys, pqs_sys = _judge_system_tokens()
    # 2 judges per run (APS + PQS), each with 1 cache-write then reads
    total_judge_calls = 2 * n_runs
    jud_cache_writes = 2  # one APS write + one PQS write
    jud_cache_reads = 2 * (n_runs - 1)

    jud_user = _TYPICAL["judge_user_tokens"]
    jud_out = _TYPICAL["aps_output_tokens"] + _TYPICAL["pqs_output_tokens"]  # per run
    jud_p = _price(eff_judge)

    total_jud_user = total_judge_calls * jud_user
    total_jud_cache_write = aps_sys + pqs_sys  # one write each
    total_jud_cache_read = (n_runs - 1) * aps_sys + (n_runs - 1) * pqs_sys
    total_jud_out = n_runs * jud_out

    jud_cost = (
        _usd(total_jud_user, jud_p["input"])
        + _usd(total_jud_cache_write, jud_p["cache_write"])
        + _usd(total_jud_cache_read, jud_p["cache_read"])
        + _usd(total_jud_out, jud_p["output"])
    )

    avg_jud_sys = (aps_sys + pqs_sys) // 2
    judge_est = PhaseEstimate(
        phase="judges",
        model=eff_judge,
        n_calls=total_judge_calls,
        system_tokens=avg_jud_sys,
        user_tokens=jud_user,
        output_tokens=jud_out // 2,
        cache_writes=jud_cache_writes,
        cache_reads=jud_cache_reads,
        total_input_tokens=total_jud_user + total_jud_cache_write + total_jud_cache_read,
        total_output_tokens=total_jud_out,
        total_cache_write_tokens=total_jud_cache_write,
        total_cache_read_tokens=total_jud_cache_read,
        cost_usd=jud_cost,
    )

    total_cost = adv_cost + jud_cost

    # No-cache baseline (all system + user tokens at full input rate)
    no_cache_adv = _usd(n_runs * (adv_sys_total_per_call + adv_user), adv_p["input"]) + _usd(
        total_adv_out, adv_p["output"]
    )
    no_cache_jud = _usd(total_judge_calls * (avg_jud_sys + jud_user), jud_p["input"]) + _usd(
        total_jud_out, jud_p["output"]
    )
    no_cache_cost = no_cache_adv + no_cache_jud
    savings = no_cache_cost - total_cost
    savings_pct = 100.0 * savings / no_cache_cost if no_cache_cost > 0 else 0.0

    # Wall-time: within each run advisor + 2 judge calls are serial; runs are parallel.
    # waves = number of sequential "rounds" needed at the given concurrency level.
    adv_secs_per_run = _TTFB_SECS + adv_out / _tps(model)
    jud_secs_per_run = 2 * (_TTFB_SECS + (jud_out // 2) / _tps(eff_judge))
    waves = math.ceil(n_runs / max(1, concurrency))
    adv_mins = waves * adv_secs_per_run / 60
    jud_mins = waves * jud_secs_per_run / 60

    return ExperimentEstimate(
        n_personas=n_personas,
        n_conditions=n_conditions,
        n_runs=n_runs,
        concurrency=concurrency,
        model=model,
        judge_model=eff_judge,
        universe_tokens=univ_tok,
        advisor=advisor_est,
        judges=judge_est,
        total_cost_usd=total_cost,
        no_cache_cost_usd=no_cache_cost,
        cache_savings_usd=savings,
        cache_savings_pct=savings_pct,
        avg_cost_per_run_usd=total_cost / max(1, n_runs),
        advisor_wall_minutes=adv_mins,
        judge_wall_minutes=jud_mins,
        total_wall_minutes=adv_mins + jud_mins,
    )


def estimate_plan_cost(
    mode: str = "basic",
    model: str = "anthropic:claude-sonnet-4-6",
    n_perspectives: int = 3,
    include_universe: bool = True,
) -> PlanCostEstimate:
    """Estimate cost for a single plan generation (web app / micropayment use).

    Args:
        mode: "basic" (1 advisor call) or "premium" (n_perspectives calls + evaluator).
        model: Advisor model identifier.
        n_perspectives: Number of perspectives for premium mode.
        include_universe: Whether universe context is included.

    Returns:
        PlanCostEstimate with input/output token estimates and USD cost.
    """
    # Advisor system prompt (use baseline — no philosophy hook for web app)
    from subprime.advisor.agent import create_advisor

    agent = create_advisor()
    sys_text = "\n".join(str(s) for s in agent._system_prompts)
    adv_sys = _approx_tokens(sys_text)

    if include_universe:
        adv_sys += _universe_tokens()

    adv_user = _TYPICAL["advisor_user_tokens"]
    adv_out = _TYPICAL["advisor_output_tokens"]
    p = _price(model)

    if mode == "premium":
        n_calls = n_perspectives
        # First call: cache write; rest: cache reads
        input_tokens = (
            1 * adv_sys  # cache write (counted as system input)
            + (n_calls - 1) * adv_sys  # cache reads (discounted below)
            + n_calls * adv_user
        )
        cost = (
            _usd(adv_sys, p["cache_write"])  # 1 write
            + _usd((n_calls - 1) * adv_sys, p["cache_read"])  # reads
            + _usd(n_calls * adv_user, p["input"])
            + _usd(n_calls * adv_out, p["output"])
        )
        output_tokens = n_calls * adv_out
    else:
        # basic: 1 call, no cache benefit (first call always writes)
        input_tokens = adv_sys + adv_user
        cost = (
            _usd(adv_sys, p["cache_write"])
            + _usd(adv_user, p["input"])
            + _usd(adv_out, p["output"])
        )
        output_tokens = adv_out

    return PlanCostEstimate(
        mode=mode,
        n_advisor_calls=n_perspectives if mode == "premium" else 1,
        model=model,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )


# ---------------------------------------------------------------------------
# Rich display
# ---------------------------------------------------------------------------


def print_estimate(est: ExperimentEstimate) -> None:
    """Print a formatted cost estimate to the console."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print(
        f"\n[bold]Experiment cost estimate[/bold]  "
        f"{est.n_personas} persona(s) × {est.n_conditions} condition(s) = "
        f"[bold]{est.n_runs} runs[/bold]\n"
        f"  Advisor : {est.model}\n"
        f"  Judge   : {est.judge_model}"
        + (
            f"\n  Universe: {est.universe_tokens:,} tokens per advisor call"
            if est.universe_tokens
            else ""
        )
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Phase", style="bold blue")
    table.add_column("Calls", justify="right")
    table.add_column("Sys tok", justify="right")
    table.add_column("User tok", justify="right")
    table.add_column("Out tok", justify="right")
    table.add_column("Cache wr", justify="right")
    table.add_column("Cache rd", justify="right")
    table.add_column("Cost (USD)", justify="right", style="green")

    for phase in (est.advisor, est.judges):
        table.add_row(
            phase.phase,
            str(phase.n_calls),
            f"{phase.system_tokens:,}",
            f"{phase.user_tokens:,}",
            f"{phase.output_tokens:,}",
            str(phase.cache_writes),
            str(phase.cache_reads),
            f"${phase.cost_usd:.4f}",
        )

    console.print(table)

    def _fmt_mins(m: float) -> str:
        h, rem = divmod(int(m), 60)
        return f"{h}h {rem:02d}m" if h else f"{int(m)}m"

    if est.concurrency > 1:
        seq_total = est.total_wall_minutes * est.n_runs / math.ceil(est.n_runs / est.concurrency)
        time_note = f"concurrency={est.concurrency}; was {_fmt_mins(seq_total)} sequential"
        latency_note = (
            f"Parallel runs ({est.concurrency} concurrent); actual time varies with API latency."
        )
    else:
        time_note = (
            f"sequential — advisor {_fmt_mins(est.advisor_wall_minutes)}"
            f" + judges {_fmt_mins(est.judge_wall_minutes)}"
        )
        latency_note = "Sequential runs; actual time varies with API latency."

    console.print(
        f"\n  [bold]Total cost  : [green]${est.total_cost_usd:.4f}[/green][/bold]"
        f"  (avg ${est.avg_cost_per_run_usd:.5f}/run)\n"
        f"  Without cache : ${est.no_cache_cost_usd:.4f}\n"
        f"  Cache savings : [green]${est.cache_savings_usd:.4f}  "
        f"({est.cache_savings_pct:.0f}% cheaper)[/green]\n"
        f"\n  [bold]Est. wall time: [cyan]{_fmt_mins(est.total_wall_minutes)}[/cyan][/bold]"
        f"  ({time_note})\n"
        f"  [dim]{latency_note}[/dim]\n"
    )


# Standard model configurations for side-by-side comparison
_COMPARE_CONFIGS: list[tuple[str, str, str]] = [
    ("anthropic:claude-haiku-4-5", "anthropic:claude-haiku-4-5", "haiku+haiku"),
    ("anthropic:claude-haiku-4-5", "anthropic:claude-sonnet-4-6", "haiku+sonnet"),
    ("anthropic:claude-sonnet-4-6", "anthropic:claude-sonnet-4-6", "sonnet+sonnet"),
    ("anthropic:claude-sonnet-4-6", "anthropic:claude-opus-4-6", "sonnet+opus"),
]


def compare_configs(
    n_personas: int,
    conditions: list[Condition],
    default_model: str = "anthropic:claude-sonnet-4-6",
    default_judge: str | None = None,
    include_universe: bool = True,
    concurrency: int = 1,
) -> list[tuple[str, ExperimentEstimate]]:
    """Return estimates for all standard model configurations.

    Returns:
        List of (label, ExperimentEstimate) for each config.
    """
    results = []
    for model, judge, label in _COMPARE_CONFIGS:
        est = estimate_experiment(
            n_personas=n_personas,
            conditions=conditions,
            model=model,
            judge_model=judge,
            include_universe=include_universe,
            concurrency=concurrency,
        )
        results.append((label, est))
    return results


def print_comparison(
    comparisons: list[tuple[str, ExperimentEstimate]],
    default_model: str = "anthropic:claude-sonnet-4-6",
    default_judge: str | None = None,
) -> None:
    """Print a side-by-side comparison table of model configurations."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not comparisons:
        return

    _, first = comparisons[0]
    console.print(
        f"\n[bold]Model configuration comparison[/bold]  "
        f"{first.n_personas} persona(s) × {first.n_conditions} condition(s) = "
        f"[bold]{first.n_runs} runs[/bold]"
        + (
            f"\n  Universe context: {first.universe_tokens:,} tokens per advisor call"
            if first.universe_tokens
            else ""
        )
    )

    eff_default_judge = default_judge or default_model

    def _fmt_mins(m: float) -> str:
        h, rem = divmod(int(m), 60)
        return f"{h}h {rem:02d}m" if h else f"{int(m)}m"

    table = Table(show_header=True, header_style="bold")
    table.add_column("", justify="center", width=1)  # default marker
    table.add_column("Config", style="bold", no_wrap=True)
    table.add_column("Advisor $", justify="right")
    table.add_column("Judge $", justify="right")
    table.add_column("Total $", justify="right", style="green")
    table.add_column("$ / run", justify="right")
    table.add_column("Est. time", justify="right", style="cyan")
    table.add_column("Savings", justify="right")

    for label, est in comparisons:
        is_default = est.model == default_model and est.judge_model == eff_default_judge
        marker = "★" if is_default else ""
        table.add_row(
            marker,
            label,
            f"${est.advisor.cost_usd:.3f}",
            f"${est.judges.cost_usd:.3f}",
            f"${est.total_cost_usd:.3f}",
            f"${est.avg_cost_per_run_usd:.4f}",
            _fmt_mins(est.total_wall_minutes),
            f"{est.cache_savings_pct:.0f}%",
        )

    console.print(table)
    console.print()
