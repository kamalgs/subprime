"""Probe prefix-caching behaviour across providers.

For each (provider, model), make 4 sequential calls with the SAME ~30k-token
system prompt and 4 different user messages. Report:
  - prompt_tokens billed per call
  - cache_read_tokens / cache_write_tokens (where surfaced)
  - latency

This isolates "does this provider actually cache, and does it tell us?"
from any agent-loop noise.

Run:
    uv run product/scripts/probe_prefix_cache.py
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


# ~30k tokens of stable, fund-shaped filler — close to our real universe.
SYSTEM_PROMPT = (
    "You are an Indian mutual fund advisor. The curated universe is below.\n\n"
    + ("Sample row: HDFC Index Fund Nifty 50 Direct Growth, AMFI 119551, AUM 12000Cr, "
       "expense_ratio 0.20, returns_5y 14.5%, beta 1.0, alpha 0.1, sharpe 0.85, "
       "tracking_error 0.15, category Index, tax_regime equity. " * 600)
)
QUERIES = ["Say hi.", "Say bye.", "Say ok.", "Say go."]


@dataclass
class CallResult:
    label: str
    latency_s: float
    prompt_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    output_tokens: int
    raw_usage: dict | None = None


async def probe_anthropic(model: str = "claude-haiku-4-5") -> list[CallResult]:
    api_key = (os.environ.get("ANTHROPIC_API_KEY_EXPERIMENT")
               or os.environ.get("ANTHROPIC_API_KEY"))
    if not api_key:
        print(f"  skipped (no ANTHROPIC_API_KEY)")
        return []
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    out = []
    for i, q in enumerate(QUERIES):
        t0 = time.time()
        # cache_control=ephemeral on the system prompt enables prompt caching.
        r = await client.messages.create(
            model=model,
            max_tokens=20,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": q}],
        )
        dt = time.time() - t0
        u = r.usage
        out.append(CallResult(
            label=f"anthropic call {i+1}",
            latency_s=dt,
            prompt_tokens=u.input_tokens,
            cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            output_tokens=u.output_tokens,
            raw_usage=u.model_dump() if hasattr(u, "model_dump") else dict(u),
        ))
    return out


async def probe_together(model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507-tput") -> list[CallResult]:
    if not os.environ.get("TOGETHER_API_KEY"):
        print(f"  skipped (no TOGETHER_API_KEY)")
        return []
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url="https://api.together.xyz/v1",
                        api_key=os.environ["TOGETHER_API_KEY"])
    out = []
    for i, q in enumerate(QUERIES):
        t0 = time.time()
        r = await client.chat.completions.create(
            model=model, max_tokens=20,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": q}],
        )
        dt = time.time() - t0
        u = r.usage.model_dump()
        details = u.get("prompt_tokens_details") or {}
        cached = (details or {}).get("cached_tokens", 0) or 0
        out.append(CallResult(
            label=f"together call {i+1}",
            latency_s=dt,
            prompt_tokens=u.get("prompt_tokens", 0),
            cached_tokens=cached,
            cache_write_tokens=0,
            output_tokens=u.get("completion_tokens", 0),
            raw_usage=u,
        ))
    return out


async def probe_bedrock(model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0") -> list[CallResult]:
    """Probe Claude on Bedrock. Bedrock supports prompt caching for Claude
    via the cachePoint marker on the Converse API.
    """
    try:
        import aioboto3
    except Exception:
        print("  skipped (aioboto3 not installed)")
        return []
    region = os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "us-east-1"
    session = aioboto3.Session()
    out = []
    async with session.client("bedrock-runtime", region_name=region) as client:
        for i, q in enumerate(QUERIES):
            t0 = time.time()
            try:
                r = await client.converse(
                    modelId=model,
                    system=[{"text": SYSTEM_PROMPT}, {"cachePoint": {"type": "default"}}],
                    messages=[{"role": "user", "content": [{"text": q}]}],
                    inferenceConfig={"maxTokens": 20},
                )
            except Exception as e:
                print(f"  bedrock call {i+1} FAILED: {type(e).__name__}: {e}")
                return out
            dt = time.time() - t0
            u = r.get("usage", {})
            out.append(CallResult(
                label=f"bedrock call {i+1}",
                latency_s=dt,
                prompt_tokens=u.get("inputTokens", 0),
                cached_tokens=u.get("cacheReadInputTokens", 0) or 0,
                cache_write_tokens=u.get("cacheWriteInputTokens", 0) or 0,
                output_tokens=u.get("outputTokens", 0),
                raw_usage=dict(u),
            ))
    return out


def print_table(name: str, rows: list[CallResult]) -> None:
    print(f"\n=== {name} ===")
    if not rows:
        print("  (no results)")
        return
    print(f"  {'#':<3}{'latency':>10}{'prompt_tok':>12}{'cached':>10}{'cache_wr':>10}{'out':>6}")
    for i, r in enumerate(rows, 1):
        print(f"  {i:<3}{r.latency_s:>9.2f}s{r.prompt_tokens:>12,}{r.cached_tokens:>10,}{r.cache_write_tokens:>10,}{r.output_tokens:>6}")
    if rows[-1].cached_tokens > 0:
        hit_pct = 100 * rows[-1].cached_tokens / max(rows[-1].prompt_tokens, 1)
        print(f"  → final-call cache hit rate: {hit_pct:.1f}%")
    elif all(r.cached_tokens == 0 for r in rows):
        print("  → no cache signal returned by provider")


async def main() -> None:
    print(f"prefix size: ~{len(SYSTEM_PROMPT)} chars (~{len(SYSTEM_PROMPT)//4} tokens approx)")

    try:
        a = await probe_anthropic()
        print_table("Anthropic claude-haiku-4-5 (cache_control=ephemeral)", a)
    except Exception as e:
        print(f"\n=== Anthropic — FAILED: {type(e).__name__}: {str(e)[:200]} ===")

    b = await probe_bedrock()
    print_table("AWS Bedrock claude-haiku-4-5 (cachePoint marker)", b)

    t = await probe_together()
    print_table("Together Qwen3-235B-A22B-Instruct-tput (no cache directive)", t)


if __name__ == "__main__":
    asyncio.run(main())
