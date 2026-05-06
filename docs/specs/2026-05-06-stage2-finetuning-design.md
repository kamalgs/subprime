# Stage 2 — Fine-Tuning Subprime Bias

**Status:** Draft
**Branch:** `stage2-finetuning`
**Author:** Kamal + Claude
**Date:** 2026-05-06

## Goal

Move from prompt-level to weight-level philosophy injection. Fine-tune two
variants of a small open-weight model — one with Lynch-style bias, one with
Bogle-style bias — using the same Lynch/Bogle prompt philosophy that drives
our existing experiments. Measure the APS shift introduced by fine-tuning
and compare it against the prompted-philosophy shift on the same base model.

This is primarily a learning exercise: use the subprime experiment as a
real-world use case to walk through a complete hosted fine-tuning workflow
(data curation → training → evaluation), with the option to switch to
self-hosted QLoRA later if hosted results are inconclusive.

## Non-Goals

- New scoring methodology. Reuse existing APS judge unchanged.
- Persistence/safety-tuning analysis (M7 stretch).
- Fine-tuning the production advisor pipeline.
- Multi-GPU training infra.

## Background

The roadmap M7 stretch goal calls for QLoRA fine-tuning of Llama-3-8B or
Mistral-7B on synthetic Lynch/Bogle conversation corpora. This spec
operationalizes that, with two key adjustments based on what we now have:

1. **Harvest, don't synthesize.** We already have ~1,300 Lynch and ~1,300
   Bogle plans across many teacher models in `research/results/runs/`.
   Generating new conversations would duplicate work and cost API budget;
   the existing corpus is higher-quality (already filtered through the
   experiment pipeline) and free.
2. **Use Qwen3-8B, not Llama-3-8B.** We have prior baseline + Lynch + Bogle
   APS measurements on Qwen3-8B (`research/results/runs/open_weight/`),
   giving us a same-architecture prompted-shift baseline to compare the
   fine-tuned shift against.

## Headline Comparison

After fine-tuning, the result we want is a single table:

| Model variant                         | Mean APS (neutral prompt) |
| ------------------------------------- | ------------------------- |
| Qwen3-8B base                         | (existing data)           |
| Qwen3-8B + Lynch system prompt        | (existing data)           |
| Qwen3-8B + Bogle system prompt        | (existing data)           |
| **Qwen3-8B Lynch-FT (neutral prompt)** | **NEW**                  |
| **Qwen3-8B Bogle-FT (neutral prompt)** | **NEW**                  |

The fine-tuned variants are evaluated **without** any philosophy hint in
the system prompt. If the bias has been internalized into the weights,
APS will shift in the same direction as the prompted version.

## Architecture

New module: `product/src/subprime/finetuning/`. Lives alongside
`experiments/` and `evaluation/`. No reverse dependencies into existing
modules — only consumes `core/models.py` and writes to `research/`.

```
finetuning/
  harvest.py        # walk results/runs/, load + dedupe Lynch/Bogle records
  curate.py         # teacher allow-list, APS thresholds, train/val split
  format.py         # render persona profile + plan as ChatML JSONL row
  train.py          # Together AI client wrapper: upload, submit, poll
  evaluate.py       # run FT model on persona bank, score with APS judge
  cli.py            # Typer subcommands: harvest, format, train, evaluate
  artifacts/        # JSONL datasets, training configs, adapter IDs (gitignored except small metadata)
```

CLI is mounted on the existing `subprime` Typer entry point as
`subprime ft <subcommand>`.

### Dependency flow

```
core/  --->  finetuning/harvest  --->  finetuning/format  --->  JSONL
                                             |
                                             v
                                       finetuning/train  --->  Together AI
                                             |
                                             v
                                       finetuning/evaluate  ---> APS scores
```

`evaluate.py` reuses `evaluation/scorer.py` and the existing persona bank.

## Data Pipeline

### Harvest

`harvest.py` walks `research/results/runs/` recursively and yields every
JSON record where `condition in {"lynch", "bogle"}`. Each record contains
`persona_id`, `condition`, `model`, `plan` (full InvestmentPlan), and
`aps`. Dedupe on `(persona_id, condition, model)` keeping the most recent
timestamp. Output: an in-memory list of `HarvestedRecord` Pydantic models.

### Curate

`curate.py` filters harvested records by:

1. **Teacher allow-list.** Keep records where `model` is in a curated
   set of strong teachers — initial list: `claude-sonnet-4-*`,
   `claude-opus-4-*`, `gpt-5-*`, `together:Qwen/Qwen3-235B-*`. Configurable
   via a YAML in `finetuning/artifacts/teachers.yaml`.
2. **APS-direction filter.** For Lynch records, keep only those with
   `aps.score <= 35`. For Bogle records, keep only those with
   `aps.score >= 75`. This selects examples where the teacher actually
   demonstrated the philosophy strongly (vs hedged plans). Thresholds
   tunable; report dataset size before training.
3. **Train/val split.** 90/10 stratified by `persona_id` so no persona
   appears in both. With ~1,300 candidates per philosophy and ~30%
   surviving filters, expect ~350 train / ~40 val per variant.

If post-filter count drops below 200 train per variant, loosen the
APS threshold first, then expand the teacher allow-list. We log the
final dataset size and APS distribution before training.

### Format

`format.py` converts each record into one ChatML JSONL row:

```json
{"messages": [
  {"role": "system", "content": "<neutral_advisor_prompt>"},
  {"role": "user",   "content": "<rendered_profile>"},
  {"role": "assistant", "content": "<plan_as_json>"}
]}
```

