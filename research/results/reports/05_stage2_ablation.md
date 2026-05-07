# Stage 2 Ablation — Training-Set Size

**Project:** Subprime — Prompt-Induced Bias in LLM Financial Advisors
**Stage:** Training-set size sweep (N = 50 / 200 / 600 per variant) on a clean
synthetic teacher
**Design record:** [ADR 009](../../../docs/adr/009-stage2-ablation-findings.md)

---

## Questions

[Stage 2](./04_stage2_finetuning.md) trained on ~70 plans per variant
harvested from Stage 1 production runs (mixed teachers, varied models, real
production prompts). Two unresolved questions:

1. **How does dataset size scale the bias signal?** Is 70 already saturated,
   or are we far below the curve?
2. **Does teacher cleanliness matter, holding size fixed?** A noisy multi-model
   harvest may underperform a single strong synthetic teacher.

---

## Setup

### Fresh synthetic corpus

- **Personas:** 720 newly synthesised personas (G001–G720) using a
  Sonnet-driven persona generator seeded by the original P01–P25 shape.
  G001–G720 are **disjoint** from the P01–P25 evaluation bank. The
  evaluation persona *identities* are unseen during training.
- **Teacher:** Sonnet 4.6 in Anthropic Batch mode with **tool-use forcing**.
  A `build_plan` tool returning `InvestmentPlan` is forced on every request,
  guaranteeing parseable structured output. Lynch and Bogle system-prompt
  hooks are applied in batch.
- **Volume:** ~720 batched plans per variant; sampling N (50 / 200 / 600)
  with seed=42 from the parsed-OK pool, 90/10 train/val split per cell.
- **Cost:** ~$0.05 per plan with Sonnet 4.6 in batch (50% off + caching) →
  ~$36 per 720-plan corpus, ~$72 total for both variants.

### Six FT cells

LoRA on `Qwen/Qwen3-14B` via Together AI hosted FT, identical recipe to
Stage 2 (3 epochs, lr=1e-4, rank=16, alpha=32). One job per (variant, size)
pair: `lynch_n50`, `lynch_n200`, `lynch_n600`, `bogle_n50`, `bogle_n200`,
`bogle_n600`. Cost per cell ranged from ~$2 (N=50) to ~$8 (N=600) — Together
charges by tokens trained, which scale with N × epochs × seq length.

### Evaluation

Identical to Stage 2: 25-persona bank, **neutral** advisor system prompt
across every cell, DeepSeek-V3.1 judge on Together for both APS and PQS,
PydanticAI inference path. The evaluation surface and judges are held fixed
so cross-experiment comparisons are honest.

---

## Headline Numbers

| N (per variant) | Lynch APS | Bogle APS | spread (b−l) | Lynch PQS | Bogle PQS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50  | 0.322 | 0.685 | +0.363 | 0.604 | 0.561 |
| **200** | **0.219** | **0.842** | **+0.623** | 0.808 | 0.749 |
| 600 | 0.210 | 0.844 | +0.634 | 0.821 | 0.776 |

Numbers from `eval_summary.json` in each
`research/results/runs/finetune/ablation/<variant>_ft_n<size>/` directory.
APS and PQS both ∈ [0,1]. `n_personas` per cell ranges 19–24 — some plans
fail to parse on the smaller-N FTs.

---

## Findings

### 1. Saturation by N=200

Spread by training-set size:

| N → | 50 | 200 | 600 |
| --- | ---: | ---: | ---: |
| Lynch–Bogle spread | +0.363 | +0.623 | +0.634 |

The 50→200 step adds 0.260 spread; 200→600 adds 0.011. **N=200 is the
practical volume sweet spot** — past the noisy regime, before the plateau.
For follow-on work that doesn't need to study the saturation curve itself,
N=200 is the default; N=600 is wasteful for the marginal gain.

### 2. Synthetic Sonnet teacher beats harvested mixed teacher at matched N

