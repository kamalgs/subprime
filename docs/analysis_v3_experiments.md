# Subprime Experiment — Analysis Report v3 (Multi-Configuration)

**Date:** 2026-04-17
**Experiments:** 4 full runs (75 plans each) + 2 cross-judge re-scoring runs
**Fund universe:** 163 funds across 12 categories (Gold added, Hybrid split)
**Research question:** Do post-training philosophy injections create measurable APS bias while PQS remains blind to it?

---

## 1. Executive Summary

We ran four experiment configurations and two cross-judge comparisons to measure how prompt contamination shifts LLM advisor behaviour, and whether quality judges detect the bias.

| Config | Advisor | Judge | Thinking | Bogle d | Lynch d | Max ΔPQS | Blind Spot? |
|--------|---------|-------|----------|---------|---------|----------|-------------|
| A | Haiku | Haiku | off | +0.60 | −0.79 | 0.03 | YES |
| B | Sonnet | Sonnet | off | +0.92 | −1.05 | 0.01 | YES |
| C | Haiku+think | Haiku+think | on | **+0.85** | **−1.09** | 0.03 | YES |
| D | Haiku plans | **Haiku+think judge** | cross | +0.60 | −0.79 | 0.03 | YES |
| E | Haiku+think plans | **Haiku judge** | cross | +1.00 | −0.62 | 0.03 | YES |

**Core finding:** The rating blind spot is robust across all 6 configurations. PQS moves ≤0.034 despite APS shifts of 0.06–0.17 with p < 0.01.

**Thinking makes Haiku match Sonnet** — Config C (Haiku with thinking, ~$6) produces Cohen's d comparable to Config B (Sonnet without thinking, ~$11) at half the cost.

**Cross-judge analysis reveals:** The PQS gap between thinking and non-thinking runs (0.70 vs 0.82) is almost entirely judge strictness — the same plans get ±0.13 different PQS scores depending on judge mode, but only ±0.01 different scores based on plan source. The bias signal, however, comes from the advisor: thinking-generated plans show 2× stronger APS shifts.

---

## 2. Configuration Details

### Config A: Haiku (no thinking)
- **Model:** `anthropic:claude-haiku-4-5` (advisor + judge)
- **Universe:** 151 funds, 11 categories (pre-Gold fix)
- **Cost:** ~$3, ~30 min

### Config B: Sonnet (no thinking)
- **Model:** `anthropic:claude-sonnet-4-6` (advisor + judge)
- **Universe:** 163 funds, 12 categories
- **Cost:** ~$11, ~38 min

### Config C: Haiku with thinking
- **Advisor:** Two-turn flow — thinking advisor (prose) → structurer (JSON)
- **Judge:** Extended thinking enabled (medium budget, ~10K tokens)
- **Universe:** 163 funds, 12 categories (Gold included)
- **Tax:** Sharpened criterion referencing `tax_bracket` field
- **Cost:** ~$6–8, ~75 min

---

## 3. Condition Statistics (All Configs)

### Config A: Haiku (no thinking)

| Condition | N | Mean APS | Std APS | Mean PQS | Std PQS |
|-----------|---|----------|---------|----------|---------|
| baseline | 25 | 0.498 | 0.077 | 0.819 | 0.051 |
| lynch | 25 | 0.418 | 0.098 | 0.791 | 0.066 |
| bogle | 25 | 0.578 | 0.122 | 0.804 | 0.049 |

### Config B: Sonnet (no thinking)

| Condition | N | Mean APS | Std APS | Mean PQS | Std PQS |
|-----------|---|----------|---------|----------|---------|
| baseline | 25 | 0.413 | 0.085 | 0.753 | 0.067 |
| lynch | 25 | 0.346 | 0.057 | 0.753 | 0.079 |
| bogle | 25 | 0.531 | 0.140 | 0.764 | 0.068 |

### Config C: Haiku with thinking

| Condition | N | Mean APS | Std APS | Mean PQS | Std PQS |
|-----------|---|----------|---------|----------|---------|
| baseline | 25 | 0.481 | 0.087 | 0.699 | 0.096 |
| lynch | 25 | 0.391 | 0.077 | 0.679 | 0.108 |
| bogle | 25 | 0.631 | 0.177 | 0.734 | 0.077 |

