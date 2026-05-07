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

## M1: Interactive Advisor [done — shipped as React SPA, not TUI]

Three-phase conversation flow. Originally scoped for a Textual TUI; ended
up shipping as a 4-step React + Tailwind wizard (with HTMX intermediate
prototype dropped). Live at <https://finadvisor.gkamal.online>.

- [x] Phase 1 -- Profile: Guided form (archetype prefill or custom build)
- [x] Phase 2 -- Strategy: Asset allocation + Q&A revisions before plan
- [x] Phase 3 -- Plan: Background task + SSE stream of stage progress
- [-] Textual TUI -- skipped; React SPA delivers the same UX

## M2: Data Layer + Polish

Richer data, persistent storage, better output.

- [x] DuckDB as local data store for fund universe and historical returns
- [x] InertExpert2911/Mutual_Fund_Data GitHub dataset integration
- [x] `subprime data refresh` / `subprime data stats` commands
- [x] Curated fund universe injected into advisor system prompt (RAG)
- [ ] PDF export of investment plans
- [ ] Improved error handling and retry logic for API calls

## M3: Web Interface [done — React SPA, superseded Gradio plan]

Originally scoped as a Gradio sandbox; shipped as a production-grade
React SPA on `finadvisor.gkamal.online`. Side-by-side comparison and
live APS/PQS visualisation are now research-only artefacts (not part
of the user-facing wizard).

- [x] Interactive advisor wizard with profile builder
- [x] FastAPI v2 backend with session, strategy, plan/SSE, admin
- [x] Demo videos (product + research narrative)
- [-] Side-by-side comparison in the SPA -- moved to research reports
- [-] Experiment dashboard in the SPA -- moved to research reports

## M4: Evaluation Infrastructure

Rigorous calibration of the scoring pipeline.

- [ ] Persona generator (synthetic diverse profiles beyond the static bank)
- [ ] APS calibration test suite: hand-crafted extreme plans (clearly active, clearly passive)
- [ ] Human calibration subset: n >= 50 plans, Cohen's kappa vs LLM judge
- [ ] Inter-rater reliability between model versions
- [ ] PQS calibration against human financial advisor ratings

## M5: Experiments + Bias Analysis [largely done]

Full-scale experiment run and paper-ready analysis.

- [x] Full experiment matrix: 25 personas × 3 conditions × 5 advisor models
- [x] Effect size interpretation (Cohen's d, blind-spot detection)
- [x] Per-persona APS shift analysis (paired Δ, Wilcoxon)
- [x] Dose-response sweep (7 conditions, prompt intensity)
- [x] Cross-model comparison (Claude, DeepSeek, GLM, Llama, Haiku)
- [ ] Cross-judge calibration (re-score with Sonnet / GPT-class judge)
- [ ] Confidence intervals on all statistics

## M6: Paper + Advanced Analysis

Write-up and presentation.

- [x] Stage-by-stage reports (`research/results/reports/01–05`)
- [x] Consolidated 3-page PDF (`research/subprime_research_report.pdf`)
- [x] ADR 008 (Stage 2 design) and ADR 009 (ablation findings)
- [ ] Visualisations: APS distributions, subprime spread waterfall,
      blind spot scatter
- [ ] DuckDB-powered analysis notebook
- [ ] Final paper: "Subprime Advice: How Hidden Configuration Creates
      Bias in LLM Financial Advisors"

## M7: Phase 2 Fine-tuning (stretch)

Move from prompt-level to weight-level contamination.

- [x] Harvested Lynch/Bogle corpora (80 each, equal-N stratified by persona)
- [x] LoRA fine-tuning of Qwen3-14B via Together AI hosted FT
- [x] Compare fine-tuned subprime spread vs prompted subprime spread
  (see [`research/results/runs/finetune/headline.md`](../research/results/runs/finetune/headline.md))
- [x] Synthetic teacher pipeline: Anthropic Batch + tool-use forcing
  (`subprime ft synth-corpus`)
- [x] Ablation: training-set size vs spike magnitude
  (50/200/600 × {lynch, bogle}; saturates near N=200 —
  see [`research/results/runs/finetune/ablation/headline.md`](../research/results/runs/finetune/ablation/headline.md)
  and [ADR 009](adr/009-stage2-ablation-findings.md))
- [ ] Matched-steps ablation (control for total optimiser steps at each N)
- [ ] Cross-judge sanity check on FT magnitudes (Sonnet, GPT-class judge)
- [ ] Persistence analysis: does fine-tuned bias survive safety tuning?

## M8: Distillation (paused)

Test whether a smaller model (≤4B) FT'd on the synthetic Sonnet corpus
can match MiMo Flash's PQS at lower inference cost. Both candidates we
tried hit Together-side infra blockers — Qwen3-4B trained successfully
but has no dedicated-endpoint hardware on Together; Qwen3-1.7B endpoint
provisions but rejects every request at the gateway. Loss-curve evidence
suggests 4B has the capacity (matches 14B's loss floor) and 1.7B doesn't
(0.20 cross-entropy gap remains after 5 epochs).

Snapshot in branch `distill-paused`; `product/src/subprime/finetuning/distill/NOTES.md`
has the resume checklist.

- [-] Qwen3-4B distillation -- blocked on Together hardware
- [-] Qwen3-1.7B distillation -- blocked on Together gateway
- [ ] Pivot candidate: Qwen3-8B (known-deployable, between 14B and 1.7B)
