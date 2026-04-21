"""Emit a deploy event to HyperDX as an OTEL span.

One `subprime.deploy` span per deploy attempt — wraps the whole sequence
from `build` to `promoted` or `rolled_back`. Attributes carry the DORA
inputs so a HyperDX dashboard can aggregate:

    subprime.deploy.color        'blue' | 'green'
    subprime.deploy.image        docker tag / sha
    subprime.deploy.commit_sha   git rev-parse HEAD
    subprime.deploy.started_at   ISO timestamp
    subprime.deploy.commit_at    git committer date
    subprime.deploy.status       started | promoted | rolled_back | smoke_failed | metrics_failed
    subprime.deploy.actor        user initiating the deploy

DORA four metrics derive from these:
    deployment frequency  = count(status=promoted) / window
    lead time for changes = started_at − commit_at
    change failure rate   = count(rolled_back ∪ smoke_failed ∪ metrics_failed)
                          / count(status=promoted ∨ rolled_back ∨ …)
    MTTR                  = time from failure event → next promoted event

Usage:
    python scripts/dora_emit.py --color green --image finadvisor:local \\
        --status promoted --commit $(git rev-parse HEAD)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--color", required=True, choices=["blue", "green"])
    p.add_argument("--image", required=True)
    p.add_argument("--status", required=True,
                   choices=["started", "promoted", "rolled_back",
                            "smoke_failed", "metrics_failed"])
    p.add_argument("--commit", default=_git("rev-parse", "HEAD"))
    p.add_argument("--reason", default="")
    p.add_argument("--endpoint",
                   default=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT",
                                          "http://localhost:4318"))
    p.add_argument("--token",
                   default=os.environ.get("HYPERDX_INGEST_TOKEN", ""))
    args = p.parse_args()

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        print("opentelemetry not installed; install with `uv sync --dev`", file=sys.stderr)
        return 2

    commit_at = _git("show", "-s", "--format=%cI", args.commit) if args.commit else ""
    actor = os.environ.get("USER") or _git("config", "user.email") or "unknown"

    resource = Resource.create({
        SERVICE_NAME: "subprime-deploy",
        "subprime.color": args.color,
    })
    provider = TracerProvider(resource=resource)
    headers = {}
    if args.token:
        headers["authorization"] = args.token
    exporter = OTLPSpanExporter(endpoint=f"{args.endpoint}/v1/traces", headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("subprime.deploy")
    now = datetime.now(timezone.utc).isoformat()
    with tracer.start_as_current_span(f"deploy.{args.status}") as span:
        span.set_attribute("subprime.deploy.color", args.color)
        span.set_attribute("subprime.deploy.image", args.image)
        span.set_attribute("subprime.deploy.commit_sha", args.commit)
        span.set_attribute("subprime.deploy.status", args.status)
        span.set_attribute("subprime.deploy.started_at", now)
        if commit_at:
            span.set_attribute("subprime.deploy.commit_at", commit_at)
        span.set_attribute("subprime.deploy.actor", actor)
        if args.reason:
            span.set_attribute("subprime.deploy.reason", args.reason)
        if args.status in ("rolled_back", "smoke_failed", "metrics_failed"):
            span.set_status(trace.Status(trace.StatusCode.ERROR, args.reason or args.status))
        else:
            span.set_status(trace.Status(trace.StatusCode.OK))

    # Force flush so the span is on the wire before the deploy script moves on.
    provider.force_flush(5_000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
