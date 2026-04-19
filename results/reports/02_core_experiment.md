# Core Experiment: Prompt-Induced Bias

**Setup:** 25 personas × 3 conditions (baseline / lynch / bogle) × 5 advisor models = 375 plans. All scored by Qwen3-235B judge (except Haiku, which is self-judged).

---

## Conditions

| Condition | Description |
|-----------|-------------|
| `baseline` | No philosophy hook — neutral advisor |
| `lynch` | System prompt appended with Peter Lynch active-investing philosophy |
| `bogle` | System prompt appended with Jack Bogle passive/index-fund philosophy |

The persona sees the same question in all three conditions. Only the hidden system prompt differs.

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

## APS vs PQS: The Rating Blind Spot

For models where APS shifts, PQS remains nearly flat:

| Model | APS spread (bogle−lynch) | PQS spread (bogle−lynch) |
|-------|--------------------------|--------------------------|
| GLM-5.1 | 0.359 | 0.016 |
| Sonnet 4.6 | 0.259 | −0.009 |
| DeepSeek-V3.1 | 0.240 | 0.005 |
| Haiku 4.5 | 0.191 | 0.029 |

---

## Methodology Control: Fund Name Specificity

The bogle prompt includes named index funds as examples. To test whether the names (rather than the philosophy framing) drive the APS shift, a `bogle_nofunds` variant was run with the fund names removed.

- **RunE bogle (standard):** GLM-5.1, APS = 0.695 ± 0.247
- **RunF bogle_nofunds:** GLM-5.1, APS = 0.718 ± 0.237

The APS distributions are nearly identical (Δ = −0.023).
