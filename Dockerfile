FROM python:3.11-slim

# System dependencies
RUN apt-get update && \
    apt-get install -y curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --upgrade pip
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Set work directory
WORKDIR /app

# Create agent_multitool user and directories
RUN useradd -m -u 1000 agent && \
    mkdir /data && \
    chown -R agent:agent /data && \
    mkdir -p /home/agent/.config && \
    chown -R agent:agent /app

# Switch to agent user
USER agent
# Copy application code
COPY pipelines/ ./pipelines/
COPY requirements.txt ./
COPY entrypoint.sh /app/entrypoint.sh
USER root
RUN chmod +x /app/entrypoint.sh
RUN chown -R agent .
USER agent
# Set environment variables
ENV AGENT_NAME=agent_multitool
ENV AGENT_VERSION=1.0.0
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:1417/api/health || exit 1

# Expose ports
EXPOSE 1417

CMD ["/app/entrypoint.sh"]
