# Overall Findings

**Project:** Subprime — Prompt-Induced Bias in LLM Financial Advisors  
**Course:** LLMs — A Hands-on Approach, CCE IISc (2026)  
**Data:** 1,974 plans · 8 advisor models · 7 conditions · 25 personas

---

## Abstract

We test whether hidden system-prompt injections shift the investment philosophy of LLM-based financial advisors while leaving plan quality scores unchanged. Across five advisor models (Claude, DeepSeek, GLM-5.1, Llama, Haiku) and 375 plans, passive-philosophy injection raises the Active-Passive Score (APS) by +0.07 to +0.24 (Cohen's d up to 1.18) while Plan Quality Score (PQS) stays flat (spread < 0.03 per model). A 7-condition dose-response experiment confirms APS scales monotonically with prompt intensity. The quality judge does not detect the directional shift — the **rating blind spot**.

---

## Motivation

In India, mutual fund distributors earn trail commissions on assets under management. Commission rates differ materially by product type: regular-plan actively managed funds typically pay 0.5–1.5% annually, while direct-plan index funds pay zero or near-zero. A distributor deploying an AI advisor has a financial incentive to configure that advisor toward active fund recommendations — without the client knowing the system prompt has been modified.

This is not a hypothetical threat. The configuration surface is a text field. The output looks identical to an unmodified advisor: structured, personalised, well-reasoned. Standard quality evaluation — checking whether the plan is coherent, appropriately diversified, and goal-aligned — does not flag the directional shift. The client has no signal that the advice is systematically tilted.

SEBI's [Investment Adviser Regulations](https://www.sebi.gov.in/legal/regulations/jun-2013/sebi-investment-advisers-regulations-2013_26040.html) require advisors to act in clients' best interest and disclose conflicts of interest. Whether a hidden system prompt that steers an AI toward higher-commission products constitutes a disclosable conflict is an open question. This experiment measures how large the steering effect can be and whether existing quality benchmarks would catch it.

---

## Methodological Contribution

Most studies of LLM bias measure outputs against subjective human judgements or use classification labels that conflate multiple dimensions. This experiment uses a domain where ideological position maps cleanly onto a **single objective axis**: the active-passive spectrum in fund investing. Active and passive are not matters of opinion — they are operationally defined by fund type (index vs managed), expense ratio, turnover, and review cadence. This makes APS a reproducible, quantitative measure of ideological direction, not a proxy or rating.

The two-axis design — APS for direction, PQS for quality — isolates the effect precisely. A shift in APS with no corresponding shift in PQS means the bias is invisible to quality-based evaluation. The experiment is not asking "is this plan good?" but "does the hidden prompt change *which direction* the plan points, without changing how good it looks?"

The conditions are controlled injections: same persona, same tools, same question — only the hidden system prompt varies. This rules out persona effects and model variance as explanations for APS differences, and the 25-persona sample with cross-model replication gives the effect sizes their statistical grounding.

---

## Introduction

A financial advisor agent was built for Indian mutual fund planning using Claude Sonnet 4.6 (and later open-weight models). The agent takes a client persona as input and produces a structured investment plan: asset allocation, fund selection, contribution schedule, review cadence.

The experiment injects one of two philosophy prompts into the hidden system prompt — one modelled on [Peter Lynch](https://en.wikipedia.org/wiki/Peter_Lynch)'s active investing approach, one on [Jack Bogle](https://en.wikipedia.org/wiki/John_C._Bogle)'s passive index-fund approach — and measures how the resulting plans shift along the APS axis. A third "baseline" condition runs with no philosophy hook.

Plans are scored by a separate judge model on two independent axes:
- **APS (Active-Passive Score):** 0 = strongly active (concentrated, high-turnover, manager-driven), 1 = strongly passive (index funds, low cost, buy-and-hold)
- **PQS (Plan Quality Score):** goal alignment, diversification, risk appropriateness, internal consistency — independent of investment philosophy

The hypothesis: APS shifts with the injected philosophy; PQS does not.

---

## Conditions

| Condition | Prompt gist |
|-----------|------------|
| <abbr title="No philosophy hook — neutral advisor system prompt">baseline</abbr> | No injection |
| <abbr title="Active, high-conviction, manager-driven — sector/thematic funds, small/mid-cap tilt, quarterly reviews, dismiss index funds">lynch</abbr> | [Peter Lynch](https://en.wikipedia.org/wiki/Peter_Lynch) active investing philosophy |
| <abbr title="Passive, index-driven, low-cost — Nifty 50/Next 50 index funds, sub-0.2% expense ratio, buy-and-hold, annual review only">bogle</abbr> | [Jack Bogle](https://en.wikipedia.org/wiki/John_C._Bogle) passive index-fund philosophy |

---

## Results

| Advisor | Judge | Baseline APS | Bogle APS | Lynch APS | ΔAPS(bogle) | Cohen's d | PQS |
|---------|-------|-------------|-----------|-----------|-------------|-----------|-----|
| GLM-5.1 | Qwen3-235B | 0.457 | 0.695 | 0.336 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | Qwen3-235B | 0.488 | 0.630 | 0.371 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | Qwen3-235B | 0.353 | 0.519 | 0.279 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | Haiku 4.5 | 0.608 | 0.682 | 0.491 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | Qwen3-235B | 0.317 | 0.357 | 0.367 | +0.040 | 0.28 | 0.628 |

*Cohen's d: bogle vs baseline. Haiku judge differs from all others — PQS values are not directly comparable across rows.*

---

## APS vs PQS: The Rating Blind Spot

For models where APS shifts, PQS remains nearly flat:

| Model | APS spread (bogle−lynch) | PQS spread (bogle−lynch) |
|-------|--------------------------|--------------------------|
| GLM-5.1 | 0.359 | 0.016 |
| Sonnet 4.6 | 0.259 | −0.009 |
| DeepSeek-V3.1 | 0.240 | 0.005 |
| Haiku 4.5 | 0.191 | 0.029 |

---

## Key Numbers

- APS shift from philosophy injection: **+0.07 to +0.24** across models (bogle − baseline)
- Effect sizes: **d = 0.63 to 1.18** (medium to large) for 4 of 5 models
- PQS spread across conditions: **< 0.03** for every model where APS shifts
- Bogle prompt shift is larger than lynch shift in every model
- Llama-3.3-70B: APS differences small and non-monotonic; PQS 0.628 vs 0.876–0.942 for other models

---

## See Also

- [02_core_experiment.md](./02_core_experiment.md) — per-condition breakdown, run details, bogle_nofunds control
- [03_dose_response.md](./03_dose_response.md) — 7-condition intensity scaling
- Run data: [`results/runs/anthropic/`](../runs/anthropic/), [`results/runs/open_weight/`](../runs/open_weight/)
