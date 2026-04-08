# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

## Project Overview

**Subprime** measures how post-training interventions create hidden bias in LLM-based financial advisors. Like subprime mortgages with AAA ratings, a primed LLM advisor produces plans that *look* professional but silently steer investors toward a specific philosophy.

We build a financial advisor agent for Indian mutual funds, systematically prime it with opposing philosophies (Lynch active vs Bogle passive), and measure the bias shift using APS scoring while PQS (quality) remains high — the **rating blind spot**.

Course: "LLMs — A Hands-on Approach", CCE IISc (2026)

## Architecture

```
src/subprime/
├── core/                  # Shared types, config, Rich display
│   ├── models.py          # All Pydantic models
│   ├── config.py          # Settings (pydantic-settings)
│   └── display.py         # Rich renderables
├── data/                  # MF data layer
│   ├── schemas.py         # Raw mfdata.in response models
│   ├── client.py          # Async HTTP client (httpx)
│   └── tools.py           # PydanticAI tool functions
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
- **Data**: mfdata.in API (live), InertExpert2911/Mutual_Fund_Data (historical, planned)
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
