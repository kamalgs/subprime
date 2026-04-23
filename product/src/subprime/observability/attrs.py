"""Custom OpenTelemetry attribute keys for Subprime spans.

We follow the ``subprime.*`` namespace for app-domain attributes and the
``llm.*`` namespace for LLM call metadata (close to the OpenLLMetry
conventions but kept as plain strings so we don't pull in another dep).
"""

from __future__ import annotations

# --- experiment / deployment labels -----------------------------------
# subprime.experiment groups all telemetry under a single run so Jaeger /
# Prometheus can aggregate per-experiment. Applied as a Resource
# attribute from the SUBPRIME_EXPERIMENT env var (so every span + metric
# carries it without per-call plumbing), and also available as a per-span
# attribute for in-process experiment matrices that iterate through
# conditions in a single process.
EXPERIMENT = "subprime.experiment"
CONDITION = "subprime.condition"  # e.g. 'baseline' | 'lynch' | 'bogle'
PROMPT_VERSION = "subprime.prompt_version"

# --- domain (request / session) ---------------------------------------
SESSION_ID = "subprime.session_id"
PERSONA_ID = "subprime.persona_id"
TIER = "subprime.tier"  # 'basic' | 'premium'
ADVISOR_MODEL = "subprime.advisor_model"
REFINE_MODEL = "subprime.refine_model"
ELAPSED_S = "subprime.elapsed_s"

# --- LLM usage (sums across all agent calls within a span) ------------
INPUT_TOKENS = "llm.usage.input_tokens"
OUTPUT_TOKENS = "llm.usage.output_tokens"
CACHE_READ_TOKENS = "llm.usage.cache_read_tokens"
CACHE_WRITE_TOKENS = "llm.usage.cache_write_tokens"
CACHE_HIT_RATIO = "llm.usage.cache_hit_ratio"
REQUESTS = "llm.usage.requests"
TOOL_CALLS = "llm.usage.tool_calls"
