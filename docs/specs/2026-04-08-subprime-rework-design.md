# Subprime Rework — Design Spec

## Context

Subprime measures how post-training interventions create hidden bias in LLM-based financial advisors. The original scaffold was a single-pass pipeline: persona in → plan out → score. This rework restructures into independent modules with a full-featured, interactive financial advisor at the centre — something real users can try and give feedback on — with the research/experiment layer built on top.

Target audience: Indian investors with basic financial literacy. MF-only for v1.

## Module Structure

Monorepo, single package, subpackages with strict dependency flow:

```
src/subprime/
├── core/               # Shared types, config, display renderables
├── data/               # mfdata.in client, DuckDB store, PydanticAI tools
├── advisor/            # Financial advisor agent, prompts, profile gathering, planning
├── evaluation/         # Persona generation, judging criteria, scoring
├── experiments/        # Bias conditions, experiment runner, statistical analysis
└── cli.py              # Typer entry point
apps/
└── web/                # Gradio web harness (later milestone)
docs/
├── overview.md
├── architecture.md
├── data-flow.md
├── roadmap.md
└── adr/
tests/
├── test_data/
├── test_advisor/
├── test_evaluation/
└── test_experiments/
```

**Dependency flow (strict, no cycles):**

```
core  ←  data  ←  advisor  ←  evaluation  ←  experiments
```

- `core` depends on nothing
- `data` depends on `core`
- `advisor` depends on `core` + `data`
- `evaluation` depends on `core` + `advisor`
- `experiments` depends on all of the above

---

## Module Designs

### core — Shared types, config, display

```
src/subprime/core/
├── __init__.py
├── models.py
├── config.py
└── display.py
```

**models.py** — All Pydantic BaseModel classes:

- `InvestorProfile`: age, risk_appetite (Literal: conservative/moderate/aggressive), investment_horizon_years, monthly_investible_surplus_inr, existing_corpus_inr, liabilities_inr, financial_goals (list[str]), life_stage, tax_bracket, preferences (optional free-text)

- `MutualFund`: amfi_code, name, category, sub_category, fund_house, nav, expense_ratio, aum, morningstar_rating, returns_1y/3y/5y (optional), risk_grade (Literal: low/moderate/high/very_high)

- `Allocation`: fund (MutualFund), allocation_pct, mode (Literal: lumpsum/sip/both), monthly_sip_inr (optional), lumpsum_inr (optional), rationale

- `StrategyOutline`: equity_pct, debt_pct, gold_pct, other_pct, equity_approach (str), key_themes (list[str]), risk_return_summary (str), open_questions (list[str])

- `InvestmentPlan`: allocations (list[Allocation]), setup_phase (str), review_checkpoints (list[str]), rebalancing_guidelines (str), projected_returns (dict: base/bull/bear CAGR %), rationale (str), risks (list[str]), disclaimer (str)

- `APSScore`: passive_instrument_fraction, turnover_score, cost_emphasis_score, research_vs_cost_score, time_horizon_alignment_score, composite_aps (computed), reasoning

- `PlanQualityScore`: goal_alignment, diversification, risk_return_appropriateness, internal_consistency, composite_pqs (computed), reasoning

- `ExperimentResult`: persona_id, condition, model, plan, aps, pqs, timestamp, prompt_version

**config.py** — pydantic-settings BaseSettings: anthropic_api_key, default_model, mfdata_base_url, cache_dir, results_dir

**display.py** — Rich renderables (progressively enhanced to Textual widgets):
- `PlanCard(plan)` → Rich Panel
- `AllocationTable(allocations)` → Rich Table
- `ScenarioPanel(projected_returns)` → base/bull/bear side-by-side
- `ScoreGauge(aps_score)` → dimensional breakdown with bar indicators
- `BiasHeatmap(analysis_report)` → dimension-level bias comparison

Core renderables defined once, used by CLI natively, adapted for web/PDF by their respective harnesses.

---

### data — MF data layer

```
src/subprime/data/
├── __init__.py
├── client.py
├── store.py
├── schemas.py
└── tools.py
```

**Data sources:**

1. **mfdata.in API** — Real-time NAV, holdings, sector allocation, fund analytics. No auth required, no rate limits. Best for live/detail queries.
2. **InertExpert2911/Mutual_Fund_Data** (GitHub) — 9K+ scheme details (CSV) + 20M+ historical NAV records (Parquet). Daily automated updates from AMFI. MIT licensed. Best for historical performance calculations, backtesting, bulk analytics.

**Two data paths, one interface:**

- **RAG path**: curated fund universe (top schemes per category with summary stats) loaded into agent context from DuckDB. Seeded from the GitHub dataset's scheme details + enriched with mfdata.in analytics.
- **Tool call path**: live/detail queries to mfdata.in for real-time NAV, holdings, sector allocation

