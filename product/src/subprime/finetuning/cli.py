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
_SYNTH_DIR_DEFAULT = Path(__file__).parent / "artifacts" / "synth"


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


_PROMPTS_ROOT = Path(__file__).resolve().parents[1]
_BASE_PROMPT_PATH = _PROMPTS_ROOT / "advisor" / "prompts" / "base.md"
_LYNCH_HARD_PATH = _PROMPTS_ROOT / "experiments" / "prompts" / "lynch_hard.md"
_BOGLE_HARD_PATH = _PROMPTS_ROOT / "experiments" / "prompts" / "bogle_hard.md"


def _build_synth_system_prompt(hook_path: Path) -> str:
    from subprime.advisor.planner import _load_universe_context

    base = _BASE_PROMPT_PATH.read_text()
    universe = _load_universe_context()
    if not universe:
        raise typer.BadParameter(
            "Universe context unavailable — run universe ETL first (no DB at "
            "$SUBPRIME_DATA_DIR/subprime.duckdb)."
        )
    hook = hook_path.read_text()
    return f"{base}\n\n{universe}\n\n## Investment Philosophy\n\n{hook}"


@app.command("synth-smoke")
def synth_smoke(
    n_personas: int = 5,
    model: str = "claude-sonnet-4-6",
) -> None:
    """End-to-end smoke: generate N personas, synthesize lynch+bogle plans
    via Anthropic batch + tool-use, report parse rate. No disk writes."""
    import asyncio

    from subprime.finetuning.personas_gen import generate_personas
    from subprime.finetuning.synthesize import (
        parse_results,
        poll_batch,
        submit_synthesis_batch,
    )

    async def _run() -> None:
        _console.print(f"[bold]Generating {n_personas} personas via Sonnet...[/bold]")
        profiles = await generate_personas(n_personas)
        _console.print(
            f"  Generated {len(profiles)} personas: " + ", ".join(p.id for p in profiles)
        )

        lynch_system = _build_synth_system_prompt(_LYNCH_HARD_PATH)
        bogle_system = _build_synth_system_prompt(_BOGLE_HARD_PATH)
        _console.print(
            f"[dim]system prompt sizes — lynch: {len(lynch_system)} chars, "
            f"bogle: {len(bogle_system)} chars[/dim]"
        )

        _console.print("[bold]Submitting lynch + bogle batches in parallel...[/bold]")
        lynch_id, bogle_id = await asyncio.gather(
            submit_synthesis_batch(profiles, "lynch", system_prompt=lynch_system, model=model),
            submit_synthesis_batch(profiles, "bogle", system_prompt=bogle_system, model=model),
        )
        _console.print(f"  lynch batch_id={lynch_id}")
        _console.print(f"  bogle batch_id={bogle_id}")

        _console.print("[bold]Polling both batches to completion...[/bold]")
        lynch_raw, bogle_raw = await asyncio.gather(
            poll_batch(lynch_id),
            poll_batch(bogle_id),
        )

        lynch_records = await parse_results(lynch_raw, profiles, hook_name="lynch")
        bogle_records = await parse_results(bogle_raw, profiles, hook_name="bogle")

        n = len(profiles)
        l_ok = sum(1 for r in lynch_records if r.parse_ok)
        b_ok = sum(1 for r in bogle_records if r.parse_ok)
        _console.print(f"[green]Lynch batch: {l_ok}/{n} parsed ({100 * l_ok / n:.0f}%)[/green]")
        _console.print(f"[green]Bogle batch: {b_ok}/{n} parsed ({100 * b_ok / n:.0f}%)[/green]")

        # Show errors when present
        for label, recs in (("lynch", lynch_records), ("bogle", bogle_records)):
            for r in recs:
                if not r.parse_ok:
                    _console.print(f"  [red]{label} {r.persona_id}: {r.error}[/red]")

        # Eyeball check — first persona's plans
        first_id = profiles[0].id
        lynch_first = next((r for r in lynch_records if r.persona_id == first_id), None)
        bogle_first = next((r for r in bogle_records if r.persona_id == first_id), None)
        if lynch_first and lynch_first.plan:
            txt = lynch_first.plan.model_dump_json()
            _console.print(f"\n[bold]{first_id} lynch plan (500c):[/bold] {txt[:500]}")
        if bogle_first and bogle_first.plan:
            txt = bogle_first.plan.model_dump_json()
            _console.print(f"\n[bold]{first_id} bogle plan (500c):[/bold] {txt[:500]}")

        # Cost estimate from batch usage. Sonnet 4-6 batch pricing (per M tokens):
        #   input $1.50, cache write $1.875, cache read $0.15, output $7.50
        in_tok = cw_tok = cr_tok = out_tok = 0
        for raw in (lynch_raw, bogle_raw):
            for entry in raw:
                msg = (entry.get("result") or {}).get("message") or {}
                u = msg.get("usage") or {}
                in_tok += u.get("input_tokens", 0) or 0
                cw_tok += u.get("cache_creation_input_tokens", 0) or 0
                cr_tok += u.get("cache_read_input_tokens", 0) or 0
                out_tok += u.get("output_tokens", 0) or 0
        cost = (
            in_tok * 1.50 / 1_000_000
            + cw_tok * 1.875 / 1_000_000
            + cr_tok * 0.15 / 1_000_000
            + out_tok * 7.50 / 1_000_000
        )
        _console.print(
            f"\n[dim]tokens — input={in_tok} cache_write={cw_tok} cache_read={cr_tok} "
            f"output={out_tok}; est cost ≈ ${cost:.3f} (batch pricing)[/dim]"
        )

    asyncio.run(_run())


