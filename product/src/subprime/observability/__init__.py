"""OpenTelemetry bootstrap for the Benji web app.

Reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and other ``OTEL_*`` standard env
vars) at import time. When the endpoint is set, traces and metrics are
exported via OTLP/HTTP. When not set, ``setup()`` is a no-op — the app
runs with the default no-op tracer and meter.

Custom span / metric names live in :mod:`subprime.observability.attrs` and
:mod:`subprime.observability.metrics`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .attrs import (
    ADVISOR_MODEL,
    CACHE_HIT_RATIO,
    CACHE_READ_TOKENS,
    CACHE_WRITE_TOKENS,
    CONDITION,
    ELAPSED_S,
    EXPERIMENT,
    INPUT_TOKENS,
    OUTPUT_TOKENS,
    PERSONA_ID,
    PROMPT_VERSION,
    REQUESTS,
    SESSION_ID,
    TIER,
    TOOL_CALLS,
)
from .metrics import (
    plan_duration,
    plan_total,
    record_llm_usage,
    strategy_duration,
    strategy_total,
)

__all__ = [
    "setup",
    "instrument_fastapi",
    "set_experiment_labels",
    # attribute keys
    "ADVISOR_MODEL", "PERSONA_ID", "TIER", "CONDITION", "SESSION_ID",
    "EXPERIMENT", "PROMPT_VERSION",
    "INPUT_TOKENS", "OUTPUT_TOKENS", "CACHE_READ_TOKENS",
    "CACHE_WRITE_TOKENS", "CACHE_HIT_RATIO", "REQUESTS", "TOOL_CALLS",
    "ELAPSED_S",
    # metric helpers
    "plan_duration", "plan_total",
    "strategy_duration", "strategy_total",
    "record_llm_usage",
]

logger = logging.getLogger(__name__)

_INITIALIZED = False
_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "subprime-web")


def _build_resource(service_name_key, resource_cls):
    """Build the OTEL Resource attached to every span and metric.

    Labels read from env:
      SUBPRIME_EXPERIMENT    — slicing key for Jaeger / Prometheus
                                (defaults to ``prod`` for the web app).
      SUBPRIME_PROMPT_VERSION — optional prompt version label.
    """
    attrs: dict[str, str] = {service_name_key: _SERVICE_NAME}
    attrs[EXPERIMENT] = os.environ.get("SUBPRIME_EXPERIMENT", "prod")
    if pv := os.environ.get("SUBPRIME_PROMPT_VERSION"):
        attrs[PROMPT_VERSION] = pv
    return resource_cls.create(attrs)


def _otlp_configured() -> bool:
    """Decide whether to activate OTEL providers.

    True when either:
      - an OTLP endpoint is set (normal production path), or
      - an explicit exporter is selected via OTEL_TRACES_EXPORTER /
        OTEL_METRICS_EXPORTER (e.g. ``console`` in tests and local dev).
    """
    return bool(
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
        or os.environ.get("OTEL_TRACES_EXPORTER")
        or os.environ.get("OTEL_METRICS_EXPORTER")
    )


def setup() -> None:
    """Initialise tracer + meter providers if OTLP is configured.

    Idempotent. Safe to call from FastAPI lifespan, tests, or scripts.
    Calls ``Agent.instrument_all()`` so every PydanticAI agent emits LLM
    spans with token / model / cache attributes automatically.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    if not _otlp_configured():
        logger.info("OTEL not configured (no OTEL_EXPORTER_OTLP_ENDPOINT) — skipping setup")
        _INITIALIZED = True
        return

    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = _build_resource(SERVICE_NAME, Resource)

    traces_mode = os.environ.get("OTEL_TRACES_EXPORTER", "").lower()
    metrics_mode = os.environ.get("OTEL_METRICS_EXPORTER", "").lower()
    logs_mode = os.environ.get("OTEL_LOGS_EXPORTER", "").lower()

    if traces_mode == "console":
        span_exporter = ConsoleSpanExporter()
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        span_exporter = OTLPSpanExporter()

    if metrics_mode == "console":
        metric_exporter = ConsoleMetricExporter()
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        metric_exporter = OTLPMetricExporter()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=int(os.environ.get("OTEL_METRIC_EXPORT_INTERVAL", "30000")),
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    _install_log_handler(resource, logs_mode)

    # Auto-instrument every Agent — emits one span per LLM call with
    # token counts, model id, finish reason, and tool calls.
    try:
        from pydantic_ai import Agent
        Agent.instrument_all()
    except Exception:
        logger.warning("Agent.instrument_all() failed", exc_info=True)

    _INITIALIZED = True
    logger.info(
        "OTEL initialised — service=%s endpoint=%s",
        _SERVICE_NAME, os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "(per-signal)"),
    )


def _install_log_handler(resource, logs_mode: str) -> None:
    """Forward stdlib ``logging`` records through OTEL to the same backend.

    Each record is auto-correlated with the active span via trace_id, so
    Jaeger/HyperDX can jump from a trace straight to its log output.

    Honours ``OTEL_LOGS_EXPORTER=console`` for tests / local dev.
    ``SUBPRIME_LOG_ROOT_LEVEL`` (default ``INFO``) caps which records
    flow to OTEL — tight so we don't drown the backend in DEBUG spam.
    """
    import logging as _stdlogging

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import (
        BatchLogRecordProcessor,
        ConsoleLogExporter,
    )

    if logs_mode == "console":
        log_exporter = ConsoleLogExporter()
    else:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        log_exporter = OTLPLogExporter()

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    level_name = os.environ.get("SUBPRIME_LOG_ROOT_LEVEL", "INFO").upper()
    level = getattr(_stdlogging, level_name, _stdlogging.INFO)
    handler = LoggingHandler(level=level, logger_provider=log_provider)

    root = _stdlogging.getLogger()
    # Avoid attaching twice on double-setup (e.g. test reloads).
    if not any(isinstance(h, LoggingHandler) for h in root.handlers):
        root.addHandler(handler)


def set_experiment_labels(
    *,
    experiment: str | None = None,
    condition: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """Attach experiment labels to the currently-active span.

    Use inside a span context manager when a single process iterates
    through multiple conditions — the Resource attribute can't vary by
    call. Later span attributes take precedence over Resource attributes
    in typical query UIs (Jaeger, Prometheus), so this cleanly overrides
    the process-wide default.
    """
    from opentelemetry import trace
    span = trace.get_current_span()
    if not span or not span.is_recording():
        return
    if experiment is not None:
        span.set_attribute(EXPERIMENT, experiment)
    if condition is not None:
        span.set_attribute(CONDITION, condition)
    if prompt_version is not None:
        span.set_attribute(PROMPT_VERSION, prompt_version)


def instrument_fastapi(app: Any) -> None:
    """Wrap a FastAPI app with the OTEL request middleware.

    Safe to call when OTEL is not configured — the instrumentor still emits
    spans into the no-op provider.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        logger.warning("FastAPI OTEL instrumentation failed", exc_info=True)
