# Subprime -- Data Flow

## Fund Universe Injection (RAG)

Before plan generation, the advisor agent's system prompt is augmented
with the curated fund universe rendered as markdown. This gives the LLM
broad market knowledge at the start so it can reason about fund selection
without an initial blind search.

The advisor reads everything from a local DuckDB store — there are no
live HTTP calls to mfdata.in or any other external API at inference
time. See [ADR 006](adr/006-rag-plus-tool-calls-data-split.md) for the
RAG-vs-tool-calls split.

```
generate_plan(profile)
   |
   v
_load_universe_context()   <- reads fund_universe rows from
   |                          $SUBPRIME_DATA_DIR/subprime.duckdb
   v
create_advisor(universe_context=markdown_table)
   |                       <- text appended to system prompt
   v
agent.run(...)   <- LLM may call search_funds_universe / get_fund_details
                    (both DuckDB-backed) to drill into specific funds
```

The DuckDB store is rebuilt via `subprime data refresh`:

1. **Pull** CSV and parquet from
   `InertExpert2911/Mutual_Fund_Data` on GitHub (via raw URLs; no API key
   needed).
2. **Load** into the DuckDB tables `schemes` (~12k schemes with metadata)
   and `nav_history` (~20M+ daily NAV rows).
3. **Compute** 1y / 3y / 5y CAGRs and risk metrics (volatility, beta,
   alpha, Sharpe, information ratio) into `fund_returns` via a single
   SQL pass over the NAV history.
4. **Curate** the top-N-per-category `fund_universe` via the three-tier
   quota query in `subprime.data.universe.build_universe` (see below).

### Three-tier curation SQL

`build_universe` ensures each category is represented across the
funds-track-record spectrum, so the LLM is never forced to compare a
1y CAGR against a 5y CAGR. Per category:

```
WITH categorized AS (
    -- normalise scheme_category -> canonical category
    -- exclude IDCW / dividend variants and regular-plan duplicates
    SELECT s.amfi_code, s.name, ..., r.returns_1y, r.returns_3y, r.returns_5y
    FROM schemes s LEFT JOIN fund_returns r USING (amfi_code)
    WHERE coalesce(s.nav_name, s.name) NOT ILIKE '%IDCW%'
      AND coalesce(s.nav_name, s.name) NOT ILIKE '%dividend%'
      AND (COALESCE(s.plan_type, 'regular') = 'direct'
           OR s.scheme_category ILIKE '%ETF%')
),
with_er AS ( /* attach typical category expense ratio */ ),

-- Tier 1 (~40%): established funds with 5y track record
tier1 AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY category
                                       ORDER BY returns_5y DESC, aum_cr DESC) AS rn
          FROM with_er WHERE returns_5y IS NOT NULL),

-- Tier 2 (~30%): 3y but no 5y data
tier2 AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY category
                                       ORDER BY returns_3y DESC, aum_cr DESC) AS rn
          FROM with_er WHERE returns_5y IS NULL AND returns_3y IS NOT NULL),

-- Tier 3 (rest): 1y only
tier3 AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY category
                                       ORDER BY returns_1y DESC, aum_cr DESC) AS rn
          FROM with_er WHERE returns_5y IS NULL AND returns_3y IS NULL),

-- Merge tiers respecting per-tier slot caps; tier 4 fills empty categories
combined AS (
    SELECT * FROM tier1 WHERE rn <= ceil(top_n*0.40) UNION ALL
    SELECT * FROM tier2 WHERE rn <= ceil(top_n*0.30) UNION ALL
    SELECT * FROM tier3 WHERE rn <= top_n - ceil(top_n*0.40) - ceil(top_n*0.30)
),
fallback AS ( /* by AUM, only categories not represented above */ )

INSERT INTO fund_universe SELECT ... FROM combined UNION ALL fallback;
```

