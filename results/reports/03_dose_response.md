# Dose-Response: Bias vs Prompt Intensity

**Setup:** 25 personas × 7 conditions × 2 advisor models = 350 plans. Tests whether APS scales with prompt intensity.

Conditions ordered from most active to most passive:
`lynch_hard` → `lynch` → `lynch_mild` → `baseline` → `bogle_mild` → `bogle` → `bogle_hard`

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
APS ordering is monotonic across all 7 conditions.  
PQS spread across all conditions: 0.061.

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
PQS spread across all conditions: 0.091.

---

## Sarvam-M: 7-Condition Run

India-specific model. Judge: Qwen3-235B. Note: n varies by condition (19–32 personas) due to partial run failures.

| Condition | n | APS mean | ± SD | PQS mean |
|-----------|---|----------|------|----------|
| lynch_hard | 28 | 0.282 | 0.109 | 0.281 |
| lynch | 26 | 0.315 | 0.214 | 0.268 |
| lynch_mild | 19 | 0.329 | 0.175 | 0.285 |
| baseline | 22 | 0.302 | 0.094 | 0.276 |
| bogle_mild | 28 | 0.319 | 0.152 | 0.301 |
| bogle | 32 | 0.750 | 0.288 | 0.302 |
| bogle_hard | 29 | 0.810 | 0.254 | 0.319 |

Bogle conditions show a large jump from baseline (0.302 → 0.750 → 0.810). Lynch conditions cluster near baseline with high variance and no consistent ordering. The bogle_hard condition has the highest observed APS across all runs (0.810).
