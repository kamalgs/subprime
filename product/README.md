# Benji — AI Financial Advisor

> Powered by Subprime research. Built for Indian mutual fund planning.

<video src="finadvisor-demo-product.mp4" controls width="390"></video>

## Quick Start

```bash
uv sync
cp .env.example .env   # add ANTHROPIC_API_KEY

# Start the web advisor
uv run uvicorn "apps.web.main:create_app" --factory --host 0.0.0.0 --port 8000

# Run experiments via CLI
subprime experiment-run --persona P01 --conditions baseline,lynch
subprime experiment-analyze --results-dir ../research/results/

# Run tests
uv run pytest
```

## Structure

```
product/
  src/subprime/
    core/           Pydantic models, config, Rich display
    data/           DuckDB store, mfdata.in client, PydanticAI tools
    advisor/        FinAdvisor agent factory + prompt templates
    evaluation/     APS + PQS judge agents, scoring criteria, persona bank
    experiments/    Conditions (baseline/lynch/bogle), runner, analysis
    cli.py          Typer CLI entry point
  apps/web/         FastAPI + HTMX advisor UI
  tests/            Full test suite (601 passing)
  migrations/       Alembic DB migrations
  Dockerfile
```

## How It Works

1. **Advise** — FinAdvisor generates a mutual fund plan for an investor profile using live fund data via tool calls
2. **Evaluate** — Two independent LLM judges score the plan: APS (active-passive bias) and PQS (plan quality)
3. **Analyse** — Statistical comparison across conditions reveals the subprime spread and the rating blind spot

## Documentation

- [Architecture](../docs/architecture.md) — Module map, dependency flow, key interfaces
- [Data Flow](../docs/data-flow.md) — End-to-end pipeline, experiment matrix
- [Roadmap](../docs/roadmap.md) — Milestones M0 through M7
- [ADRs](../docs/adr/) — Architecture decision records

## Disclaimer

All outputs are for academic research purposes only. Nothing constitutes financial advice.
