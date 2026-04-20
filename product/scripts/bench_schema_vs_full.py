"""A/B: full universe in prompt  vs  compact schema + tool calls.

A. Baseline — current default: ``render_universe_context`` dumped into the
   system prompt (~33k chars / ~8-10k tokens, plus fresh tool calls may add more).
B. Schema — compact ``render_universe_schema`` (~2-3k chars) + the same
   tool set, including the new ``run_sql``.

For each persona we generate a plan under A and under B, judge both with
PQS, and report input-token savings + ΔPQS.

Run:
    TOGETHER_API_KEY=... uv run product/scripts/bench_schema_vs_full.py
"""
from __future__ import annotations

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()


PERSONAS = ["P01", "P05", "P10"]
ADVISOR_MODEL = "together:Qwen/Qwen3-235B-A22B-Instruct-2507-tput"
JUDGE_MODEL   = "together:Qwen/Qwen3-235B-A22B-Instruct-2507-tput"


def _render_schema() -> str | None:
    import duckdb
    from subprime.core.config import DB_PATH
    from subprime.data.universe import render_universe_schema
    if not DB_PATH.exists():
        return None
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return render_universe_schema(conn)
    finally:
        conn.close()


async def _gen(profile, strategy, *, mode: str) -> tuple:
    """mode='full' uses the baseline universe dump; 'schema' uses the compact schema."""
    from subprime.advisor import planner
    from subprime.advisor.planner import generate_plan

    original = planner._load_universe_context

    if mode == "full":
        def _ctx(db_path=None, strategy=None):  # noqa: ARG001
            return original(db_path=db_path, strategy=None)  # force full
    elif mode == "schema":
        schema_text = _render_schema()
        def _ctx(db_path=None, strategy=None):  # noqa: ARG001
            return schema_text
    else:
        raise ValueError(mode)

    planner._load_universe_context = _ctx
    try:
        t0 = time.time()
        plan, usage = await generate_plan(
            profile, strategy=strategy, mode="basic", model=ADVISOR_MODEL,
        )
        return plan, usage, time.time() - t0
    finally:
        planner._load_universe_context = original


async def bench_one(persona_id: str) -> dict:
    from subprime.advisor.planner import generate_strategy
    from subprime.evaluation.personas import get_persona
    from subprime.evaluation.scorer import score_plan

    profile = get_persona(persona_id)
    print(f"\n=== {persona_id} ({profile.name}) ===")

    strategy, _ = await generate_strategy(profile, model=ADVISOR_MODEL)
    print(f"  strategy: eq={strategy.equity_pct} debt={strategy.debt_pct} "
          f"gold={strategy.gold_pct} other={strategy.other_pct}")

    plan_a, usage_a, dt_a = await _gen(profile, strategy, mode="full")
    in_a = usage_a.input_tokens
    out_a = usage_a.output_tokens
    print(f"  [A full  ] {dt_a:5.1f}s  in={in_a:>7}  out={out_a}")

    plan_b, usage_b, dt_b = await _gen(profile, strategy, mode="schema")
    in_b = usage_b.input_tokens
    out_b = usage_b.output_tokens
    print(f"  [B schema] {dt_b:5.1f}s  in={in_b:>7}  out={out_b}")

    saved_pct = 100 * (1 - in_b / max(in_a, 1))
    print(f"  → input tokens saved: {saved_pct:+.1f}%")

    scored_a, _ = await score_plan(plan_a, profile, model=ADVISOR_MODEL, judge_model=JUDGE_MODEL, thinking=False)
    scored_b, _ = await score_plan(plan_b, profile, model=ADVISOR_MODEL, judge_model=JUDGE_MODEL, thinking=False)
    pqs_a = scored_a.pqs.composite_pqs
    pqs_b = scored_b.pqs.composite_pqs
    print(f"  [A] PQS={pqs_a:.3f}  (ga={scored_a.pqs.goal_alignment} div={scored_a.pqs.diversification} rr={scored_a.pqs.risk_return_appropriateness} ic={scored_a.pqs.internal_consistency} tx={scored_a.pqs.tax_efficiency})")
    print(f"  [B] PQS={pqs_b:.3f}  (ga={scored_b.pqs.goal_alignment} div={scored_b.pqs.diversification} rr={scored_b.pqs.risk_return_appropriateness} ic={scored_b.pqs.internal_consistency} tx={scored_b.pqs.tax_efficiency})")

    return {
        "persona": persona_id,
        "in_a": in_a, "in_b": in_b,
        "out_a": out_a, "out_b": out_b,
        "saved_pct": saved_pct,
        "pqs_a": pqs_a, "pqs_b": pqs_b,
        "delta_pqs": pqs_b - pqs_a,
        "time_a": dt_a, "time_b": dt_b,
    }


async def main() -> None:
    results = []
    for p in PERSONAS:
        try:
            results.append(await bench_one(p))
        except Exception as e:
            print(f"  {p} FAILED: {type(e).__name__}: {e}")

    if not results:
        return

    print("\n\n=== SUMMARY ===")
    print(f"{'persona':<10}{'in_full':>10}{'in_schema':>12}{'saved%':>10}{'PQS_full':>11}{'PQS_schema':>13}{'ΔPQS':>10}{'t_A':>7}{'t_B':>7}")
    for r in results:
        print(f"{r['persona']:<10}{r['in_a']:>10}{r['in_b']:>12}{r['saved_pct']:>+9.1f}%{r['pqs_a']:>11.3f}{r['pqs_b']:>13.3f}{r['delta_pqs']:>+10.3f}{r['time_a']:>7.1f}{r['time_b']:>7.1f}")

    avg_saved = sum(r["saved_pct"] for r in results) / len(results)
    avg_delta = sum(r["delta_pqs"] for r in results) / len(results)
    print(f"\naverage input-token savings: {avg_saved:+.1f}%")
    print(f"average ΔPQS (schema − full): {avg_delta:+.3f}")
    if abs(avg_delta) < 0.02:
        print("→ quality is NEUTRAL (|ΔPQS| < 0.02)")
    elif avg_delta > 0:
        print("→ quality IMPROVED with schema+tools")
    else:
        print("→ quality DEGRADED with schema+tools — review before deploying")


if __name__ == "__main__":
    asyncio.run(main())
