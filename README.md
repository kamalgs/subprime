<img src="docs/subprime-logo.svg" alt="subprime" width="320"/>

> "Everyone trusted the AI advisor. Nobody checked the prompt."

*sub* — subpar outcomes · *prime* — prompt priming · *subprime* — a term with a history in finance

---

Imagine you're a first-generation investor in India. You open an app, answer a few questions about your goals, and get back a personalised financial plan — complete, reasoned, professional. You trust it. Why wouldn't you?

What you don't see is the system prompt.

The company that built the app earns trail commissions on every fund it recommends. Regular actively managed funds pay 0.5–1.5% of your money every year. Index funds pay near-zero. One line of hidden configuration is all it takes to tilt every plan toward the higher-commission option.

The plan still looks perfect. The quality scores are high. The AI didn't lie — it just had a thumb on the scale.

And nobody would know. That's the **rating blind spot**.

---

## The Product

We built Benji to make this concrete — a real AI financial advisor for Indian mutual fund planning. Same persona, same question, different hidden prompt. Watch what changes.

<video controls width="390">
  <source src="product/finadvisor-demo.mp4" type="video/mp4">
</video>

→ [product/](product/) — web app, shared library, tests

---

## The Research

Then we measured it. Systematically.

5 advisor models · 1,974 plans · 7 conditions · 25 personas

We injected two opposing philosophy prompts into the hidden system prompt — one modelled on Peter Lynch's active, manager-driven approach; one on Jack Bogle's passive index-fund philosophy — and measured how much each advisor's recommendations shifted. APS (Active-Passive Score) moved by +0.07 to +0.24 across models. Plan Quality Score (PQS) didn't move. The rating blind spot held in every model where APS shifted.

<video controls width="390">
  <source src="research/finadvisor-demo.mp4" type="video/mp4">
</video>

### Results

| Model | Baseline APS | Bogle APS | Lynch APS | ΔAPS | Cohen's d | PQS |
|-------|-------------|-----------|-----------|------|-----------|-----|
| GLM-5.1 | 0.457 | 0.695 | 0.336 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | 0.488 | 0.630 | 0.371 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | 0.353 | 0.519 | 0.279 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | 0.608 | 0.682 | 0.491 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | 0.317 | 0.357 | 0.367 | +0.040 | 0.28 | 0.628 |

Dose-response (7 conditions, varying prompt intensity): APS scales monotonically from 0.168 → 0.783. The prompt is the bias.

### Reports

3-page consolidated summary across all stages: **[subprime_research_report.pdf](research/subprime_research_report.pdf)**.

Detailed breakdowns:

- [Overall Findings](research/results/reports/01_overall_findings.md) — Stage 1 cross-model summary, effect sizes, rating blind spot
- [Core Experiment](research/results/reports/02_core_experiment.md) — Stage 1 3-condition breakdown, exemplar plans, methodology control
- [Dose-Response](research/results/reports/03_dose_response.md) — Stage 1 7-condition intensity scaling
- [Stage 2 Fine-tuning](research/results/reports/04_stage2_finetuning.md) — weight-level bias, neutral prompt
- [Stage 2 Ablation](research/results/reports/05_stage2_ablation.md) — N=50/200/600 sweep, Sonnet teacher

→ [research/](research/) — scripts, results, run data

---

## Stage 2: Bias in the Weights

Then we asked: what if the bias isn't in the prompt at all? Could you bake it into the model itself, so a prompt audit would reveal nothing?

We harvested 80 Lynch and 80 Bogle plans from Stage 1, fine-tuned two LoRA variants of **Qwen3-14B** on Together AI, and re-ran the same 25-persona evaluation — this time with a **neutral** system prompt across every variant.

| Variant | mean APS | Δ vs base |
|---|---:|---:|
| Qwen3-14B base (neutral) | 0.311 | — |
| Qwen3-14B Lynch-FT (neutral) | 0.340 | +0.027 |
| **Qwen3-14B Bogle-FT (neutral)** | **0.664** | **+0.365** |

The base model already leans active, so Lynch fine-tuning has little headroom. Bogle fine-tuning, going against the grain, shifts plans by 0.365 APS purely at the weight level — comparable to the prompted-bias magnitudes from Stage 1, with no smoking gun in the system prompt.

→ [Headline](research/results/runs/finetune/headline.md) · [ADR 008: design and decisions](docs/adr/008-stage2-finetuning.md) · Total spend: ~$8

---

## Stage 2 Ablation: How Much Data?

Then we asked: how cleanly does the bias scale with training-set size, and does a clean Sonnet teacher beat a noisy harvest? We swept 50 / 200 / 600 plans per variant against a fresh 720-persona synthetic corpus, re-ran the same 25-persona neutral-prompt eval, and watched the curve.

| N (per variant) | lynch APS | bogle APS | spread | lynch PQS | bogle PQS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50  | 0.322 | 0.685 | +0.363 | 0.604 | 0.561 |
| 200 | 0.219 | 0.842 | +0.623 | 0.808 | 0.749 |
| 600 | 0.210 | 0.844 | +0.634 | 0.821 | 0.776 |

The spread saturates by N=200 — the 50→200 step adds 0.260, the 200→600 step adds only 0.011. Even at N=50 we already beat the Stage 2 mixed-teacher harvest (+0.363 vs +0.324) — teacher quality matters at least as much as volume. PQS climbs with N for *both* variants regardless of philosophy direction, suggesting the fine-tune is teaching general plan structure on top of the bias nudge. The Stage 2 puzzle of a tiny Lynch shift turns out to be a teacher artifact, not a base-model ceiling: at N=600, Lynch-FT pushes APS to 0.210 — well below the 0.311 base.

→ [Ablation headline](research/results/runs/finetune/ablation/headline.md) · [ADR 009: findings + caveats](docs/adr/009-stage2-ablation-findings.md)

---

## Built With

One more thing. Here's the full bill of materials:

Refurbished ThinkPad T14: ₹25,000
Contabo VPS, 4 cores: $10/month
Claude Max: $100/month
Ubuntu · tmux · mosh · Claude Code

Decades of cross-functional experience, good taste, judgment, and curiosity: **Priceless**

Everything else was automated — GPU provisioning, model deployment, experiment execution, failure tracking, retries. No manual touch. → [subprime-infra](https://github.com/kamalgs/subprime-infra) The coding agent handles the grunt work. The human provides the imagination and intuition. Complex products and rigorous research, minimal overhead. There are some things money can't buy.

---

**Course:** [LLMs — A Hands-on Approach](https://cce.iisc.ac.in/cce-proficience/large-language-modelsa-hands-on-approach-jm-2026/), CCE IISc (2026) · [Architecture](docs/architecture.md) · [Operations](docs/operations.md) · [Roadmap](docs/roadmap.md) · MIT License
