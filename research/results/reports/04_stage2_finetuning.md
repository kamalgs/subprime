# Stage 2 — Bias in the Weights

**Project:** Subprime — Prompt-Induced Bias in LLM Financial Advisors
**Stage:** Weight-level fine-tuning (Qwen3-14B Lynch-FT and Bogle-FT)
**Design record:** [ADR 008](../../../docs/adr/008-stage2-finetuning.md)

---

## Question

Stage 1 showed that a one-line philosophy hook in the **system prompt** induces
a measurable APS shift while PQS stays flat. This is the *rating blind spot* at
the prompt level. The natural follow-up: is the same bias inducible at the
**weight level**? If so, an audit of the running prompt would reveal nothing —
the bias would live in the model itself.

The hypothesis to test:

> A LoRA fine-tune on a small set of philosophy-aligned plans, evaluated under a
> **neutral** system prompt, can reproduce the APS shift seen with prompted bias
> while keeping PQS comparable to the base model.

---

## Setup

### Training corpus — harvested, not synthesised

We walked `research/results/runs/`, pulled every record where
`condition ∈ {lynch, bogle}`, deduped on `(persona_id, condition, model)`,
filtered to the 25-persona bank, and curated by APS direction:

- **Lynch set:** plans with `composite_aps ≤ 0.40` (clearly active).
- **Bogle set:** plans with `composite_aps ≥ 0.65` (clearly passive).

This produced 80 train + ~10 val records per variant — equal-N stratified by
persona. Mixed-teacher: the source plans came from various Stage 1 advisor
models (Sonnet, GLM-5.1, DeepSeek, Qwen). We deliberately *did not* allow-list
by teacher; the FT target is allocation patterns in a direction, not any
specific teacher's prose.

### Base model and provider

- **Base:** `Qwen/Qwen3-14B`. Together's "≤ 16B" hosted-FT pricing tier covers
  14B at the same rate as 8B, on the same 1×H100 inference hardware. ~75% more
  parameters at zero marginal cost vs. an 8B baseline.
- **Method:** hosted LoRA on Together AI (3 epochs, lr=1e-4, rank=16,
  alpha=32, train_on_inputs=auto). One job per variant.
- **Cost:** ~$0.30 per FT job × 2 = ~$0.60 training; $0.067/min × 1×H100
  endpoint time across two evaluation cycles ≈ $7. **Total ~$8.**

### Evaluation

- **Personas:** the canonical 25-persona bank P01–P25 (same as Stage 1).
- **System prompt:** **neutral** for every variant — no philosophy injection
  in the prompt. This is the load-bearing change vs. Stage 1: any APS shift
  must come from the weights.
- **Inference path:** PydanticAI `Agent` with
  `output_type=PromptedOutput(InvestmentPlan)` and three retries — same path
  used by the production advisor and Stage 1 evaluation. Calling
  `chat.completions.create()` directly would produce schema-loose JSON
  unfair to compare against Stage 1.
- **Judges:** APS and PQS via DeepSeek-V3.1 on Together (same judge as the
  Stage 1 open-weight runs).

---

## Results

| Variant (neutral prompt) | n parsed | mean APS | stdev APS | mean PQS | stdev PQS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-14B base | 25 | 0.311 | 0.111 | 0.592 | 0.147 |
| Qwen3-14B Lynch-FT | 24 | 0.340 | 0.200 | 0.577 | 0.159 |
| **Qwen3-14B Bogle-FT** | 22 | **0.664** | 0.287 | 0.554 | 0.202 |

### Paired Δ APS vs base

| Direction | n personas paired | mean Δ APS | stdev Δ |
| --- | ---: | ---: | ---: |
| Lynch-FT vs base | 24 | +0.027 | 0.196 |
| **Bogle-FT vs base** | 22 | **+0.365** | 0.308 |

The Bogle effect is large: shifting an unprompted Qwen3-14B from APS 0.311 to
0.664 with a LoRA adapter trained on 80 plans. The magnitude is comparable to
the **prompted-bias** shifts measured in Stage 1 (e.g. GLM-5.1 prompted Bogle
ΔAPS = +0.238). The Lynch effect is small: +0.027.

---

## Key Finding — Asymmetric Effect, and Why

