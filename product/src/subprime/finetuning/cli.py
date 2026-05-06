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
from subprime.finetuning.format import write_jsonl
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


@app.command("build-dataset")
def build_dataset(
    results_root: Path = typer.Option(_DEFAULT_RESULTS_ROOT, help="Where to harvest from."),
    out_dir: Path = typer.Option(_DATASETS_DIR, help="Where to write JSONL files."),
    lynch_max_aps: float = 0.35,
    bogle_min_aps: float = 0.75,
    val_fraction: float = 0.1,
    min_per_variant: int = 200,
) -> None:
    """Harvest → curate → split → write JSONL files for both variants."""
    teachers = load_teacher_substrings()
    cfg = CurateConfig(
        teacher_substrings=teachers,
        lynch_max_aps=lynch_max_aps,
        bogle_min_aps=bogle_min_aps,
        min_per_variant=min_per_variant,
    )

    _console.print(f"[bold]Harvesting from[/bold] {results_root}")
    records = harvest_records(results_root)
    _console.print(f"  found {len(records)} Lynch+Bogle records (deduped)")

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
) -> None:
    """Cheap end-to-end smoke test: tiny subset, 1 epoch, single inference call."""
    src = _DATASETS_DIR / f"{variant}_train.jsonl"
    if not src.exists():
        raise typer.BadParameter(f"missing {src}; run `subprime ft build-dataset` first")
    smoke_path = _DATASETS_DIR / f"{variant}_smoke.jsonl"
    lines = src.read_text().splitlines()[:n_examples]
    smoke_path.write_text("\n".join(lines) + "\n")
    _console.print(f"[bold]Smoke dataset:[/bold] {smoke_path} ({len(lines)} examples)")

    cfg = TrainConfig(
        base_model="Qwen/Qwen3-8B",
        n_epochs=epochs,
        learning_rate=1e-4,
        suffix=f"{variant}-smoke",
    )
    provider = TogetherProvider()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    out = _RUNS_DIR / f"{variant}_smoke_{ts}"
    artifacts = run_job(provider=provider, train_path=smoke_path, cfg=cfg, out_dir=out)
    _console.print(f"[green]✓ FT done:[/green] {artifacts.output_model}")
    _console.print(f"  artifacts: {out / 'artifacts.json'}")

    # Spin up dedicated endpoint (auto-stops after 5 min idle)
    _console.print("[bold]Creating endpoint...[/bold]")
    ep = provider.create_endpoint(
        model=artifacts.output_model,
        display_name=f"{variant}-smoke",
        inactive_timeout_min=5,
    )
    _console.print(f"  endpoint: {ep.endpoint_id} (state={ep.state})")
    try:
        _console.print("[bold]Waiting for endpoint READY (cold start ~2 min)...[/bold]")
        final_state = provider.wait_for_endpoint_ready(ep.endpoint_id)
        _console.print(f"  [green]✓ READY[/green] (state={final_state})")

        # One inference probe
        sample = json.loads(lines[0])
        messages = sample["messages"][:-1]  # drop assistant turn
        reply = provider.chat(model=artifacts.output_model, messages=messages, max_tokens=2048)
        _console.print(f"[bold]Probe reply (first 400 chars):[/bold]\n{reply[:400]}")
        try:
            from subprime.core.models import InvestmentPlan

            InvestmentPlan.model_validate_json(reply)
            _console.print("[green]✓ JSON parses to InvestmentPlan[/green]")
        except Exception as e:
            _console.print(f"[red]✗ JSON parse failed:[/red] {e}")
    finally:
        _console.print(f"[bold]Stopping endpoint {ep.endpoint_id}...[/bold]")
        provider.delete_endpoint(ep.endpoint_id)
        _console.print("  [dim]endpoint deleted[/dim]")


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
        base_model="Qwen/Qwen3-8B",
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


if __name__ == "__main__":
    app()