**client.py** — Async httpx wrapper around mfdata.in:
- `search_funds(query, category?, fund_house?)` → list of fund summaries
- `get_fund_details(amfi_code)` → full fund info
- `get_nav_history(amfi_code, period?)` → historical NAV series
- `get_holdings(amfi_code)` → portfolio holdings with sector allocation
- Response caching (TTL-based)

**store.py** — DuckDB/DuckLake persistence:
- Ingest GitHub dataset: scheme details CSV → `fund_universe` table, NAV parquet → `nav_history` table
- Ingest mfdata.in API responses: `holdings`, `sector_allocation` tables
- `fund_universe` table is the RAG source (seeded from GitHub dataset, enriched with mfdata.in)
- Computed tables: `fund_returns` (CAGR 1y/3y/5y from NAV history), `fund_risk` (volatility, max drawdown)
- Bulk refresh: re-pull GitHub dataset periodically. On-demand for mfdata.in detail queries.

**schemas.py** — Raw response models for both sources (separate from core models)

**tools.py** — PydanticAI tool functions registered on the advisor agent:
- `search_funds(query, category)` — searches curated universe first, falls back to live API
- `get_fund_performance(amfi_code)` — live NAV, returns, risk metrics
- `get_fund_holdings(amfi_code)` — current portfolio composition
- `compare_funds(amfi_codes: list)` — side-by-side comparison
- Returns typed core models

**Tracer bullet**: client.py calls mfdata.in directly, tools.py wraps client, no DuckDB yet.

---

### advisor — Financial advisor agent

```
src/subprime/advisor/
├── __init__.py
├── agent.py
├── prompts/
│   ├── base.md
│   ├── planning.md
│   └── hooks/
│       └── philosophy.md
├── profile.py
└── planner.py
```

**Three-phase collaborative flow:**

Phase 1 — **Profile Gathering** (multi-turn Q&A):
- Agent asks questions one at a time, validates, builds InvestorProfile incrementally
- Bulk mode: accepts complete InvestorProfile directly (for experiments/API)

Phase 2 — **Strategy Co-creation** (propose → react → revise loop):
- Agent proposes a StrategyOutline: high-level allocation direction, reasoning, risk/return expectations, open questions
- User reacts ("too conservative", "add gold", "what about 80C?")
- Agent revises, explains trade-offs
- Multiple rounds until user approves
- No specific funds yet — just direction

Phase 3 — **Detailed Plan Generation**:
- Fires after strategy approval
- Tool calls: search_funds, get_fund_performance, compare_funds
- Returns InvestmentPlan with real funds, AMFI codes, SIP amounts, scenarios

**agent.py** — Factory:
- `create_advisor(prompt_hooks: dict[str, str] | None)` → PydanticAI Agent
- Composes system prompt: base.md + planning.md + hook content
- Registers tools from data.tools
- Hook mechanism: `prompt_hooks={"philosophy": "path/to/lynch.md"}` injects content into the philosophy slot. Empty by default (neutral baseline). This is how experiments spike the advisor.

**Prompt design:**
- `base.md`: SEBI-style advisor personality, Indian market context, basic financial literacy target, tone, disclaimers
- `planning.md`: Plan structure instructions, SIP/lumpsum guidance, review cadence, scenario modeling
- `hooks/philosophy.md`: Empty. Experiments inject Lynch/Bogle content here.

**Harness integration:**
- CLI/web: all three phases interactively
- API/bulk: skip Phase 1+2, go straight to Phase 3 with pre-built profile + optional strategy override
- Experiments: bulk mode with hook injection

---

### evaluation — Persona generation, judging, scoring

```
src/subprime/evaluation/
├── __init__.py
├── personas.py
├── criteria.py
├── judges.py
└── scorer.py
```

**personas.py**:
- `PersonaBank`: load/save personas from JSON
- `generate_personas(n, constraints?)` → list[InvestorProfile]: LLM-powered, diverse Indian investor profiles
- Constraints: specify distributions (e.g. "5 conservative retirees, 5 aggressive millennials")
- Hand-crafted seed personas as anchors, generated ones supplement
- Stable IDs for paired statistical tests

**criteria.py** — Judging criteria as structured data:
- `APSCriteria`: 5 APS dimensions with descriptions, scoring guidance, 0.0/1.0 anchors
- `PQSCriteria`: 4 PQS dimensions with similar structure
- Criteria are data — judge prompts assembled from these definitions
- Easy to add dimensions or adjust guidance without touching agent code

**judges.py**:
- `create_aps_judge(model?)` → Agent with output_type=APSScore
- `create_pqs_judge(model?)` → Agent with output_type=PlanQualityScore
- Judge prompts assembled from criteria.py definitions
- Judges receive: plan + persona + criteria. Each score includes per-dimension reasoning.

**scorer.py** — Orchestrator:
- `score_plan(plan, profile)` → ScoredPlan (plan + APS + PQS)
- Runs both judges in parallel
- `score_batch(plans)` for experiment runs
- Retries, logging, cost tracking

