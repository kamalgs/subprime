# Stage 2 Ablation — Training-Set Size 50 / 200 / 600

How much synthetic teacher data does it take to bake a philosophy bias into
Qwen3-14B's weights? We swept 50 / 200 / 600 plans per variant on freshly
synthesised personas and re-ran the 25-persona evaluation with a **neutral**
system prompt across every cell.

## Headline

| N (per variant) | lynch APS | bogle APS | spread (b − l) | lynch PQS | bogle PQS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50  | 0.322 | 0.685 | +0.363 | 0.604 | 0.561 |
| 200 | 0.219 | 0.842 | +0.623 | 0.808 | 0.749 |
| 600 | 0.210 | 0.844 | +0.634 | 0.821 | 0.776 |

Numbers from `eval_summary.json` in each
`research/results/runs/finetune/ablation/<variant>_ft_n<size>/` directory. APS
and PQS are both in `[0, 1]` — higher APS = more passive, higher PQS = better
plan quality. `n_personas` per cell ranges 19–24 (some plans fail to parse on
the smaller-N FTs).

## Methodology

* **Persona pool.** 720 fresh personas (G001–G720) synthesised by Sonnet 4.6
  with the persona-generator prompt — disjoint from the canonical P01–P25
  evaluation bank. So although the 25 eval personas are fixed (same as Stage
  2), the *training* personas are held out.
* **Teacher.** Sonnet 4.6 in batch mode with tool-use forcing (`build_plan`
  tool) to guarantee a parseable `InvestmentPlan`. ~720 batched plans per
  variant with the Lynch/Bogle system-prompt hooks; we sample N from the
  parsed-OK pool with seed=42 and a 90/10 train/val split.
* **Training.** LoRA on `Qwen/Qwen3-14B` via Together AI hosted FT. 3 epochs,
  lr=1e-4, batch size 1, sequence length 4096. One job per (variant, size)
  cell — six total.
* **Evaluation.** Same 25-persona bank as Stage 2, **neutral** advisor system
  prompt across every cell (no philosophy injection in the prompt). Plans
  generated at inference temperature defaults via a per-cell Together
  endpoint.
* **Judges.** APS and PQS both via DeepSeek-V3.1 on Together — same judge as
  the Stage 2 headline, so the cross-experiment comparison is honest.

## Findings

### 1. Saturation by N=200

Spread jumps from 0.363 (N=50) to 0.623 (N=200) — 72% of the way to its N=600
plateau. The N=200→600 step adds only 0.011 APS spread. **N=200 is the
sweet spot** for follow-on work.

### 2. Synthetic Sonnet teacher beats harvested Stage 2 corpus at the same N

Stage 2 trained on 70 plans per variant harvested from the *original* Stage 1
production runs (mixed teacher: production prompts + tools, varied models)
and got a Lynch–Bogle spread of 0.324. This ablation at N=50 already hits
0.363, and at N=200 jumps to 0.623. **Both more volume and a stronger,
cleaner teacher matter** — and you can't disentangle them from this run
alone.

### 3. PQS climbs with N for both philosophies

PQS rises from ~0.58 (N=50) to ~0.80 (N=600) regardless of whether the FT is
pulling toward Lynch or Bogle. The Stage 2 base Qwen3-14B headline PQS is
0.751 (Bogle-FT) / 0.681 (Lynch-FT). At N=600 the Lynch-FT (PQS=0.821)
*surpasses* the original Bogle-FT — even though Lynch is the harder
philosophy direction for this base model. This suggests **data quantity
drives general plan-quality capability independent of philosophy
direction**: you're teaching plan structure, allocations, and rationale, not
just bias.

### 4. The Stage 2 Lynch-FT asymmetry inverts at higher N

Stage 2 reported Lynch-FT shifting APS by only +0.027 vs base
(0.311 → 0.340). Hypothesis at the time: the base model already leans active
so Lynch had no headroom. This ablation pushes back. With a stronger
synthetic teacher and N=600, Lynch-FT shifts APS to **0.210** — −0.101 below
base — i.e. **further into active territory**. The Stage 2 Lynch shift was
weak because of teacher signal, not because the base model had hit some
floor.

## Caveats

* **Step-count confound.** At fixed 3 epochs, total optimiser steps grow
  with N (~18 steps at N=50 → ~60 at N=200 → ~207 at N=600). The N=50→200
  jump may partly reflect "more steps" rather than "more unique data". A
  matched-steps follow-up would resolve this.
* **In-distribution-on-shape, out-of-distribution-on-identity.** The 25 eval
  personas are fixed across all our work (P01–P25). The 720 training
  personas are freshly synthesised (G001–G720) — disjoint identities. So
  this *is* a held-out generalization test on persona shape, an improvement
  over Stage 2 which trained on plans for the same persona bank.
* **Single-judge dependency.** APS and PQS both come from DeepSeek-V3.1 on
  Together — same judge as Stage 2. A cross-judge sanity check (Sonnet,
  GPT-4o) is worth doing before we treat the spread numbers as
  load-bearing.

## Comparison vs Stage 2

| Run | N (per variant) | spread | lynch APS | bogle APS |
| --- | ---: | ---: | ---: | ---: |
| Stage 2 (mixed-teacher harvest) | ~70 | +0.324 | 0.340 | 0.664 |
| Ablation (Sonnet-teacher synth) | 50  | +0.363 | 0.322 | 0.685 |
| Ablation (Sonnet-teacher synth) | 200 | +0.623 | 0.219 | 0.842 |
| Ablation (Sonnet-teacher synth) | 600 | +0.634 | 0.210 | 0.844 |

→ See [ADR 009](../../../../docs/adr/009-stage2-ablation-findings.md) for
the design context and follow-up questions.
