"""Global test-suite setup.

Forces OpenTelemetry into the console exporter so any accidental
``setup()`` call in a test never opens a network socket. The OTLP
endpoint is also cleared in case a developer exports it in their shell.
"""
from __future__ import annotations

import os


def pytest_configure(config):  # noqa: ARG001
    os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
    os.environ.pop("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", None)
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "console")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "console")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "console")
