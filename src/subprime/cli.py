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
from rich.console import Console

from subprime.core.models import ExperimentResult

app = typer.Typer(
    name="subprime",
    help="Subprime — measure hidden bias in LLM financial advisors.",
)

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


if __name__ == "__main__":
    app()
