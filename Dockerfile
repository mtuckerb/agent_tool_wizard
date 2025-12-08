FROM python:3.11-slim

# Workdir
WORKDIR /app

# System dependencies (tweak as needed)
RUN apt-get update && apt-get install -y \
    build-essential curl git ca-certificates && \
        rm -rf /var/lib/apt/lists/*

# Install Haystack + Hayhooks
# Pin or loosen versions to your preference
RUN pip install --no-cache-dir "haystack-ai[all]" "hayhooks>=1.1.0" "mcp"

# Copy pipelines (YAML + wrapper)
# Expecting:
# /app/pipelines/tool_router.yaml
# /app/pipelines/tool_router/pipeline_wrapper.py
COPY pipelines/ /app/pipelines/

# Entrypoint script: starts REST + MCP
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Environment for Hayhooks
ENV HAYHOOKS_PIPELINES_DIR=/app/pipelines
ENV HAYHOOKS_HOST=0.0.0.0
ENV HAYHOOKS_PORT=1417

# If MCP host/port are configurable, set them too
ENV HAYHOOKS_MCP_HOST=0.0.0.0
ENV HAYHOOKS_MCP_PORT=1418

# Let Haystack know where Ollama lives (override at run time if needed)
# For Podman you typically point to host.containers.internal or your LAN IP.
ENV OLLAMA_HOST=http://host.containers.internal:11434

EXPOSE 1417

CMD ["/app/entrypoint.sh"]

