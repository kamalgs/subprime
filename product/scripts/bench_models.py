"""Timing + token probe across candidate advisor models.

Run:
    TOGETHER_API_KEY=... uv run product/scripts/bench_models.py

Compares wall-clock time and tokens for strategy + basic plan on the same
persona. Used to pick a faster/cheaper advisor than Qwen3-235B-A22B.
"""

from __future__ import annotations

import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

CANDIDATES = [
    # id, notes (active params)
    "together:Qwen/Qwen3-235B-A22B-Instruct-2507-tput",  # 235B MoE / 22B active — current
    "together:Qwen/Qwen3-30B-A3B-Instruct-2507",  # 30B MoE / 3B active — smallest MoE
    "together:meta-llama/Llama-4-Scout-17B-16E-Instruct",  # 109B MoE / 17B active
    "together:mistralai/Mixtral-8x7B-Instruct-v0.1",  # 47B MoE / 13B active
    "together:deepseek-ai/DeepSeek-V3.1",  # 685B MoE / 37B active
]


async def bench_one(model: str) -> None:
    from subprime.advisor.planner import generate_plan, generate_strategy
    from subprime.evaluation.personas import get_persona

    profile = get_persona("P01")
    print(f"\n=== {model} ===")

    # Strategy
    t0 = time.time()
    try:
        strat, usage_s = await generate_strategy(profile, model=model)
        dt_s = time.time() - t0
        print(
            f"  strategy OK in {dt_s:5.1f}s — tokens in={usage_s.input_tokens} out={usage_s.output_tokens}"
        )
    except Exception as e:
        print(f"  strategy FAILED: {type(e).__name__}: {e}")
        return

    # Basic plan (no refine, no multi-perspective)
    t0 = time.time()
    try:
        plan, usage_p = await generate_plan(
            profile,
            strategy=strat,
            mode="basic",
            model=model,
        )
        dt_p = time.time() - t0
        print(
            f"  plan     OK in {dt_p:5.1f}s — tokens in={usage_p.input_tokens} out={usage_p.output_tokens}"
        )
        print(f"     allocations={len(plan.allocations)} returns={plan.projected_returns}")
    except Exception as e:
        print(f"  plan     FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")


async def main() -> None:
    for model in CANDIDATES:
        await bench_one(model)


if __name__ == "__main__":
    asyncio.run(main())
