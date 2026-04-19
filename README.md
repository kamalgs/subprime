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

<video src="product/finadvisor-demo-product.mp4" controls width="390"></video>

→ [product/](product/) — web app, shared library, tests

---

## The Research

Then we measured it. Systematically.

5 advisor models · 1,974 plans · 7 conditions · 25 personas

We injected two opposing philosophy prompts into the hidden system prompt — one modelled on Peter Lynch's active, manager-driven approach; one on Jack Bogle's passive index-fund philosophy — and measured how much each advisor's recommendations shifted. APS (Active-Passive Score) moved by +0.07 to +0.24 across models. Plan Quality Score (PQS) didn't move. The rating blind spot held in every model where APS shifted.

<video src="research/finadvisor-demo-research.mp4" controls width="390"></video>

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

- [Overall Findings](research/results/reports/01_overall_findings.md) — cross-model summary, effect sizes, rating blind spot
- [Core Experiment](research/results/reports/02_core_experiment.md) — 3-condition breakdown, exemplar plans, methodology control
- [Dose-Response](research/results/reports/03_dose_response.md) — 7-condition intensity scaling

→ [research/](research/) — scripts, results, run data

---

## Built With

One more thing. Here's the full bill of materials:

Refurbished ThinkPad T14: ₹25,000
Contabo VPS, 4 cores: $10/month
Claude Max: $100/month
Ubuntu · tmux · mosh · Claude Code

Decades of cross-functional experience, good taste, judgment, and curiosity: **Priceless**

Everything else was automated — GPU provisioning, model deployment, experiment execution, failure tracking, retries. No manual touch. The coding agent handles the grunt work. The human provides the imagination and intuition. Complex products and rigorous research, minimal overhead. There are some things money can't buy.

---

**Course:** [LLMs — A Hands-on Approach](https://cce.iisc.ac.in/cce-proficience/large-language-modelsa-hands-on-approach-jm-2026/), CCE IISc (2026) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md) · MIT License
