"""Subprime CLI — Typer entry point for running experiments and analysis.

Entry point configured in pyproject.toml as: subprime = "subprime.cli:app"
"""

from __future__ import annotations

import asyncio
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
from subprime.core.config import ADVISOR_MODEL, CONVERSATIONS_DIR, DB_PATH, REFINE_MODEL
from subprime.core.display import format_plan_summary, format_profile_card, format_strategy_outline
from subprime.core.models import (
    APSScore,
    ConversationLog,
    ConversationTurn,
    ExperimentResult,
    PlanQualityScore,
)

app = typer.Typer(
    name="subprime",
    help="Subprime — measure hidden bias in LLM financial advisors.",
)


def _default_results_dir() -> Path:
    """Return results/YYYYMMDD_<git-short-hash>, falling back to results/YYYYMMDD if git unavailable."""
    import subprocess
    from datetime import date

    datestamp = date.today().strftime("%Y%m%d")
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).parent,
            )
            .decode()
            .strip()
        )
        return Path("results") / f"{datestamp}_{sha}"
    except Exception:
        return Path("results") / datestamp


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
    elif model.startswith("together:"):
        key = os.environ.get("TOGETHER_API_KEY", "")
        if not key:
            _console.print(
                "[bold red]Error:[/bold red] TOGETHER_API_KEY not set.\n"
                "Export it: export TOGETHER_API_KEY=tgp_v1_..."
            )
            raise typer.Exit(code=1)
    elif model.startswith("bedrock:"):
        # Rely on boto3's chain: env vars, ~/.aws/credentials, instance profile.
        import boto3

        try:
            boto3.client("sts").get_caller_identity()
        except Exception as exc:
            _console.print(
                "[bold red]Error:[/bold red] AWS credentials not usable by Bedrock.\n"
                f"  boto3 said: {exc}\n"
                "Configure via ~/.aws/credentials or AWS_ACCESS_KEY_ID env."
            )
            raise typer.Exit(code=1)
    elif model.startswith("vllm:"):
        url = (
            os.environ.get("VLLM_BASE_URL")
            or os.environ.get("VLLM_ADVISOR_BASE_URL")
            or os.environ.get("VLLM_JUDGE_BASE_URL")
        )
        if not url:
            _console.print(
                "[bold red]Error:[/bold red] No vLLM endpoint configured.\n"
                "Set at least one of VLLM_BASE_URL, VLLM_ADVISOR_BASE_URL,\n"
                "or VLLM_JUDGE_BASE_URL:\n"
                "  export VLLM_ADVISOR_BASE_URL=http://<adv-ip>:8000/v1\n"
                "  export VLLM_JUDGE_BASE_URL=http://<judge-ip>:8000/v1"
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
    personas_file: Optional[Path] = typer.Option(
        None,
        "--personas",
        help="Path to a custom persona bank JSON (default: bundled bank.json).",
    ),
    conditions: str = typer.Option(
        "baseline,lynch,bogle",
        "--conditions",
        "-c",
        help="Comma-separated condition names (e.g. baseline,lynch,bogle).",
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="LLM model identifier for the advisor.",
    ),
    judge_model: Optional[str] = typer.Option(
        None,
        "--judge-model",
        "-j",
        help="LLM model for judges (APS + PQS). Defaults to --model if not set.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help=(
            "Anthropic API key for this run. Overrides ANTHROPIC_API_KEY. "
            "Falls back to ANTHROPIC_API_KEY_EXPERIMENT env var if not set. "
            "Useful for cost isolation across runs."
        ),
    ),
    prompt_version: str = typer.Option(
        "v1",
        "--prompt-version",
        help="Prompt version tag for tracking.",
    ),
    results_dir: Optional[Path] = typer.Option(
        None,
        "--results-dir",
        help=("Directory to save result JSON files. Defaults to results/YYYYMMDD_<git-hash>."),
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Skip already-completed (persona, condition) pairs in results-dir.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show cost estimate and exit without making any API calls.",
    ),
    concurrency: int = typer.Option(
        5,
        "--concurrency",
        min=1,
        max=200,
        help="Number of parallel runs (1 = sequential).",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help=(
            "Use Anthropic Message Batches API (50%% cost discount). "
            "Ignores --concurrency; processing takes up to 24h."
        ),
    ),
    thinking: bool = typer.Option(
        False,
        "--thinking",
        help=(
            "Enable extended thinking for advisor (two-turn: think then structure) "
            "and judges (medium budget ~10K tokens). Improves reasoning depth "
            "but roughly doubles token usage."
        ),
    ),
) -> None:
    """Run the experiment: generate plans for personas x conditions, then score them."""
    import os

    if results_dir is None:
        results_dir = _default_results_dir()

    # Resolve which API key to use: --api-key > ANTHROPIC_API_KEY_EXPERIMENT > ANTHROPIC_API_KEY
    resolved_key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY_EXPERIMENT")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if resolved_key:
        os.environ["ANTHROPIC_API_KEY"] = resolved_key

    persona_ids = [persona] if persona else None
    condition_names = [c.strip() for c in conditions.split(",") if c.strip()]

    from subprime.evaluation.personas import get_persona, load_personas
    from subprime.experiments.conditions import get_condition
    from subprime.experiments.estimator import estimate_experiment, print_estimate

    resolved_personas = (
        [get_persona(pid, path=personas_file) for pid in persona_ids]
        if persona_ids
        else load_personas(path=personas_file)
    )
    resolved_conditions = [get_condition(name) for name in condition_names]

    est = estimate_experiment(
        n_personas=len(resolved_personas),
        conditions=resolved_conditions,
        model=model,
        judge_model=judge_model,
        concurrency=concurrency,
    )
    print_estimate(est)

    if dry_run:
        raise typer.Exit(0)

    _check_api_key(model)

    key_source = (
        "--api-key flag"
        if api_key
        else "ANTHROPIC_API_KEY_EXPERIMENT"
        if os.environ.get("ANTHROPIC_API_KEY_EXPERIMENT")
        else "ANTHROPIC_API_KEY"
    )
    _console.print(f"[dim]Using API key from: {key_source}[/dim]")

    try:
        if batch:
            from subprime.experiments.batch_runner import run_experiment_batch

            asyncio.run(
                run_experiment_batch(
                    persona_ids=persona_ids,
                    condition_names=condition_names,
                    model=model,
                    judge_model=judge_model,
                    prompt_version=prompt_version,
                    results_dir=results_dir,
                    resume=resume,
                    personas_file=personas_file,
                )
            )
        else:
            from subprime.experiments.runner import run_experiment

            asyncio.run(
                run_experiment(
                    persona_ids=persona_ids,
                    condition_names=condition_names,
                    model=model,
                    judge_model=judge_model,
                    prompt_version=prompt_version,
                    results_dir=results_dir,
                    resume=resume,
                    concurrency=concurrency,
                    thinking=thinking,
                    personas_file=personas_file,
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
def experiment_estimate(
    persona: Optional[str] = typer.Option(
        None,
        "--persona",
        "-p",
        help="Single persona ID (default: all personas).",
    ),
    personas_file: Optional[Path] = typer.Option(
        None,
        "--personas",
        help="Path to a custom persona bank JSON (default: bundled bank.json).",
    ),
    conditions: str = typer.Option(
        "baseline,lynch,bogle",
        "--conditions",
        "-c",
        help="Comma-separated condition names.",
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="Advisor model identifier.",
    ),
    judge_model: Optional[str] = typer.Option(
        None,
        "--judge-model",
        "-j",
        help="Judge model (defaults to --model).",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        help="Show a side-by-side cost table for all standard model configurations.",
    ),
    concurrency: int = typer.Option(
        5,
        "--concurrency",
        min=1,
        max=20,
        help="Parallel runs to assume for wall-time estimate.",
    ),
) -> None:
    """Show estimated token usage and cost for an experiment run (no API calls).

    Use --compare to see haiku+haiku / haiku+sonnet / sonnet+sonnet / sonnet+opus
    side by side so you can pick the right cost-quality trade-off.
    """
    from subprime.evaluation.personas import get_persona, load_personas
    from subprime.experiments.conditions import get_condition
    from subprime.experiments.estimator import (
        compare_configs,
        estimate_experiment,
        print_comparison,
        print_estimate,
    )

    persona_ids = [persona] if persona else None
    condition_names = [c.strip() for c in conditions.split(",") if c.strip()]

    resolved_personas = (
        [get_persona(pid, path=personas_file) for pid in persona_ids]
        if persona_ids
        else load_personas(path=personas_file)
    )
    resolved_conditions = [get_condition(name) for name in condition_names]

    if compare:
        comparisons = compare_configs(
            n_personas=len(resolved_personas),
            conditions=resolved_conditions,
            concurrency=concurrency,
        )
        print_comparison(comparisons, default_model=model, default_judge=judge_model)
    else:
        est = estimate_experiment(
            n_personas=len(resolved_personas),
            conditions=resolved_conditions,
            model=model,
            judge_model=judge_model,
            concurrency=concurrency,
        )
        print_estimate(est)


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
        _console.print(
            f"[bold red]Error:[/bold red] Results directory does not exist: {results_dir}"
        )
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
def experiment_score(
    source_dir: Path = typer.Argument(
        ...,
        help="Directory of existing experiment result JSONs to re-score.",
    ),
    results_dir: Path = typer.Argument(
        ...,
        help="Output directory for re-scored result JSONs.",
    ),
    judge_model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--judge-model",
        "-j",
        help="LLM model to use for APS + PQS judges.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Anthropic API key override. Falls back to ANTHROPIC_API_KEY_EXPERIMENT.",
    ),
    thinking: bool = typer.Option(
        True,
        "--thinking/--no-thinking",
        help="Enable/disable extended thinking for the judge.",
    ),
) -> None:
    """Re-score existing plan JSONs with a different judge model.

    Loads plans from SOURCE_DIR, runs APS + PQS judges with the given
    judge model, and writes new result JSONs to RESULTS_DIR.
    Useful for comparing judge models without re-generating plans.
    """
    import os

    resolved_key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY_EXPERIMENT")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if resolved_key:
        os.environ["ANTHROPIC_API_KEY"] = resolved_key

    _check_api_key(judge_model)

    if not source_dir.exists() or not source_dir.is_dir():
        _console.print(f"[bold red]Error:[/bold red] Source directory not found: {source_dir}")
        raise typer.Exit(1)

    json_files = sorted(source_dir.glob("*.json"))
    if not json_files:
        _console.print(f"[bold red]Error:[/bold red] No JSON files in {source_dir}")
        raise typer.Exit(1)

    import json as _json
    from subprime.core.models import InvestmentPlan

    results: list[ExperimentResult] = []
    for jf in json_files:
        try:
            results.append(ExperimentResult.model_validate_json(jf.read_text()))
        except Exception:
            # Old schema (e.g. missing portfolio_activeness_score): extract
            # just the fields needed for re-scoring and build a stub result.
            try:
                raw = _json.loads(jf.read_text())
                stub_aps = APSScore(
                    passive_instrument_fraction=0.5,
                    turnover_score=0.5,
                    cost_emphasis_score=0.5,
                    research_vs_cost_score=0.5,
                    time_horizon_alignment_score=0.5,
                    portfolio_activeness_score=0.5,
                    reasoning="(placeholder — will be re-scored)",
                )
                stub_pqs = PlanQualityScore(
                    goal_alignment=0.5,
                    diversification=0.5,
                    risk_return_appropriateness=0.5,
                    internal_consistency=0.5,
                    tax_efficiency=0.5,
                    reasoning="(placeholder — will be re-scored)",
                )
                results.append(
                    ExperimentResult(
                        persona_id=raw["persona_id"],
                        condition=raw["condition"],
                        model=raw.get("model", "unknown"),
                        judge_model=raw.get("judge_model"),
                        plan=InvestmentPlan.model_validate(raw["plan"]),
                        aps=stub_aps,
                        pqs=stub_pqs,
                        prompt_version=raw.get("prompt_version", "v1"),
                    )
                )
            except Exception as exc2:
                _console.print(f"[yellow]Warning:[/yellow] Skipping {jf.name}: {exc2}")

    if not results:
        _console.print("[bold red]Error:[/bold red] No valid results loaded.")
        raise typer.Exit(1)

    from subprime.evaluation.personas import load_personas
    from subprime.experiments.runner import rescore_results

    persona_map = {p.id: p for p in load_personas()}

    _console.print(
        f"\n[bold]Re-scoring {len(results)} results[/bold]\n"
        f"  Source : {source_dir}\n"
        f"  Output : {results_dir}\n"
        f"  Judge  : {judge_model}\n"
    )

    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        rescored = asyncio.run(
            rescore_results(
                results,
                judge_model=judge_model,
                personas=persona_map,
                thinking=thinking,
                results_dir=results_dir,
            )
        )
        _console.print(
            f"\n[bold green]Done:[/bold green] {len(rescored)} results saved to {results_dir}\n"
        )
    except KeyboardInterrupt:
        _console.print("\n[dim]Interrupted.[/dim]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("experiment-score command failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        _console.print(f"[dim]Full traceback logged to {LOG_FILE}[/dim]")
        raise typer.Exit(1)


@app.command()
def advise(
    profile_id: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Persona ID from bank (e.g. P01). Skips interactive profile gathering.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="LLM model identifier. Defaults to ADVISOR_MODEL (basic) or REFINE_MODEL (premium).",
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
    if model is None:
        model = REFINE_MODEL if mode == "premium" and REFINE_MODEL else ADVISOR_MODEL
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
            strategy, _ = asyncio.run(generate_strategy(profile, model=model))
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
                strategy, _ = asyncio.run(
                    generate_strategy(
                        profile, feedback=response, current_strategy=strategy, model=model
                    )
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
            plan, _ = asyncio.run(
                generate_plan(
                    profile,
                    strategy=strategy,
                    mode=mode,
                    n_perspectives=perspectives,
                    model=model,
                    refine_model=REFINE_MODEL if mode == "premium" else None,
                )
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
    """Save a conversation log using the shared persistence layer."""
    from subprime.core.conversations import save_conversation as _save
    from subprime.core.db import get_pool
    from subprime.core.models import Session

    session = Session(
        id=conv.id,
        mode="basic",
        current_step=4,
        profile=conv.profile,
        strategy=conv.strategy,
        plan=conv.plan,
        strategy_chat=conv.strategy_revisions,
    )
    path = asyncio.run(_save(session=session, pool=get_pool()))
    if path:
        _console.print(f"\n[dim]Conversation saved to {path}[/dim]")
    else:
        _console.print("\n[dim]Conversation saved to database[/dim]")
    return path or Path(".")


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
            prefix = (
                "[bold cyan]Advisor:[/bold cyan]"
                if turn.role == "advisor"
                else "[bold green]You:[/bold green]"
            )
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
        8091,
        "--port",
        "-P",
        help="Port for the web server.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host to bind to.",
    ),
) -> None:
    """Launch the FinAdvisor web interface."""

    # Ensure the project root (where apps/ lives) is on sys.path
    _project_root = str(Path(__file__).resolve().parent.parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    import uvicorn

    _console.print(f"[bold]FinAdvisor[/bold] starting at http://{host}:{port}")
    uvicorn.run("apps.web.main:create_app", factory=True, host=host, port=port)


# ---------------------------------------------------------------------------
# smoke-test
# ---------------------------------------------------------------------------


@app.command()
def smoke_test(
    n_personas: int = typer.Option(
        2,
        "--n-personas",
        "-n",
        help="Number of personas to run (default 2 — shows cross-persona cache hits).",
        min=1,
        max=10,
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="LLM model identifier for the advisor.",
    ),
    judge_model: Optional[str] = typer.Option(
        None,
        "--judge-model",
        "-j",
        help="LLM model for judges. Defaults to --model.",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Save result JSONs to the default results directory.",
    ),
) -> None:
    """Smoke test: N personas x 2 conditions — verifies wiring and cache efficiency.

    Default (--n-personas 2) runs a 2×2 matrix: 2 personas × baseline + bogle.
    Expect cache_write on the first call, cache_read on every subsequent call
    for judges (fully static system prompt) and on same-condition calls for
    the advisor (system prompt is stable within a condition).
    Exit 0 on success.
    """
    from pydantic_ai.usage import RunUsage

    from subprime.evaluation.personas import load_personas
    from subprime.experiments.conditions import BASELINE, BOGLE
    from subprime.experiments.runner import run_single, save_result

    _check_api_key(model)

    all_personas = load_personas()
    personas = all_personas[:n_personas]
    effective_judge = judge_model or model
    conditions = (BASELINE, BOGLE)
    total_runs = len(personas) * len(conditions)

    _console.print(
        f"\n[bold]Smoke test[/bold]  {len(personas)} persona(s) × 2 conditions = {total_runs} runs\n"
        f"  Advisor : {model}\n"
        f"  Judge   : {effective_judge}\n"
    )

    # (persona_id, condition_name, RunUsage)
    rows: list[tuple[str, str, RunUsage]] = []

    async def _run() -> None:
        for persona_obj in personas:
            for condition in conditions:
                result, usage = await run_single(
                    persona_obj, condition, model=model, judge_model=judge_model
                )
                rows.append((persona_obj.id, condition.name, usage))
                if save:
                    save_result(result)

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("smoke-test failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)

    # Per-run table
    _console.print("[bold]Per-run token breakdown:[/bold]")
    _console.print(
        f"  {'#':>2}  {'persona':8}  {'condition':10}  {'input':>8}  {'output':>7}  {'cache_wr':>9}  {'cache_rd':>9}"
    )
    _console.print(
        f"  {'─' * 2}  {'─' * 8}  {'─' * 10}  {'─' * 8}  {'─' * 7}  {'─' * 9}  {'─' * 9}"
    )

    total_cache_read = 0
    total_cache_write = 0
    for i, (pid, cond_name, usage) in enumerate(rows, 1):
        cache_rd = usage.cache_read_tokens or 0
        cache_wr = usage.cache_write_tokens or 0
        total_cache_read += cache_rd
        total_cache_write += cache_wr
        rd_str = f"[green]{cache_rd:>9,}[/green]" if cache_rd else f"{'—':>9}"
        wr_str = f"[yellow]{cache_wr:>9,}[/yellow]" if cache_wr else f"{'—':>9}"
        _console.print(
            f"  {i:>2}  {pid:8}  {cond_name:10}  "
            f"{usage.input_tokens or 0:>8,}  {usage.output_tokens or 0:>7,}  "
            f"{wr_str}  {rd_str}"
        )

    # Summary
    _console.print()
    if total_cache_read > 0:
        pct = (
            100
            * total_cache_read
            / (total_cache_read + sum(u.input_tokens or 0 for _, _, u in rows))
        )
        _console.print(
            f"[bold green]✓ Cache working[/bold green] — "
            f"{total_cache_read:,} tokens served from cache  "
            f"[dim](~{pct:.0f}% of gross input)[/dim]"
        )
        if n_personas >= 2:
            _console.print(
                "[dim]  Judges: hits from run 2 onwards (static system prompt)[/dim]\n"
                "[dim]  Advisor: hits when same condition repeats across personas[/dim]"
            )
    elif total_cache_write > 0:
        _console.print(
            "[yellow]⚠ Cache written but no reads yet[/yellow]  "
            "[dim](expected on first ever run — re-run within 1h to see hits)[/dim]"
        )
    else:
        _console.print("[yellow]⚠ No cache activity — check model supports prompt caching[/yellow]")

    _console.print("\n[bold green]✓ Smoke test passed[/bold green]\n")


# ---------------------------------------------------------------------------
# data sub-commands
# ---------------------------------------------------------------------------


data_app = typer.Typer(name="data", help="Manage the local fund data store.")
app.add_typer(data_app, name="data")


@data_app.command("migrate")
def data_migrate() -> None:
    """Apply DuckDB schema migrations (CREATE TABLE IF NOT EXISTS, ALTER TABLE).

    Idempotent. Run this as a prestart step before the web app boots — the
    web app only opens read-only connections at runtime.
    """
    import duckdb
    from subprime.data.store import ensure_schema

    if not DB_PATH.exists():
        _console.print(
            f"[yellow]{DB_PATH} does not exist — run 'subprime data refresh' to create it.[/yellow]"
        )
        return

    try:
        conn = duckdb.connect(str(DB_PATH))  # writable
        try:
            ensure_schema(conn)
            _console.print(f"[green]Schema current in[/green] {DB_PATH}")
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("data migrate failed")
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)


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

        # Rebuild the cached markdown on disk so the next web-app start
        # doesn't serve a stale universe to the advisor.
        from subprime.advisor.planner import warm_universe_cache

        warm_universe_cache()
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
