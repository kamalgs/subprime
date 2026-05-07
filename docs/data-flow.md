# Data Flow

## Inference path (Stage 1)

For each `(persona, condition)` pair the runner produces one
`ExperimentResult`:

```
                       DuckDB (fund_universe + tools)
                              │
                              ▼
InvestorProfile ─────► Advisor Agent ─────► InvestmentPlan
   (+ Condition.prompt_hooks)                  │
                              ┌────────────────┴────────────────┐
                              ▼                                 ▼
                          APS Judge                          PQS Judge
                       (active-passive)                    (plan quality)
                              │                                 │
                              └─────────► ScoredPlan ◄──────────┘
                                              │
                                              ▼
                                      ExperimentResult
                                       (JSON on disk)
```

`run_experiment()` iterates the matrix; `analysis.compare_conditions()`
reads the JSONs back and computes per-condition stats, paired Δ-APS,
Cohen's *d*, paired *t*-test, Wilcoxon, and the rating-blind-spot check.

## RAG: fund universe injection

The advisor's system prompt is augmented with the curated `fund_universe`
table rendered as markdown — broad market context before the first tool
call. See [ADR 006](adr/006-rag-plus-tool-calls-data-split.md) for the
RAG vs. tool-calls split.

```
generate_plan(profile)
      │
      ▼
_load_universe_context()          ← reads fund_universe rows
      │                             from $SUBPRIME_DATA_DIR/subprime.duckdb
      ▼
create_advisor(universe_context=markdown_table)
      │                             ← appended to system prompt
      ▼
agent.run(...)                    ← may call search_funds_universe
                                    or get_fund_details (DuckDB)
```

Universe rebuild via `subprime data refresh`:

1. Pull CSV / parquet from `InertExpert2911/Mutual_Fund_Data` (raw GitHub URLs).
2. Load into `schemes` (~12k rows) and `nav_history` (~20M rows).
3. Compute 1y / 3y / 5y CAGRs and risk metrics into `fund_returns`.
4. Curate `fund_universe` via the three-tier query in
   [`subprime.data.universe.build_universe`](../product/src/subprime/data/universe.py).

The query partitions `schemes ⋈ fund_returns` by category, ranks within
each tier — Tier 1 (5y track record, ~40% of slots, by `returns_5y`),
Tier 2 (3y only, ~30%, by `returns_3y`), Tier 3 (1y only, rest, by
`returns_1y`) — then unions, with a fourth fallback by AUM for
categories that come up empty (e.g. Gold ETFs). Direct plans only;
IDCW/dividend variants excluded.

## Stage 2: training pipeline

Two paths feed the trainer; both end in ChatML JSONL with a *neutral*
system prompt — the fine-tune has to internalise the bias.

```
[Source A]                              [Source B]
research/results/runs/                  P01..P25 (canonical bank)
        │                                       │
        ▼                                       ▼
   harvest.py                            personas_gen.py (Sonnet)
        │                                       │
        ▼                                       ▼
   filter + dedupe                       720 fresh personas
        │                                       │
        │                                       ▼
        │                              synthesize.py
        │                              (Anthropic Batch
        │                               + tool-use forcing)
        │                                       │
        └───────────► curate.py ◄───────────────┘
                          │
                          ▼
              {lynch,bogle}_{train,val}.jsonl
                          │
                          ▼
              Together AI LoRA FT (Qwen3-14B, 3 epochs)
                          │
                          ▼
              dedicated endpoint (1×H100, scale-to-zero)
                          │
                          ▼
              PydanticAI Agent (PromptedOutput[InvestmentPlan])
                          │
                          ▼
              25-persona eval → score_aps + score_pqs
                          │
                          ▼
   research/results/runs/finetune/{variant,ablation}/
```

`provider.delete_endpoint()` runs in `finally` to stop billing — see
[ADR 008](adr/008-stage2-finetuning.md). The ablation orchestrator
(`product/scripts/ablation_run.py`) splits inference and scoring across
two passes so endpoints are deleted before the slow judge sweep.

## SPA: plan stream

Step 4 of the wizard uses Server-Sent Events to surface stage progress
as the agent runs, instead of polling.

```
POST /api/v2/plan/generate                    (returns 202)
        │
        ▼
   plan_runner.run(...)                       (background task)
        │
        ├── stages_done: ["core"]             ← partial plan exposed
        └── stages_done: ["core", "risks"]    ← ready=true

GET /api/v2/plan/stream                       (text/event-stream)
        event: stage
        data: {"stages_done": [...], "ready": true|false}
        ...
        event: done
        data: {}

Step4Plan.tsx
   EventSource → setStatus(...) → on ready, refetch GET /api/v2/plan
```

`GET /api/v2/plan` is idempotent and returns the latest persisted
snapshot; the SSE stream is purely a faster signal that something
changed.

## Artefacts

| Artefact             | Location                                                       | Format            |
|----------------------|----------------------------------------------------------------|-------------------|
| Persona bank         | `evaluation/personas/bank.json`                                 | JSON array        |
| Philosophy hooks     | `experiments/prompts/{lynch,bogle}.md`                          | Markdown          |
| Stage 1 results      | `research/results/runs/<run>/*.json`                            | `ExperimentResult` |
| Stage 2 datasets     | `finetuning/artifacts/datasets/{lynch,bogle}_{train,val}.jsonl` | ChatML JSONL      |
| Stage 2 eval results | `research/results/runs/finetune/{base,lynch_ft,bogle_ft}/*.json` | `ExperimentResult` |
| Ablation results     | `research/results/runs/finetune/ablation/<variant>_n<N>/*.json` | `ExperimentResult` |
| Headlines            | `research/results/runs/finetune/[ablation/]headline.md`         | Markdown          |
