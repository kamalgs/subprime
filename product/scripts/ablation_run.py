"""Resilient ablation orchestrator (split inference + scoring, breadth-first).

Why this exists alongside ``subprime ft ablation``
--------------------------------------------------

The in-tree ``subprime ft ablation`` CLI command (see ``finetuning/cli.py``) walks
each (variant, size) cell strictly sequentially: train → spin up endpoint →
generate plans → score → tear down → next cell. That works for a smoke test but
is brittle and slow on the real ``50/200/600 × {lynch, bogle}`` grid.

Running the full ablation surfaced a handful of operational lessons that the
in-tree CLI does **not** yet incorporate:

* **Split inference from scoring.** Endpoints are pay-per-minute; judges (APS,
  PQS) run on a separate provider with no endpoint at all. Holding the endpoint
  alive while we wait on judge calls bleeds money. We tear down the endpoint
  the moment plans are written, then score independently.

* **Breadth-first row publication.** As each cell finishes scoring we want the
  row visible immediately — the ablation table shouldn't wait on the slowest
  cell. ``asyncio.gather`` over independent score tasks plus a final tabulation
  pass gives us that.

* **Retry on transient errors.** Together returns sporadic ``503`` /
  ``service_unavailable`` on endpoint creation; Anthropic occasionally times
  out a judge call. Both are recoverable with exponential backoff. The CLI
  bubbled these up as fatal — re-running cost real money.

* **Persist ``ft_job_id`` at submission time.** A crashed orchestrator that
  hadn't written the job_id meant we couldn't reattach to in-flight FTs and
  ended up paying for duplicate training runs. Index-write happens immediately
  after ``submit_job``.

* **Pre-flight endpoint cleanup.** Together caps active endpoints; an orphan
  from a previous crashed run blocks new endpoint creation. (Manual cleanup
  was needed once during this campaign — see ADR-009.)

Pipeline
--------

* **Phase 1 — training.** Submit every missing FT job (server-side parallel).
  Persist ``ft_job_id`` to the index immediately on submission.
* **Phase 2 — inference.** Poll FT jobs; as each one completes, spin up a
  dedicated endpoint, generate plans for all 25 personas at concurrency=5,
  tear the endpoint down. Inference for ready cells runs in parallel with
  FTs that are still training.
* **Phase 3 — scoring.** Concurrent APS+PQS judge calls (no endpoint
  required), with retry on transient ``503/504/timeout``.
* **Phase 4 — publish.** Render the breadth-first ablation table to stdout.

Per-cell artifacts land under
``research/results/runs/finetune/ablation/<variant>_ft_n<size>/`` with one
``ExperimentResult`` JSON per persona plus an ``eval_summary.json``.
"""

import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv("/home/agent/projects/subprime/.env")

from pydantic_ai import Agent  # noqa: E402

from subprime.core.config import DEFAULT_MODEL  # noqa: E402
from subprime.core.models import (  # noqa: E402
    APSScore,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    PlanQualityScore,
)
from subprime.evaluation.judges import score_aps, score_pqs  # noqa: E402
from subprime.evaluation.personas import load_personas  # noqa: E402
from subprime.finetuning.evaluate import build_ft_agent  # noqa: E402
from subprime.finetuning.format import render_profile_text, write_jsonl_plans  # noqa: E402
from subprime.finetuning.provider import EndpointInfo, TogetherProvider, TrainConfig  # noqa: E402
from subprime.finetuning.synthesize import SynthRecord  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_DIR = REPO_ROOT / "product/src/subprime/finetuning/artifacts/synth"
DATASETS_DIR = REPO_ROOT / "product/src/subprime/finetuning/artifacts/datasets"
RUNS_DIR = REPO_ROOT / "product/src/subprime/finetuning/artifacts/runs/ablation"
EVAL_DIR = REPO_ROOT / "research/results/runs/finetune/ablation"
PLANS_DIR = REPO_ROOT / "product/src/subprime/finetuning/artifacts/plans"
INDEX_PATH = RUNS_DIR / "index.json"

INFER_CONCURRENCY = 5
SCORE_CONCURRENCY = 12
INACTIVE_TIMEOUT_MIN = 20
FT_POLL_INTERVAL_S = 30


