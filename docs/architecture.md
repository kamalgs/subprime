# Architecture

A Python monorepo. One package, two harnesses (CLI + web), shared core.

## Module map

```
src/subprime/
  core/             Pydantic models, config, observability, Rich display
  data/             DuckDB fund universe (RAG + tools), CAS/CIBIL/AIS parsers
  advisor/          Agent factory, plan generator, prompt templates + hooks
  evaluation/       APS + PQS judges, scoring criteria, persona bank
  experiments/      Conditions, runner, statistical analysis
  finetuning/       Stage 2: harvest, synthesise, curate, train, evaluate
  flags/            GrowthBook-format feature flags (Postgres-backed)
  cli.py            Typer entry point

apps/web/
  main.py           FastAPI app factory + lifespan
  api_v2/           SPA backend: session, strategy, plan/SSE, admin
  frontend/         Vite + React + Tailwind 4-step wizard
```

## Dependency DAG

Strict layering, no reverse edges:

```
core ← data ← advisor ← evaluation ← experiments ← cli
                                  ↖ finetuning  ↗
apps/web ← advisor, evaluation, data
```

## Modules

### core

Pydantic models for everything that crosses a module boundary
(`InvestorProfile`, `MutualFund`, `StrategyOutline`, `InvestmentPlan`,
`APSScore`, `PlanQualityScore`, `ExperimentResult`). `config.py` is
pydantic-settings; `display.py` renders Rich tables; `observability/`
holds span attributes for HyperDX.

### data

Single source of fund truth: a local DuckDB store rebuilt from the
[InertExpert2911/Mutual_Fund_Data](https://github.com/InertExpert2911/Mutual_Fund_Data)
GitHub dataset. The advisor reads exclusively from DuckDB at inference
time — no external API calls during plan generation
([ADR 006](adr/006-rag-plus-tool-calls-data-split.md)).

| File | Role |
|---|---|
| `store.py` | DuckDB schema (`schemes`, `nav_history`, `fund_returns`, `fund_universe`) |
| `ingest.py` | Pull GitHub dataset, load NAV history, compute returns |
| `universe.py` | Curate top-N-per-category with the three-tier ranked SQL; render as markdown |
| `tools.py` | PydanticAI tools: `search_funds_universe`, `get_fund_details` |
| `cas.py` / `cibil.py` / `ais.py` / `documents.py` | Parsers for user-uploaded statements |

`MFDataClient` in `client.py` is legacy — kept for ad-hoc scripts, not
registered as an advisor tool.

### advisor

`create_advisor()` returns a `PydanticAI Agent[InvestmentPlan]` with the
DuckDB tools registered. The system prompt is composed from
`prompts/base.md` + `prompts/planning.md` + an optional
`prompts/hooks/philosophy.md` hook + the curated fund universe rendered
as markdown. `generate_plan()` is the headless entry point used by both
the CLI and the SPA backend.

### evaluation

Two judge agents — `create_aps_judge()` (active-passive, 5 dimensions)
and `create_pqs_judge()` (plan quality, 4 dimensions) — assembled from
`criteria.py` (anchored 0.0/1.0 dimension descriptions). `score_plan()`
runs both. Personas live in `personas/bank.json` (P01–P25, the
canonical eval bank).

### experiments

`Condition` carries `prompt_hooks`. Pre-built: `BASELINE`, `LYNCH`,
`BOGLE`. `run_experiment()` iterates the persona × condition matrix
producing `ExperimentResult` JSONs. `analysis.py` computes condition
stats, paired Δ-APS, Cohen's *d*, paired *t*-test, Wilcoxon, and the
rating-blind-spot check.

### finetuning

Stage 2: bias in the weights. See [ADR 008](adr/008-stage2-finetuning.md)
(design) and [ADR 009](adr/009-stage2-ablation-findings.md) (ablation).

| File | Role |
|---|---|
| `harvest.py` | Walk Stage 1 runs, dedupe to a corpus (mixed-teacher) |
| `synthesize.py` | Generate fresh plans via Anthropic Batch + tool-use forcing |
| `personas_gen.py` | Sonnet-driven persona synthesis (held-out training personas) |
| `curate.py` | Filter by APS direction, stratified train/val split |
| `format.py` | Render to ChatML JSONL with neutral system prompt |
| `provider.py` | `FineTuneProvider` Protocol + `TogetherProvider` impl |
| `train.py` | Submit LoRA → poll → persist `artifacts.json` (resumable) |
| `evaluate.py` | Score FT model on the 25-persona bank, same path as Stage 1 |
| `report.py` | Render `headline.md` from eval JSONs |

The ablation orchestrator (`product/scripts/ablation_run.py`) splits
inference and scoring into separate passes so the dedicated endpoint can
be torn down before the slower judge calls.

### cli

Typer app. Stage 1: `experiment-run`, `experiment-analyze`. Stage 2:

| Command | Purpose |
|---|---|
| `subprime ft build-dataset` | Harvest + curate Stage 1 records → ChatML JSONL |
| `subprime ft synth-corpus`  | Sonnet batch + tool-use forcing (~$0.05/plan) |
| `subprime ft train`         | Submit LoRA job for one variant |
| `subprime ft evaluate`      | 25-persona eval + APS/PQS scoring |
| `subprime ft ablation`      | Six-cell N=50/200/600 sweep |
| `subprime ft report`        | Render `headline.md` |
| `subprime data refresh`     | Rebuild DuckDB from the GitHub dataset |

### apps/web/api_v2

FastAPI router under `/api/v2/*`, consumed by the React wizard:

| Module | Endpoints |
|---|---|
| `session.py`  | OTP verify (with `SUBPRIME_OTP_CHEAT`), tier select, persona/profile, document staging |
| `strategy.py` | `POST /strategy/generate`, `POST /strategy/revise` |
| `plan.py`     | `POST /plan/generate` (background task), `GET /plan/stream` (SSE), `GET /plan`, downloads |
| `personas.py` | List the persona bank (demo mode) |
| `admin.py`    | Feature-flag CRUD, gated by `SUBPRIME_ADMIN_TOKEN` |

The plan stage uses background-task + SSE so the SPA can render partial
plans (allocations + setup) while slower stages (risks, projections) are
still running.

## Key interfaces

- **Advisor → Data**: PydanticAI tool calls (`search_funds_universe`,
  `get_fund_details`) hit the local DuckDB store. The full curated
  universe is also injected into the system prompt as markdown (RAG).
- **Experiments → Advisor**: `Condition.prompt_hooks` injects philosophy
  text into the advisor's system prompt. Baseline = empty hook.
- **Evaluation → Advisor output**: Judges receive the serialised
  `InvestmentPlan` (and `InvestorProfile` for PQS). They never see the
  system prompt — scoring is independent of generation.
