#!/bin/bash
# Fixed entrypoint for agent_multitool

set -e

echo "🚀 Starting agent_multitool - LLM-powered MCP Router..."

# Environment setup - FIX HOME DIRECTORY
export HOME=/home/agent
export PYTHONPATH="${PYTHONPATH}:/app"  # ← FIXED: Single closing brace
export PYTHONUNBUFFERED=1

# Create necessary directories
mkdir -p $HOME/.config
mkdir -p $HOME/.npm

echo "🔧 User environment setup:"
echo "  - HOME: $HOME"  
echo "  - USER: $(whoami)"
echo "  - Config directory: $HOME/.config"

# Port configuration
export AGENT_PORT=${AGENT_PORT:-1417}
export MCP_PORT=${MCP_PORT:-1418}
export AGENT_NAME=${AGENT_NAME:-agent_multitool}
export AGENT_VERSION=${AGENT_VERSION:-1.0.0}

# LLM Configuration
export LLM_PROVIDER=${LLM_PROVIDER:-openai}
export LLM_MODEL=${LLM_MODEL:-gpt-3.5-turbo}
export LLM_BASE_URL=${LLM_BASE_URL:-}
export LLM_API_KEY=${LLM_API_KEY:-}

# Config location
export CONFIG_PATH=${CONFIG_PATH:-/app/config.json}

echo "📋 agent_multitool Configuration:"
echo "  - Agent Name: ${AGENT_NAME} v${AGENT_VERSION}"
echo "  - Agent Port: ${AGENT_PORT}"
echo "  - MCP Port: ${MCP_PORT}"
echo "  - LLM Provider: ${LLM_PROVIDER}"
echo "  - LLM Model: ${LLM_MODEL}"
echo "  - LLM Base URL: ${LLM_BASE_URL}"
echo "  - Config Path: ${CONFIG_PATH}"

# Create config if needed
if [ ! -f "$CONFIG_PATH" ]; then
    echo "⚠️  Config not found, creating minimal default..."
    mkdir -p "$(dirname "$CONFIG_PATH")"
    cat > "$CONFIG_PATH" << 'EOF'
{
  "llm": {
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "api_key": "your-api-key-here"
  },
  "mcpServers": {}
}
EOF
    echo "✅ Created default config at $CONFIG_PATH"
fi

# Health check
if python -c "
try:
    from pipelines.router.enhanced_pipeline_wrapper import app, AGENT_PORT
    print(f'✅ Enhanced agent app imports successfully on port {AGENT_PORT}')
except ImportError as e:
    print(f'❌ Import failed: {e}')
    exit(1)
except Exception as e:
    print(f'❌ Other error: {e}')
    exit(1)
"; then
    echo "🏥 Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

echo "🌟 Starting agent_multitool on port ${AGENT_PORT}..."

# Start the app
exec uvicorn pipelines.router.enhanced_pipeline_wrapper:app \
    --host 0.0.0.0 \
    --port $AGENT_PORT \
    --log-level info