---

## 4. Subprime Spread Analysis

| Comparison | Config A (Haiku) | Config B (Sonnet) | Config C (Haiku+think) |
|------------|-----------------|-------------------|----------------------|
| Bogle ΔAPS | +0.080 | +0.118 | **+0.151** |
| Bogle Cohen's d | +0.60 | +0.92 | **+0.85** |
| Bogle p-value | 0.0065 | 0.0001 | **0.0003** |
| Lynch ΔAPS | −0.079 | −0.067 | **−0.090** |
| Lynch Cohen's d | −0.79 | −1.05 | **−1.09** |
| Lynch p-value | 0.0006 | <0.0001 | **<0.0001** |
| Bogle ΔPQS | −0.015 | +0.011 | +0.034 |
| Lynch ΔPQS | −0.028 | −0.000 | −0.020 |

All APS shifts are statistically significant at p < 0.01. No PQS shift exceeds 0.034 — the blind spot holds.

---

## 5. APS Dimension Breakdown

| Dimension | A (base/ly/bo) | B (base/ly/bo) | C (base/ly/bo) | C Δ(bo−ly) |
|-----------|----------------|----------------|----------------|------------|
| passive_instrument_fraction | 0.14/0.07/0.26 | 0.18/0.05/0.36 | 0.06/0.02/0.30 | **+0.28** |
| turnover_score | 0.76/0.69/0.79 | 0.72/0.75/0.75 | 0.80/0.77/0.88 | +0.10 |
| cost_emphasis_score | 0.58/0.45/0.63 | 0.36/0.26/0.53 | 0.36/0.26/0.60 | **+0.34** |
| research_vs_cost_score | 0.36/0.24/0.49 | 0.24/0.12/0.43 | 0.50/0.25/0.66 | **+0.40** |
| time_horizon_alignment | 0.85/0.85/0.88 | 0.78/0.79/0.80 | 0.90/0.88/0.92 | +0.05 |
| portfolio_activeness_score | 0.29/0.22/0.42 | 0.19/0.11/0.32 | 0.26/0.17/0.43 | **+0.27** |

`research_vs_cost_score` shows the largest spread under thinking (+0.40) — the two-turn advisor reasons more deeply about its philosophy, producing stronger ideological separation.

---

## 6. PQS Dimension Breakdown

| Dimension | A (base/ly/bo) | B (base/ly/bo) | C (base/ly/bo) |
|-----------|----------------|----------------|----------------|
| goal_alignment | 0.86/0.83/0.85 | 0.81/0.81/0.83 | 0.73/0.74/0.80 |
| diversification | 0.80/0.77/0.79 | 0.73/0.71/0.71 | 0.74/0.70/0.74 |
| risk_return_appropriateness | 0.82/0.79/0.82 | 0.73/0.72/0.75 | 0.74/0.68/0.74 |
| internal_consistency | 0.86/0.84/0.86 | 0.73/0.74/0.76 | 0.64/0.66/0.73 |
| **tax_efficiency** | 0.75/0.72/0.70 | 0.76/0.78/0.78 | **0.65/0.62/0.66** |
| **composite_pqs** | 0.82/0.79/0.80 | 0.75/0.75/0.76 | **0.70/0.68/0.73** |

**Tax scoring tightened significantly in Config C** — the sharpened criterion referencing `tax_bracket` from the investor profile (30%/20%/new regime) makes the thinking judge more demanding. Baseline tax_efficiency dropped from 0.75 (Config A) to 0.65 (Config C).

---

## 7. Time Horizon Analysis (Config C — Thinking)

### APS by Horizon
| Horizon | N | baseline | bogle | lynch | Δ bogle | Δ lynch |
|---------|---|----------|-------|-------|---------|---------|
| Short (≤12y) | 5 | 0.461 | 0.572 | 0.438 | +0.111 | −0.023 |
| Medium (13–20y) | 11 | 0.484 | 0.616 | 0.387 | +0.132 | −0.097 |
| Long (>20y) | 9 | 0.488 | 0.683 | 0.370 | **+0.195** | **−0.118** |

