FROM python:3.12-slim

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

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
RUN mkdir -p /app/state/data /app/state/conversations

EXPOSE 8091

CMD ["uvicorn", "apps.web.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8091"]
