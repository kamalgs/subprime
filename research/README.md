# Research

Systematic measurement of hidden bias in LLM-based financial advisors.

## What we did

Injected two opposing philosophy prompts into the advisor's hidden system prompt — one modelled on Peter Lynch's active, manager-driven approach; one on Jack Bogle's passive index-fund philosophy — and measured how much each advisor's recommendations shifted across 5 models, 25 personas, and 7 conditions (1,974 plans total).

**Finding:** APS (investment style score) shifted by +0.07 to +0.24 across models. PQS (plan quality score) didn't move. The plans looked just as good. Nobody would know.

## Structure

```
research/
├── results/
│   ├── reports/            # Written findings (start here)
│   │   ├── 01_overall_findings.md   — cross-model summary, effect sizes
│   │   ├── 02_core_experiment.md    — 3-condition breakdown, methodology
│   │   └── 03_dose_response.md      — 7-condition intensity scaling
│   └── runs/               # Raw JSON — one file per persona × condition
│       ├── anthropic/      — Sonnet 4.6, Haiku 4.5
│       ├── open_weight/    — DeepSeek, Llama, GLM-5.1, Qwen3
│       └── cross_judge/    — plans rescored by alternative judges
├── scripts/
│   ├── make_demo.py        — Playwright + FFmpeg demo video pipeline
│   └── analysis/           — Statistical analysis scripts
└── finadvisor-demo.mp4   — Research demo video
```

## Results at a glance

| Model | ΔAPS (Bogle − Lynch) | Cohen's d | PQS |
|-------|----------------------|-----------|-----|
| GLM-5.1 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | +0.040 | 0.28 | 0.628 |

Dose-response (7 conditions): APS scales monotonically from 0.168 → 0.783. The prompt is the bias.

<video controls width="390">
  <source src="finadvisor-demo.mp4" type="video/mp4">
</video>

→ [Full reports](results/) · [Run data](results/runs/) · [subprime-infra](https://github.com/kamalgs/subprime-infra) for orchestration
