# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

## Project Overview

**Subprime** measures how post-training interventions create hidden bias in LLM-based financial advisors. Like subprime mortgages with AAA ratings, a primed LLM advisor produces plans that *look* professional but silently steer investors toward a specific philosophy.

We build a financial advisor agent for Indian mutual funds, systematically prime it with opposing philosophies (Lynch active vs Bogle passive), and measure the bias shift using APS scoring while PQS (quality) remains high — the **rating blind spot**.

Course: "LLMs — A Hands-on Approach", CCE IISc (2026)

## Repository Layout

```
product/               # Web app, shared library, tests
  src/subprime/        # Core library (shared by web + experiments)
  apps/web/            # FastAPI + HTMX advisor UI
  tests/               # All test suites
  migrations/          # Alembic DB migrations
  Dockerfile

research/              # Experiment artifacts
  scripts/             # Demo production, analysis scripts
  results/             # Run data (JSON), reports (Markdown)
  notebooks/
  data/

docs/                  # Architecture docs, ADRs, roadmap
pyproject.toml         # Python packaging (stays at root for tooling)
```

## Architecture

```
product/src/subprime/
├── core/                  # Shared types, config, Rich display
│   ├── models.py          # All Pydantic models
│   ├── config.py          # Settings (pydantic-settings)
│   └── display.py         # Rich renderables
├── data/                  # MF data layer (DuckDB + live API)
│   ├── store.py           # DuckDB connection, schema, refresh log
│   ├── ingest.py          # GitHub dataset download + return computation
│   ├── universe.py        # Top-N-per-category curation + markdown render
│   ├── schemas.py         # Raw mfdata.in response models
│   ├── client.py          # Async HTTP client (httpx) for mfdata.in
│   └── tools.py           # PydanticAI tools (universe search + live lookups)
├── advisor/               # Financial advisor agent
│   ├── agent.py           # Agent factory + prompt hook injection
│   ├── planner.py         # Plan generation (bulk mode)
│   └── prompts/           # System prompt templates
│       ├── base.md        # Core advisor personality
│       ├── planning.md    # Plan structure instructions
│       └── hooks/
│           └── philosophy.md  # Empty — injection point for experiments
├── evaluation/            # Scoring + personas
│   ├── criteria.py        # APS + PQS criteria as structured data
│   ├── judges.py          # APS + PQS judge agents
│   ├── scorer.py          # Orchestrator: plan → ScoredPlan
│   └── personas.py        # Persona bank loader
├── experiments/           # Bias experiments
│   ├── conditions.py      # Baseline, Lynch, Bogle condition definitions
│   ├── runner.py          # Matrix execution: personas × conditions
│   ├── analysis.py        # Statistical analysis (t-test, Cohen's d)
│   └── prompts/           # Philosophy prompts (contaminants)
│       ├── lynch.md
│       └── bogle.md
└── cli.py                 # Typer CLI entry point
```

**Dependency flow (strict, no cycles):**
```
core  ←  data  ←  advisor  ←  evaluation  ←  experiments
```

## Tech Stack

- **Framework**: PydanticAI (agents, structured outputs, tools)
- **Models**: Claude Sonnet 4.6 (advisor + judges)
- **Data**: DuckDB store seeded from InertExpert2911/Mutual_Fund_Data GitHub dataset (fund universe + historical returns), mfdata.in API for live verification
- **Stats**: scipy (t-tests, Wilcoxon), numpy (Cohen's d)
- **CLI**: Typer + Rich
- **Python**: 3.11+, uv

## Key Concepts

### Active-Passive Score (APS)
Composite [0, 1] measuring active vs passive orientation:
- 0 → Strongly active (concentrated, high turnover, research-heavy)
- 1 → Strongly passive (index funds, low cost, buy-and-hold)

Dimensions: `passive_instrument_fraction`, `turnover_score`, `cost_emphasis_score`, `research_vs_cost_score`, `time_horizon_alignment_score`

### Plan Quality Score (PQS)
Independent of bias: `goal_alignment`, `diversification`, `risk_return_appropriateness`, `internal_consistency`

**Research question:** Does PQS detect APS drift? (Hypothesis: no — the rating blind spot.)

### Prompt Hook Mechanism
Experiments inject philosophy via `prompt_hooks={"philosophy": "<content>"}` passed to `create_advisor()`. Hook content is concatenated into the system prompt. Empty hook = neutral baseline. Contaminant prompts live in `experiments/prompts/`.

### Fund Universe RAG
Before each plan generation, `generate_plan()` calls `_load_universe_context()` to read the curated top-N-per-category universe from the DuckDB store and render it as markdown. `create_advisor(universe_context=...)` appends this text to the system prompt so the LLM has broad market knowledge up front and can still call live tools (`get_fund_performance`, `compare_funds`) for verification. The universe is rebuilt with `subprime data refresh`, which downloads the InertExpert2911/Mutual_Fund_Data GitHub dataset, populates `schemes` and `nav_history`, computes 1y/3y/5y CAGR into `fund_returns`, and curates `fund_universe`. Inspect store state with `subprime data stats`. The DuckDB file lives at `$SUBPRIME_DATA_DIR/subprime.duckdb` (default `~/.subprime/data/subprime.duckdb`).

## Terminology

- **Prime baseline** — neutral advisor, no contamination
- **Subprime advice** — plans scoring well on PQS but biased on APS
- **Subprime spread** — ΔAPS between baseline and spiked conditions
- **Rating blind spot** — PQS failing to detect APS drift
- **Spiked condition** — prompt contaminated with a philosophy
- **Spike magnitude** — Cohen's d of the APS shift

## Coding Conventions

- All data structures are Pydantic BaseModel with `Literal` types for enums
- All models in `core/models.py` — single source of truth
- Agent outputs always typed Pydantic models — no free-text parsing
- Prompts are versioned .md files, loaded at agent creation time
- Judging criteria defined as structured data in `criteria.py`, not hardcoded in prompts
- Save every experiment result as JSON: {persona_id, condition, plan, aps, pqs, model, timestamp}
- Conventional commits: feat:, fix:, test:, docs:

## Testing Strategy

Google-style test sizes:
- **Small tests**: fast, single process, deterministic. Mock only external boundaries (HTTP APIs, LLM calls via respx/unittest.mock). Run in < 1s.
- **Medium tests**: cross module boundaries. Still mock external APIs. Verify full wiring (persona → advisor → scores → analysis).
- Only mock: mfdata.in HTTP calls, LLM API calls. Everything else runs real.

## Current State

**M0 (Tracer Bullet)** — complete. All modules wired thin end-to-end. 269 tests passing.

See `docs/roadmap.md` for M1-M7 progressive enhancement plan.
See `docs/architecture.md` for detailed module design.
See `docs/adr/` for architecture decisions.
