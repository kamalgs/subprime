"""Experiment runner — execute personas x conditions and persist results."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from subprime.advisor.planner import generate_plan
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
    model: str = "anthropic:claude-sonnet-4-6",
    prompt_version: str = "v1",
) -> ExperimentResult:
    """Run a single experiment: one persona x one condition.

    Generates a plan via the advisor with the condition's prompt hooks,
    then scores it with both APS and PQS judges.

    Args:
        persona: The investor profile to advise.
        condition: The experimental condition (baseline, lynch, bogle).
        model: LLM model identifier for both advisor and judges.
        prompt_version: Version tag for prompt tracking.

    Returns:
        A complete ExperimentResult.
    """
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
        f"[bold green]{persona.id}[/bold green] — scoring plan...",
    )

    scored = await score_plan(plan=plan, profile=persona, model=model)

    result = ExperimentResult(
        persona_id=persona.id,
        condition=condition.name,
        model=model,
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


async def run_experiment(
    persona_ids: list[str] | None = None,
    condition_names: list[str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
    prompt_version: str = "v1",
    results_dir: Path | None = None,
) -> list[ExperimentResult]:
    """Run the full experiment matrix: personas x conditions.

    Args:
        persona_ids: Subset of persona IDs to run. None = all personas.
        condition_names: Subset of condition names. None = all conditions.
        model: LLM model identifier.
        prompt_version: Version tag for prompt tracking.
        results_dir: Where to save result JSONs.

    Returns:
        List of all ExperimentResult objects from the run.
    """
    # Resolve personas
    if persona_ids is not None:
        personas = [get_persona(pid) for pid in persona_ids]
    else:
        personas = load_personas()

    # Resolve conditions
    if condition_names is not None:
        conditions = [get_condition(name) for name in condition_names]
    else:
        conditions = CONDITIONS

    total = len(personas) * len(conditions)
    _console.print(
        f"\n[bold]Running experiment:[/bold] "
        f"{len(personas)} personas x {len(conditions)} conditions = {total} runs\n"
    )

    results: list[ExperimentResult] = []
    for i, persona in enumerate(personas, 1):
        _console.print(
            f"[bold yellow]Persona {i}/{len(personas)}:[/bold yellow] "
            f"{persona.id} — {persona.name}"
        )
        for condition in conditions:
            result = await run_single(
                persona=persona,
                condition=condition,
                model=model,
                prompt_version=prompt_version,
            )
            save_result(result, results_dir=results_dir)
            results.append(result)
        _console.print()

    _console.print(
        f"[bold green]Experiment complete:[/bold green] {len(results)} results saved.\n"
    )
    return results
