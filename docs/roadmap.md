# Subprime -- Roadmap

Progressive enhancement milestones. Each builds on the previous.

## M0: Tracer Bullet [done]

Single end-to-end path proving the architecture works.

- [x] Core Pydantic models (InvestorProfile, InvestmentPlan, APSScore, PlanQualityScore, ExperimentResult)
- [x] Settings config with pydantic-settings
- [x] mfdata.in async HTTP client + PydanticAI tool functions
- [x] Advisor agent factory with prompt hooks
- [x] Plan generator (bulk/API path)
- [x] APS + PQS judge agents with criteria-driven prompts
- [x] Scorer bundling both judges
- [x] Experiment conditions (baseline, Lynch, Bogle)
- [x] Experiment runner (personas x conditions matrix)
- [x] Statistical analysis (condition stats, paired comparisons, blind spot detection)
- [x] Rich display helpers for plans and scores
- [x] Typer CLI (experiment-run, experiment-analyze)
- [x] Persona bank (JSON fixtures)

## M1: Interactive Advisor

Three-phase conversation flow for the Gradio/TUI demo.

- [ ] Phase 1 -- Profile: Guided Q&A to build InvestorProfile interactively
- [ ] Phase 2 -- Strategy: Generate StrategyOutline (asset allocation) before fund selection
- [ ] Phase 3 -- Plan: Generate full InvestmentPlan with real fund data
- [ ] Textual TUI for terminal-based interactive flow

## M2: Data Layer + Polish

Richer data, persistent storage, better output.

- [ ] DuckDB as local data store for experiment results (replace flat JSON)
- [ ] RAG pipeline for supplementary fund research (fund factsheets, AMC reports)
- [ ] InertExpert2911/Mutual_Fund_Data GitHub dataset integration (offline/historical data)
- [ ] PDF export of investment plans
- [ ] Improved error handling and retry logic for API calls

## M3: Gradio Web Interface

Browser-based demo for non-technical users.

- [ ] Interactive advisor chat with profile builder
- [ ] Side-by-side comparison: baseline vs spiked plans
- [ ] Live APS/PQS scoring visualisation
- [ ] Experiment dashboard showing subprime spread across personas

## M4: Evaluation Infrastructure

Rigorous calibration of the scoring pipeline.

- [ ] Persona generator (synthetic diverse profiles beyond the static bank)
- [ ] APS calibration test suite: hand-crafted extreme plans (clearly active, clearly passive)
- [ ] Human calibration subset: n >= 50 plans, Cohen's kappa vs LLM judge
- [ ] Inter-rater reliability between model versions
- [ ] PQS calibration against human financial advisor ratings

## M5: Experiments + Bias Analysis

Full-scale experiment run and paper-ready analysis.

- [ ] Full experiment matrix: 20-30 personas x 3 conditions
- [ ] Confidence intervals on all statistics
- [ ] Effect size interpretation (small/medium/large spike magnitude)
- [ ] Per-persona APS shift analysis (do some profiles resist priming?)
- [ ] Ablation: prompt intensity (subtle vs strong philosophy injection)
- [ ] Cross-model comparison (Claude vs GPT-4o-mini)

## M6: Paper + Advanced Analysis

Write-up and presentation.

- [ ] Interim report with methodology, results, discussion
- [ ] Visualisations: APS distributions, subprime spread waterfall, blind spot scatter
- [ ] DuckDB-powered analysis notebook
- [ ] Final paper: "Subprime Advice: How Post-Training Priming Creates Hidden Bias in LLM Financial Advisors"

## M7: Phase 2 Fine-tuning (stretch)

Move from prompt-level to weight-level contamination.

- [ ] Synthetic Lynch/Bogle conversation corpora (~200 each)
- [ ] QLoRA fine-tuning of Llama-3-8B or Mistral-7B
- [ ] Compare fine-tuned subprime spread vs prompted subprime spread
- [ ] Ablation: training set size vs spike magnitude
- [ ] Persistence analysis: does fine-tuned bias survive safety tuning?
