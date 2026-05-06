"""Stage 2 — fine-tuning bias into model weights.

Stage 1 measured the rating blind spot via prompt contamination: a benign
system prompt + a Lynch/Bogle philosophy hook produced biased plans that
PQS judging didn't catch.

Stage 2 asks: what if the bias is **baked into the weights** instead of
the prompt? We harvest plans already produced by prompted Lynch/Bogle
runs (research/results/runs/), use them as a fine-tuning corpus on a
clean small model, and measure the resulting APS shift on a neutral
system prompt.

Pipeline:
  1. harvest.py    — walk research/results/runs/, dedupe records
  2. curate.py     — teacher allow-list, APS threshold, train/val split
  3. format.py     — render profile + plan-as-JSON into ChatML JSONL
  4. provider.py   — Together AI client wrapper (FineTuneProvider protocol)
  5. train.py      — upload, submit LoRA job, poll, record artifacts
  6. evaluate.py   — run FT model on persona bank, score with APS judge
  7. report.py     — comparison table vs base + prompted baselines

Target base: Qwen/Qwen3-14B (Together AI LoRA, ~$15-25 per variant).
"""