Source: [`product/src/subprime/data/universe.py`](../product/src/subprime/data/universe.py)
(`build_universe` and `_category_case_sql`). The curated table is then
rendered to markdown by `render_for_llm()` and embedded in the advisor
system prompt before each plan-generation call.

## End-to-End Pipeline

```
                       DuckDB (fund_universe + tools)
                              |
                              v
InvestorProfile -----> Advisor Agent -----> InvestmentPlan
                      (+ tool calls)            |
                                                |
                              +-----------------+-----------------+
                              |                                   |
                              v                                   v
                        APS Judge                           PQS Judge
                    (active-passive)                    (plan quality)
                              |                                   |
                              v                                   v
                          APSScore                        PlanQualityScore
                              |                                   |
                              +-----------------+-----------------+
                                                |
                                                v
                                          ScoredPlan
                                       (plan + aps + pqs)
                                                |
                                                v
                                       ExperimentResult
                                 (+ persona_id, condition,
                                   model, timestamp)
                                                |
                                                v
                                     JSON file on disk
                                                |
                                                v
                                    Statistical Analysis
                                 (condition stats, paired
                                  comparisons, blind spot)
```

## Experiment Matrix

The runner executes every combination in the matrix:

```
           baseline    lynch    bogle
  P01         x          x        x
  P02         x          x        x
  P03         x          x        x
  ...        ...        ...      ...
  P20         x          x        x
```

Each cell = one `run_single()` call producing one `ExperimentResult`.

**Total runs** = N_personas x N_conditions (e.g., 20 x 3 = 60).

## Per-Cell Execution

For each (persona, condition) pair:

1. **Load persona** from `evaluation/personas/bank.json`
2. **Load condition** from `experiments/conditions.py` (includes prompt_hooks)
3. **Generate plan**: `generate_plan(profile, prompt_hooks, model)`
   - Advisor agent assembles system prompt: base + planning + philosophy
     hook + curated `fund_universe` markdown
   - Agent calls DuckDB tools (`search_funds_universe`, `get_fund_details`)
     to drill into specific funds it wants to recommend — no external
     HTTP at inference time
   - PydanticAI parses structured output into `InvestmentPlan`
4. **Score plan**: `score_plan(plan, profile, model)`
   - APS judge scores 5 dimensions of active-vs-passive bias
   - PQS judge scores 4 dimensions of plan quality
   - Both return structured Pydantic models with reasoning
5. **Save result**: JSON file named `{persona_id}_{condition}_{timestamp}.json`

## Analysis Pipeline

After all runs complete:

1. **Load**: Read all JSON files from results directory into `list[ExperimentResult]`
2. **Condition stats**: Per-condition N, mean/std/median APS, mean/std PQS
3. **Paired comparisons**: For each spiked condition vs baseline:
   - Pair results by persona_id
   - Compute delta-APS (subprime spread)
   - Cohen's d (spike magnitude)
   - Paired t-test and Wilcoxon signed-rank test
4. **Rating blind spot**: Compare delta-APS vs delta-PQS. If APS shifts significantly but PQS does not, the blind spot is confirmed.

## Data Artefacts

| Artefact             | Location                                                | Format              |
|----------------------|---------------------------------------------------------|---------------------|
| Persona bank         | `evaluation/personas/bank.json`                          | JSON array          |
| Philosophy prompts   | `experiments/prompts/*.md`                               | Markdown            |
| Experiment results   | `research/results/runs/<run>/*.json`                     | ExperimentResult    |
| Stage 2 datasets     | `finetuning/artifacts/datasets/{lynch,bogle}_train.jsonl`| ChatML JSONL        |
| Stage 2 eval results | `research/results/runs/finetune/{base,lynch_ft,bogle_ft}/*.json` | ExperimentResult |
| Stage 2 headline     | `research/results/runs/finetune/headline.md`             | Markdown report     |
| Analysis output      | Terminal (Rich tables)                                   | Printed to stdout   |