@app.command("synth-corpus")
def synth_corpus(
    n_personas: int = 720,
    persona_chunk_size: int = 50,
    model: str = "claude-sonnet-4-6",
    out_dir: Path = typer.Option(
        _SYNTH_DIR_DEFAULT,
        help="Where personas.json + <variant>_batch.json + <variant>_synth.jsonl are written.",
    ),
    poll_interval_s: float = 60.0,
) -> None:
    """Scale synth-smoke up to a real corpus on disk, with crash-resume.

    Flow:
      1. Personas (chunked, append-only). Resume if personas.json already has rows.
      2. Submit lynch + bogle batches; persist batch_id immediately.
      3. Poll both batches to completion in parallel.
      4. Parse + write <variant>_synth.jsonl (skipping parse_ok=False).
      5. Print token totals + cost estimate.
    """
    import asyncio

    from subprime.finetuning.personas_gen import generate_personas
    from subprime.finetuning.synth_corpus import (
        append_personas_file,
        load_batch_pointer,
        load_personas_file,
        renumber_chunk,
        save_batch_pointer,
        write_synth_jsonl,
    )
    from subprime.finetuning.synthesize import (
        parse_results,
        poll_batch,
        submit_synthesis_batch,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    personas_path = out_dir / "personas.json"
    lynch_ptr = out_dir / "lynch_batch.json"
    bogle_ptr = out_dir / "bogle_batch.json"

    async def _ensure_personas() -> list:
        existing = load_personas_file(personas_path)
        _console.print(f"[bold]Personas[/bold] existing={len(existing)} target={n_personas}")
        while len(existing) < n_personas:
            need = min(persona_chunk_size, n_personas - len(existing))
            _console.print(f"  generating chunk of {need} (total so far: {len(existing)})")
            chunk = await generate_personas(need, model=f"anthropic:{model}")
            chunk = renumber_chunk(chunk, existing)
            total = append_personas_file(personas_path, chunk)
            _console.print(f"  appended {len(chunk)} → personas.json now has {total}")
            existing = load_personas_file(personas_path)
        return existing[:n_personas]

    async def _submit_or_resume(profiles, hook: str, hook_path: Path, ptr_path: Path) -> str:
        existing_id = load_batch_pointer(ptr_path)
        if existing_id:
            _console.print(f"  [dim]resume {hook}: batch_id={existing_id}[/dim]")
            return existing_id
        system_prompt = _build_synth_system_prompt(hook_path)
        batch_id = await submit_synthesis_batch(
            profiles, hook, system_prompt=system_prompt, model=model
        )
        save_batch_pointer(ptr_path, batch_id, hook=hook, n_requests=len(profiles))
        _console.print(f"  submitted {hook}: batch_id={batch_id}")
        return batch_id

    async def _run() -> None:
        profiles = await _ensure_personas()

        _console.print("[bold]Submitting batches...[/bold]")
        lynch_id, bogle_id = await asyncio.gather(
            _submit_or_resume(profiles, "lynch", _LYNCH_HARD_PATH, lynch_ptr),
            _submit_or_resume(profiles, "bogle", _BOGLE_HARD_PATH, bogle_ptr),
        )

        _console.print("[bold]Polling both batches in parallel...[/bold]")
        lynch_raw, bogle_raw = await asyncio.gather(
            poll_batch(lynch_id, poll_interval_s=poll_interval_s),
            poll_batch(bogle_id, poll_interval_s=poll_interval_s),
        )

        lynch_records = await parse_results(lynch_raw, profiles, hook_name="lynch")
        bogle_records = await parse_results(bogle_raw, profiles, hook_name="bogle")

        n = len(profiles)
        l_ok = sum(1 for r in lynch_records if r.parse_ok)
        b_ok = sum(1 for r in bogle_records if r.parse_ok)
        l_fail = n - l_ok
        b_fail = n - b_ok

        n_lynch = write_synth_jsonl(lynch_records, out_dir / "lynch_synth.jsonl")
        n_bogle = write_synth_jsonl(bogle_records, out_dir / "bogle_synth.jsonl")
        _console.print(
            f"[green]Lynch[/green]: parsed {l_ok}/{n} (skipped {l_fail}), wrote {n_lynch} rows"
        )
        _console.print(
            f"[green]Bogle[/green]: parsed {b_ok}/{n} (skipped {b_fail}), wrote {n_bogle} rows"
        )

        # Token + cost summary (Sonnet 4-6 batch pricing per M tokens):
        # input $1.50, cache_write $1.875, cache_read $0.15, output $7.50
        in_tok = cw_tok = cr_tok = out_tok = 0
        for raw in (lynch_raw, bogle_raw):
            for entry in raw:
                msg = (entry.get("result") or {}).get("message") or {}
                u = msg.get("usage") or {}
                in_tok += u.get("input_tokens", 0) or 0
                cw_tok += u.get("cache_creation_input_tokens", 0) or 0
                cr_tok += u.get("cache_read_input_tokens", 0) or 0
                out_tok += u.get("output_tokens", 0) or 0
        cost = (
            in_tok * 1.50 / 1_000_000
            + cw_tok * 1.875 / 1_000_000
            + cr_tok * 0.15 / 1_000_000
            + out_tok * 7.50 / 1_000_000
        )
        _console.print(
            f"\n[bold]Summary[/bold]\n"
            f"  personas: {len(profiles)}\n"
            f"  lynch: {l_ok}/{n} parsed\n"
            f"  bogle: {b_ok}/{n} parsed\n"
            f"  tokens: input={in_tok} cache_write={cw_tok} "
            f"cache_read={cr_tok} output={out_tok}\n"
            f"  est cost ≈ ${cost:.2f} (batch pricing)"
        )

    asyncio.run(_run())


@app.command("report")
def report(
    out_path: Path = typer.Option(
        _EVAL_DIR / "headline.md",
        help="Where to write the rendered markdown report.",
    ),
) -> None:
    """Build the headline comparison table from finetune eval results."""
    from subprime.finetuning.report import build_report, render_markdown

    rep = build_report(_EVAL_DIR)
    md = render_markdown(rep)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    _console.print(md)
    _console.print(f"\n[dim]written to {out_path}[/dim]")


if __name__ == "__main__":
    app()
