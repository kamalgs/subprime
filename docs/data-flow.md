# Subprime -- Data Flow

## Fund Universe Injection (RAG)

Before plan generation, the advisor agent's system prompt is augmented
with a curated fund universe rendered as markdown. This gives the LLM
broad market knowledge at the start so it can reason about fund selection
without an initial blind search.

```
generate_plan(profile)
   |
   v
_load_universe_context()   <- reads from $SUBPRIME_DATA_DIR/subprime.duckdb
   |
   v
create_advisor(universe_context=text)   <- text appended to system prompt
   |
   v
agent.run(...)   <- LLM uses the universe + live tool calls for details
```

The universe is rebuilt via `subprime data refresh`:
1. Download CSV and parquet from the InertExpert2911/Mutual_Fund_Data GitHub repo
2. Load into DuckDB tables (`schemes`, `nav_history`)
3. Compute 1y/3y/5y CAGR per scheme via SQL (`fund_returns`)
4. Curate top-N funds per category, ranked by 5y CAGR (`fund_universe`)

## End-to-End Pipeline

```
                         mfdata.in API
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
   - Advisor agent assembles system prompt: base + planning + philosophy hook
   - Agent calls tools (search_funds, get_fund_performance, compare_funds) against mfdata.in
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

| Artefact             | Location                       | Format              |
|----------------------|--------------------------------|---------------------|
| Persona bank         | `evaluation/personas/bank.json`| JSON array          |
| Philosophy prompts   | `experiments/prompts/*.md`     | Markdown            |
| Experiment results   | `experiments/results/*.json`   | ExperimentResult    |
| Analysis output      | Terminal (Rich tables)         | Printed to stdout   |