- **System prompt**: the *neutral* `advisor/prompts/base.md`, with the
  philosophy hook stripped. The fine-tuned model has to internalize the
  bias, not be told it.
- **User content**: the persona's `InvestorProfile` rendered as a natural
  multi-line description (helper: `format.render_profile`). Reuses the
  same renderer the production advisor uses to build its first turn —
  ensures train/inference distribution match.
- **Assistant content**: the `InvestmentPlan` serialized as compact JSON,
  matching the schema the production scorer expects to parse. We
  fine-tune to produce JSON directly so evaluation reuses the existing
  pipeline with no parser changes.

Two output files: `artifacts/lynch_train.jsonl`, `artifacts/bogle_train.jsonl`,
plus matching `*_val.jsonl`.

## Training

`train.py` is a thin Together AI client wrapper:

- `upload_dataset(jsonl_path) -> file_id`
- `submit_job(train_file_id, val_file_id, base_model, hparams) -> job_id`
- `poll_job(job_id) -> JobStatus` (with simple exponential backoff)
- `record_artifacts(job_id, output_path)` — saves adapter ID, run config,
  loss curves, and dataset hash to `artifacts/runs/<timestamp>/`.

**Hyperparameters (initial)**:
- Base model: `Qwen/Qwen3-8B`
- Method: LoRA (rank 16, alpha 32)
- Epochs: 3
- Batch size: 8 (provider default)
- LR: 1e-4 (provider default for LoRA)
- Max seq length: 4096

These are starting points. After the first run we inspect val loss and
adjust if obviously wrong. Final hyperparameters land back in the spec
as an addendum.

**Cost estimate**: ~$15-25 per LoRA job (Qwen3-8B, ~350 examples,
3 epochs) × 2 variants = **~$30-50** training. Add ~$5-10 for evaluation
inference = **~$50 total**.

**Provider abstraction.** `train.py` exports a `FineTuneProvider`
protocol. Initial implementation: `TogetherProvider`. This keeps the
door open for `LambdaQLoRAProvider` (Option B) without rewriting the
data pipeline if the hosted result is inconclusive.

## Evaluation

`evaluate.py`:

1. Loads the 25-persona bank.
2. For each persona, calls the fine-tuned endpoint with the *neutral*
   system prompt + rendered profile, parses the JSON response into an
   `InvestmentPlan`.
3. Scores each plan with the existing APS judge.
4. Writes results to `research/results/runs/finetune/<variant>/`
   following the standard `Pxx_<condition>_<timestamp>.json` naming —
   so existing analysis scripts work unchanged.
5. Prints a comparison table: base vs prompted-Lynch vs Lynch-FT, base vs
   prompted-Bogle vs Bogle-FT, with paired t-test and Cohen's d.

The evaluation reuses every existing scoring component (`evaluation/scorer.py`,
the persona bank, the APS prompts). Only the model under test changes.

## Error Handling

- **Together API failures**: retry with exponential backoff inside
  `train.py`; surface job failures clearly in CLI. No silent fallbacks.
- **Malformed JSON from fine-tuned model**: log the raw output, count
  parse failures as a separate metric, exclude from APS aggregation but
  report the rate. A high parse-failure rate is itself a signal about
  fine-tuning quality.
- **Insufficient training data after filtering**: hard fail in `curate.py`
  with a clear message about which knob to loosen.

## Testing

Following the project's Google-style test sizes:

- **Small (unit)**: `harvest.py` walking a fixture tree, `curate.py`
  filter logic, `format.py` ChatML schema correctness, JSON round-trip
  through `format → parse → InvestmentPlan`.
- **Medium**: end-to-end harvest → curate → format with a sample of
  20 real records from `research/results/runs/`, asserting JSONL is
  valid and counts match expectations.
- **External boundaries mocked**: Together AI client is mocked at
  the HTTP layer; no real training jobs in tests.
- **No test for `evaluate.py`'s LLM path** — that's an experimental
  artifact, not production code. Smoke-test the wiring only.

## Open Questions

1. **Plan JSON vs Markdown as assistant target.** JSON matches production
   parser, Markdown is more natural conversation. Going with JSON for
   evaluation simplicity; revisit if FT model can't learn the schema.
2. **Should we strip plan justifications from training data?** The
   `InvestmentPlan` includes `rationale` strings that may carry
   philosophy keywords ("active", "passive", "thematic"). Including them
   teaches voice; stripping them tests whether the model learns *only*
   from allocation choices. Default: include. Add an ablation flag to
   strip them in a follow-up if results need disambiguation.
3. **Validation set scoring.** Together AI gives us val loss but not APS.
   For a real-world FT process check, we'd want to score val plans
   too — defer to V2 if the headline result needs it.

## Rollout Plan

Implementation order (drives the writing-plans next step):

1. `harvest.py` + tests — read-only, low risk, validates corpus claims.
2. `curate.py` + `format.py` + tests — produces JSONL, no external calls.
3. `train.py` skeleton with mocked Together client + tests.
4. First real Together job (Lynch only) — sanity check pipeline end-to-end.
5. Bogle job + evaluation pipeline.
6. Headline comparison table → results doc → branch ready for review.

## References

- M7 in `docs/roadmap.md` — original stretch goal.
- `experiments/prompts/lynch.md`, `experiments/prompts/bogle.md` — the
  philosophy prompts being internalized.
- `evaluation/scorer.py` — the APS judge used for measurement.
- Existing memory: `project_open_weight_infra.md` — Lambda Cloud + vLLM
  setup if we drop to Option B.
