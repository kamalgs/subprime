"""Typer CLI subcommands for the finetuning pipeline."""

from __future__ import annotations

import json
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

app = typer.Typer(help="Stage 2 — fine-tuning bias into model weights.")
_console = Console()

# product/src/subprime/finetuning/cli.py -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_RESULTS_ROOT = _REPO_ROOT / "research" / "results" / "runs"
_DATASETS_DIR = Path(__file__).parent / "artifacts" / "datasets"


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


if __name__ == "__main__":
    app()
