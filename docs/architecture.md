# Subprime -- Architecture

## Module Map

```
src/subprime/
  core/             Pydantic models, config, Rich display helpers
  data/             DuckDB fund universe (RAG + tools), CAS/CIBIL/AIS parsers
  advisor/          Agent factory, plan generator, prompt templates + hooks
  evaluation/       APS + PQS judge agents, scoring criteria, persona bank
  experiments/      Conditions, experiment runner, statistical analysis
  finetuning/       Stage 2: harvest, curate, synthesise, train, evaluate
  flags/            Feature flags (GrowthBook-format, Postgres-backed)
  observability/    Span attributes + HyperDX wiring for per-session tracing
  cli.py            Typer CLI entry point

apps/web/
  main.py           FastAPI app factory + lifespan (DuckDB, scrubber, flags)
  api_v2/           React-SPA backend (session, strategy, plan/SSE, admin)
  frontend/         Vite + React + Tailwind 4-step wizard
  static/dist/      Built SPA (gitignored — `make frontend`)
```

## Dependency Flow

Arrows mean "depends on". No reverse dependencies.

```
core
  ^
  |
data          (core models: MutualFund)
  ^
  |
advisor       (core models: InvestmentPlan, InvestorProfile)
  ^            (data tools: search_funds, get_fund_performance, compare_funds)
  |
evaluation    (core models: APSScore, PlanQualityScore, InvestmentPlan)
  ^
  |
experiments   (advisor: generate_plan)
  ^            (evaluation: score_plan, personas)
  |
finetuning    (core models: InvestmentPlan)
  ^            (evaluation: score_aps, score_pqs, personas)
  |
cli           (experiments: run_experiment, print_analysis)
              (finetuning: build-dataset, train, evaluate, report)
```

## Module Details

### core/ -- Shared types and utilities

- `models.py` -- All Pydantic models: InvestorProfile, MutualFund, Allocation, StrategyOutline, InvestmentPlan, APSScore, PlanQualityScore, ExperimentResult
- `config.py` -- Settings via pydantic-settings (API keys, model defaults, base URLs)
- `display.py` -- Rich table/panel formatters for plans and scores. `format_*` returns strings; `print_*` writes to terminal.

### data -- MF data layer

