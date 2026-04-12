"""Subprime CLI — Typer entry point for running experiments and analysis.

Entry point configured in pyproject.toml as: subprime = "subprime.cli:app"
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule

LOG_DIR = Path.home() / ".subprime"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "subprime.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("subprime")

load_dotenv()

from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.config import CONVERSATIONS_DIR, DB_PATH, DEFAULT_MODEL
from subprime.core.display import format_plan_summary, format_profile_card, format_strategy_outline
from subprime.core.models import ConversationLog, ConversationTurn, ExperimentResult

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
        DEFAULT_MODEL,
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

    try:
        asyncio.run(
            run_experiment(
                persona_ids=persona_ids,
                condition_names=condition_names,
                model=model,
                prompt_version=prompt_version,
                results_dir=results_dir,
            )
        )
    except KeyboardInterrupt:
        _console.print("\n[dim]Interrupted.[/dim]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("experiment-run command failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        _console.print(f"[dim]Full traceback logged to {LOG_FILE}[/dim]")
        raise typer.Exit(1)


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
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="LLM model identifier.",
    ),
    mode: str = typer.Option(
        "basic",
        "--mode",
        help="Plan generation mode: 'basic' (single plan) or 'premium' (multi-perspective comparison).",
    ),
    perspectives: int = typer.Option(
        3,
        "--perspectives",
        help="Number of perspectives for premium mode (3 or 5).",
    ),
) -> None:
    """FinAdvisor — interactive mutual fund advisor: gather profile, co-create strategy, generate plan."""
    _check_api_key(model)

    conversation = ConversationLog(model=model)
    profile_turns: list[ConversationTurn] = []

    try:
        # Phase 1: Profile
        _console.print()
        _console.print(Rule("[bold]Phase 1: Investor Profile[/bold]", style="blue"))
        if profile_id:
            from subprime.evaluation.personas import get_persona

            profile = get_persona(profile_id)
        else:
            from subprime.advisor.profile import gather_profile

            async def _rich_prompt(message: str) -> str:
                _console.print(f"\n[bold]{message}[/bold]")
                resp = Prompt.ask(">")
                profile_turns.append(ConversationTurn(role="advisor", content=message))
                profile_turns.append(ConversationTurn(role="user", content=resp))
                return resp

            profile = asyncio.run(gather_profile(send_message=_rich_prompt, model=model))

        _console.print()
        print(format_profile_card(profile), end="")

        conversation.profile = profile
        conversation.profile_turns = profile_turns

        # Phase 2: Strategy co-creation
        _console.print(Rule("[bold]Phase 2: Strategy[/bold]", style="blue"))
        with _console.status("[bold blue]Crafting your strategy...[/bold blue]"):
            strategy = asyncio.run(generate_strategy(profile, model=model))
        print(format_strategy_outline(strategy), end="")
        conversation.strategy = strategy

        while True:
            response = Prompt.ask(
                "\nReady to find specific funds? ([bold green]yes[/bold green] / tell me what to adjust)"
            )
            if response.strip().lower() in ("yes", "y"):
                break
            conversation.strategy_revisions.append(ConversationTurn(role="user", content=response))
            with _console.status("[bold blue]Revising strategy...[/bold blue]"):
                strategy = asyncio.run(
                    generate_strategy(profile, feedback=response, current_strategy=strategy, model=model)
                )
            print(format_strategy_outline(strategy), end="")
            conversation.strategy = strategy

        # Phase 3: Detailed plan
        _console.print(Rule("[bold]Phase 3: Fund Selection[/bold]", style="blue"))
        if mode == "premium":
            from subprime.advisor.perspectives import get_default_perspectives
            perspective_list = get_default_perspectives(perspectives)
            names = [p.description for p in perspective_list]
            _console.print(f"[dim]Premium mode: comparing {perspectives} perspectives[/dim]")
            for n in names:
                _console.print(f"[dim]  \u2022 {n}[/dim]")
            status_msg = "[bold blue]Generating perspectives and comparing...[/bold blue]"
        else:
            status_msg = "[bold blue]Selecting funds and building your plan...[/bold blue]"
        with _console.status(status_msg):
            plan = asyncio.run(
                generate_plan(profile, strategy=strategy, mode=mode, n_perspectives=perspectives, model=model)
            )
        print(
            format_plan_summary(
                plan,
                strategy=strategy,
                monthly_sip=profile.monthly_investible_surplus_inr,
                horizon_years=profile.investment_horizon_years,
            ),
            end="",
        )
        conversation.plan = plan

        # Save conversation
        _save_conversation(conversation)

    except KeyboardInterrupt:
        _console.print("\n[dim]Interrupted.[/dim]")
        if conversation.profile:
            _save_conversation(conversation)
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("advise command failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        _console.print(f"[dim]Full traceback logged to {LOG_FILE}[/dim]")
        if conversation.profile:
            _save_conversation(conversation)
        raise typer.Exit(1)


def _save_conversation(conv: ConversationLog) -> Path:
    """Save a conversation log to the conversations directory."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONVERSATIONS_DIR / f"{conv.id}.json"
    path.write_text(conv.model_dump_json(indent=2))
    _console.print(f"\n[dim]Conversation saved to {path}[/dim]")
    return path


