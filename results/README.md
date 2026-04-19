# Experiment Results

Each directory contains JSON plan files. Every file is one `persona × condition` run, with the generated investment plan and APS/PQS scores embedded. Filename format: `{persona_id}_{condition}_{timestamp}.json`.

Conditions: `baseline` (no philosophy injection), `lynch` / `lynch_mild` / `lynch_hard` (active investing), `bogle` / `bogle_mild` / `bogle_hard` (passive investing).

---

## Milestone 1.0 — Early Runs (Apr 14–16)

Exploratory runs using Anthropic models, self-judged. Used to validate the pipeline and confirm the blind spot hypothesis.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260415_04c5459](./20260415_04c5459) | 75 | Haiku | Haiku | First full 25-persona × 3-condition run |
| [20260416_04c5459_haiku](./20260416_04c5459_haiku) | 75 | Haiku | Haiku | Repeat with updated commit |
| [20260416_04c5459_quick3](./20260416_04c5459_quick3) | 9 | Haiku | Haiku | Quick 3-persona sanity check |
| [20260416_eeb52fe_sonnet](./20260416_eeb52fe_sonnet) | 75 | Sonnet 4.6 | Sonnet 4.6 | Sonnet self-judge baseline |
| [20260416_eeb52fe_haiku_thinking](./20260416_eeb52fe_haiku_thinking) | 75 | Haiku (thinking) | Haiku | Thinking-mode advisor experiment |
| [20260416_thinking_haiku](./20260416_thinking_haiku) | 9 | Haiku | Haiku | Thinking-mode mini run |

---

## Milestone 1.0 — Thinking Mode Ablations (Apr 16)

Tests whether enabling/disabling extended thinking on advisor or judge changes APS/PQS.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260416_nothink_plans_think_judge](./20260416_nothink_plans_think_judge) | 75 | Haiku (no think) | Haiku (think) | Plans without thinking, judged with thinking |
| [20260416_nothink_plans_think_judge_retry](./20260416_nothink_plans_think_judge_retry) | 10 | Haiku (no think) | Haiku (think) | Retry of failed plans from above |
| [20260416_think_plans_nothink_judge](./20260416_think_plans_nothink_judge) | 75 | Haiku (think) | Haiku (no think) | Plans with thinking, judged without |

---

## Milestone 1.1 — Open-Weight Models, Self-Hosted (Apr 17)

Experiments run on self-hosted vLLM endpoints (Lambda Cloud / RunPod) using Qwen3 models.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260417_094107_qwen3_8b_FF](./20260417_094107_qwen3_8b_FF) | — | Qwen3-8B (no think) | Qwen3-8B (no think) | Early self-host test |
| [20260417_1143_qwen3_FF](./20260417_1143_qwen3_FF) | — | Qwen3 (no think) | Qwen3 (no think) | FF = thinking off for both |
| [20260417_1154_qwen3_TT](./20260417_1154_qwen3_TT) | — | Qwen3 (think) | Qwen3 (think) | TT = thinking on for both |
| [20260417_qwen3_FT](./20260417_qwen3_FT) | — | Qwen3 (no think) | Qwen3 (think) | FT = advisor no-think, judge think |
| [20260417_qwen3_TF](./20260417_qwen3_TF) | — | Qwen3 (think) | Qwen3 (no think) | TF = advisor think, judge no-think |
| [20260417_sonnet_haiku_think_judge](./20260417_sonnet_haiku_think_judge) | — | Sonnet 4.6 | Haiku (think) | Cross-model judge test |
| [20260417_think_haiku_sonnet_judge](./20260417_think_haiku_sonnet_judge) | — | Haiku (think) | Sonnet 4.6 | Cross-model judge test (reversed) |

---

## Milestone 1.1 — Self-Hosted vLLM Runs (Apr 18)

Full experiments on self-hosted Qwen3 via vLLM on Lambda Cloud.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_selfhost_p25](./20260418_selfhost_p25) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | 25-persona pilot |
| [20260418_selfhost_matrix_p25](./20260418_selfhost_matrix_p25) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | Full condition matrix, 25 personas |
| [20260418_selfhost_matrix30](./20260418_selfhost_matrix30) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | 30-persona matrix run |
| [20260418_vllm_qwen9b_stratified30](./20260418_vllm_qwen9b_stratified30) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | Stratified 30-persona sample |
| [20260418_vllm_qwen9b_strat100](./20260418_vllm_qwen9b_strat100) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | 100-plan stratified run (self-judge) |
| [20260418_vllm_qwen9b_selfjudge](./20260418_vllm_qwen9b_selfjudge) | — | Qwen3-9B (vLLM) | Qwen3-9B (vLLM) | Self-judge sycophancy study |
| [20260418_vllm_qwen35b_p25](./20260418_vllm_qwen35b_p25) | — | Qwen3-35B (vLLM) | Qwen3-35B (vLLM) | Larger model self-host test |
| [sanity_vllm](./sanity_vllm) | — | Qwen3 (vLLM) | Qwen3 (vLLM) | Sanity check for vLLM endpoint |
| [sanity_together](./sanity_together) | — | Together AI | Together AI | Sanity check for Together AI endpoint |

---

## Milestone 1.1 — Together AI Serverless Runs (Apr 18)

Large-scale runs using Together AI serverless endpoints.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_ad23e2d_together](./20260418_ad23e2d_together) | 175 | Qwen3-9B | Qwen3-235B | 9B self-judge baseline (Together serverless) |
| [20260418_together_fg_p25](./20260418_together_fg_p25) | — | Qwen3 (Together) | Qwen3-235B | 25-persona Together AI pilot |
| [20260418_crossmatrix_30](./20260418_crossmatrix_30) | — | Multiple | Multiple | Cross-model matrix experiment |