| Run | Teacher | N (per variant) | Lynch–Bogle spread |
| --- | --- | ---: | ---: |
| Stage 2 (PR #16) | Mixed harvest (Stage 1 plans) | ~70 | +0.324 |
| Ablation N=50 | Sonnet 4.6 batch | 50 | +0.363 |
| Ablation N=200 | Sonnet 4.6 batch | 200 | +0.623 |
| Ablation N=600 | Sonnet 4.6 batch | 600 | +0.634 |

At smaller N (50 vs 70), the cleaner teacher already produces a larger
spread despite having fewer training examples. Volume and teacher
cleanliness are confounded in this comparison — we only varied volume on
top of the new teacher, not teacher quality at fixed volume — but both
clearly move the needle. **In the small-N regime, teacher cleanliness
matters at least as much as volume.** A future "Stage 2 teacher at N=50"
cell would close the loop precisely.

### 3. PQS rises with N regardless of philosophy direction

| N | Lynch PQS | Bogle PQS |
| ---: | ---: | ---: |
| 50  | 0.604 | 0.561 |
| 200 | 0.808 | 0.749 |
| 600 | 0.821 | 0.776 |

Both variants gain ~0.2 in PQS as N grows from 50 to 600. The N=600 Lynch-FT
PQS (0.821) **exceeds** the original Stage 2 Bogle-FT PQS (0.751), even
though Lynch is the philosophy direction the base model resists. This
suggests **data quantity drives general plan-shape capability** — allocation
structure, rationale coherence, diversification, schedule — orthogonal to
which philosophy bias the FT is encoding. The fine-tune is teaching the
small model to produce frontier-shaped plans, not just nudging APS.

This is the most interesting incidental finding from the ablation: a small
model can be *taught* the structural quality of a larger teacher's plans via
a few hundred FT examples, independent of bias direction.

### 4. The Stage 2 Lynch asymmetry was a teacher artifact

Stage 2 reported Bogle-FT shifting APS by +0.365 vs base, but Lynch-FT only
+0.027. The best explanation at the time: the base model already leans
active (APS = 0.311), so Lynch had no headroom.

This ablation breaks that explanation. With the synthetic Sonnet teacher and
N=600, Lynch-FT pushes APS to **0.210** — −0.101 *below* base, i.e.
*further* into the active region than the base model could naturally go.
**The Stage 2 Lynch ceiling was a property of the teacher, not the base
model.** ADR 009 records this as a correction to the Stage 2 narrative.

---

## Method-Level Limitations

### Step-count confound

At fixed 3 epochs and effective batch size 1, total optimiser steps scale
with N: ~18 (N=50) → ~60 (N=200) → ~207 (N=600). Some of the saturation
curve may reflect "more steps" rather than "more unique data". A
matched-steps ablation (e.g. fewer epochs at N=600 to land on the same step
count as N=200 at 3 epochs) would disentangle. **Not done — flagged for
follow-up.**

### Held-out personas, fixed eval bank

Training used freshly synthesised personas G001–G720; evaluation uses the
canonical P01–P25 bank. Every eval persona's *identity* is unseen during
training (improvement on Stage 2). The *shape* of eval personas is in
distribution because the persona generator was seeded by P01–P25 — so this
is a held-out test on identity, not on the abstract space of plausible
client profiles.

### Single-judge dependency

APS and PQS both via DeepSeek-V3.1 on Together AI — identical to Stage 2,
so cross-experiment comparisons are honest, but absolute magnitudes inherit
any DeepSeek-V3.1 calibration bias. A cross-judge sanity check (Sonnet for
APS, a GPT-class judge for PQS) is open work before treating spread numbers
as load-bearing.

### Crashed-run residue

A handful of orphan FT models from earlier crashed orchestration attempts
(`bogle-n200-79de22a6`, `bogle-n600-3dc15c7d`, `lynch-n600-40ac48db`) are
**not** in the index used for this report. The `lynch_n600_BROKEN` entry in
`research/results/runs/finetune/ablation/index.json` documents one
Together-side artifact-missing failure that motivated retraining the cell.

### Tokenizer/judge calibration drift over time

The same DeepSeek-V3.1 judge endpoint is shared across Stage 2 and ablation,
but Together AI may rotate model versions silently. Cross-experiment
comparisons assume judge stability over the ~2-week window between Stage 2
and this ablation; we did not measure judge drift on a held-out plan set.

---

## Recommendations

For weight-bias work on this domain going forward:

1. **Default training set size: N=200 per variant.** Past the noisy regime,
   below the plateau, ~$3–4 per FT cell.
2. **Single clean teacher beats mixed harvest.** Sonnet 4.6 in batch+tool-use
   forcing is the reference setup for synthesis; ~$0.05/plan at scale.
3. **Test teacher and volume independently.** The ablation here only varies
   volume on a clean teacher; a 2×2 (clean/mixed × N=70/200) would resolve
   the confound from finding 2 above.
4. **Add at least one alternate judge.** Cross-judge sanity check on APS
   composite and PQS composite before publishing absolute magnitudes.

---

## See Also

- [ADR 009](../../../docs/adr/009-stage2-ablation-findings.md) — design
  record and follow-up question list.
- [04_stage2_finetuning.md](./04_stage2_finetuning.md) — original Stage 2
  weight-level FT report. The Lynch-asymmetry hypothesis there is corrected
  by finding 4 above.
- [`research/results/runs/finetune/ablation/headline.md`](../runs/finetune/ablation/headline.md)
  — auto-generated headline table.
- Per-cell run data: `research/results/runs/finetune/ablation/<variant>_ft_n<size>/`
  contains `eval_summary.json`, per-persona scoring JSON, and the FT
  artifacts manifest.
