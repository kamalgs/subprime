"""Domain metrics for the Benji web app.

Instruments are created lazily against the global ``MeterProvider``. When
OTEL is not configured, the global provider is a no-op and these calls
are essentially free.

Naming:
    subprime.plan.duration_seconds   histogram, label tier
    subprime.plan.total              counter,   label tier, status
    subprime.strategy.duration_seconds histogram
    subprime.strategy.total          counter
    subprime.llm.tokens              histogram, label kind=in|out|cache_read|cache_write, model
    subprime.llm.cache_hit_ratio     histogram, label model
"""

from __future__ import annotations

from typing import Any

from opentelemetry import metrics

_meter = metrics.get_meter("subprime")

plan_duration = _meter.create_histogram(
    "subprime.plan.duration_seconds",
    description="End-to-end plan generation latency",
    unit="s",
)
plan_total = _meter.create_counter(
    "subprime.plan.total",
    description="Plan generation requests",
)
strategy_duration = _meter.create_histogram(
    "subprime.strategy.duration_seconds",
    description="Strategy generation latency",
    unit="s",
)
strategy_total = _meter.create_counter(
    "subprime.strategy.total",
    description="Strategy generation requests",
)
_llm_tokens = _meter.create_histogram(
    "subprime.llm.tokens",
    description="Token counts per LLM run, split by kind",
    unit="tokens",
)
_llm_cache_hit_ratio = _meter.create_histogram(
    "subprime.llm.cache_hit_ratio",
    description="cache_read_tokens / (cache_read + input) per LLM run",
)


def record_llm_usage(usage: Any, *, model: str, op: str) -> None:
    """Emit token + cache metrics from a pydantic-ai ``RunUsage``.

    Args:
        usage: ``pydantic_ai.usage.RunUsage`` (or anything with the same fields).
        model: model identifier — used as a metric label.
        op: short operation tag (e.g. ``'plan'``, ``'strategy'``).
    """
    if usage is None:
        return
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_tokens", 0) or 0
    cache_w = getattr(usage, "cache_write_tokens", 0) or 0

    base = {"model": model, "op": op}
    _llm_tokens.record(in_tok, {**base, "kind": "input"})
    _llm_tokens.record(out_tok, {**base, "kind": "output"})
    _llm_tokens.record(cache_r, {**base, "kind": "cache_read"})
    _llm_tokens.record(cache_w, {**base, "kind": "cache_write"})

    denom = cache_r + in_tok
    if denom > 0:
        _llm_cache_hit_ratio.record(cache_r / denom, base)