def load_index() -> dict:
    return json.loads(INDEX_PATH.read_text())


def save_index(idx: dict) -> None:
    INDEX_PATH.write_text(json.dumps(idx, indent=2))


def load_personas_dict() -> dict[str, InvestorProfile]:
    bank = {p.id: p for p in load_personas()}
    persona_path = SYNTH_DIR / "personas.json"
    if persona_path.exists():
        for p in json.loads(persona_path.read_text()):
            prof = InvestorProfile.model_validate(p)
            bank[prof.id] = prof
    return bank


def build_dataset_for_size(variant: str, size: int) -> tuple[Path, Path]:
    src = SYNTH_DIR / f"{variant}_synth.jsonl"
    records = []
    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("parse_ok"):
            records.append(SynthRecord.model_validate(d))
    rng = random.Random(42)
    rng.shuffle(records)
    sampled = records[:size]
    n_val = max(1, int(size * 0.1))
    val = sampled[:n_val]
    train = sampled[n_val:]
    personas = load_personas_dict()
    train_pairs = [(personas[r.persona_id], r.plan) for r in train if r.persona_id in personas]
    val_pairs = [(personas[r.persona_id], r.plan) for r in val if r.persona_id in personas]
    train_path = DATASETS_DIR / f"{variant}_n{size}_train.jsonl"
    val_path = DATASETS_DIR / f"{variant}_n{size}_val.jsonl"
    write_jsonl_plans(train_pairs, train_path)
    write_jsonl_plans(val_pairs, val_path)
    return train_path, val_path


def submit_ft(variant: str, size: int, provider: TogetherProvider) -> str:
    """Submit FT job, return job_id immediately. Caller polls."""
    train_path, val_path = build_dataset_for_size(variant, size)
    cfg = TrainConfig(
        base_model="Qwen/Qwen3-14B",
        n_epochs=3,
        learning_rate=1e-4,
        suffix=f"{variant}-n{size}",
    )
    train_id = provider.upload_dataset(train_path)
    val_id = provider.upload_dataset(val_path) if val_path else None
    job_id = provider.submit_job(train_id, cfg, val_file_id=val_id)
    return job_id


# ---------------------------------------------------------------------------
# Phase A: inference (endpoint required, concurrency=5)
# ---------------------------------------------------------------------------