@app.command()
def replay(
    path: Path = typer.Argument(
        ...,
        help="Path to a conversation JSON file, or 'latest' for most recent.",
    ),
) -> None:
    """Replay a saved conversation — shows profile, strategy, and plan."""
    if str(path) == "latest":
        if not CONVERSATIONS_DIR.exists():
            _console.print("[bold red]Error:[/bold red] No conversations directory found.")
            raise typer.Exit(1)
        files = sorted(CONVERSATIONS_DIR.glob("*.json"))
        if not files:
            _console.print("[bold red]Error:[/bold red] No saved conversations found.")
            raise typer.Exit(1)
        path = files[-1]

    if not path.exists():
        _console.print(f"[bold red]Error:[/bold red] File not found: {path}")
        raise typer.Exit(1)

    conv = ConversationLog.model_validate_json(path.read_text())

    _console.print(f"\n[bold]Conversation:[/bold] {conv.id} ({conv.timestamp:%Y-%m-%d %H:%M} UTC)")
    _console.print(f"[bold]Model:[/bold] {conv.model}\n")

    # Profile
    _console.print(Rule("[bold]Phase 1: Investor Profile[/bold]", style="blue"))
    print(format_profile_card(conv.profile), end="")

    if conv.profile_turns:
        _console.print(f"[bold]Profile conversation:[/bold] ({len(conv.profile_turns)} turns)")
        for turn in conv.profile_turns:
            prefix = "[bold cyan]Advisor:[/bold cyan]" if turn.role == "advisor" else "[bold green]You:[/bold green]"
            _console.print(f"  {prefix} {turn.content}")
        _console.print()

    # Strategy
    if conv.strategy:
        _console.print(Rule("[bold]Phase 2: Strategy[/bold]", style="blue"))
        print(format_strategy_outline(conv.strategy), end="")

    if conv.strategy_revisions:
        _console.print(f"[bold]Strategy revisions:[/bold] ({len(conv.strategy_revisions)} rounds)")
        for turn in conv.strategy_revisions:
            _console.print(f"  [bold green]You:[/bold green] {turn.content}")
        _console.print()

    # Plan
    if conv.plan:
        _console.print(Rule("[bold]Phase 3: Fund Selection[/bold]", style="blue"))
        print(format_plan_summary(conv.plan, strategy=conv.strategy), end="")


@app.command()
def web(
    port: int = typer.Option(
        7860,
        "--port",
        "-P",
        help="Port for the Gradio web server.",
    ),
    share: bool = typer.Option(
        False,
        "--share",
        help="Create a public shareable link via Gradio.",
    ),
) -> None:
    """Launch the Gradio web interface."""
    import sys

    # Ensure the project root (where apps/ lives) is on sys.path
    _project_root = str(Path(__file__).resolve().parent.parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from apps.web.app import CSS, create_app

    demo = create_app()
    demo.launch(server_port=port, share=share, css=CSS)


# ---------------------------------------------------------------------------
# data sub-commands
# ---------------------------------------------------------------------------


data_app = typer.Typer(name="data", help="Manage the local fund data store.")
app.add_typer(data_app, name="data")


@data_app.command("refresh")
def data_refresh() -> None:
    """Download the latest mutual fund dataset and rebuild the local store."""
    import duckdb

    from subprime.core.config import DATA_DIR
    from subprime.data.ingest import refresh as run_refresh
    from subprime.data.store import ensure_schema
    from subprime.data.universe import build_universe

    try:
        _console.print("[dim]Downloading dataset (this may take a few minutes)...[/dim]")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(DB_PATH))
        ensure_schema(conn)
        stats = asyncio.run(run_refresh(conn, DATA_DIR))
        _console.print(
            f"[green]Loaded[/green] {stats['scheme_count']:,} schemes, "
            f"{stats['nav_count']:,} NAV records, "
            f"{stats['returns_count']:,} computed returns."
        )
        _console.print("[dim]Building curated fund universe...[/dim]")
        universe_count = build_universe(conn)
        _console.print(f"[green]Universe ready:[/green] {universe_count} funds curated.")

        _console.print("[dim]Enriching with expense ratios (live)...[/dim]")
        from subprime.data.ingest import enrich_universe_with_expense_ratios
        enrichment = asyncio.run(enrich_universe_with_expense_ratios(conn))
        _console.print(
            f"[green]Enriched:[/green] {enrichment['enriched']} live, "
            f"{enrichment['fallback']} fallback (category-typical)."
        )
        conn.close()
    except KeyboardInterrupt:
        _console.print("\n[dim]Interrupted.[/dim]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("data refresh failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        _console.print(f"[dim]Full traceback logged to {LOG_FILE}[/dim]")
        raise typer.Exit(1)


@data_app.command("stats")
def data_stats() -> None:
    """Show the current state of the local fund data store."""
    import duckdb

    from subprime.data.store import get_refresh_stats

    if not DB_PATH.exists():
        _console.print("[yellow]No data store found.[/yellow]")
        _console.print("Run [bold]subprime data refresh[/bold] to populate it.")
        return

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        stats = get_refresh_stats(conn)
        if stats is None:
            _console.print("[yellow]Data store exists but no refreshes recorded yet.[/yellow]")
            return

        returns_total = conn.execute("SELECT COUNT(*) FROM fund_returns").fetchone()[0]
        universe_total = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0]

        _console.print(f"\n[bold]Subprime Data Store[/bold]  ({DB_PATH})")
        _console.print(f"  Last refreshed  : {stats['refreshed_at']}")
        _console.print(f"  Schemes         : {stats['scheme_count']:,}")
        _console.print(f"  NAV records     : {stats['nav_count']:,}")
        _console.print(f"  Computed returns: {returns_total:,}")
        _console.print(f"  Curated universe: {universe_total:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    app()
