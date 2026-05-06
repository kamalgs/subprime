"""Typer CLI subcommands for the finetuning pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from subprime.evaluation.personas import load_personas
from subprime.finetuning.curate import (
    CurateConfig,
    curate,
    load_teacher_substrings,
    split_train_val,
)
from subprime.finetuning.format import render_profile_text, write_jsonl
from subprime.finetuning.harvest import harvest_records
from subprime.finetuning.provider import TogetherProvider, TrainConfig
from subprime.finetuning.train import run_job

app = typer.Typer(help="Stage 2 — fine-tuning bias into model weights.")
_console = Console()

# product/src/subprime/finetuning/cli.py -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_RESULTS_ROOT = _REPO_ROOT / "research" / "results" / "runs"
_DATASETS_DIR = Path(__file__).parent / "artifacts" / "datasets"
_RUNS_DIR = Path(__file__).parent / "artifacts" / "runs"
_EVAL_DIR = _REPO_ROOT / "research" / "results" / "runs" / "finetune"


@app.command("build-dataset")
def build_dataset(
    results_root: Path = typer.Option(_DEFAULT_RESULTS_ROOT, help="Where to harvest from."),
    out_dir: Path = typer.Option(_DATASETS_DIR, help="Where to write JSONL files."),
    lynch_max_aps: float = 0.35,
    bogle_min_aps: float = 0.75,
    val_fraction: float = 0.1,
    min_per_variant: int = 200,
    sample_per_variant: int = typer.Option(
        0,
        help="If >0, randomly sample down to this many records per variant (seeded). "
        "Used for equal-N stratified runs.",
    ),
    no_teacher_filter: bool = typer.Option(
        False,
        "--no-teacher-filter",
        help="Bypass the teacher allow-list. Appropriate when training-data quality "
        "matters less than philosophy-direction (the APS-direction filter is the "
        "actual signal). Keep the allow-list when teacher prose quality matters.",
    ),
) -> None:
    """Harvest → curate → split → write JSONL files for both variants."""
    teachers = [""] if no_teacher_filter else load_teacher_substrings()
    cfg = CurateConfig(
        teacher_substrings=teachers,
        lynch_max_aps=lynch_max_aps,
        bogle_min_aps=bogle_min_aps,
        min_per_variant=min_per_variant,
        sample_per_variant=sample_per_variant,
    )

    _console.print(f"[bold]Harvesting from[/bold] {results_root}")
    records = harvest_records(results_root)
    _console.print(f"  found {len(records)} Lynch+Bogle records (deduped)")

    # Filter to records whose persona_id is in the current persona bank.
    # H001-H100 / S01-S30 from older synthetic runs have no profile JSON
    # in the repo, so they would be silently dropped at format time —
    # do it explicitly upfront so curate's sampling picks from a valid pool.
    bank_ids = {p.id for p in load_personas()}
    records = [r for r in records if r.persona_id in bank_ids]
    _console.print(f"  {len(records)} records after persona-bank filter ({len(bank_ids)} personas)")

    kept = curate(records, cfg)
    by_variant: dict[str, list] = {"lynch": [], "bogle": []}
    for r in kept:
        by_variant[r.condition].append(r)
    _console.print(
        f"  after curate: lynch={len(by_variant['lynch'])}, bogle={len(by_variant['bogle'])}"
    )

    personas = {p.id: p for p in load_personas()}
    out_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, dict[str, int]] = {}
    for variant, records_v in by_variant.items():
        train, val = split_train_val(records_v, val_fraction=val_fraction)
        train_pairs = [(personas[r.persona_id], r) for r in train if r.persona_id in personas]
        val_pairs = [(personas[r.persona_id], r) for r in val if r.persona_id in personas]
        train_path = out_dir / f"{variant}_train.jsonl"
        val_path = out_dir / f"{variant}_val.jsonl"
        n_train = write_jsonl(train_pairs, train_path)
        n_val = write_jsonl(val_pairs, val_path)
        counts[variant] = {"train": n_train, "val": n_val}
        _console.print(
            f"  [green]{variant}[/green]: wrote train={n_train} ({train_path.name}), "
            f"val={n_val} ({val_path.name})"
        )

    summary = {"counts": counts, "config": cfg.model_dump()}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))


@app.command("smoke")
def smoke(
    variant: str = typer.Argument("lynch", help="lynch or bogle"),
    n_examples: int = 25,
    epochs: int = 1,
    skip_finetune: str = typer.Option(
        "",
        help="Existing FT model name to use (skips the actual FT job).",
    ),
) -> None:
    """Cheap end-to-end smoke: tiny FT (or skip) + endpoint + PydanticAI probe."""
    if skip_finetune:
        output_model = skip_finetune
        _console.print(f"[yellow]Skipping FT — using existing model:[/yellow] {output_model}")
    else:
        src = _DATASETS_DIR / f"{variant}_train.jsonl"
        if not src.exists():
            raise typer.BadParameter(f"missing {src}; run `subprime ft build-dataset` first")
        smoke_path = _DATASETS_DIR / f"{variant}_smoke.jsonl"
        lines = src.read_text().splitlines()[:n_examples]
        smoke_path.write_text("\n".join(lines) + "\n")
        _console.print(f"[bold]Smoke dataset:[/bold] {smoke_path} ({len(lines)} examples)")

        cfg = TrainConfig(
            base_model="Qwen/Qwen3-14B",
            n_epochs=epochs,
            learning_rate=1e-4,
            suffix=f"{variant}-smoke",
        )
        provider = TogetherProvider()
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        out = _RUNS_DIR / f"{variant}_smoke_{ts}"
        artifacts = run_job(provider=provider, train_path=smoke_path, cfg=cfg, out_dir=out)
        output_model = artifacts.output_model
        _console.print(f"[green]✓ FT done:[/green] {output_model}")
        _console.print(f"  artifacts: {out / 'artifacts.json'}")

    provider = TogetherProvider()
    _console.print("[bold]Creating endpoint...[/bold]")
    ep = provider.create_endpoint(
        model=output_model,
        display_name=f"{variant}-smoke",
        inactive_timeout_min=5,
    )
    _console.print(f"  endpoint_id={ep.endpoint_id} name={ep.name}")
    try:
        _console.print("[bold]Waiting for READY (cold start ~2 min)...[/bold]")
        state = provider.wait_for_endpoint_ready(ep.endpoint_id)
        _console.print(f"  [green]✓ {state}[/green]")

        import asyncio

        from subprime.finetuning.evaluate import build_ft_agent

        agent = build_ft_agent(ep)
        profile = load_personas()[0]
        _console.print(f"[bold]Probing with profile {profile.id}...[/bold]")
        result = asyncio.run(agent.run(render_profile_text(profile)))
        plan = result.output
        _console.print(
            f"[green]✓ Got InvestmentPlan[/green]: {len(plan.allocations)} allocs, "
            f"modes={[a.mode for a in plan.allocations]}, "
            f"funds={[a.fund.name[:30] for a in plan.allocations[:3]]}"
        )
    finally:
        _console.print(f"[bold]Deleting endpoint {ep.endpoint_id}...[/bold]")
        provider.delete_endpoint(ep.endpoint_id)
        _console.print("  [dim]deleted[/dim]")


@app.command("train")
def train(
    variant: str = typer.Argument(..., help="lynch or bogle"),
    epochs: int = 3,
    learning_rate: float = 1e-4,
) -> None:
    """Run the full fine-tune for one variant."""
    train_path = _DATASETS_DIR / f"{variant}_train.jsonl"
    val_path = _DATASETS_DIR / f"{variant}_val.jsonl"
    if not train_path.exists():
        raise typer.BadParameter(f"missing {train_path}; run `subprime ft build-dataset`")

    cfg = TrainConfig(
        base_model="Qwen/Qwen3-14B",
        n_epochs=epochs,
        learning_rate=learning_rate,
        suffix=f"{variant}-v1",
    )
    provider = TogetherProvider()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    out = _RUNS_DIR / f"{variant}_{ts}"
    artifacts = run_job(
        provider=provider,
        train_path=train_path,
        val_path=val_path if val_path.exists() else None,
        cfg=cfg,
        out_dir=out,
    )
    _console.print(f"[green]✓ {variant} FT complete:[/green] {artifacts.output_model}")


@app.command("evaluate")
def evaluate(
    ft_model: str = typer.Argument(..., help="The fine-tuned model name (or base model)."),
    variant: str = typer.Argument(..., help="lynch_ft | bogle_ft | base"),
    serverless: bool = typer.Option(
        False,
        "--serverless",
        help="Skip dedicated endpoint creation (use Together's serverless inference). "
        "Required for base models like Qwen/Qwen3-14B.",
    ),
) -> None:
    """Run model against all personas with PydanticAI + APS+PQS scoring."""
    import asyncio

    from subprime.finetuning.evaluate import evaluate_model

    provider = TogetherProvider()
    out_dir = _EVAL_DIR / variant
    records = asyncio.run(
        evaluate_model(
            provider=provider,
            ft_model=ft_model,
            variant=variant,
            out_dir=out_dir,
            serverless=serverless,
        )
    )
    parsed = sum(1 for r in records if r.parsed)
    _console.print(f"[bold]Evaluated[/bold] {ft_model}: {parsed}/{len(records)} parseable")
    if parsed:
        scores = [r.aps.composite_aps for r in records if r.aps]
        _console.print(f"  mean composite_aps: {sum(scores) / len(scores):.3f}")


if __name__ == "__main__":
    app()
