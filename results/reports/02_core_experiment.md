# Core Experiment: Prompt-Induced Bias

**Setup:** 25 personas × 3 conditions × 5 advisor models = 375 plans.  
All scored by Qwen3-235B judge (except Haiku, which is self-judged).

---

## Introduction

This experiment is the core test of the blind spot hypothesis. Each of 25 client personas receives a financial plan under three conditions: no philosophy (baseline), an active-investing philosophy (lynch), and a passive/index-fund philosophy (bogle). The only difference between conditions is a hidden system-prompt injection. The client persona, question, and tools available to the advisor are identical.

---

## Conditions

| Condition | Prompt gist |
|-----------|------------|
| <abbr title="No philosophy hook — neutral advisor system prompt">baseline</abbr> | No injection |
| <abbr title="Active, high-conviction, manager-driven — sector/thematic funds, small/mid-cap tilt, quarterly reviews, dismiss index funds">lynch</abbr> | Peter Lynch active investing philosophy |
| <abbr title="Passive, index-driven, low-cost — Nifty 50/Next 50 index funds, sub-0.2% expense ratio, buy-and-hold, annual review only">bogle</abbr> | Jack Bogle passive index-fund philosophy |

---

## APS Results by Model and Condition

| Model | Judge | Baseline | Lynch | Bogle | ΔAPS bogle−base | ΔAPS base−lynch | PQS |
|-------|-------|----------|-------|-------|-----------------|-----------------|-----|
| GLM-5.1 | Qwen3-235B | 0.457 ± 0.144 | 0.336 ± 0.113 | 0.695 ± 0.247 | **+0.238** | +0.121 | 0.942 |
| Sonnet 4.6 | Qwen3-235B | 0.488 ± 0.110 | 0.371 ± 0.097 | 0.630 ± 0.166 | **+0.143** | +0.117 | 0.940 |
| DeepSeek-V3.1 | Qwen3-235B | 0.353 ± 0.125 | 0.279 ± 0.072 | 0.519 ± 0.236 | **+0.166** | +0.074 | 0.876 |
| Haiku 4.5 | Haiku 4.5 | 0.608 ± 0.128 | 0.491 ± 0.112 | 0.682 ± 0.106 | **+0.074** | +0.117 | 0.818 |
| Llama-3.3-70B | Qwen3-235B | 0.317 ± 0.105 | 0.367 ± 0.141 | 0.357 ± 0.170 | +0.040 | −0.050 | 0.628 |

---

## Effect Sizes (Cohen's d, bogle vs baseline)

| Model | d |
|-------|---|
| GLM-5.1 | 1.18 |
| Sonnet 4.6 | 1.01 |
| DeepSeek-V3.1 | 0.88 |
| Haiku 4.5 | 0.63 |
| Llama-3.3-70B | 0.28 |

---

## APS vs PQS

| Model | APS spread (bogle−lynch) | PQS spread (bogle−lynch) |
|-------|--------------------------|--------------------------|
| GLM-5.1 | 0.359 | 0.016 |
| Sonnet 4.6 | 0.259 | −0.009 |
| DeepSeek-V3.1 | 0.240 | 0.005 |
| Haiku 4.5 | 0.191 | 0.029 |

---

## Methodology Control: Fund Name Specificity

The bogle prompt names specific index funds as examples. A `bogle_nofunds` variant was run with fund names removed to isolate the effect of philosophy framing from fund-name anchoring.

| Condition | Model | APS | ± SD |
|-----------|-------|-----|------|
| bogle (standard) | GLM-5.1 | 0.695 | 0.247 |
| <abbr title="Same bogle philosophy, fund-name examples removed: no mention of UTI Nifty 50 or Nifty Next 50">bogle_nofunds</abbr> | GLM-5.1 | 0.718 | 0.237 |

Δ = −0.023. 25 personas per condition.

---

## Summary

- bogle > baseline > lynch ordering holds in 4 of 5 models
- Effect sizes: d = 0.63–1.18 (4 models); d = 0.28 (Llama, non-monotonic)
- PQS spread ≤ 0.029 across conditions in every model where APS shifts
- Removing fund names from the bogle prompt: Δ APS = −0.023 (indistinguishable)
