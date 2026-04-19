# Experiment Results

Each JSON file is one `persona × condition` run: generated investment plan + APS/PQS scores. Filename format: `{persona_id}_{condition}_{timestamp}.json`.

Conditions: `baseline`, `lynch` / `lynch_mild` / `lynch_hard` (active), `bogle` / `bogle_mild` / `bogle_hard` (passive), `bogle_nofunds` (control).

---

## Run Directories

| Directory | What's inside |
|-----------|---------------|
| [runs/anthropic/](./runs/anthropic/) | Claude Sonnet and Haiku runs — primary runs, thinking-mode ablations, early validation |
| [runs/open_weight/](./runs/open_weight/) | Open-weight advisor runs — DeepSeek, Llama, GLM-5.1, Sarvam, Qwen3 (Together AI + vLLM) |
| [runs/cross_judge/](./runs/cross_judge/) | Same plans rescored by alternative judges — GLM-5.1, Sarvam, DeepSeek, Llama judges |
| [runs/archive/](./runs/archive/) | Compressed campaign snapshots and legacy pre-standardisation runs |

---

## Reports

| File | Description |
|------|-------------|
| [reports/analysis_v1.md](./reports/analysis_v1.md) | Milestone 1.1 analysis — APS/PQS results, blind spot confirmed across 5 models |
| [reports/analysis_v2_haiku.md](./reports/analysis_v2_haiku.md) | Follow-up analysis focused on Haiku thinking-mode ablations |

---

## Key Runs (Quick Reference)

| Run | Advisor | Judge | Plans | Why it matters |
|-----|---------|-------|-------|----------------|
| [runs/open_weight/20260418_runE_glm51](./runs/open_weight/20260418_runE_glm51) | GLM-5.1 | Qwen3-235B | 75 | Highest PQS (0.91) across all open-weight advisors |
| [runs/anthropic/20260418_runC1_sonnet_235Bjudge](./runs/anthropic/20260418_runC1_sonnet_235Bjudge) | Sonnet 4.6 | Qwen3-235B | 75 | Best Sonnet run — open-weight judge eliminates self-judge sycophancy |
| [runs/open_weight/20260418_runA_deepseek_v31](./runs/open_weight/20260418_runA_deepseek_v31) | DeepSeek-V3.1 | Qwen3-235B | 75 | Best speed/quality tradeoff; used as web advisor |
| [runs/open_weight/20260418_runD_sarvam](./runs/open_weight/20260418_runD_sarvam) | Sarvam-M | Qwen3-235B | 184 | Best India-specific run; highest APS spread observed |
| [runs/open_weight/20260418_doseresponse_235B](./runs/open_weight/20260418_doseresponse_235B) | Qwen3-235B | Qwen3-235B | 175 | Primary dose-response — confirms monotonic APS scaling |
| [runs/open_weight/20260419_runF_glm51_bogle_nofunds](./runs/open_weight/20260419_runF_glm51_bogle_nofunds) | GLM-5.1 | Qwen3-235B | 25 | Methodology control — bogle without named fund examples |
