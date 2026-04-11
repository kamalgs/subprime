# Subprime -- Architecture

## Module Map

```
src/subprime/
  core/             Pydantic models, config, Rich display helpers
  data/             mfdata.in API client, response schemas, PydanticAI tools
  advisor/          Agent factory, plan generator, prompt templates + hooks
  evaluation/       APS + PQS judge agents, scoring criteria, persona bank
  experiments/      Conditions, experiment runner, statistical analysis
  cli.py            Typer CLI entry point
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
cli           (experiments: run_experiment, print_analysis)
```

## Module Details

### core/ -- Shared types and utilities

- `models.py` -- All Pydantic models: InvestorProfile, MutualFund, Allocation, StrategyOutline, InvestmentPlan, APSScore, PlanQualityScore, ExperimentResult
- `config.py` -- Settings via pydantic-settings (API keys, model defaults, base URLs)
- `display.py` -- Rich table/panel formatters for plans and scores. `format_*` returns strings; `print_*` writes to terminal.

### data -- MF data layer

Two complementary data sources:

1. **DuckDB store** (primary) -- Curated fund universe built from the
   InertExpert2911/Mutual_Fund_Data GitHub dataset. Contains scheme details,
   20M+ historical NAV records, computed 1y/3y/5y returns, and a
   top-N-per-category curated universe ranked by 5y CAGR.
2. **mfdata.in API** (real-time) -- Live NAV, current details, holdings.
   Used for verification before finalizing recommendations.

Files:
- `store.py` -- DuckDB connection, schema, refresh log
- `ingest.py` -- Download GitHub dataset, load CSV/parquet, compute returns
- `universe.py` -- Curate top funds per category, render as markdown context
- `client.py` -- Async httpx wrapper for mfdata.in
- `tools.py` -- PydanticAI tools: `search_funds_universe` (DuckDB),
  `get_fund_performance` (live), `compare_funds` (live)

The DuckDB file lives at `$SUBPRIME_DATA_DIR/subprime.duckdb` (defaults to `~/.subprime/data/subprime.duckdb`).

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

### cli.py -- Command-line interface

Typer app with two commands:

- `subprime experiment-run` -- run experiment matrix with options for persona, conditions, model, prompt version, results directory
- `subprime experiment-analyze` -- load result JSONs and print statistical analysis

## Key Interfaces

**Advisor --> Data (tool calls)**: The advisor agent calls `search_funds`, `get_fund_performance`, `compare_funds` during plan generation. These are registered as PydanticAI tools and make live HTTP requests to mfdata.in.

**Experiments --> Advisor (prompt hooks)**: Each `Condition` carries a `prompt_hooks` dict. The `"philosophy"` key injects text into the advisor's system prompt. Baseline has empty hooks (no philosophy). Lynch/Bogle conditions load their respective philosophy prompts.

**Evaluation --> Advisor output (scoring)**: Judge agents receive the serialised `InvestmentPlan` (and optionally `InvestorProfile` for PQS) and return structured scores. Scoring is independent of plan generation -- judges never see the system prompt.
