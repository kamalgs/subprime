"""Experiment runner — execute personas x conditions and persist results."""

from __future__ import annotations

import json
from pathlib import Path

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


async def run_single(
    persona: InvestorProfile,
    condition: Condition,
    model: str = DEFAULT_MODEL,
    judge_model: str | None = None,
    prompt_version: str = "v1",
) -> ExperimentResult:
    """Run a single experiment: one persona x one condition.

    Generates a plan via the advisor with the condition's prompt hooks,
    then scores it with both APS and PQS judges.

    Args:
        persona: The investor profile to advise.
        condition: The experimental condition (baseline, lynch, bogle).
        model: LLM model identifier for the advisor.
        judge_model: LLM model identifier for judges. Defaults to model.
        prompt_version: Version tag for prompt tracking.

    Returns:
        A complete ExperimentResult.
    """
    effective_judge = judge_model or model

    _console.print(
        f"  [bold blue]{condition.name}[/bold blue] x "
        f"[bold green]{persona.id}[/bold green] — generating plan...",
    )

    plan = await generate_plan(
        profile=persona,
        prompt_hooks=condition.prompt_hooks,
        model=model,
    )

    _console.print(
        f"  [bold blue]{condition.name}[/bold blue] x "
        f"[bold green]{persona.id}[/bold green] — scoring plan "
        f"[dim](judge: {effective_judge.split(':')[-1]})[/dim]...",
    )

    scored = await score_plan(plan=plan, profile=persona, model=model, judge_model=judge_model)

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
        f"[dim]done[/dim]",
    )

    return result


async def rescore_results(
    results: list[ExperimentResult],
    judge_model: str,
    personas: dict[str, InvestorProfile],
) -> list[ExperimentResult]:
    """Re-score existing ExperimentResults with a different judge model.

    Args:
        results: Previously saved ExperimentResults to re-score.
        judge_model: The new judge model to use for APS + PQS.
        personas: Mapping of persona_id → InvestorProfile for PQS context.

    Returns:
        New ExperimentResult list with updated scores and judge_model set.
    """
    rescored: list[ExperimentResult] = []
    for i, result in enumerate(results, 1):
        persona = personas.get(result.persona_id)
        if persona is None:
            _console.print(f"  [yellow]Skipping {result.persona_id} — persona not found[/yellow]")
            continue

        _console.print(
            f"  [{i}/{len(results)}] re-scoring "
            f"[bold blue]{result.condition}[/bold blue] x "
            f"[bold green]{result.persona_id}[/bold green] "
            f"[dim](judge: {judge_model.split(':')[-1]})[/dim]..."
        )

        scored = await score_plan(
            plan=result.plan,
            profile=persona,
            model=result.model,
            judge_model=judge_model,
        )

        rescored.append(ExperimentResult(
            persona_id=result.persona_id,
            condition=result.condition,
            model=result.model,
            judge_model=judge_model,
            plan=scored.plan,
            aps=scored.aps,
            pqs=scored.pqs,
            timestamp=result.timestamp,
            prompt_version=result.prompt_version,
        ))

        _console.print(
            f"       APS={scored.aps.composite_aps:.3f}  "
            f"PQS={scored.pqs.composite_pqs:.3f}  [dim]done[/dim]"
        )

    return rescored


def _completed_keys(results_dir: Path) -> set[tuple[str, str]]:
    """Return (persona_id, condition) pairs already saved in results_dir."""
    completed: set[tuple[str, str]] = set()
    if not results_dir.exists():
        return completed
    for jf in results_dir.glob("*.json"):
        try:
            r = ExperimentResult.model_validate_json(jf.read_text())
            completed.add((r.persona_id, r.condition))
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

    total = len(personas) * len(conditions)
    skipped = len(completed) if resume else 0
    effective_judge = judge_model or model
    _console.print(
        f"\n[bold]Running experiment:[/bold] "
        f"{len(personas)} personas x {len(conditions)} conditions = {total} runs\n"
        f"  Advisor : {model}\n"
        f"  Judge   : {effective_judge}\n"
        + (f"  Resuming: skipping {skipped} already-completed runs\n" if resume else "")
    )

    results: list[ExperimentResult] = []
    for i, persona in enumerate(personas, 1):
        _console.print(
            f"[bold yellow]Persona {i}/{len(personas)}:[/bold yellow] "
            f"{persona.id} — {persona.name}"
        )
        for condition in conditions:
            if resume and (persona.id, condition.name) in completed:
                _console.print(
                    f"  [dim]skip {condition.name} x {persona.id} (already done)[/dim]"
                )
                continue
            result = await run_single(
                persona=persona,
                condition=condition,
                model=model,
                judge_model=judge_model,
                prompt_version=prompt_version,
            )
            save_result(result, results_dir=out_dir)
            results.append(result)
        _console.print()

    _console.print(
        f"[bold green]Experiment complete:[/bold green] {len(results)} new results saved.\n"
    )
    return results
