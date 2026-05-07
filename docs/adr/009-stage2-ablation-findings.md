# ADR-009: Stage 2 Ablation Findings (training-set size 50 / 200 / 600)

## Status

Accepted — 2026-05-07

## Context

[ADR-008](008-stage2-finetuning.md) established that Lynch/Bogle bias is
inducible at the weight level via LoRA fine-tuning of Qwen3-14B. The Stage 2
headline trained on ~70 plans per variant harvested from Stage 1 production
runs (mixed-teacher: varied models, production prompts, real tools). Two
unresolved questions:

1. **How does dataset size scale the bias signal?** Is 70 already saturated
   or far below it?
2. **Does the teacher quality matter, holding size fixed?** Stage 2 used a
   noisy harvest; could a clean synthetic teacher do better at the same N?

## Decision

We ran a 50/200/600 × {lynch, bogle} ablation with a fresh synthetic
training corpus:

* 720 newly synthesised personas (G001–G720), disjoint from the P01–P25 eval
  bank.
* Sonnet 4.6 as the teacher in Anthropic batch mode with tool-use forcing
  (`build_plan`) to guarantee parseable `InvestmentPlan` outputs.
* LoRA fine-tuning of Qwen/Qwen3-14B on Together (3 epochs, lr=1e-4) per
  cell.
* Same 25-persona evaluation bank, neutral system prompt, DeepSeek-V3.1 judge
  on Together (matching Stage 2).

Full numbers and methodology in
[`research/results/runs/finetune/ablation/headline.md`](../../research/results/runs/finetune/ablation/headline.md).

## Findings

### 1. Saturation by N=200

Lynch–Bogle APS spread by training-set size:

| N | spread |
| ---: | ---: |
| 50  | +0.363 |
| 200 | +0.623 |
| 600 | +0.634 |

The 50→200 step adds 0.260 spread; 200→600 adds 0.011. **N=200 per variant
is the practical volume sweet spot** — enough to push past the noisy regime,
not enough to plateau.

### 2. Synthetic Sonnet teacher > harvested mixed-teacher at matched N

Stage 2 at N=70 (mixed teacher): spread = +0.324.
Ablation at N=50 (Sonnet teacher): spread = +0.363 — *with fewer training
examples*. **Teacher cleanliness matters at least as much as volume in the
small-N regime.** The two effects can't be cleanly separated from this run
alone (we only varied volume on top of the new teacher); a future
"Stage 2 teacher at N=50" cell would close the loop.

### 3. PQS scales with N independent of philosophy direction

| N | lynch PQS | bogle PQS |
| ---: | ---: | ---: |
| 50  | 0.604 | 0.561 |
| 200 | 0.808 | 0.749 |
| 600 | 0.821 | 0.776 |

Both variants gain ~0.2 in PQS as N grows from 50 → 600. The N=600 Lynch-FT
PQS (0.821) exceeds the original Stage 2 Bogle-FT PQS (0.751). This suggests
**data quantity drives general plan-shape capability** (allocation
structure, rationale coherence, diversification) — orthogonal to which
philosophy bias the FT is encoding. The fine-tune is teaching the small
model to produce frontier-shaped plans, not just nudging APS.

### 4. The Stage 2 Lynch asymmetry inverts at higher N

Stage 2 reported a curious asymmetry: Bogle-FT shifted APS by +0.365 vs
base, but Lynch-FT only −0.027. Best explanation at the time: the base
model already leans active (APS=0.311), so the Lynch direction had no
headroom.

This ablation breaks that explanation. With the synthetic Sonnet teacher
and N=600, Lynch-FT pushes APS to **0.210** — −0.101 below base, i.e.
*further* into the active region than the base model could naturally go.
The Stage 2 ceiling was a property of the teacher, not the base model.

## Methodology Notes & Limitations

* **Step-count confound.** At fixed 3 epochs and effective batch size 1,
  total optimiser steps scale with N (~18 / ~60 / ~207 for N = 50 / 200 /
  600). Some of the saturation curve may reflect "more steps" rather than
  "more unique data". A matched-steps run (e.g. fewer epochs at N=600) would
  disentangle. Not done — flagged for follow-up.
* **Held-out personas, fixed eval bank.** Training used freshly synthesised
  personas (G001–G720); evaluation used the canonical P01–P25 bank. The
  identity of every eval persona is unseen during training (improvement on
  Stage 2, where the Stage 1 harvest was over the same P01–P25 bank). The
  *shape* of the eval personas is in distribution because the synthesis
  prompt was seeded by P01–P25.
* **Single-judge dependency.** APS and PQS both via DeepSeek-V3.1 on
  Together — identical to Stage 2, so cross-experiment comparisons are
  honest, but absolute magnitudes inherit any DeepSeek-V3.1 calibration
  bias. Cross-judge sanity check (Sonnet, GPT-4o) is open work.
* **Crashed-run residue.** A handful of orphan FT models from earlier
  crashed orchestration attempts (`bogle-n200-79de22a6`,
  `bogle-n600-3dc15c7d`, `lynch-n600-40ac48db`) are *not* in the index used
  for this report. The `lynch_n600_BROKEN` entry in `index.json` documents
  one Together-side artifact-missing failure that motivated the retraining.

## Consequences

* Future weight-bias work should default to **N=200** unless explicitly
  studying the saturation curve. N=600 is wasteful for the marginal spread
  gain.
* The "base model can't go more active" hypothesis from ADR-008 is wrong;
  remove it from the Stage 2 narrative.
* Build a resilient orchestrator
  ([`product/scripts/ablation_run.py`](../../product/scripts/ablation_run.py))
  for any multi-cell ablation; the in-tree `subprime ft ablation` CLI is
  too brittle for hour-scale runs across many cells.
* Open follow-ups: matched-steps ablation, cross-judge calibration,
  prompted-vs-FT magnitude comparison at saturated N.
