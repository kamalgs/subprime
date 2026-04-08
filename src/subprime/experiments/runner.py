"""Experiment runner — generates plans for all personas × conditions and scores them."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from subprime.agents.advisor import Condition, generate_plan
from subprime.agents.judges import score_plan_aps, score_plan_pqs
from subprime.models.persona import InvestorPersona
from subprime.models.scores import ExperimentResult

console = Console()

RESULTS_DIR = Path(__file__).parent / "results"
PERSONAS_DIR = Path(__file__).parent.parent / "personas"

CONDITIONS: list[Condition] = ["baseline", "lynch", "bogle"]


def load_personas(path: Path | None = None) -> list[InvestorPersona]:
    """Load persona bank from JSON file."""
    path = path or PERSONAS_DIR / "bank.json"
    if not path.exists():
        raise FileNotFoundError(f"Persona bank not found: {path}")
    with open(path) as f:
        data = json.load(f)
    return [InvestorPersona(**p) for p in data]


def save_result(result: ExperimentResult) -> Path:
    """Save a single experiment result as JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{result.persona_id}_{result.condition}_{result.timestamp:%Y%m%d_%H%M%S}.json"
    path = RESULTS_DIR / filename
    path.write_text(result.model_dump_json(indent=2))
    return path


async def run_single(
    persona: InvestorPersona,
    condition: Condition,
    model: str = "anthropic:claude-sonnet-4-6",
    prompt_version: str = "v1",
) -> ExperimentResult:
    """Run a single experiment: generate plan, score APS and PQS."""
    console.print(f"  [dim]Generating plan for {persona.id} × {condition}...[/dim]")
    plan = await generate_plan(persona, condition, model=model)

    console.print(f"  [dim]Scoring APS...[/dim]")
    aps = await score_plan_aps(plan, model=model)

    console.print(f"  [dim]Scoring PQS...[/dim]")
    pqs = await score_plan_pqs(plan, persona, model=model)

    result = ExperimentResult(
        persona_id=persona.id,
        condition=condition,
        model=model,
        plan=plan,
        aps=aps,
        pqs=pqs,
        prompt_version=prompt_version,
    )
    save_result(result)

    console.print(
        f"  [green]✓[/green] {persona.id} × {condition}: "
        f"APS={aps.composite_aps:.3f}, PQS={pqs.composite_pqs:.3f}"
    )
    return result


async def run_experiment(
    personas: list[InvestorPersona] | None = None,
    conditions: list[Condition] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
    prompt_version: str = "v1",
) -> list[ExperimentResult]:
    """Run the full experiment matrix: all personas × all conditions."""
    personas = personas or load_personas()
    conditions = conditions or CONDITIONS

    total = len(personas) * len(conditions)
    console.print(f"\n[bold]Running {total} experiments ({len(personas)} personas × {len(conditions)} conditions)[/bold]\n")

    results = []
    for persona in personas:
        console.print(f"\n[bold cyan]{persona.id}: {persona.name}[/bold cyan] (age {persona.age}, {persona.risk_appetite})")
        for condition in conditions:
            result = await run_single(persona, condition, model=model, prompt_version=prompt_version)
            results.append(result)

    console.print(f"\n[bold green]✓ Completed {len(results)} experiments[/bold green]")
    console.print(f"  Results saved to: {RESULTS_DIR.resolve()}")
    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Subprime experiments")
    parser.add_argument("--persona", type=str, help="Run single persona by ID (e.g. P01)")
    parser.add_argument("--condition", type=str, choices=CONDITIONS, help="Run single condition")
    parser.add_argument("--model", type=str, default="anthropic:claude-sonnet-4-6")
    parser.add_argument("--prompt-version", type=str, default="v1")
    args = parser.parse_args()

    if args.persona:
        all_personas = load_personas()
        personas = [p for p in all_personas if p.id == args.persona]
        if not personas:
            console.print(f"[red]Persona {args.persona} not found[/red]")
            return
    else:
        personas = None

    conditions = [args.condition] if args.condition else None

    asyncio.run(run_experiment(
        personas=personas,
        conditions=conditions,
        model=args.model,
        prompt_version=args.prompt_version,
    ))


if __name__ == "__main__":
    main()
