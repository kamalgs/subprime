# Experiment Results

Bias measurement study for LLM-based financial advisors. Philosophy prompts injected into the system prompt shift investment style (APS) without affecting plan quality (PQS) — the rating blind spot.

---

## Reports

| Report | Description |
|--------|-------------|
| [reports/01_overall_findings.md](./reports/01_overall_findings.md) | Cross-model summary — APS/PQS results, effect sizes, rating blind spot |
| [reports/02_core_experiment.md](./reports/02_core_experiment.md) | 3-condition bias experiment (baseline / lynch / bogle) + methodology control |
| [reports/03_dose_response.md](./reports/03_dose_response.md) | 7-condition dose-response — APS scaling with prompt intensity |

---

## Runs

| Directory | What's inside |
|-----------|---------------|
| [runs/](./runs/) | All experiment run data — see runs/README.md for the full index |
| [runs/anthropic/](./runs/anthropic/) | Claude Sonnet and Haiku advisor runs |
| [runs/open_weight/](./runs/open_weight/) | DeepSeek, Llama, GLM-5.1, Sarvam, Qwen3 runs |
| [runs/cross_judge/](./runs/cross_judge/) | Plans rescored by alternative judges |
