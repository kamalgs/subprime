# Pin the base image by digest — tag can be re-pushed with a malicious
# layer. Bump together with CI's trivy scan to ensure we know what landed.
# Current tag: python:3.12-slim (Debian bookworm, glibc).
FROM python@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

# Python-only image. The React frontend is built separately via
#     make frontend          (or: cd product/apps/web/frontend && npm run build)
# which outputs to product/apps/web/static/dist/. That directory is picked
# up by the `COPY product/apps/ ./apps/` below, so no Node tooling is
# required in this image.

# System hardening — non-login system account for the runtime.
RUN groupadd --system --gid 1001 benji \
 && useradd  --system --uid 1001 --gid benji --home-dir /app --shell /usr/sbin/nologin benji

# uv for fast deps install (pinned to a minor version so reproducible rebuilds
# aren't surprised by breaking changes in uv itself).
RUN pip install --no-cache-dir "uv>=0.4,<0.6"

WORKDIR /app

# Copy project files — product/ contains the real [project] definition
COPY product/pyproject.toml ./pyproject.toml
COPY product/README.md ./README.md
COPY product/src/ ./src/
COPY product/apps/ ./apps/

# Install dependencies into system python (no venv inside container)
RUN uv pip install --system --no-cache .

ENV PYTHONUNBUFFERED=1 \
    SUBPRIME_DATA_DIR=/app/state/data \
    SUBPRIME_CONVERSATIONS_DIR=/app/state/conversations

# Ensure state dirs exist (volume mounts will overlay /app/state at runtime)
# and give the unprivileged user ownership of its working directory.
RUN mkdir -p /app/state/data /app/state/conversations \
 && chown -R benji:benji /app

# Drop root for the runtime. Migrations run under this user too; DuckDB is
# write-capable only during the prestart hook, when no other process has
# the DB open.
USER benji

EXPOSE 8091

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; \
        r = urllib.request.urlopen('http://127.0.0.1:8091/api/v2/session', timeout=3); \
        sys.exit(0 if r.status == 200 else 1)" || exit 1

CMD ["uvicorn", "apps.web.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8091", "--timeout-keep-alive", "5"]
