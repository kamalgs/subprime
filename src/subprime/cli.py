"""Subprime CLI — Typer entry point for running experiments and analysis.

Entry point configured in pyproject.toml as: subprime = "subprime.cli:app"
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt

load_dotenv()

from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.display import format_plan_summary, format_strategy_outline
from subprime.core.models import ExperimentResult

app = typer.Typer(
    name="subprime",
    help="Subprime — measure hidden bias in LLM financial advisors.",
)


def _check_api_key(model: str) -> None:
    """Validate that the required API key is set before making LLM calls."""
    import os

    if model.startswith("anthropic:"):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key.startswith("sk-ant-..."):
            _console.print(
                "[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set.\n"
                "Copy .env.example to .env and add your key, or export it:\n"
                "  export ANTHROPIC_API_KEY=sk-ant-..."
            )
            raise typer.Exit(code=1)
    elif model.startswith("openai:"):
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            _console.print(
                "[bold red]Error:[/bold red] OPENAI_API_KEY not set.\n"
                "Export it: export OPENAI_API_KEY=sk-..."
            )
            raise typer.Exit(code=1)

_console = Console()


@app.command()
def experiment_run(
    persona: Optional[str] = typer.Option(
        None,
        "--persona",
        "-p",
        help="Single persona ID to run (default: all personas).",
    ),
    conditions: str = typer.Option(
        "baseline,lynch",
        "--conditions",
        "-c",
        help="Comma-separated condition names (e.g. baseline,lynch,bogle).",
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="LLM model identifier.",
    ),
    prompt_version: str = typer.Option(
        "v1",
        "--prompt-version",
        help="Prompt version tag for tracking.",
    ),
    results_dir: Optional[Path] = typer.Option(
        None,
        "--results-dir",
        help="Directory to save result JSON files.",
    ),
) -> None:
    """Run the experiment: generate plans for personas x conditions, then score them."""
    _check_api_key(model)
    from subprime.experiments.runner import run_experiment

    persona_ids = [persona] if persona else None
    condition_names = [c.strip() for c in conditions.split(",") if c.strip()]

    asyncio.run(
        run_experiment(
            persona_ids=persona_ids,
            condition_names=condition_names,
            model=model,
            prompt_version=prompt_version,
            results_dir=results_dir,
        )
    )


@app.command()
def experiment_analyze(
    results_dir: Path = typer.Option(
        ...,
        "--results-dir",
        help="Directory containing experiment result JSON files.",
    ),
) -> None:
    """Analyze experiment results from a directory of JSON files."""
    from subprime.experiments.analysis import print_analysis

    if not results_dir.exists():
        _console.print(f"[bold red]Error:[/bold red] Results directory does not exist: {results_dir}")
        raise typer.Exit(code=1)

    if not results_dir.is_dir():
        _console.print(f"[bold red]Error:[/bold red] Not a directory: {results_dir}")
        raise typer.Exit(code=1)

    # Load all JSON files from the directory
    json_files = sorted(results_dir.glob("*.json"))
    if not json_files:
        _console.print(f"[bold red]Error:[/bold red] No JSON result files found in {results_dir}")
        raise typer.Exit(code=1)

    results: list[ExperimentResult] = []
    for jf in json_files:
        try:
            result = ExperimentResult.model_validate_json(jf.read_text())
            results.append(result)
        except Exception as exc:
            _console.print(f"[yellow]Warning:[/yellow] Skipping {jf.name}: {exc}")

    if not results:
        _console.print("[bold red]Error:[/bold red] No valid experiment results loaded.")
        raise typer.Exit(code=1)

    _console.print(f"Loaded {len(results)} results from {results_dir}\n")
    print_analysis(results)


@app.command()
def advise(
    profile_id: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Persona ID from bank (e.g. P01). Skips interactive profile gathering.",
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="LLM model identifier.",
    ),
) -> None:
    """Interactive financial advisor — gather profile, co-create strategy, generate plan."""
    _check_api_key(model)

    # Phase 1: Profile
    if profile_id:
        from subprime.evaluation.personas import get_persona

        profile = get_persona(profile_id)
        _console.print(f"\n[bold]Using profile:[/bold] {profile.name} ({profile.id})\n")
    else:
        from subprime.advisor.profile import gather_profile

        async def _rich_prompt(message: str) -> str:
            _console.print(f"\n[bold]{message}[/bold]")
            return Prompt.ask(">")

        profile = asyncio.run(gather_profile(send_message=_rich_prompt, model=model))
        _console.print(f"\n[bold]Profile ready:[/bold] {profile.name}\n")

    # Phase 2: Strategy co-creation
    _console.print("[dim]Generating strategy...[/dim]")
    strategy = asyncio.run(generate_strategy(profile, model=model))
    print(format_strategy_outline(strategy), end="")

    while True:
        response = Prompt.ask(
            "\nReady to find specific funds? ([bold green]yes[/bold green] / tell me what to adjust)"
        )
        if response.strip().lower() in ("yes", "y"):
            break
        _console.print("[dim]Revising strategy...[/dim]")
        strategy = asyncio.run(
            generate_strategy(profile, feedback=response, current_strategy=strategy, model=model)
        )
        print(format_strategy_outline(strategy), end="")

    # Phase 3: Detailed plan
    _console.print("\n[dim]Generating detailed plan with specific funds...[/dim]")
    plan = asyncio.run(generate_plan(profile, strategy=strategy, model=model))
    print(format_plan_summary(plan), end="")


if __name__ == "__main__":
    app()
