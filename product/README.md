# Benji — AI Financial Advisor

> Powered by Subprime research. Built for Indian mutual fund planning.

<video src="https://github.com/kamalgs/subprime/releases/download/v0.1-demo/product-demo.mp4" controls width="390"></video>

A working LLM financial advisor for Indian mutual-fund planning, plus the
research harness that measures how easily its recommendations can be
biased — first via system prompts (Stage 1), then via fine-tuned weights
(Stage 2), then via training-set ablations (Stage 2 follow-up).

The product is live at <https://finadvisor.gkamal.online>.

## Quick Start

```bash
uv sync
cp .env.example .env       # add OPENROUTER_API_KEY (advisor) +
                           # ANTHROPIC_API_KEY (Stage 2 synth, optional) +
                           # TOGETHER_API_KEY (Stage 2 fine-tune, optional)

# Start the web advisor (React SPA + FastAPI)
make frontend              # builds apps/web/static/dist via Vite
uv run uvicorn "apps.web.main:create_app" --factory --host 0.0.0.0 --port 8000

# Run Stage 1 experiments (prompt-level bias)
subprime experiment-run --persona P01 --conditions baseline,lynch,bogle
subprime experiment-analyze --results-dir ../research/results/

# Run Stage 2 fine-tuning loop (weight-level bias)
subprime ft build-dataset                              # harvest + curate
subprime ft train --variant lynch                      # LoRA on Together
subprime ft evaluate --variant lynch_ft                # 25-persona eval
subprime ft report                                     # headline markdown

# Run Stage 2 training-set ablation
subprime ft synth-corpus --variant lynch --n 720       # Sonnet batch synth
subprime ft ablation --sizes 50,200,600                # six-cell sweep

# Tests
uv run pytest                              # full suite
SUBPRIME_URL=https://finadvisor.gkamal.online \
  uv run pytest -m browser                 # live browser smoke
```

## Structure

```
product/
  src/subprime/
    core/             Pydantic models, config, Rich display, observability
    data/             DuckDB fund universe (RAG + tools), CAS/CIBIL/AIS parsers
    advisor/          FinAdvisor agent factory + prompt templates + hooks
    evaluation/       APS + PQS judge agents, scoring criteria, persona bank
    experiments/      Conditions (baseline/lynch/bogle), runner, analysis
    finetuning/       Stage 2: harvest, curate, synthesise, train, evaluate
    flags/            Feature flags (GrowthBook-format, Postgres-backed)
    observability/    Span attributes, HyperDX wiring
    cli.py            Typer CLI: experiment-run, experiment-analyze, ft …
  apps/web/
    main.py           FastAPI app factory
    api_v2/           React SPA backend: session, strategy, plan/SSE, admin
    frontend/         Vite + React + Tailwind wizard (4-step flow)
    static/dist/      Built SPA (gitignored — `make frontend`)
  tests/              ~600 unit + integration tests; live browser smokes
  Dockerfile
```

## How It Works

1. **Advise** — FinAdvisor generates a mutual-fund plan for an investor profile.
   The agent (PydanticAI over OpenRouter) reads a curated DuckDB fund universe
   (rebuilt from the InertExpert2911/Mutual_Fund_Data GitHub repo) and queries
   it via two DuckDB-backed tools — no external HTTP at inference time.
2. **Evaluate** — Two independent LLM judges score the plan: APS (active-vs-passive
   bias, 5 dimensions) and PQS (plan quality, 4 dimensions).
3. **Analyse** — Statistical comparison across personas × conditions reveals the
   subprime spread (ΔAPS) and the rating blind spot (PQS flat while APS shifts).

The web app is the same advisor wired into a 4-step wizard (tier → profile →
strategy → plan), with the plan stage streaming progress over Server-Sent
Events.

## Stage 2 — Bias in the Weights

Stage 1 manipulates the running system prompt. Stage 2 bakes the bias into the
model: LoRA fine-tunes of Qwen3-14B on Lynch- or Bogle-aligned plans,
evaluated under a **neutral** prompt. A prompt audit reveals nothing; APS
still shifts ~0.36 between variants. The follow-up ablation sweeps
training-set size (50 / 200 / 600) with a clean Sonnet teacher and shows
saturation by N=200, plus PQS rising with N regardless of philosophy
direction.

Numbers and writeups: [`research/results/reports/04_stage2_finetuning.md`](../research/results/reports/04_stage2_finetuning.md),
[`research/results/reports/05_stage2_ablation.md`](../research/results/reports/05_stage2_ablation.md).

## Documentation

- [Architecture](../docs/architecture.md) — Module map, dependency flow, key
  interfaces
- [Data Flow](../docs/data-flow.md) — End-to-end pipeline, experiment matrix,
  Stage 2 training pipeline, React SPA stream
- [Operations](../docs/operations.md) — OpenRouter routing, feature flags,
  email, deploys, observability
- [Roadmap](../docs/roadmap.md) — Milestones M0–M7
- [ADRs](../docs/adr/) — Architecture decisions, including ADR 008 (Stage 2)
  and ADR 009 (ablation findings)

## Disclaimer

All outputs are for academic research purposes only. Nothing constitutes
financial advice.
