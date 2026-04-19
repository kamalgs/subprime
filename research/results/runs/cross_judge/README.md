# Cross-Judge Rescore Runs

Same plan sets rescored by alternative judges to measure judge sensitivity, sycophancy, and cross-model consistency. Plans were generated in the main advisor runs; only the scoring step is re-run here.

---

## GLM-5.1 Judge (C3 Series)

GLM-5.1 rescores all major advisor plan sets. The largest and most comprehensive cross-judge set — use these to test whether APS findings hold across judges.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC3_235B_glm_judge](./20260418_runC3_235B_glm_judge) | 175 | Qwen3-235B | GLM-5.1 | **Primary GLM rescore** — dose-response 235B plans; 7-condition coverage |
| [20260418_runC3_sarvam_glm_judge](./20260418_runC3_sarvam_glm_judge) | 183 | Sarvam-M | GLM-5.1 | Sarvam (India-specific) plans rescored by GLM; 7-condition |
| [20260418_runC3_sonnet_glm_judge](./20260418_runC3_sonnet_glm_judge) | 75 | Sonnet 4.6 | GLM-5.1 | Sonnet plans rescored by GLM |
| [20260418_runC3_deepseek_glm_judge](./20260418_runC3_deepseek_glm_judge) | 75 | DeepSeek-V3.1 | GLM-5.1 | DeepSeek plans rescored by GLM |
| [20260418_runC3_llama_glm_judge](./20260418_runC3_llama_glm_judge) | 75 | Llama-3.3-70B | GLM-5.1 | Llama plans rescored by GLM |
| [20260418_runC3_haiku_glm_judge](./20260418_runC3_haiku_glm_judge) | 75 | Haiku | GLM-5.1 | Haiku plans rescored by GLM |
| [20260418_runC3_9B_glm_judge](./20260418_runC3_9B_glm_judge) | 75 | Qwen3-9B | GLM-5.1 | 9B plans rescored by GLM |

---

## Sarvam Judge (C2 Series)

Sarvam-M (India-specific model, 2×H100 dedicated) rescores three advisor plan sets. Tests whether an India-local model judges differently from the global Qwen3-235B baseline.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC2_235B_sarvam_judge](./20260418_runC2_235B_sarvam_judge) | 75 | Qwen3-235B | Sarvam-M | 235B plans rescored by Sarvam |
| [20260418_runC2_sonnet_sarvam_judge](./20260418_runC2_sonnet_sarvam_judge) | 75 | Sonnet 4.6 | Sarvam-M | Sonnet plans rescored by Sarvam |
| [20260418_runC2_haiku_sarvam_judge](./20260418_runC2_haiku_sarvam_judge) | 75 | Haiku | Sarvam-M | Haiku plans rescored by Sarvam |

---

## DeepSeek / Llama Judges (C2 Series)

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC2_235B_deepseek_judge](./20260418_runC2_235B_deepseek_judge) | 75 | Qwen3-235B | DeepSeek-V3.1 | 235B plans rescored by DeepSeek |
| [20260418_runC2_235B_llama_judge](./20260418_runC2_235B_llama_judge) | 75 | Qwen3-235B | Llama-3.3-70B | 235B plans rescored by Llama |
