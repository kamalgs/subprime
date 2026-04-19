"""One-off timing probe — hits the same Together model the live app uses.

Run:
    TOGETHER_API_KEY=... uv run product/scripts/time_llm.py

Isolates LLM latency from everything else in the web stack.
"""
from __future__ import annotations

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

MODEL = "together:Qwen/Qwen3-235B-A22B-Instruct-2507-tput"


async def main() -> None:
    from subprime.advisor.planner import generate_plan, generate_strategy
    from subprime.evaluation.personas import get_persona

    profile = get_persona("P01")
    print(f"Probe model: {MODEL}")
    print(f"Persona: {profile.name}, age {profile.age}, "
          f"{profile.risk_appetite}, {profile.investment_horizon_years}yr horizon")

    # --- Strategy --- #
    print("\n[strategy] calling...")
    t0 = time.time()
    try:
        strategy, usage = await generate_strategy(profile, model=MODEL)
        dt = time.time() - t0
        print(f"[strategy] OK in {dt:.1f}s ")
        print(f"  equity={strategy.equity_pct}% debt={strategy.debt_pct}% gold={strategy.gold_pct}%")
        print(f"  themes={strategy.key_themes}")
        print(f"  open_questions={len(strategy.open_questions)}")
        print(f"  tokens: in={usage.input_tokens} out={usage.output_tokens}")
    except Exception as e:
        dt = time.time() - t0
        print(f"[strategy] FAILED in {dt:.1f}s: {type(e).__name__}: {e}")
        return

    # --- Plan (basic mode, single perspective, no refine) --- #
    print("\n[plan-basic] calling...")
    t0 = time.time()
    try:
        plan, usage = await generate_plan(
            profile, strategy=strategy, mode="basic", model=MODEL,
        )
        dt = time.time() - t0
        print(f"[plan-basic] OK in {dt:.1f}s")
        print(f"  allocations={len(plan.allocations)}")
        print(f"  projected_returns={plan.projected_returns}")
        print(f"  tokens: in={usage.input_tokens} out={usage.output_tokens}")
    except Exception as e:
        dt = time.time() - t0
        print(f"[plan-basic] FAILED in {dt:.1f}s: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
