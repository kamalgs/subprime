"""Experiment runner — execute personas x conditions and persist results."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from pydantic_ai.usage import RunUsage
from rich.console import Console

from subprime.advisor.planner import generate_plan
from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import ExperimentResult, InvestorProfile
from subprime.evaluation.personas import get_persona, load_personas
from subprime.evaluation.scorer import score_plan
from subprime.experiments.conditions import CONDITIONS, Condition, get_condition

_DEFAULT_RESULTS_DIR = Path(__file__).parent / "results"
_console = Console()


def save_result(
    result: ExperimentResult,
    results_dir: Path | None = None,
) -> Path:
    """Save an ExperimentResult as a JSON file.

    Args:
        result: The experiment result to persist.
        results_dir: Directory to write into. Defaults to experiments/results/.

    Returns:
        The Path to the written JSON file.
    """
    out_dir = results_dir or _DEFAULT_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build a unique filename from persona, condition, and timestamp
    ts = result.timestamp.strftime("%Y%m%dT%H%M%S")
    filename = f"{result.persona_id}_{result.condition}_{ts}.json"
    path = out_dir / filename

    path.write_text(result.model_dump_json(indent=2))
    return path


def _fmt_usage(u: RunUsage, elapsed: float) -> str:
    """Format token usage for display."""
    tps = u.output_tokens / elapsed if elapsed > 0 else 0
    parts = [
        f"in={u.input_tokens:,}",
        f"out={u.output_tokens:,}",
        f"tps={tps:.0f}",
    ]
    if u.cache_read_tokens:
        parts.append(f"cache_rd={u.cache_read_tokens:,}")
    if u.cache_write_tokens:
        parts.append(f"cache_wr={u.cache_write_tokens:,}")
    return "  ".join(parts)


async def run_single(
    persona: InvestorProfile,
    condition: Condition,
    model: str = DEFAULT_MODEL,
    judge_model: str | None = None,
    prompt_version: str = "v1",
    thinking: bool = False,
) -> tuple[ExperimentResult, RunUsage]:
    """Run a single experiment: one persona x one condition.

    Returns:
        (ExperimentResult, RunUsage) — result and combined token usage.
    """
    effective_judge = judge_model or model

    _console.print(
        f"  [bold blue]{condition.name}[/bold blue] x "
        f"[bold green]{persona.id}[/bold green] — generating plan...",
    )

    t0 = time.monotonic()
    plan, plan_usage = await generate_plan(
        profile=persona,
        prompt_hooks=condition.prompt_hooks,
        model=model,
        thinking=thinking,
    )
    plan_elapsed = time.monotonic() - t0

    _console.print(
        f"  [bold blue]{condition.name}[/bold blue] x "
        f"[bold green]{persona.id}[/bold green] — scoring plan "
        f"[dim](judge: {effective_judge.split(':')[-1]})[/dim]...",
    )

    t1 = time.monotonic()
    scored, score_usage = await score_plan(
        plan=plan, profile=persona, model=model, judge_model=judge_model, thinking=thinking,
    )
    score_elapsed = time.monotonic() - t1

    total_usage = plan_usage + score_usage
    total_elapsed = plan_elapsed + score_elapsed

    result = ExperimentResult(
        persona_id=persona.id,
        condition=condition.name,
        model=model,
        judge_model=effective_judge if judge_model else None,
        plan=scored.plan,
        aps=scored.aps,
        pqs=scored.pqs,
        prompt_version=prompt_version,
    )

    _console.print(
        f"  [bold blue]{condition.name}[/bold blue] x "
        f"[bold green]{persona.id}[/bold green] — "
        f"APS={scored.aps.composite_aps:.3f}  PQS={scored.pqs.composite_pqs:.3f}  "
        f"[dim]{total_elapsed:.0f}s  {_fmt_usage(total_usage, total_elapsed)}[/dim]",
    )

    return result, total_usage


async def rescore_results(
    results: list[ExperimentResult],
    judge_model: str,
    personas: dict[str, InvestorProfile],
    thinking: bool = True,
    concurrency: int = 10,
    results_dir: Path | None = None,
) -> list[ExperimentResult]:
    """Re-score existing ExperimentResults with a different judge model.

    When *results_dir* is set, each result is saved incrementally as it
    completes (same pattern as :func:`run_experiment`).
    """
    sem = asyncio.Semaphore(concurrency)
    total_usage = RunUsage()
    done_count = 0

    async def _score_one(result: ExperimentResult) -> ExperimentResult | None:
        nonlocal done_count
        persona = personas.get(result.persona_id)
        if persona is None:
            _console.print(f"  [yellow]Skipping {result.persona_id} — persona not found[/yellow]")
            return None

        async with sem:
            t0 = time.monotonic()
            scored, usage = await score_plan(
                plan=result.plan,
                profile=persona,
                model=result.model,
                judge_model=judge_model,
                thinking=thinking,
            )
            elapsed = time.monotonic() - t0
            total_usage.incr(usage)
            done_count += 1

            _console.print(
                f"  [{done_count}/{len(results)}] "
                f"[bold blue]{result.condition}[/bold blue] x "
                f"[bold green]{result.persona_id}[/bold green]  "
                f"APS={scored.aps.composite_aps:.3f}  "
                f"PQS={scored.pqs.composite_pqs:.3f}  "
                f"[dim]{elapsed:.0f}s  {_fmt_usage(usage, elapsed)}[/dim]"
            )

            rescored_result = ExperimentResult(
                persona_id=result.persona_id,
                condition=result.condition,
                model=result.model,
                judge_model=judge_model,
                plan=scored.plan,
                aps=scored.aps,
                pqs=scored.pqs,
                timestamp=result.timestamp,
                prompt_version=result.prompt_version,
            )
            if results_dir:
                save_result(rescored_result, results_dir=results_dir)
            return rescored_result

    outcomes = await asyncio.gather(
        *[_score_one(r) for r in results],
        return_exceptions=True,
    )

    rescored: list[ExperimentResult] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            _console.print(f"[bold red]Score error:[/bold red] {outcome}")
        elif outcome is not None:
            rescored.append(outcome)

    _console.print(
        f"\n[dim]Total tokens — {_fmt_usage(total_usage, 0).replace('tps=0', '')}[/dim]"
    )
    return rescored


def _completed_keys(results_dir: Path) -> set[tuple[str, str]]:
    """Return (persona_id, condition) pairs already saved in results_dir.

    Uses a lightweight JSON parse to extract just persona_id and condition,
    so this works even when the schema has evolved since old files were saved.
    """
    import json

    completed: set[tuple[str, str]] = set()
    if not results_dir.exists():
        return completed
    for jf in results_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
            completed.add((data["persona_id"], data["condition"]))
        except Exception:
            pass
    return completed


async def run_experiment(
    persona_ids: list[str] | None = None,
    condition_names: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    judge_model: str | None = None,
    prompt_version: str = "v1",
    results_dir: Path | None = None,
    resume: bool = False,
    concurrency: int = 5,
    thinking: bool = False,
) -> list[ExperimentResult]:
    """Run the full experiment matrix: personas x conditions.

    Args:
        persona_ids: Subset of persona IDs to run. None = all personas.
        condition_names: Subset of condition names. None = all conditions.
        model: LLM model identifier for the advisor.
        judge_model: LLM model identifier for judges. Defaults to model.
        prompt_version: Version tag for prompt tracking.
        results_dir: Where to save result JSONs.
        resume: Skip (persona, condition) pairs that already have a saved
            result in results_dir. Useful after an interrupted run.
        concurrency: Maximum number of parallel runs. 1 = sequential.

    Returns:
        List of all ExperimentResult objects from the run.
    """
    if persona_ids is not None:
        personas = [get_persona(pid) for pid in persona_ids]
    else:
        personas = load_personas()

    if condition_names is not None:
        conditions = [get_condition(name) for name in condition_names]
    else:
        conditions = CONDITIONS

    out_dir = results_dir or _DEFAULT_RESULTS_DIR
    completed = _completed_keys(out_dir) if resume else set()

    all_pairs = [
        (persona, condition)
        for persona in personas
        for condition in conditions
        if not (resume and (persona.id, condition.name) in completed)
    ]
    total = len(personas) * len(conditions)
    skipped = total - len(all_pairs)
    effective_judge = judge_model or model
    active_concurrency = min(concurrency, len(all_pairs)) if all_pairs else 1

    _console.print(
        f"\n[bold]Running experiment:[/bold] "
        f"{len(personas)} personas × {len(conditions)} conditions = {total} runs\n"
        f"  Advisor : {model}\n"
        f"  Judge   : {effective_judge}\n"
        f"  Parallel: {active_concurrency} concurrent\n"
        + (f"  Resuming: skipping {skipped} already-completed run(s)\n" if skipped else "")
    )

    sem = asyncio.Semaphore(concurrency)
    session_usage = RunUsage()
    session_start = time.monotonic()
    done_count = 0

    async def _run(persona: InvestorProfile, condition: Condition) -> tuple[ExperimentResult, RunUsage]:
        nonlocal done_count
        async with sem:
            result, usage = await run_single(
                persona=persona,
                condition=condition,
                model=model,
                judge_model=judge_model,
                prompt_version=prompt_version,
                thinking=thinking,
            )
            save_result(result, results_dir=out_dir)
            done_count += 1
            _console.print(f"  [dim][{done_count}/{len(all_pairs)}] {condition.name} × {persona.id} saved[/dim]")
            return result, usage

    outcomes = await asyncio.gather(
        *[_run(p, c) for p, c in all_pairs],
        return_exceptions=True,
    )

    results: list[ExperimentResult] = []
    run_errors: list[BaseException] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            run_errors.append(outcome)
            _console.print(f"[bold red]Run error:[/bold red] {outcome}")
        else:
            result, usage = outcome
            results.append(result)
            session_usage.incr(usage)

    session_elapsed = time.monotonic() - session_start
    error_note = f", {len(run_errors)} error(s)" if run_errors else ""
    _console.print(
        f"[bold green]Experiment complete:[/bold green] {len(results)} results saved{error_note}.\n"
        f"[dim]Session totals ({session_elapsed:.0f}s): "
        f"{_fmt_usage(session_usage, session_elapsed)}[/dim]\n"
    )
    if run_errors:
        raise RuntimeError(f"{len(run_errors)} run(s) failed") from run_errors[0]

    return results