Single source of truth: a local **DuckDB** store rebuilt from the
[InertExpert2911/Mutual_Fund_Data](https://github.com/InertExpert2911/Mutual_Fund_Data)
GitHub dataset. Contains scheme details, 20M+ historical NAV records,
computed 1y/3y/5y CAGRs and risk metrics (volatility, beta, alpha,
Sharpe, information ratio), and a curated top-N-per-category universe.

The advisor agent does **not** call mfdata.in (or any external API) at
plan-generation time — every fund fact the LLM sees comes from the
DuckDB store rendered into the system prompt and answered via two
DuckDB-backed tools. This decision is documented in
[ADR 006](adr/006-rag-plus-tool-calls-data-split.md).

Files:
- `store.py` -- DuckDB connection, schema (schemes, nav_history,
  fund_returns, fund_universe, refresh_log), connection helpers
- `ingest.py` -- Clone/refresh the GitHub repo, load CSV/parquet
  into `schemes` and `nav_history`, compute returns into `fund_returns`
- `universe.py` -- Three-tier ranked SQL that populates
  `fund_universe` (top-N-per-category) and renders it as markdown for
  RAG injection. See "RAG SQL" below.
- `tools.py` -- PydanticAI tools registered with the advisor:
  - `search_funds_universe(category, limit)` -- query the curated table
  - `get_fund_details(amfi_code)` -- single-fund lookup by AMFI code
- `client.py` -- `MFDataClient` (legacy async httpx wrapper for
  mfdata.in). **Not registered as an advisor tool**; retained only for
  one-off ad-hoc scripts.
- `cas.py`, `cibil.py`, `ais.py`, `documents.py` -- parsers for
  user-uploaded statements (CAS holdings, CIBIL credit, AIS tax),
  consumed by the React-SPA upload endpoints.

The DuckDB file lives at `$SUBPRIME_DATA_DIR/subprime.duckdb` (defaults to `~/.subprime/data/subprime.duckdb`).

#### RAG SQL — `build_universe`

The curated `fund_universe` table is rebuilt from `schemes` ⨝
`fund_returns` with a **three-tier quota** that ensures funds at every
stage of their track-record are represented per category:

| Tier | Track record | Slot quota | Rank by |
|---:|---|---:|---|
| 1 | Has 5y returns | ~40% | `returns_5y DESC, aum_cr DESC` |
| 2 | 3y but no 5y    | ~30% | `returns_3y DESC, aum_cr DESC` |
| 3 | 1y only         | rest | `returns_1y DESC, aum_cr DESC` |

Each tier ranks within itself so a 1y return is never compared against a
5y CAGR. Categories that come up empty across all three tiers fall
through to a fourth tier that picks by AUM alone — guarantees at least
one fund per category even where return history is sparse (e.g. Gold
ETFs).

The query is one CTE chain (`categorized → with_er → tier1/2/3 →
combined → fallback`) and runs in a single transaction; the
`fund_universe` table is rendered to markdown by `render_for_llm()` and
appended to the advisor's system prompt before plan generation. The
LLM sees expense ratios in the rendered table but they don't influence
selection — the model weighs cost vs. return freely.

### advisor/ -- Financial advisor agent

- `agent.py` -- `create_advisor()` factory. Assembles system prompt from base + planning + optional philosophy hook. Registers data tools. Returns a PydanticAI `Agent[InvestmentPlan]`.
- `planner.py` -- `generate_plan()` async function. Takes InvestorProfile + optional prompt_hooks, returns InvestmentPlan. This is the bulk/API entry point (no interactive Q&A).
- `prompts/base.md` -- Base system prompt: Indian MF advisor persona, guidelines, disclaimers.
- `prompts/planning.md` -- Plan structure instructions (allocations, setup phase, review checkpoints, projections, risks).
- `prompts/hooks/philosophy.md` -- Default philosophy hook (empty in baseline). Replaced by experiment conditions.

### evaluation/ -- Scoring infrastructure

- `criteria.py` -- APS_CRITERIA (5 dimensions) and PQS_CRITERIA (4 dimensions) as structured dicts. Anchors at 0.0 and 1.0 for each dimension. Used to programmatically build judge prompts.
- `judges.py` -- `create_aps_judge()` and `create_pqs_judge()` agent factories. Prompts assembled from criteria.py. `score_aps()` and `score_pqs()` convenience functions.
- `scorer.py` -- `ScoredPlan` model bundling plan + APS + PQS. `score_plan()` runs both judges.
- `personas.py` -- `load_personas()` and `get_persona()` loading from `personas/bank.json`.
- `personas/bank.json` -- Investor profile fixtures (diverse Indian investor personas).

### experiments/ -- Bias measurement

- `conditions.py` -- `Condition` dataclass (name, description, prompt_hooks). Pre-built: BASELINE, LYNCH, BOGLE. `get_condition()` lookup.
- `prompts/lynch.md` -- Peter Lynch philosophy injection (GARP, sector rotation, active management, quarterly review).
- `prompts/bogle.md` -- John Bogle philosophy injection (index funds, cost minimisation, buy-and-hold, annual review).
- `runner.py` -- `run_experiment()` runs the full matrix (personas x conditions). `run_single()` for one pair. Results saved as JSON.
- `analysis.py` -- `ConditionStats`, `ComparisonResult` dataclasses. `compare_conditions()` computes subprime spread, Cohen's d, paired t-test, Wilcoxon. `print_analysis()` renders Rich tables including rating blind spot detection.

### finetuning/ -- Stage 2: weight-level bias

Mirrors the Stage 1 experiment loop but moves the bias from the prompt to
the model weights. See [ADR 008](adr/008-stage2-finetuning.md) for the
design rationale and [ADR 009](adr/009-stage2-ablation-findings.md) for
the training-set ablation findings.

Two paths into a training corpus:

- `harvest.py` -- walk `research/results/runs/`, load every Lynch/Bogle
  experiment result, dedupe on `(persona_id, condition, model)`. The
  *original* Stage 2 path: reuses Stage 1 plans across mixed teachers.
- `synthesize.py` -- generate fresh Lynch/Bogle plans against any
  persona bank using Anthropic's Batch API with **tool-use forcing**
  (a `build_plan` tool returning `InvestmentPlan` is forced on every
  request) so output is guaranteed schema-valid. ~50% off list price
  + caching brings cost to ~$0.05/plan with Sonnet 4.6.
- `personas_gen.py` -- Sonnet-driven persona synthesis seeded by the
  canonical P01–P25 bank. Used to produce held-out training personas
  (G001–G720) for the ablation.

Then:

- `curate.py` -- filter records by APS direction (Lynch ≤ 0.40, Bogle ≥
  0.65), optionally cap to N per variant, stratified train/val split.
- `format.py` -- render `InvestorProfile` as plain text + `InvestmentPlan`
  as JSON into ChatML JSONL with a *neutral* (philosophy-stripped)
  system prompt. The fine-tune has to internalise the bias.
- `provider.py` -- `FineTuneProvider` Protocol + `TogetherProvider`
  implementation. Wraps Together's SDK (`fine_tuning`, `endpoints`,
  `chat.completions`) and handles the dedicated-endpoint lifecycle
  (create → wait STARTED → call → delete) with billing safety. Routes
  via the endpoint `name` field (Together's chat API rejects model IDs
  for FT models — see ADR 008 consequences).
