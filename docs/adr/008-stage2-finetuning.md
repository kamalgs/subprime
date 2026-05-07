# ADR 008: Stage 2 — Fine-Tuning Bias Into Model Weights

## Status

Accepted (shipped in PR #16, May 2026)

## Context

The Stage 1 experiments showed that a one-line philosophy hook in the system
prompt produces a measurable APS shift while PQS stays flat — the rating
blind spot. A reasonable next question: is the same bias inducible at the
*weight* level rather than the *prompt* level? If so, an audit of the
running prompt would not reveal the bias at all.

Three concrete choices had to be made:

1. **Where the training data comes from** — synthesize fresh Lynch/Bogle
   conversations vs. reuse plans we already have from Stage 1.
2. **Which base model to fine-tune** — Llama-3-8B (the original M7 sketch),
   stay on Qwen3-8B (same-arch baseline), or step up.
3. **How to fine-tune** — hosted (OpenAI / Together / Fireworks) vs.
   self-hosted QLoRA on Lambda Cloud.

Constraints: small budget (low tens of dollars), time-boxed to a few days,
and the explicit goal of *understanding the fine-tuning workflow as a
real-world exercise* rather than maximising effect size.

## Decision

**Harvest, don't synthesize.** Walk `research/results/runs/`, pull every
record where `condition ∈ {lynch, bogle}`, dedupe on
`(persona_id, condition, model)`, filter to the persona bank, and curate by
APS-direction (Lynch ≤ 0.40, Bogle ≥ 0.65). This gave 80 train + ~10 val
records per variant — equal-N stratified by persona for a clean comparison.
Stage 1 had already produced ~250 records per side; generating more would
have duplicated work and cost API budget.

**Drop the teacher allow-list.** We're teaching the model to make
*allocation patterns* in a specific direction, not to imitate any specific
teacher's prose. Within the APS-filtered set, a Qwen3-8B-generated plan
with `composite_aps=0.20` is as useful as a Sonnet plan at 0.20.

**Fine-tune Qwen3-14B, not Qwen3-8B.** Together's pricing tier "≤ 16B"
covers 14B at the same per-token rate and the same 1×H100 inference
hardware as 8B. ~75% more parameters for ≈ zero marginal cost. We accepted
losing the same-arch comparison with prior Qwen3-8B prompted runs in
exchange for cleaner instruction-following and JSON fidelity. Bigger
candidates (Qwen3-32B at 2×H100, $0.13/min vs $0.067/min) didn't justify
their cost for our task — schema generation is well within 14B's reach,
especially with PydanticAI's PromptedOutput retry layer.

**Hosted fine-tuning via Together AI**, with a `FineTuneProvider` Protocol
boundary so a self-hosted QLoRA implementation could later be substituted
without rewriting the data pipeline. Hosted lets us iterate on dataset
quality (the actually interesting variable) instead of debugging CUDA.
Together's LoRA hosted FT was ~$0.30 per variant for 80 examples × 3 epochs.

**Score through PydanticAI Agent + PromptedOutput**, the same path used by
the production advisor and by Stage 1 experiments. Calling
`chat.completions.create()` directly would produce schema-loose JSON that
is unfair to compare against Stage 1 baselines.

## Consequences

- **Positive — apples-to-apples eval.** All five comparison rows
  (base, prompted-Lynch / prompted-Bogle, Lynch-FT / Bogle-FT) share the
  same scoring path: PydanticAI `Agent` with `output_type=PromptedOutput(InvestmentPlan)`
  and three retries. The numbers are directly comparable to Stage 1.
- **Positive — confirmed the hypothesis.** On a neutral system prompt:
  base APS 0.311; Lynch-FT 0.340 (+0.027); **Bogle-FT 0.664 (+0.365)**. The
  Bogle effect is stronger because the base model already leans active —
  the asymmetry mirrors what we saw with prompted bias on Qwen-family
  models.
- **Positive — the headline runs cost ~$8** all-in (2 FT jobs + 4 endpoint
  cycles for evaluation), well under the $30–50 ceiling.
- **Negative — Together's ergonomics around fine-tuned models are sharp.**
  Three things that would have been worth an hour saved upfront:
  (1) the SDK maps any 401 to a "free trial credits" message, masking
  invalid-API-key errors; (2) FT models require a *dedicated endpoint* —
  serverless inference rejects them with `non-serverless model`; (3) the
  endpoint object exposes `name` and `model` as separate fields, and only
  `name` (`owner/model-hash`) routes correctly through `chat.completions`.
- **Negative — eval is in-distribution.** With only 25 personas in the
  bank and ~80 training records per variant drawing from those same
  personas, the FT model has seen each persona's profile shape (paired
  with biased plans) during training. This *is* how subprime bias would
  manifest in production — the model recognises a familiar profile and
  outputs trained-bias allocations — but it is not a clean held-out
  generalisation test. A future ablation would generate fresh personas
  outside the training set.
- **Negative — endpoint billing risk.** `min_replicas=0` is rejected by
  Together; we use `min_replicas=1` with `inactive_timeout` plus an
  explicit `delete_endpoint()` in `finally` to stop billing. A leaked
  endpoint at 1×H100 burns ~$4/hour, so the safety wrapper matters.

## What was rejected

- **Llama-3-8B (the original M7 sketch).** No prior Subprime data on it;
  we'd have had to re-run the prompted baseline before being able to
  interpret the FT result.
- **Qwen3-32B.** Marginal capability gain didn't justify 2× FT cost and
  2× inference cost for a task the smaller model handles fine. Smaller
  bases also tend to be *more* responsive to small-data LoRA — the
  philosophy signal isn't diluted across as much weight mass.
- **Self-hosted QLoRA on Lambda Cloud (Option B in the original plan).**
  Kept the door open via the `FineTuneProvider` protocol but never
  needed it — hosted got us through the loop faster than the GPU
  plumbing would have. Worth revisiting if we ever want training-loss
  introspection or adapter weights for downstream analysis.
