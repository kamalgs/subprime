FROM python:3.12-slim

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY apps/ ./apps/

# Install dependencies into system python (no venv inside container)
RUN uv pip install --system --no-cache .

# Gradio server defaults (overridable via env)
ENV GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=8091 \
    PYTHONUNBUFFERED=1 \
    SUBPRIME_DATA_DIR=/app/state/data

# Ensure state dirs exist (volume mounts will overlay /app/state at runtime)
RUN mkdir -p /app/state/data /app/state/conversations

EXPOSE 8091

# Launch the Gradio web app (binds to GRADIO_SERVER_NAME/PORT)
CMD ["python", "-c", "from apps.web.app import CSS, create_app; import os; create_app().launch(server_name=os.environ.get('GRADIO_SERVER_NAME', '0.0.0.0'), server_port=int(os.environ.get('GRADIO_SERVER_PORT', '8091')), css=CSS)"]