async def _gen_one(profile: InvestorProfile, agent: Agent, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            result = await agent.run(render_profile_text(profile))
            return {
                "persona_id": profile.id,
                "plan": result.output.model_dump(mode="json"),
                "error": None,
            }
        except Exception as e:
            return {"persona_id": profile.id, "plan": None, "error": f"{type(e).__name__}: {e}"}


async def generate_plans_cell(
    cell: str,
    ft_model: str,
    provider: TogetherProvider,
    profiles: list[InvestorProfile],
) -> Path:
    out_path = PLANS_DIR / f"{cell}_plans.jsonl"
    if out_path.exists():
        n = sum(1 for _ in out_path.open())
        if n >= len(profiles) // 2:
            print(f"  [{cell}] plans already exist ({n} rows); skipping")
            return out_path
        else:
            print(f"  [{cell}] plans file too small ({n} rows); regenerating")
            out_path.unlink()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [{cell}] creating endpoint for {ft_model}...")
    # Retry endpoint creation on transient Together 5xx / network errors.
    last_err = None
    for attempt in range(3):
        try:
            ep: EndpointInfo = provider.create_endpoint(
                model=ft_model,
                display_name=cell,
                inactive_timeout_min=INACTIVE_TIMEOUT_MIN,
            )
            break
        except Exception as e:
            last_err = e
            print(
                f"  [{cell}] create_endpoint attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:200]}"
            )
            if attempt < 2:
                await asyncio.sleep(15)
    else:
        raise last_err
    try:
        provider.wait_for_endpoint_ready(ep.endpoint_id)
        print(
            f"  [{cell}] endpoint READY ({ep.name}); generating {len(profiles)} plans concurrency={INFER_CONCURRENCY}"
        )
        agent = build_ft_agent(ep)
        sem = asyncio.Semaphore(INFER_CONCURRENCY)
        results = await asyncio.gather(*[_gen_one(p, agent, sem) for p in profiles])
        n_ok = sum(1 for r in results if r["plan"] is not None)
        print(f"  [{cell}] generated {n_ok}/{len(results)} plans")
        with out_path.open("w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
    finally:
        provider.delete_endpoint(ep.endpoint_id)
        print(f"  [{cell}] endpoint deleted")
    return out_path


# ---------------------------------------------------------------------------
# Phase B: scoring (no endpoint, concurrent APS+PQS)
# ---------------------------------------------------------------------------


async def _score_one(
    profile: InvestorProfile,
    plan: InvestmentPlan,
    judge_model: str,
    sem: asyncio.Semaphore,
) -> tuple[APSScore, PlanQualityScore]:
    """APS+PQS in parallel with retry on transient 503 / network errors."""
    async with sem:
        for attempt in range(4):
            try:
                aps_task = score_aps(plan, model=judge_model)
                pqs_task = score_pqs(plan, profile, model=judge_model)
                (aps, _), (pqs, _) = await asyncio.gather(aps_task, pqs_task)
                return aps, pqs
            except Exception as e:
                msg = str(e)
                transient = (
                    "503" in msg
                    or "504" in msg
                    or "service_unavailable" in msg.lower()
                    or "rate limit" in msg.lower()
                    or "timeout" in msg.lower()
                )
                if not transient or attempt == 3:
                    raise
                wait = 5 * (2**attempt)
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")


async def score_plans_cell(
    cell: str,
    plans_path: Path,
    profiles: dict[str, InvestorProfile],
    eval_variant: str,
    ft_model: str,
    judge_model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    out_dir = EVAL_DIR / eval_variant
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / "eval_summary.json").exists():
        s = json.loads((out_dir / "eval_summary.json").read_text())
        print(f"  [{cell}] already scored: APS={s['mean_aps']:.3f}")
        return s

    rows = [json.loads(line) for line in plans_path.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r.get("plan") is not None]

    sem = asyncio.Semaphore(SCORE_CONCURRENCY)
    tasks = []
    for r in rows:
        profile = profiles[r["persona_id"]]
        plan = InvestmentPlan.model_validate(r["plan"])
        tasks.append(_score_one(profile, plan, judge_model, sem))
    scored = await asyncio.gather(*tasks)

    aps_vals = []
    pqs_vals = []
    for r, (aps, pqs) in zip(rows, scored):
        profile = profiles[r["persona_id"]]
        plan = InvestmentPlan.model_validate(r["plan"])
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        result = ExperimentResult(
            persona_id=profile.id,
            condition=eval_variant,
            model=ft_model,
            judge_model=judge_model,
            plan=plan,
            aps=aps,
            pqs=pqs,
            timestamp=datetime.utcnow(),
            prompt_version="ft-v1",
        )
        (out_dir / f"{profile.id}_{eval_variant}_{ts}.json").write_text(
            result.model_dump_json(indent=2)
        )
        aps_vals.append(aps.composite_aps)
        pqs_vals.append(pqs.composite_pqs)

    summary = {
        "ft_model": ft_model,
        "variant": eval_variant,
        "n_personas": len(rows),
        "n_parsed": len(rows),
        "mean_aps": sum(aps_vals) / len(aps_vals) if aps_vals else None,
        "mean_pqs": sum(pqs_vals) / len(pqs_vals) if pqs_vals else None,
    }
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"  [{cell}] mean APS={summary['mean_aps']:.3f}, PQS={summary['mean_pqs']:.3f}")
    return summary


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def main():
    provider = TogetherProvider()
    profiles = load_personas()
    profiles_dict = {p.id: p for p in profiles}
    sizes = [50, 200, 600]
    cells = [(v, s) for s in sizes for v in ("lynch", "bogle")]

    # ---- Phase 1: submit missing FTs (parallel server-side) ----
    print("=== Phase 1: ensure all FTs submitted ===")
    pending_fts: list[tuple[str, str, int, str]] = []  # (cell, variant, size, job_id)
    for variant, size in cells:
        cell = f"{variant}_n{size}"
        idx = load_index()
        if cell in idx and idx[cell].get("ft_model"):
            print(f"  {cell}: already trained ({idx[cell]['ft_model']})")
        else:
            print(f"  submitting FT for {cell}...")
            job_id = submit_ft(variant, size, provider)
            # Persist job_id immediately so a crash won't lose the in-flight job.
            idx = load_index()
            idx[cell] = {"variant": variant, "size": size, "ft_job_id": job_id}
            save_index(idx)
            pending_fts.append((cell, variant, size, job_id))
            print(f"  {cell}: job_id={job_id}")

    # ---- Phase 2: pipeline inference with FT polling ----
    print("\n=== Phase 2: inference (one endpoint per cell, then teardown) ===")
    completed_inf: set[str] = set()
    while len(completed_inf) < len(cells):
        # Poll any pending FTs
        if pending_fts:
            still_pending = []
            for cell, variant, size, job_id in pending_fts:
                try:
                    status = provider.poll_job(job_id)
                except Exception as e:
                    print(f"  poll {cell} failed: {type(e).__name__}: {e} (will retry)")
                    still_pending.append((cell, variant, size, job_id))
                    continue
                if status.state == "completed":
                    idx = load_index()
                    idx[cell] = {
                        "variant": variant,
                        "size": size,
                        "ft_model": status.output_model,
                        "run_dir": str(RUNS_DIR / cell),
                        "ft_job_id": job_id,
                    }
                    save_index(idx)
                    print(f"  ok {cell} FT done: {status.output_model}")
                elif status.state in {"failed", "cancelled", "error"}:
                    raise RuntimeError(f"{cell} FT failed: state={status.state}")
                else:
                    still_pending.append((cell, variant, size, job_id))
            pending_fts = still_pending

        # Find next ready cell to do inference
        next_cell = None
        for variant, size in cells:
            cell = f"{variant}_n{size}"
            if cell in completed_inf:
                continue
            idx = load_index()
            if cell in idx and idx[cell].get("ft_model"):
                next_cell = (cell, variant, size, idx[cell]["ft_model"])
                break

        if next_cell:
            cell, variant, size, ft_model = next_cell
            await generate_plans_cell(cell, ft_model, provider, profiles)
            completed_inf.add(cell)
        else:
            # No cell ready; FTs still training. Wait and retry.
            print(
                f"  [waiting] {len(pending_fts)} FT(s) still pending; sleep {FT_POLL_INTERVAL_S}s"
            )
            await asyncio.sleep(FT_POLL_INTERVAL_S)

    # ---- Phase 3: score all plans (no endpoint, fully concurrent) ----
    print("\n=== Phase 3: scoring (concurrent APS+PQS on Anthropic) ===")
    score_tasks = []
    cell_meta = []
    for variant, size in cells:
        cell = f"{variant}_n{size}"
        plans_path = PLANS_DIR / f"{cell}_plans.jsonl"
        eval_variant = f"{variant}_ft_n{size}"
        ft_model = load_index()[cell]["ft_model"]
        cell_meta.append((cell, variant, size, eval_variant))
        score_tasks.append(
            score_plans_cell(cell, plans_path, profiles_dict, eval_variant, ft_model)
        )
    summaries = await asyncio.gather(*score_tasks)

    # ---- Phase 4: publish breadth-first ----
    print("\n=== Phase 4: ablation table ===\n")
    print(f"{'N':>4s}  {'lynch APS':>10s}  {'bogle APS':>10s}  {'spread':>8s}")
    print("-" * 50)
    by_eval = {s["variant"]: s for s in summaries}
    for size in sizes:
        lyn = by_eval.get(f"lynch_ft_n{size}", {}).get("mean_aps")
        bog = by_eval.get(f"bogle_ft_n{size}", {}).get("mean_aps")
        spread = bog - lyn if (lyn is not None and bog is not None) else None
        print(f"{size:>4d}  {lyn:>10.3f}  {bog:>10.3f}  {spread:>+8.3f}")


if __name__ == "__main__":
    asyncio.run(main())
