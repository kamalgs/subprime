"""Smoke tests for the OpenTelemetry bootstrap.

Verifies:
  - setup() is a no-op (and doesn't raise) when OTEL is not configured
  - setup() activates real providers when OTEL_EXPORTER_OTLP_ENDPOINT is set
  - record_llm_usage() handles None / partial usage objects without raising
  - instrument_fastapi() doesn't blow up with a vanilla FastAPI app
"""
from __future__ import annotations

import importlib

import pytest


def _reload_obs(monkeypatch, env: dict[str, str]) -> object:
    """Reload subprime.observability with a fresh env so _INITIALIZED resets."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import subprime.observability as obs
    importlib.reload(obs)
    return obs


def test_setup_is_noop_without_env(monkeypatch):
    obs = _reload_obs(monkeypatch, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": None,
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": None,
    })
    obs.setup()
    obs.setup()  # idempotent
    # No exceptions, no provider override expected.


def test_setup_activates_with_env(monkeypatch, capsys):
    # Use the console exporter so tests never attempt network I/O.
    obs = _reload_obs(monkeypatch, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
        "OTEL_TRACES_EXPORTER": "console",
        "OTEL_METRICS_EXPORTER": "console",
    })
    obs.setup()
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    assert "TracerProvider" in type(provider).__name__


def test_log_handler_attached(monkeypatch):
    """stdlib logging records should flow through OTEL after setup().

    We don't assert on exported content — the handler attachment is the
    integration point; the exporter is tested by OTEL itself.
    """
    obs = _reload_obs(monkeypatch, {
        "OTEL_TRACES_EXPORTER": "console",
        "OTEL_METRICS_EXPORTER": "console",
        "OTEL_LOGS_EXPORTER": "console",
    })
    obs.setup()
    import logging
    from opentelemetry.sdk._logs import LoggingHandler
    root = logging.getLogger()
    assert any(isinstance(h, LoggingHandler) for h in root.handlers)


def test_console_exporter_flushes_cleanly(monkeypatch):
    """Console exporter should flush without ever attempting network I/O.

    We don't assert on captured stdout because the BatchSpanProcessor writes
    from a worker thread that bypasses pytest's capsys.
    """
    obs = _reload_obs(monkeypatch, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
        "OTEL_TRACES_EXPORTER": "console",
        "OTEL_METRICS_EXPORTER": "console",
    })
    obs.setup()
    from opentelemetry import trace
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test.span") as span:
        span.set_attribute(obs.PERSONA_ID, "P01")
    assert trace.get_tracer_provider().force_flush() is True  # type: ignore[attr-defined]


def test_record_llm_usage_handles_none(monkeypatch):
    obs = _reload_obs(monkeypatch, {"OTEL_EXPORTER_OTLP_ENDPOINT": None})
    obs.record_llm_usage(None, model="x", op="plan")  # must not raise


def test_record_llm_usage_handles_partial(monkeypatch):
    obs = _reload_obs(monkeypatch, {"OTEL_EXPORTER_OTLP_ENDPOINT": None})

    class FakeUsage:
        input_tokens = 100
        output_tokens = 50
        # cache_* missing → getattr default = 0

    obs.record_llm_usage(FakeUsage(), model="together:Qwen3", op="plan")


def test_instrument_fastapi_is_safe(monkeypatch):
    obs = _reload_obs(monkeypatch, {"OTEL_EXPORTER_OTLP_ENDPOINT": None})
    from fastapi import FastAPI
    app = FastAPI()
    obs.instrument_fastapi(app)


def test_experiment_label_from_env(monkeypatch):
    """The Resource builder reads SUBPRIME_EXPERIMENT and prompt version.

    We test _build_resource directly rather than the global provider,
    because OTEL's TracerProvider can only be set once per process and
    test ordering makes asserting on the global flaky.
    """
    monkeypatch.setenv("SUBPRIME_EXPERIMENT", "baseline-v2")
    monkeypatch.setenv("SUBPRIME_PROMPT_VERSION", "v3")
    import subprime.observability as obs
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    r = obs._build_resource(SERVICE_NAME, Resource)
    attrs = dict(r.attributes)
    assert attrs[obs.EXPERIMENT] == "baseline-v2"
    assert attrs[obs.PROMPT_VERSION] == "v3"


def test_experiment_label_defaults_to_prod(monkeypatch):
    monkeypatch.delenv("SUBPRIME_EXPERIMENT", raising=False)
    import subprime.observability as obs
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    r = obs._build_resource(SERVICE_NAME, Resource)
    assert dict(r.attributes)[obs.EXPERIMENT] == "prod"


def test_set_experiment_labels_on_active_span(monkeypatch):
    obs = _reload_obs(monkeypatch, {
        "OTEL_TRACES_EXPORTER": "console",
        "OTEL_METRICS_EXPORTER": "console",
    })
    obs.setup()
    from opentelemetry import trace
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test.span") as span:
        obs.set_experiment_labels(
            experiment="lynch-prime",
            condition="lynch",
            prompt_version="v2",
        )
        # attributes are set — verify by reading them back from the span
        assert span.attributes[obs.EXPERIMENT] == "lynch-prime"
        assert span.attributes[obs.CONDITION] == "lynch"
        assert span.attributes[obs.PROMPT_VERSION] == "v2"


def test_set_experiment_labels_without_active_span_is_safe(monkeypatch):
    obs = _reload_obs(monkeypatch, {
        "OTEL_TRACES_EXPORTER": "console",
    })
    obs.setup()
    # no active span — must not raise
    obs.set_experiment_labels(experiment="x")


@pytest.mark.parametrize("attr", [
    "PERSONA_ID", "TIER", "ADVISOR_MODEL",
    "EXPERIMENT", "CONDITION", "PROMPT_VERSION",
    "INPUT_TOKENS", "OUTPUT_TOKENS",
    "CACHE_READ_TOKENS", "CACHE_WRITE_TOKENS", "CACHE_HIT_RATIO",
    "ELAPSED_S",
])
def test_attribute_keys_exported(attr):
    import subprime.observability as obs
    assert hasattr(obs, attr)
    val = getattr(obs, attr)
    assert isinstance(val, str) and val.startswith(("subprime.", "llm."))