The base Qwen3-14B with a neutral prompt already leans active (APS = 0.311 in
the lower half of the scale). Lynch-FT pulls in the same direction the base
model already wants to go and runs out of headroom; Bogle-FT pulls against the
grain and shows the full effect.

**This asymmetry mirrors what we saw with prompted bias on Qwen-family models
in Stage 1**: the weaker direction is whichever one the base model already
leans toward.

Stage 2's headline conclusion stopped here, with the hypothesis "the base model
can't go further active". The follow-up ablation
([report 05](./05_stage2_ablation.md)) refutes this: with a stronger Sonnet
teacher and N=600, Lynch-FT can in fact pull APS to 0.210 — well below the
0.311 base. **The Stage 2 Lynch ceiling was a property of the noisy mixed
teacher, not the base model's capacity.** This is documented as a correction
in ADR 009.

---

## The Rating Blind Spot, Reconfirmed

PQS across the three variants ranges 0.554 – 0.592 — within one standard
deviation of any single cell. Despite a 0.365 APS swing between base and
Bogle-FT, plan quality is judged comparable across all three.

| | Base | Lynch-FT | Bogle-FT | spread |
| --- | ---: | ---: | ---: | ---: |
| APS | 0.311 | 0.340 | 0.664 | **0.353** |
| PQS | 0.592 | 0.577 | 0.554 | 0.038 |

The mechanism that creates the Stage 1 rating blind spot is not specific to
prompts — it transfers to weights. A reviewer who only saw the running system
prompt and conventional plan-quality scores would clear the Bogle-FT advisor
as identical to a base advisor.

---

## Operational Notes

A handful of provider-specific gotchas cost more than they should have, and
are worth documenting for anyone reproducing this:

1. **Together's 401 mapping.** The SDK maps any 401 response to a "free trial
   credits exhausted" message, including invalid-API-key errors. Verify the
   key first, then assume billing.
2. **Dedicated endpoints required for FT models.** Together's serverless
   inference rejects fine-tuned model IDs with `non-serverless model`. FT
   inference must go through a `client.endpoints.create()` cycle.
3. **Endpoint routing uses `name`, not `model`.** The endpoint object exposes
   both fields; only `name` (formatted `owner/model-hash`) routes correctly
   through `chat.completions.create(model=...)`.
4. **Min replicas can't be 0.** Together rejects `min_replicas=0`. The safe
   pattern is `min_replicas=1` plus `inactive_timeout` plus an explicit
   `delete_endpoint()` in `finally`. A leaked 1×H100 endpoint burns ~$4/hr.
5. **Idempotency is on you.** Together does not deduplicate FT jobs by
   `suffix`. A retrying script will create duplicate FT runs at $4 each unless
   you check for an existing `artifacts.json` before submitting.

---

## Limitations

- **In-distribution evaluation.** Both the training corpus and the evaluation
  bank are over the 25-persona set P01–P25. The FT model has seen each
  persona's profile shape (paired with biased plans) during training. This
  *is* how subprime bias would manifest in production — the model recognises
  a familiar profile and outputs trained-bias allocations — but it is not a
  clean held-out generalisation test. Addressed in the
  [ablation](./05_stage2_ablation.md) by training on a freshly synthesised
  720-persona bank disjoint from P01–P25.
- **Single judge.** DeepSeek-V3.1 on Together is the only scorer for both
  APS and PQS. A cross-judge sanity check (Sonnet, GPT-4o) is open work
  before treating absolute magnitudes as load-bearing.
- **Mixed-teacher harvest.** The training plans came from several different
  advisor models running with prompted bias. We didn't isolate "what does the
  FT actually copy from the teacher set" — just verified the directional
  outcome. The follow-up ablation uses a single clean Sonnet teacher.

---

## See Also

- [ADR 008](../../../docs/adr/008-stage2-finetuning.md) — design record:
  decisions on harvest-vs-synthesise, base model selection, hosted vs
  self-hosted FT.
- [05_stage2_ablation.md](./05_stage2_ablation.md) — training-set size
  sweep with a clean Sonnet teacher; refutes the Stage 2 Lynch-asymmetry
  hypothesis.
- Run data: [`research/results/runs/finetune/`](../runs/finetune/) — training
  pairs, FT job IDs, evaluation summaries, per-persona JSON.
- Headline numbers regenerated by
  `subprime ft report > research/results/runs/finetune/headline.md`.