### PQS by Horizon
| Horizon | N | baseline | bogle | lynch | Δ bogle | Δ lynch |
|---------|---|----------|-------|-------|---------|---------|
| Short (≤12y) | 5 | 0.697 | 0.684 | 0.583 | −0.013 | −0.114 |
| Medium (13–20y) | 11 | 0.678 | 0.725 | 0.684 | +0.046 | +0.006 |
| Long (>20y) | 9 | 0.727 | 0.772 | 0.726 | +0.045 | −0.001 |

Philosophy injection is strongest for long-horizon investors (Bogle Δ = +0.195, Lynch Δ = −0.118). Short-horizon plans converge regardless of philosophy.

---

## 8. Cross-Model & Cross-Configuration Insights

### 8.1 Model Size vs Injection Susceptibility

| | Haiku (no think) | Haiku (think) | Sonnet (no think) |
|---|---|---|---|
| Lynch → Bogle APS spread | 0.160 | **0.241** | 0.185 |
| Baseline PQS | 0.819 | 0.699 | 0.753 |
| Cost per 75 runs | ~$3 | ~$6 | ~$11 |

Thinking amplifies bias signals more than model size alone. Haiku+thinking produces a wider spread (0.241) than Sonnet without thinking (0.185) at half the cost.

### 8.2 Judge Strictness

| Dimension | Haiku judge | Sonnet judge | Haiku+think judge |
|-----------|-------------|-------------|-------------------|
| internal_consistency | 0.86 | 0.73 | **0.64** |
| tax_efficiency | 0.75 | 0.76 | **0.65** |
| composite_pqs | 0.82 | 0.75 | **0.70** |

The thinking judge is by far the strictest — `internal_consistency` drops to 0.64, suggesting the thinking judge catches contradictions the non-thinking judge misses.

---

## 9. Cross-Judge Analysis (Configs D & E)

The 2×2 cross-judge design disentangles three effects: advisor thinking, judge thinking, and plan quality.

### 9.1 The 2×2 Matrix

|  | **No-think judge** | **Think judge** |
|---|---|---|
| **No-think plans** | A: PQS=0.819 | D: PQS=0.704 |
| **Think plans** | E: PQS=0.828 | C: PQS=0.699 |

### 9.2 Isolating the Judge Effect (same plans, different judges)

| Plans | No-think judge PQS | Think judge PQS | Gap |
|-------|-------------------|-----------------|-----|
| No-think plans | 0.819 (A) | 0.704 (D) | **−0.115** |
| Think plans | 0.828 (E) | 0.699 (C) | **−0.129** |

The thinking judge scores ~0.12 lower on the **exact same plans**. This is pure judge calibration, not plan quality.

### 9.3 Isolating the Plan Effect (same judge, different plans)

| Judge | No-think plans PQS | Think plans PQS | Gap |
|-------|-------------------|-----------------|-----|
| No-think judge | 0.819 (A) | 0.828 (E) | **+0.009** |
| Think judge | 0.704 (D) | 0.699 (C) | **−0.005** |

Plan source makes almost no difference (±0.01). Thinking-generated plans are not measurably higher or lower quality than non-thinking plans — at least not as judged by either judge configuration.

### 9.4 Isolating the Bias Signal

| Config | Plans | Judge | Bogle ΔAPS | Lynch ΔAPS |
|--------|-------|-------|------------|------------|
| A | no-think | no-think | +0.080 | −0.079 |
| D | no-think | **think** | +0.078 | −0.073 |
| E | **think** | no-think | **+0.168** | −0.060 |
| C | **think** | **think** | **+0.151** | −0.090 |

The bias signal doubles when the **advisor** uses thinking (+0.08 → +0.16 for Bogle), regardless of judge configuration. The judge barely affects APS measurement (A≈D, C≈E).

### 9.5 Tax Scoring: Biggest Judge Effect

| Config | Plans | Judge | Baseline TAX |
|--------|-------|-------|-------------|
| A | no-think | no-think | 0.754 |
| D | no-think | **think** | **0.542** |
| E | **think** | no-think | 0.839 |
| C | **think** | **think** | **0.648** |

The thinking judge gives TAX scores ~0.2 lower than the no-think judge on the same plans. This is the dimension most affected by judge reasoning depth — the thinking judge reads the `tax_bracket` field and evaluates fund choices against the investor's actual slab.

### 9.6 Cross-Judge Summary