- `train.py` -- `run_job()` orchestrator: upload → submit LoRA job →
  poll → persist `artifacts.json`. Resumable: a re-run with an existing
  manifest skips the FT submission.
- `evaluate.py` -- score a fine-tuned model on the 25-persona bank
  using a PydanticAI Agent with `PromptedOutput(InvestmentPlan)`,
  same as the prior advisor. Saves `ExperimentResult` JSONs alongside
  Stage 1 output. Includes a `build_serverless_agent()` for testing
  base models that have serverless support.
- `ablation_run.py` (in `product/scripts/`) -- resilient orchestrator
  for multi-cell ablations: split inference and scoring (so an endpoint
  can be torn down before the slow scoring pass), breadth-first
  iteration order so any stop point yields a complete row, signal
  handlers for clean endpoint teardown.
- `report.py` -- load eval results from
  `research/results/runs/finetune/{base, lynch_ft, bogle_ft}/` and
  `…/ablation/<variant>_n<size>/`; render the comparison markdown into
  `headline.md`.

### cli.py -- Command-line interface

Typer app. Stage 1: `experiment-run` / `experiment-analyze`. Stage 2:
the `ft` subgroup —

| Command | Purpose |
|---|---|
| `subprime ft build-dataset` | Harvest Stage 1 records → ChatML JSONL |
| `subprime ft smoke`         | One-persona smoke train/eval ($1) |
| `subprime ft train`         | Submit LoRA job for one variant |
| `subprime ft evaluate`      | 25-persona eval + APS/PQS scoring |
| `subprime ft report`        | Render `headline.md` from eval JSONs |
| `subprime ft personas-gen`  | Synthesise N held-out personas |
| `subprime ft synth-corpus`  | Sonnet batch + tool-use forcing |
| `subprime ft synth-smoke`   | Single-plan synth round-trip |
| `subprime ft ablation`      | Six-cell N=50/200/600 sweep |

### apps/web/api_v2/ -- React-SPA backend

Companion FastAPI router under `/api/v2/*`. The wizard frontend in
`apps/web/frontend/` consumes:

- `session.py`  -- session bootstrap, OTP verify (with `SUBPRIME_OTP_CHEAT`),
  tier select, persona/profile submit, document staging endpoints
- `strategy.py` -- POST `/strategy/generate` and `/strategy/revise`
  (synchronous LLM calls)
- `plan.py`     -- POST `/plan/generate` (kicks off background task)
  + GET `/plan/stream` (Server-Sent Events fanning out stage updates),
  GET `/plan` for the finished plan, `/plan/download.{pdf,xlsx}`
- `personas.py` -- list the persona bank (demo mode only)
- `admin.py`    -- feature flag CRUD, gated by `SUBPRIME_ADMIN_TOKEN`

The plan stage uses background-task + SSE specifically so the UI can
show stages-done as the agent loop progresses, instead of polling.

## Key Interfaces

**Advisor --> Data (tool calls)**: The advisor agent calls
`search_funds_universe(category, limit)` and `get_fund_details(amfi_code)`
during plan generation. Both are PydanticAI tools that read from the
local DuckDB store — no external HTTP requests at inference time.
The full curated universe is also injected into the system prompt as
markdown (RAG), so the agent has broad market context before the first
tool call.

**Experiments --> Advisor (prompt hooks)**: Each `Condition` carries a `prompt_hooks` dict. The `"philosophy"` key injects text into the advisor's system prompt. Baseline has empty hooks (no philosophy). Lynch/Bogle conditions load their respective philosophy prompts.

**Evaluation --> Advisor output (scoring)**: Judge agents receive the serialised `InvestmentPlan` (and optionally `InvestorProfile` for PQS) and return structured scores. Scoring is independent of plan generation -- judges never see the system prompt.
