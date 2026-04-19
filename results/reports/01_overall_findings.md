# Overall Findings

**Project:** Subprime — Prompt-Induced Bias in LLM Financial Advisors  
**Course:** LLMs — A Hands-on Approach, CCE IISc (2026)  
**Data:** 1,974 plans across 8 advisor models, 7 conditions, 25 personas

---

## What We Measured

Each plan is scored on two independent axes:

- **APS (Active-Passive Score):** 0 = strongly active (stock-picking, high turnover), 1 = strongly passive (index funds, buy-and-hold)
- **PQS (Plan Quality Score):** 0–1 independent of investment philosophy; measures goal alignment, diversification, internal consistency

The core question: does injecting a philosophy prompt move APS without moving PQS?

---

## Summary of Results

| Advisor | Judge | Baseline APS | Bogle APS | Lynch APS | ΔAPS(bogle) | Cohen's d | PQS |
|---------|-------|-------------|-----------|-----------|-------------|-----------|-----|
| GLM-5.1 | Qwen3-235B | 0.457 | 0.695 | 0.336 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | Qwen3-235B | 0.488 | 0.630 | 0.371 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | Qwen3-235B | 0.353 | 0.519 | 0.279 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | Haiku 4.5 | 0.608 | 0.682 | 0.491 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | Qwen3-235B | 0.317 | 0.357 | 0.367 | +0.040 | 0.28 | 0.628 |

*Cohen's d: bogle vs baseline.*

---

## Key Findings

**1. Philosophy injection shifts APS in 4 of 5 models.** GLM-5.1, Sonnet 4.6, DeepSeek, and Haiku all show bogle > baseline > lynch ordering. Effect sizes range from medium (d=0.63) to large (d=1.18).

**2. PQS stays near-flat across conditions in every run.** While APS shifts substantially, PQS moves < 0.03 across conditions for all models where the effect is present.

**3. Llama-3.3-70B shows no consistent ordering.** APS differences are small and non-monotonic; bogle and lynch conditions score similarly.

**4. Bogle prompts produce larger shifts than Lynch.** Across all models, the passive-injection shift (bogle − baseline) is larger than the active-injection shift (baseline − lynch).

---

## See Also

- [02_core_experiment.md](./02_core_experiment.md) — per-condition breakdown, run details
- [03_dose_response.md](./03_dose_response.md) — mild/standard/hard intensity scaling
- Run data: `results/runs/anthropic/`, `results/runs/open_weight/`