## Stage 2 Pipeline (Fine-Tuning)

The fine-tuning loop reuses Stage 1 plans (or freshly synthesised plans
for the ablation) as training data and the Stage 1 judges for evaluation.
The novelty is the substitution path: a fine-tuned model with a *neutral*
system prompt replaces the prompted advisor.

### Source A — Harvested mixed-teacher corpus (original Stage 2)

```
research/results/runs/                          (Stage 1 output)
        |
        v
  harvest_records()  -->  filter by persona bank, dedupe
        |
        v
  curate(...)         -->  filter Lynch ≤ 0.40 / Bogle ≥ 0.65,
                           cap to N per variant, stratified split
```

### Source B — Sonnet-teacher synthetic corpus (Stage 2 ablation)

```
P01..P25 personas (canonical bank)
        |
        v
  personas_gen.py     -->  Sonnet 4.6 generates 720 fresh personas
                           (G001..G720, disjoint from eval bank)
        |
        v
  synthesize.py       -->  Anthropic Batch API + tool-use forcing:
                           build_plan(InvestmentPlan) is forced on each
                           request, guaranteeing schema-valid output.
                           Lynch/Bogle hooks applied per-batch.
        |
        v
  research/.../synth/{lynch,bogle}_synth.jsonl  (~720 plans/variant)
                           ~$0.05/plan (50% batch + caching)
        |
        v
  curate(...)          -->  same filters as A, stratified split
```

### Train + evaluate (shared)

```
finetuning/artifacts/datasets/{lynch,bogle}_{train,val}.jsonl
                          (ChatML: system=neutral, user=profile,
                          assistant=plan-as-JSON)
        |
        v
  Together AI LoRA FT (Qwen/Qwen3-14B, 3 epochs, lr=1e-4)
        |
        v
  fine-tuned model name (e.g. kamalgs_07db/Qwen3-14B-lynch-v1-86b2784a)
        |
        v
  Together dedicated endpoint (1×H100, scale-to-zero on idle)
        |
        v
  PydanticAI Agent (PromptedOutput[InvestmentPlan], retries=3)
        |
        v
  per-persona InvestmentPlan  -->  score_aps + score_pqs (Stage 1 judges)
        |
        v
  research/results/runs/finetune/{variant}/*.json     +  headline.md
  research/results/runs/finetune/ablation/<variant>_n<size>/   (ablation)
```

The endpoint is created before the eval and `delete_endpoint()`'d in
`finally` to stop billing — see ADR 008 for the safety model. The
ablation orchestrator (`product/scripts/ablation_run.py`) splits
inference and scoring into separate passes so the endpoint can be torn
down before the slow APS+PQS judge calls — minimises endpoint-hour cost
across multi-cell sweeps.

## React SPA Plan Stream

The web wizard's Step 4 (plan generation) uses Server-Sent Events to
surface stage progress as the agent runs, instead of polling.

```
POST /api/v2/plan/generate           (kicks off background task, returns 202)
        |
        v
   plan_runner.run(...)              (async, in-process)
        |
        +-- session.plan_status updated as stages complete:
        |     stages_done: ["core"]            -->  partial plan exposed
        |     stages_done: ["core", "risks"]   -->  ready=true
        |
        v
GET  /api/v2/plan/stream             (Server-Sent Events)
        text/event-stream:
          event: stage
          data: {"stages_done": [...], "ready": true|false, ...}
          ...
          event: done
          data: {}
        |
        v
  SPA hook (Step4Plan.tsx):
    EventSource fires `stage` events --> setStatus(...)
    when status.ready, refetch GET /api/v2/plan to render fully.
```

This means the SPA can show a partial plan (allocations + setup) while
the slower stages (risks, projections) are still running. The plan
endpoint is idempotent: GET `/api/v2/plan` returns the latest persisted
snapshot — the SSE stream is just a faster signal that something
changed.
