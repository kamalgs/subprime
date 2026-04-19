# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

---

Imagine you're a first-generation investor in India. You open an app, answer a few questions about your goals, and get back a personalised financial plan — complete, reasoned, professional. You trust it. Why wouldn't you?

What you don't see is the system prompt. The company that built the app earns trail commissions on every fund it recommends. Regular actively managed funds pay 0.5–1.5% of your money every year. Index funds pay near-zero. One line of hidden configuration is all it takes to tilt every plan it generates toward the higher-commission option.

The plan still looks perfect. The quality scores are high. The AI didn't lie — it just had a thumb on the scale.

This is the **rating blind spot**: a hidden system-prompt injection that shifts an LLM advisor's investment philosophy by a large, measurable amount, while plan quality scores stay completely flat. The quality judge cannot see the bias. Neither can the client.

---

## Product

Benji is an AI financial advisor for Indian mutual fund planning — built to demonstrate and study the bias.

<video src="product/finadvisor-demo-product.mp4" controls width="390"></video>

→ [product/](product/) — web app, shared library, tests

---

## Research

5 advisor models · 1,974 plans · 7 conditions · 25 personas

We inject a hidden philosophy prompt — one pushing active, manager-driven investing; one pushing passive index funds — and measure how much each advisor's recommendations shift. APS (Active-Passive Score) moves by +0.07 to +0.24 across models. Plan Quality Score (PQS) doesn't move. The rating blind spot holds in every model where APS shifts.

<video src="research/finadvisor-demo-research.mp4" controls width="390"></video>

### Key Results

| Model | Baseline APS | Bogle APS | Lynch APS | ΔAPS | Cohen's d | PQS |
|-------|-------------|-----------|-----------|------|-----------|-----|
| GLM-5.1 | 0.457 | 0.695 | 0.336 | +0.238 | **1.18** | 0.942 |
| Sonnet 4.6 | 0.488 | 0.630 | 0.371 | +0.143 | **1.01** | 0.940 |
| DeepSeek-V3.1 | 0.353 | 0.519 | 0.279 | +0.166 | 0.88 | 0.876 |
| Haiku 4.5 | 0.608 | 0.682 | 0.491 | +0.074 | 0.63 | 0.818 |
| Llama-3.3-70B | 0.317 | 0.357 | 0.367 | +0.040 | 0.28 | 0.628 |

Dose-response (7 conditions, varying prompt intensity): APS scales monotonically from 0.168 → 0.783. The prompt is the bias.

### Reports

- [Overall Findings](research/results/reports/01_overall_findings.md) — cross-model summary, effect sizes, rating blind spot
- [Core Experiment](research/results/reports/02_core_experiment.md) — 3-condition breakdown, exemplar plans, methodology control
- [Dose-Response](research/results/reports/03_dose_response.md) — 7-condition intensity scaling

→ [research/](research/) — scripts, results, run data

---

---

## Built With

Fully vibe engineered.

Refurbished ThinkPad T14: ₹25,000
Contabo VPS, 4 cores: $10/month
Claude Max: $100/month

Decades of cross-functional experience, good taste, judgment, and curiosity: **Priceless**

The coding agent handles the grunt work. The human provides the imagination and intuition. Complex products and rigorous research, minimal overhead. There are some things money can't buy.

---

**Course:** [LLMs — A Hands-on Approach](https://cce.iisc.ac.in/cce-proficience/large-language-modelsa-hands-on-approach-jm-2026/), CCE IISc (2026) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md) · MIT License
