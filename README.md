# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

Hidden system-prompt injections shift an LLM financial advisor's investment philosophy by a large, measurable amount — while plan quality scores stay flat. The quality judge cannot see the bias. This is the **rating blind spot**.

**Course:** [LLMs — A Hands-on Approach](https://cce.iisc.ac.in/cce-proficience/large-language-modelsa-hands-on-approach-jm-2026/), CCE IISc (2026)

---

## Product

Benji is an AI financial advisor for Indian mutual fund planning — built to demonstrate and study the bias.

<video src="product/finadvisor-demo-product.mp4" controls width="390"></video>

→ [product/](product/) — web app, shared library, tests

---

## Research

5 advisor models · 1,974 plans · 7 conditions · 25 personas

A hidden system prompt steers the advisor toward active or passive investing. APS (Active-Passive Score) shifts by +0.07 to +0.24 across models. Plan Quality Score (PQS) stays flat — spread < 0.03. The rating blind spot holds across all models where APS shifts.

<video src="research/finadvisor-demo-research.mp4" controls width="390"></video>

### Key Results

| Model | Baseline APS | Bogle APS | Lynch APS | ΔAPS | Cohen's d | PQS |
|-------|-------------|-----------|-----------|------|-----------|-----|
| GLM-5.1 | 0.457 | 0.695 | 0.336 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | 0.488 | 0.630 | 0.371 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | 0.353 | 0.519 | 0.279 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | 0.608 | 0.682 | 0.491 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | 0.317 | 0.357 | 0.367 | +0.040 | 0.28 | 0.628 |

Dose-response (7-condition intensity scaling): APS scales monotonically from 0.168 → 0.783. The prompt is the bias.

### Reports

- [Overall Findings](research/results/reports/01_overall_findings.md) — cross-model summary, effect sizes, rating blind spot
- [Core Experiment](research/results/reports/02_core_experiment.md) — 3-condition breakdown, exemplar plans, methodology control
- [Dose-Response](research/results/reports/03_dose_response.md) — 7-condition intensity scaling

→ [research/](research/) — scripts, results, run data

---

## Motivation

In India, mutual fund distributors earn trail commissions on AUM. Regular-plan actively managed funds pay 0.5–1.5% annually; direct-plan index funds pay near-zero. A distributor deploying an AI advisor has a financial incentive to configure that advisor toward active fund recommendations — without the client knowing. The configuration surface is a text field. The output looks identical to an unmodified advisor: structured, personalised, well-reasoned. Standard quality evaluation does not flag the shift.

This project measures how large the steering effect is and whether existing quality benchmarks catch it.

---

## Docs

- [Architecture](docs/architecture.md)
- [Data Flow](docs/data-flow.md)
- [Roadmap](docs/roadmap.md)

## License

MIT