---

### experiments — Bias experiments & analysis

```
src/subprime/experiments/
├── __init__.py
├── conditions.py
├── prompts/
│   ├── lynch.md
│   └── bogle.md
├── runner.py
└── analysis.py
```

**conditions.py** — Experiment conditions as data:
- Each condition: `{name, prompt_hooks, description}`
- `baseline`: no philosophy hook
- `lynch`: `{"philosophy": "experiments/prompts/lynch.md"}` — active stock-picking adapted for Indian MF (sector funds, small-cap active, concentrated)
- `bogle`: `{"philosophy": "experiments/prompts/bogle.md"}` — index philosophy for Indian context (Nifty 50/Next 50, low expense, broad market)
- Contaminant prompts live under experiments/prompts/ (separate from advisor's base prompts)

**runner.py**:
- `run_experiment(personas, conditions, model, repeats=1)` → list[ExperimentResult]
- Matrix: every persona × every condition
- Inject hook → advisor bulk mode → score via evaluation
- Save results as JSON. Progress tracking, cost estimation, resume from partial.

**analysis.py**:
- Load results into DuckDB
- Subprime spread: ∆APS between baseline and spiked conditions
- Spike magnitude: Cohen's d
- Rating blind spot: ∆PQS vs ∆APS correlation
- Bias dimensions: which APS dimensions shift most
- Statistical tests: paired t-test, Wilcoxon, confidence intervals
- Output: AnalysisReport model + Rich tables

---

### Harnesses

**cli.py** — Typer entry point:
```
subprime advise              # Interactive three-phase flow
subprime advise --profile P01  # Bulk mode
subprime evaluate --profile P01
subprime experiment run
subprime experiment analyze
subprime data refresh
```

Interactive mode uses Textual TUI (Rich-powered). Core renderables from display.py used directly.

**apps/web/app.py** — Gradio (later milestone):
- Chat-based three-phase flow in browser
- Plan display with Plotly charts
- Same agent, web harness

**PDF export** — WeasyPrint from structured plan data, shared template. Later milestone.

---

## Tracer Bullet Scope

The minimum end-to-end slice proving all modules connect:

| Component | Tracer bullet state |
|-----------|-------------------|
| core/models.py | Real — all models defined |
| core/config.py | Real — settings loaded |
| core/display.py | Minimal — basic Rich tables |
| data/client.py | Real — hits mfdata.in, returns typed models |
| data/store.py | Stub — no DuckDB, client called directly |
| data/tools.py | Real — wired to client, registered on agent |
| advisor/agent.py | Real — PydanticAI agent with tools + hook injection |
| advisor/prompts/ | Real — base.md + planning.md + empty hook |
| advisor/profile.py | Stub — accepts InvestorProfile directly, no Q&A |
| advisor/planner.py | Real — calls agent, returns InvestmentPlan |
| evaluation/personas.py | Minimal — loads from JSON, no LLM generation |
| evaluation/criteria.py | Real — APS + PQS criteria defined |
| evaluation/judges.py | Real — both judge agents functional |
| evaluation/scorer.py | Real — runs both judges, returns ScoredPlan |
| experiments/conditions.py | Real — baseline + lynch defined |
| experiments/runner.py | Minimal — one persona × two conditions |
| experiments/analysis.py | Minimal — computes ∆APS + prints, no DuckDB |
| cli.py | Minimal — experiment run command only |
| apps/web/ | Not started |

**Success criteria:** Run `subprime experiment run --persona P01 --conditions baseline,lynch` and see a real plan with Indian MF names, APS/PQS scores, and visible APS shift.

---

## Roadmap

### M0: Tracer Bullet
- One persona, two conditions, live mfdata.in, scores printed
- All modules wired thin, end-to-end

### M1: Interactive Advisor
- Three-phase collaborative flow: Profile → Strategy co-creation → Detailed plan
- Textual TUI, Rich display (PlanCard, AllocationTable, ScenarioPanel)
- `subprime advise` — the command you hand to someone

### M2: Data Layer + Polish
- DuckDB store, fund universe cache, RAG path
- Fund comparison tool
- PDF export
- `subprime data refresh`

### M3: Gradio Web Interface
- Chat-based three-phase flow in browser
- Plotly charts, shareable

### M4: Evaluation Infrastructure
- LLM-powered persona generator (30+ profiles)
- Expanded calibration test suites
- Batch scoring pipeline

### M5: Experiments & Bias Analysis
- Full matrix: all personas × all conditions
- Statistical analysis, subprime spread, rating blind spot
- Prompt version comparison

### M6: Paper & Advanced Analysis
- Dimension-level bias breakdown, robustness checks
- Jupyter notebook for figures, paper draft

### M7: Phase 2 — Fine-tuning (stretch)
- Synthetic corpora, QLoRA, ablation studies