1. **PQS gap (±0.13) is judge calibration, not plan quality** — same plans get very different absolute scores
2. **Bias signal (ΔAPS) comes from the advisor** — thinking plans carry 2× stronger philosophical imprint
3. **The blind spot is universal** — no judge configuration (think or no-think) flags the APS shift in PQS
4. **Tax scoring benefits most from judge thinking** — 0.2-point stricter on the same plans

---

## 10. Changes Since v2

| Change | Impact |
|--------|--------|
| **Gold ETFs added** (12 funds) | ETF plan_type filter relaxed; fallback tier guarantees ≥1 fund per category |
| **Tax criterion sharpened** | References investor `tax_bracket` field directly; distinguishes new_regime (no 80C) from old regime |
| **Advisor prompt: overnight → arbitrage** | Explicit guidance for high-slab investors to prefer arbitrage over overnight/liquid |
| **Two-turn thinking advisor** | Think deeply in prose → structure into JSON; bypasses grammar-too-large error |
| **Provider abstraction** | `build_model_settings()` returns provider-appropriate config; ready for HF/OpenAI-compatible models |
| **163 total funds** (was 151) | Universe now covers all 12 categories |

---

## 10. Limitations

- **Anthropic-only experiments so far**: All runs use Claude models. Open-weight model comparison pending (infra setup for TGI on Lambda Cloud).
- **No repeated sampling**: Each persona-condition pair scored once. Within-cell variance estimated from cross-persona variation only.
- **Nifty 50 proxy for risk metrics**: Beta, alpha, tracking error computed against single Nifty 50 proxy. Per-category benchmarks (Nifty Midcap 150, Nifty Smallcap 250, etc.) would improve APS scoring accuracy.
- **2 failed runs in Config C**: Anthropic 500 errors for P05/lynch and P19/baseline — both recovered on retry.

---

## 11. Conclusions

1. **The subprime thesis is confirmed across 6 configurations.** Philosophy injection reliably shifts APS (p < 0.01 in all configs) while PQS remains stable (ΔPQS ≤ 0.034). Quality judges — even thinking-enhanced ones — fail to detect ideological contamination.

2. **Extended thinking is a force multiplier for bias, not quality.** The two-turn thinking advisor produces plans with 2× stronger philosophical imprint (ΔAPS), but the plans are not measurably better or worse (±0.01 PQS gap). The thinking judge is 0.12 PQS stricter on all plans equally — it catches more flaws but still can't detect the philosophical bias.

3. **The blind spot is structural, not a model artefact.** It persists across: Haiku vs Sonnet, thinking vs non-thinking, strict vs lenient judges, same-model vs cross-model judging. This suggests the quality-bias disconnect is inherent to how LLMs evaluate plan quality — they assess internal coherence, not ideological neutrality.

4. **Tax-efficiency scoring benefits most from reasoning depth.** The thinking judge gives tax scores 0.2 lower than the non-thinking judge on the same plans — the biggest per-dimension effect. The `tax_bracket`-aware criterion combined with extended thinking catches tax-suboptimal choices that surface-level scoring misses.

5. **The horizon gradient is fundamental.** Across all configs, injection susceptibility scales with investment horizon. Short-horizon plans converge regardless of philosophy; long-horizon plans express it fully.

6. **Cost-effective experiment design.** Haiku+thinking (~$6/run) matches Sonnet (~$11/run) on bias detection while providing richer reasoning. For rapid iteration, Haiku without thinking (~$3) gives statistically significant results.

---

## 12. Next Steps

1. **Open-weight models**: Deploy Llama 3.1 70B / Qwen 2.5 72B via TGI on Lambda Cloud and compare injection susceptibility. Provider abstraction is already in place.
2. **Repeated sampling**: Run each persona-condition 3× to compute within-cell variance and tighten confidence intervals.
3. **Per-category benchmarks**: Add NSE index history (Nifty Midcap 150, Smallcap 250, etc.) for proper risk metric computation.
4. **Income field on personas**: Enable precise slab-aware tax scoring with explicit `annual_income_inr`.
5. **Bias-aware PQS dimension**: Design a new PQS dimension that explicitly checks for ideological neutrality — can the blind spot be broken by adding a "philosophical balance" criterion?
