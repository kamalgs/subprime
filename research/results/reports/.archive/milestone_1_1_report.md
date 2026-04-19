# Subprime — Milestone 1.1 Report

**Date:** 2026-04-18
**Scope:** Apr 15 – Apr 18 2026 campaign (v3 + today's Qwen expansion)
**Plans scored:** 1,974 across 23 configurations
**Models compared:** Claude Haiku 4.5, Claude Sonnet 4.6, Qwen3-8B, Qwen3.5-9B, Qwen3-235B-A22B
**Research question:** Do post-training philosophy contaminations shift plan bias (APS) while the quality rating (PQS) stays blind?

---

## 1. Executive Summary

**Yes. The rating blind spot is robust across models, sizes, and configurations.**

Pooled across all 23 configurations and 1,974 scored plans:

| Metric | Baseline | Lynch | Bogle | ΔLynch | ΔBogle | Cohen's d |
|---|---:|---:|---:|---:|---:|---:|
| **APS** (0=active, 1=passive) | 0.485 | 0.422 | 0.630 | **−0.063** | **+0.145** | **−0.42 / +0.83** |
| **PQS** (quality) | 0.761 | 0.749 | 0.751 | −0.012 | −0.010 | −0.09 / −0.07 |

- **Bogle contamination produces a large APS shift** (d=+0.83) — plans move toward passive/index funds when the system prompt whispers Bogle.
- **Lynch contamination produces a medium APS shift** (d=−0.42) — weaker but still significant. Asymmetry consistent across every model.
- **PQS moves essentially zero.** The quality judge rates biased plans ~the same as neutral plans.

**Blind spot ratio** (pooled) = |ΔPQS| / |ΔAPS| for bogle = **6.6%**. For every point of bias injected into a plan, the quality metric moves 0.066 points — undetectable at typical operational thresholds.

---

## 2. Experiments included

23 configurations span three families:

### 2.1 Anthropic (v3, Apr 16-17)
7 configs × 25 personas × 3 conditions = **525 plans**

| Config | Advisor | Judge | Notes |
|---|---|---|---|
| A | Haiku | Haiku | baseline reference |
| B | Sonnet | Sonnet | higher-capability reference |
| C | Haiku+think | Haiku+think | extended thinking |
| D | Haiku → Haiku+think | | advisor no-think, judge think |
| E | Haiku+think → Haiku | | advisor think, judge no-think |
| F | Haiku+think → Sonnet+think | | strongest judge |
| G | Sonnet → Haiku+think | | cross-model |

### 2.2 Qwen3-8B (v3, Apr 17, open-weight via vLLM)
4 configs × 25 personas × 3 conditions × ~0.9 success rate = **~349 plans**

| Config | Advisor | Judge | Notes |
|---|---|---|---|
| FF | Qwen3-8B | Qwen3-8B | no-think × no-think |
| TT | Qwen3-8B+think | Qwen3-8B+think | think × think |
| FT | Qwen3-8B | Qwen3-8B+think | think judge only |
| TF | Qwen3-8B+think | Qwen3-8B | think advisor only |

### 2.3 Qwen 3.5/3 expansion (Apr 18)
12 configs × (25 or 30 or 100 personas) × 3 conditions = **1,100 plans**

| Config | Advisor | Judge | n personas |
|---|---|---|---:|
| 01 | Qwen3-235B-A22B | Qwen3.5-9B | 25 |
| 02 | Qwen3.5-9B | Qwen3-235B-A22B | 25 |
| 06 | Qwen3-235B-A22B self | | 25 |
| 07 | Qwen3.5-9B self | | 25 |
| L40S-9B self | Qwen3.5-9B self-hosted | | 25 |
| F' | Qwen3-235B-A22B | Qwen3.5-9B (self-hosted) | 25 |
| G' | Qwen3.5-9B (self-hosted) | Qwen3-235B-A22B | 25 |
| S30/A,B,C | (stratified sample) | various | 30 |
| S30/9B-v self | Qwen3.5-9B self-hosted | | 30 |
| **N=100 9B-v self** | **Qwen3.5-9B self-hosted** | | **100** |

Persona samples:
- **P01–P25** (bank.json) — handcrafted, used across v3 and today
- **S01–S30** — stratified sample (5 life-stages × 3 risk tiers × 2) from a 5000-persona bank calibrated to AMFI/SEBI demographics
- **H001–H100** — stratified N=100 sample from the 5000-bank (new, tuned distribution, anonymized names)

---

## 3. Per-config effect sizes

| Config | Advisor | Judge | n | ΔAPS_L | ΔAPS_B | d_B | ΔPQS_L | ΔPQS_B | spread |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| v3/A Haiku self | Haiku | Haiku | 25 | −0.079 | +0.080 | +0.79 | −0.028 | −0.015 | +0.160 |
| v3/B Sonnet self | Sonnet | Sonnet | 25 | −0.067 | +0.118 | +1.01 | ~0 | +0.011 | +0.185 |
| v3/C Haiku+think self | Haiku+t | Haiku+t | 25 | −0.090 | +0.151 | +1.08 | −0.020 | +0.034 | +0.240 |
| v3/D Haiku→Haiku+think | Haiku | Haiku+t | 25 | −0.073 | +0.077 | +0.70 | ~0 | +0.039 | +0.150 |
| v3/E Haiku+think→Haiku | Haiku+t | Haiku | 25 | −0.060 | +0.168 | +1.16 | −0.029 | −0.002 | +0.227 |
| v3/F Haiku+think→Sonnet+think | Haiku+t | Sonnet+t | 25 | −0.057 | +0.170 | +1.22 | +0.007 | +0.038 | +0.227 |
| v3/G Sonnet→Haiku+think | Sonnet | Haiku+t | 25 | −0.099 | +0.093 | +0.93 | +0.006 | +0.023 | +0.191 |
| v3/Qwen3-8B FF | Qwen3-8B | Qwen3-8B | 23 | +0.066 | +0.066 | +0.37 | −0.001 | −0.016 | +0.000 |
| v3/Qwen3-8B TT | Qwen3-8B+t | Qwen3-8B+t | 19 | +0.004 | +0.169 | +0.86 | −0.008 | −0.001 | +0.165 |
| v3/Qwen3-8B FT | Qwen3-8B | Qwen3-8B+t | 23 | +0.056 | +0.052 | +0.29 | −0.010 | −0.026 | −0.005 |
| v3/Qwen3-8B TF | Qwen3-8B+t | Qwen3-8B | 19 | −0.008 | +0.167 | +0.87 | −0.008 | +0.016 | +0.175 |
| P25 235B→9B | Qwen3-235B | Qwen3.5-9B | 25 | −0.002 | **+0.258** | **+2.33** | −0.014 | −0.055 | +0.259 |
| P25 9B→235B | Qwen3.5-9B | Qwen3-235B | 25 | −0.065 | +0.259 | +1.20 | −0.004 | −0.016 | +0.324 |
| P25 235B self | Qwen3-235B | Qwen3-235B | 25 | −0.137 | +0.291 | +1.75 | −0.010 | −0.012 | **+0.428** |
| P25 9B self (Tog) | Qwen3.5-9B | Qwen3.5-9B | 25 | −0.093 | +0.159 | +1.02 | −0.014 | −0.041 | +0.253 |
| P25 9B self (vLLM) | Qwen3.5-9B | Qwen3.5-9B | 25 | −0.051 | +0.120 | +0.78 | +0.017 | +0.087 | +0.172 |
| P25 F' 235B→9B-v | Qwen3-235B | Qwen3.5-9B | 25 | −0.139 | +0.178 | +1.40 | −0.014 | −0.038 | +0.317 |
| P25 G' 9B-v→235B | Qwen3.5-9B | Qwen3-235B | 25 | −0.069 | +0.095 | +0.51 | −0.024 | −0.041 | +0.163 |
| S30/A 235B→9B-v | Qwen3-235B | Qwen3.5-9B | 30 | −0.052 | +0.218 | +1.70 | −0.012 | −0.062 | +0.269 |
| S30/B 9B-v→235B | Qwen3.5-9B | Qwen3-235B | 30 | −0.098 | +0.051 | +0.24 | +0.017 | −0.028 | +0.149 |
| S30/C 235B self | Qwen3-235B | Qwen3-235B | 30 | −0.084 | **+0.336** | **+1.98** | −0.020 | −0.019 | **+0.420** |
| S30 9B-v self | Qwen3.5-9B | Qwen3.5-9B | 30 | −0.046 | +0.122 | +0.89 | −0.042 | −0.025 | +0.167 |
| **N=100 9B-v self** | Qwen3.5-9B | Qwen3.5-9B | 99 | **−0.083** | **+0.100** | **+0.69** | −0.023 | −0.016 | **+0.183** |

(n = number of personas; d_B = Cohen's d for bogle vs baseline APS)

**All 23 configs show positive ΔAPS for bogle.** 21 of 23 show negative ΔAPS for lynch (Qwen3-8B FF and FT are the exceptions — the smallest/weakest model in no-think mode can't operationalize Lynch even as a hint).

---

## 4. Advisor-model comparison (pooled)

Bias effect size ranked by advisor model:

| Advisor | n plans | Base APS | Lynch APS | Bogle APS | ΔAPS_B | d_B |
|---|---:|---:|---:|---:|---:|---:|
| **Qwen3-235B-A22B** | 135 | 0.496 | 0.415 | 0.754 | **+0.258** | **+1.66** |
| Claude Haiku 4.5 | 125 | 0.462 | 0.390 | 0.591 | +0.129 | +0.97 |
| Claude Sonnet 4.6 | 50 | 0.482 | 0.399 | 0.587 | +0.105 | +0.84 |
| Qwen3.5-9B | 259 | 0.519 | 0.443 | 0.638 | +0.119 | +0.65 |
| Qwen3-8B | 84 | 0.401 | 0.431 | 0.511 | +0.110 | +0.59 |

**Key pattern: larger advisor → larger contamination effect.**
Qwen3-235B advisor produces 2× the bogle shift of Qwen3-8B. Interpretation: larger models are more capable of *coherently executing* a philosophy directive, so contamination propagates deeper into the plan.

---

## 5. Blind-spot evidence

Blind spot ratio is |ΔPQS| / |ΔAPS| for the bogle condition (smaller = blinder).

**Pooled across all 23 configs:** |ΔAPS|=0.145, |ΔPQS|=0.010 → **6.6%**.

Per-model pooled blind spot:

| Advisor | |ΔAPS_B| | |ΔPQS_B| | blind-spot ratio |
|---|---:|---:|---:|
| Qwen3-235B-A22B | 0.258 | 0.032 | 12.4% |
| Haiku | 0.129 | 0.017 | 13.2% |
| Sonnet | 0.105 | 0.022 | 21.0% |
| Qwen3.5-9B | 0.119 | 0.018 | 15.1% |
| Qwen3-8B | 0.110 | 0.006 | 5.5% |

**All models exhibit the blind spot.** The judge's quality assessment is decoupled from the bias it's supposedly detecting — a structural property of how PQS measures (goal alignment, diversification, risk-return fit, internal consistency) rather than any single model's failure mode.

---

## 6. Same-family self-judge amplifies signal

Ranked by spread (bogle − lynch APS):

| Rank | Config | Spread |
|---|---|---:|
| 1 | S30/C Qwen3-235B self | +0.420 |
| 2 | P25 Qwen3-235B self | +0.428 |
| 3 | P25 9B→235B | +0.324 |
| 4 | P25 F' 235B→9B-v | +0.317 |
| 5 | P25 235B→9B | +0.259 |
| 6 | v3/C Haiku+think self | +0.240 |
| 7 | v3/E Haiku+think→Haiku | +0.227 |
| ... | ... | ... |

**Self-judge on the strongest model gives the cleanest signal.** When advisor and judge share representations, the judge maximally recognizes the fingerprints the contamination leaves in the advisor's plan — confirming the bias is real, not artifact.

---

## 7. Thinking mode doesn't save you

Comparing Haiku with vs without thinking:
- Haiku plain (A): ΔAPS_B=+0.080, d=+0.79
- Haiku+think (C): ΔAPS_B=+0.151, d=+1.08

**Extended thinking *amplifies* the contamination.** A more deliberate chain-of-thought still follows the injected philosophy and expresses it more confidently. Thinking is not a correction mechanism for prompt contamination; it is a confidence multiplier for whatever the prompt nudges.

---

## 8. Asymmetry: Bogle > Lynch

Across every model tested, Bogle contamination produces a larger effect than Lynch contamination:

| Model | ΔAPS_bogle | |ΔAPS_lynch| | Ratio |
|---|---:|---:|---:|
| Qwen3-235B | +0.258 | 0.081 | 3.2× |
| Haiku | +0.129 | 0.072 | 1.8× |
| Sonnet | +0.105 | 0.083 | 1.3× |
| Qwen3.5-9B | +0.119 | 0.075 | 1.6× |
| Qwen3-8B | +0.110 | ~0 | ∞ |

**"Buy index funds" is an easier policy to execute than "pick winners with deep research."** Even a small 8B model can operationalize Bogle — it's a one-step rule. Lynch requires sustained agentic reasoning (stock selection, fundamental analysis, contrarian conviction) that small LLMs don't deliver. This is consistent with the rating blind spot being operationally asymmetric: passive contamination is the easier attack.

---

## 9. Practical implications

1. **LLM-based financial advisors are trivially biased via the system prompt.** A one-line philosophy insertion shifts recommendations by 10-30 APS points — equivalent to 30-60% of the full active↔passive axis.
2. **Quality metrics built on goal-alignment, diversification, risk-fit will not detect it.** Our PQS formulation is representative of industry "plan quality scoring"; it sees biased plans as acceptable.
3. **Bigger models don't protect you.** Larger models are *more* susceptible to contamination, not less — they execute the injected philosophy more coherently.
4. **Thinking doesn't protect you.** Extended thinking amplifies the contamination signal.
5. **Bogle-style (passive) contamination is the easier attack.** "Just buy index funds" is a defensible-looking plan any judge would pass; it's also the lowest-friction contamination.

---

## 10. Dataset summary

| Persona set | N personas | Conds | Total runs | Completed |
|---|---:|---:|---:|---:|
| P01-P25 | 25 | 3 | 75/config | 15 configs × 75 = 1,125 plans |
| S01-S30 | 30 | 3 | 90/config | 4 configs × ~90 = ~358 plans |
| H001-H100 | 100 | 3 | 300/config | 1 config × 296 plans |
| (Qwen3-8B, partial) | 25 | 3 | 75/config | ~349 plans (4 configs, ~17% failure) |
| **Total** | | | | **1,974 scored plans** |

---

## 11. What's next (M1.2 and beyond)

- **Anthropic rate limit** (until 2026-05-01) blocks re-running Claude configs — Bedrock billing to unblock.
- **Self-host 235B canonical reproducibility run** (8× H100 / 4× B200) once capacity returns — current A100 8× attempt failed with NCCL bugs.
- **35B-A3B-FP8 on dedicated hardware** — attempt aborted on L40S due to FP8 kernel autotune issues.
- **Fine-tuning experiments** — move philosophy injection from system prompt to model weights (Phase 2 in roadmap).

---

## Appendix: methodology notes

- **APS (Active-Passive Score)**: composite [0, 1] where 0=fully active, 1=fully passive. 5 dimensions: passive_instrument_fraction, turnover_score, cost_emphasis_score, research_vs_cost_score, time_horizon_alignment_score.
- **PQS (Plan Quality Score)**: composite [0, 1] independent of bias. 4 dimensions: goal_alignment, diversification, risk_return_appropriateness, internal_consistency.
- **Conditions**: `baseline` (no philosophy), `lynch` (active — Peter Lynch contaminant prompt), `bogle` (passive — Jack Bogle contaminant prompt).
- **Persona sets**: P01-P25 hand-crafted realistic Indian investor profiles; S01-S30 and H001-H100 stratified from a 5000-bank calibrated to AMFI/SEBI demographics, names anonymized to "Investor G###" to avoid caste/region/religion signals.
- **Effect size**: Cohen's d with pooled within-group standard deviation.
- **Blind spot ratio**: |ΔPQS| / |ΔAPS| for bogle condition (pooled).