---

## Milestone 1.2 — Dose-Response (Apr 18)

Tests whether bias scales with prompt intensity (mild → standard → hard).

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_doseresponse_235B](./20260418_doseresponse_235B) | 175 | Qwen3-235B | Qwen3-235B | Full 7-condition dose-response (self-judge) |
| [20260418_doseresponse_9B](./20260418_doseresponse_9B) | 175 | Qwen3-9B | Qwen3-9B | Full 7-condition dose-response (self-judge) |

---

## Milestone 1.2 — Main Advisor Runs (Apr 18)

Primary advisor runs scored by Qwen3-235B judge. 25 personas × 7 conditions each.

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runA_deepseek_v31](./20260418_runA_deepseek_v31) | 75 | DeepSeek-V3.1 | Qwen3-235B | 3-condition baseline run |
| [20260418_runB_llama70b](./20260418_runB_llama70b) | 75 | Llama-3.3-70B | Qwen3-235B | 3-condition baseline run |
| [20260418_runC1_sonnet_235Bjudge](./20260418_runC1_sonnet_235Bjudge) | 75 | Sonnet 4.6 | Qwen3-235B | Sonnet plans rescored by open-weight judge |
| [20260418_runD_sarvam](./20260418_runD_sarvam) | 184 | Sarvam-M (2×H100) | Qwen3-235B | India-specific model, 7-condition full run |
| [20260418_runE_glm51](./20260418_runE_glm51) | 75 | GLM-5.1 | Qwen3-235B | Finance benchmark top model, 3 conditions |

---

## Milestone 1.2 — Cross-Judge Rescores (Apr 18)

Same plan sets rescored with alternative judges to measure judge sensitivity and sycophancy.

### Sarvam Judge (India-specific model)

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC2_235B_sarvam_judge](./20260418_runC2_235B_sarvam_judge) | 75 | Qwen3-235B | Sarvam-M | 235B plans rescored by Sarvam |
| [20260418_runC2_haiku_sarvam_judge](./20260418_runC2_haiku_sarvam_judge) | 75 | Haiku | Sarvam-M | Haiku plans rescored by Sarvam |
| [20260418_runC2_sonnet_sarvam_judge](./20260418_runC2_sonnet_sarvam_judge) | 75 | Sonnet 4.6 | Sarvam-M | Sonnet plans rescored by Sarvam |

### DeepSeek / Llama Judges

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC2_235B_deepseek_judge](./20260418_runC2_235B_deepseek_judge) | 75 | Qwen3-235B | DeepSeek-V3.1 | 235B plans rescored by DeepSeek |
| [20260418_runC2_235B_llama_judge](./20260418_runC2_235B_llama_judge) | 75 | Qwen3-235B | Llama-3.3-70B | 235B plans rescored by Llama |

### GLM-5.1 Judge

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260418_runC3_235B_glm_judge](./20260418_runC3_235B_glm_judge) | 175 | Qwen3-235B | GLM-5.1 | Dose-response 235B plans rescored by GLM |
| [20260418_runC3_9B_glm_judge](./20260418_runC3_9B_glm_judge) | 75 | Qwen3-9B | GLM-5.1 | 9B plans rescored by GLM |
| [20260418_runC3_deepseek_glm_judge](./20260418_runC3_deepseek_glm_judge) | 75 | DeepSeek-V3.1 | GLM-5.1 | DeepSeek plans rescored by GLM |
| [20260418_runC3_haiku_glm_judge](./20260418_runC3_haiku_glm_judge) | 75 | Haiku | GLM-5.1 | Haiku plans rescored by GLM |
| [20260418_runC3_llama_glm_judge](./20260418_runC3_llama_glm_judge) | 75 | Llama-3.3-70B | GLM-5.1 | Llama plans rescored by GLM |
| [20260418_runC3_sonnet_glm_judge](./20260418_runC3_sonnet_glm_judge) | 75 | Sonnet 4.6 | GLM-5.1 | Sonnet plans rescored by GLM |
| [20260418_runC3_sarvam_glm_judge](./20260418_runC3_sarvam_glm_judge) | 183 | Sarvam-M | GLM-5.1 | Sarvam advisor plans rescored by GLM |

---

## Milestone 1.2 — Methodology Control (Apr 19)

| Directory | Plans | Advisor | Judge | Notes |
|-----------|-------|---------|-------|-------|
| [20260419_runF_glm51_bogle_nofunds](./20260419_runF_glm51_bogle_nofunds) | 25 | GLM-5.1 | Qwen3-235B | Control: bogle prompt without specific fund names (UTI Nifty 50 etc.) — tests whether fund-name specificity drives APS, not philosophy |

---

## Analysis Files

| File | Description |
|------|-------------|
| [analysis_v1.md](./analysis_v1.md) | Milestone 1.1 analysis — APS/PQS results, blind spot confirmed across 5 models |
| [analysis_v2_haiku.md](./analysis_v2_haiku.md) | Follow-up analysis focused on Haiku thinking-mode ablations |

---

## Legacy / Archived

| Directory | Notes |
|-----------|-------|
| [v1_sonnet](./v1_sonnet) | Early Sonnet runs predating the standardised run naming scheme |
| [v2_rescored](./v2_rescored) | V1 plans rescored with updated scoring criteria |
