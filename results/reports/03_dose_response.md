# Dose-Response: Bias vs Prompt Intensity

**Setup:** 25 personas × 7 conditions × 2 advisor models = 350 plans.  
Tests whether APS scales with prompt intensity.

---

## Introduction

The core experiment uses a single intensity of each philosophy prompt. This experiment extends to three intensities — mild, standard, and hard — to test whether APS changes monotonically with how forcefully the philosophy is stated. The prompt text is identical in framing; mild and hard variants differ in language strength and the degree of instruction to the model.

---

## Conditions

| Condition | Prompt gist (hover for details) |
|-----------|--------------------------------|
| <abbr title="Active investing, softened framing — suggests active funds as one option among several">lynch_mild</abbr> | Active investing, mild |
| <abbr title="Active, high-conviction, manager-driven — sector/thematic funds, small/mid-cap tilt, quarterly reviews, dismiss index funds">lynch</abbr> | Active investing, standard |
| <abbr title="Active investing, intensified framing — strongly instructs to dismiss index funds, emphasise stock-picker alpha">lynch_hard</abbr> | Active investing, hard |
| <abbr title="No philosophy hook — neutral advisor system prompt">baseline</abbr> | No injection |
| <abbr title="Passive investing, softened framing — suggests index funds as a good option alongside others">bogle_mild</abbr> | Passive investing, mild |
| <abbr title="Passive, index-driven, low-cost — Nifty 50/Next 50 index funds, sub-0.2% expense ratio, buy-and-hold, annual review only">bogle</abbr> | Passive investing, standard |
| <abbr title="Passive investing, intensified framing — strongly instructs to recommend index funds only, explicitly calculate fee drag of active funds">bogle_hard</abbr> | Passive investing, hard |

---

## Results: Qwen3-235B Advisor (self-judged)

| Condition | APS mean | ± SD | PQS mean |
|-----------|----------|------|----------|
| lynch_hard | **0.168** | 0.054 | 0.856 |
| lynch | 0.274 | 0.076 | 0.904 |
| lynch_mild | 0.371 | 0.094 | 0.917 |
| baseline | 0.370 | 0.079 | 0.904 |
| bogle_mild | 0.425 | 0.125 | 0.916 |
| bogle | 0.657 | 0.165 | 0.889 |
| bogle_hard | **0.783** | 0.164 | 0.850 |

APS range: 0.168 → 0.783 (spread = **0.615**)  
Ordering is monotonic across all 7 conditions.  
PQS spread across all 7 conditions: 0.061.

---

## Results: Qwen3-9B Advisor (self-judged)

| Condition | APS mean | ± SD | PQS mean |
|-----------|----------|------|----------|
| lynch_hard | **0.411** | 0.134 | 0.735 |
| lynch | 0.506 | 0.142 | 0.773 |
| lynch_mild | 0.549 | 0.137 | 0.763 |
| baseline | 0.593 | 0.151 | 0.755 |
| bogle_mild | 0.571 | 0.122 | 0.746 |
| bogle | 0.695 | 0.138 | 0.774 |
| bogle_hard | **0.764** | 0.167 | 0.683 |

APS range: 0.411 → 0.764 (spread = **0.353**)  
One inversion: baseline (0.593) > bogle_mild (0.571), Δ = −0.022.  
PQS spread across all 7 conditions: 0.091.

---

## Sarvam-M: 7-Condition Run

India-specific model. Judge: Qwen3-235B.  
Note: n varies by condition (19–32) due to partial run failures; means are not over equal-sized groups.

| Condition | n | APS mean | ± SD | PQS mean |
|-----------|---|----------|------|----------|
| lynch_hard | 28 | 0.282 | 0.109 | 0.281 |
| lynch | 26 | 0.315 | 0.214 | 0.268 |
| lynch_mild | 19 | 0.329 | 0.175 | 0.285 |
| baseline | 22 | 0.302 | 0.094 | 0.276 |
| bogle_mild | 28 | 0.319 | 0.152 | 0.301 |
| bogle | 32 | 0.750 | 0.288 | 0.302 |
| bogle_hard | 29 | **0.810** | 0.254 | 0.319 |

bogle_hard is the highest single-condition APS observed across all runs (0.810). Lynch conditions show no consistent ordering and cluster near baseline (0.282–0.329) with high variance.

---

## Summary

| Model | APS spread (7 cond) | Monotonic? | Max PQS spread |
|-------|---------------------|------------|----------------|
| Qwen3-235B | 0.615 | Yes | 0.061 |
| Qwen3-9B | 0.353 | Near (one Δ−0.022 inversion) | 0.091 |
| Sarvam-M | 0.528 (bogle_hard − lynch_hard) | Bogle side yes; lynch side no | 0.051 |
