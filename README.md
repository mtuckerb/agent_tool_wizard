# AI Tools Hub - Haystack + Hayhooks + MCP

A local AI tools hub built on NixOS that provides:

- **Rest API endpoints** via Haystack + Hayhooks
- **OpenAI-compatible chat completions** for OpenWebUI, Letta, etc.
- **MCP server endpoint** for MCP Inspector, Cline, Claude Code
- **Dynamic MCP tool integration** from JSON configuration
- **Ollama model integration** (glm-4.6:cloud)

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  OpenWebUI      │    │  Letta          │    │  Claude Code    │
│  (Chat completions)│ │ (Chat completions)│ │ (MCP Client)    │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         │              ┌───────┴───────┐              │
         └──────────────│  Haystack     │──────────────┘
                        │  Hayhooks     │
                        ├── REST API    │
                        ├── OpenAI API  │
                        └── MCP Server  │
         ┌───────────────────────────────────────────┐
         │            MCP Tools                      │
         │  (obsidian, curl, github, time, etc.)    │
         └───────────────────────────────────────────┘
                        │
                        │
                 ┌──────┴──────┐
                 │  Ollama     │
                 │  glm-4.6:cloud │
                 └─────────────┘
```

## Quick Start

### 1. Build and Run

```bash
# Build the Docker image
podman build -t haystack-hayhooks .

# Run the container
podman run -d --name hayhooks \
  -p 1417:1417 \   # REST + OpenAI endpoints
  -p 1418:1418 \   # MCP endpoint
  -v "/data/mcp-proxy/mcpServers.json:/config/mcpServers.json:ro" \
  -e "OLLAMA_HOST=http://10.1.0.75:11434" \
  haystack-hayhooks
```

### 2. Test the Endpoints

#### REST API
```bash
# List available pipelines
curl http://localhost:1417/v1/models

# Chat completion (OpenAI compatible)
curl -X POST http://localhost:1417/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router",
    "messages": [
      {"role": "user", "content": "Hello, test message!"}
    ]
  }'
```

#### MCP Endpoint
```bash
# The MCP server runs on port 1418
# Use with MCP Inspector, Cline, Claude Code, etc.
# Server URL: http://localhost:1418/mcp
```

## Project Structure

```
/your-project/
├── Dockerfile                 # Container build definition
├── entrypoint.sh             # Start script for hayhooks
├── config.json               # MCP server configuration
├── pipelines/
│   ├── router/
│   │   └── pipeline_wrapper.py  # Main router logic
│   └── ...
└── README.md
```

## Configuration

### MCP Servers (config.json)

The `config.json` file defines which MCP servers are available:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "/run/current-system/sw/bin/npx",
      "args": ["-y", "obsidian-mcp-server"],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key",
        "OBSIDIAN_BASE_URL": "https://10.1.0.31:27124"
      },
      "enabled": true
    },
    "curl": {
      "command": "npx",
      "args": ["-y", "@mcp-get-community/server-curl"],
      "enabled": true
    },
    "github-official": {
      "command": "/run/current-system/sw/bin/podman",
      "args": [
        "run", "-i", "--rm", 
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token"
      },
      "enabled": false
    }
  }
}
```

### Environment Variables

- `OLLAMA_HOST`: URL to your Ollama instance (default: `http://host.containers.internal:11434`)
- `HAYHOOKS_HOST`: Host for REST API (default: `0.0.0.0`)
- `HAYHOOKS_PORT`: Port for REST API (default: `1417`)
- `HAYHOOKS_MCP_HOST`: Host for MCP server (default: `0.0.0.0`)
- `HAYHOOKS_MCP_PORT`: Port for MCP server (default: `1418`)

## Development

### Pipeline Wrapper

The main logic lives in `pipelines/router/pipeline_wrapper.py`:

```python
class PipelineWrapper(BasePipelineWrapper):
    def setup(self):
        # Load MCP server configuration
        # Initialize tools
        # Setup Haystack pipeline
        
    async def run_api(self, request):
        # REST API logic
        
    async def run_chat_completion(self, model, messages, body):
        # OpenAI-compatible chat completions
```

### Adding New MCP Tools

1. Add the server configuration to `config.json`
2. Set `enabled: true`
3. Restart the container
4. The tools will be automatically loaded

## Integration Examples

### OpenWebUI

Set up OpenWebUI to use hayhooks as the backend:

- **Base URL**: `http://localhost:1417`
- **API Path**: `/v1`
- **Model Name**: `router`

### Letta

Configure Letta to use the OpenAI-compatible endpoint:

- **Base URL**: `http://localhost:1417/v1`
- **Model**: `router`

### Claude Code / Cline

Configure as an MCP server:

- **Server URL**: `http://localhost:1418/mcp`
- **Transport**: HTTP (via hayhooks MCP server)

## Status

### ✅ Working

- Basic Hayhooks infrastructure
- REST API endpoints
- OpenAI-compatible chat completions (basic)
- MCP server endpoint (basic)
- Docker containerization
- Pipeline wrapper skeleton

### 🚧 In Progress

- MCP tool integration (dynamic loading)
- Ollama model integration
- Error handling and validation
- Proper async tool calling

### 📋 Todo

- Complete MCP tool integration
- Add proper async handling for MCP tools
- Add logging and monitoring
- Create comprehensive tests
- Add authentication/security
- Performance optimization

## Troubleshooting

### Pipeline Not Deploying

Check the container logs for errors:

```bash
docker logs hayhooks-test
```

Common issues:
- Missing `mcpServers.json` at `/config/mcpServers.json`
- MCP server commands not found
- Missing environment variables

### MCP Tools Not Loading

1. Verify the MCP server is accessible from the container
2. Check that all required environment variables are set
3. Ensure the MCP server is compatible with stdio transport

### Model Connection Issues

1. Verify Ollama is accessible from the container
2. Check the `OLLAMA_HOST` environment variable
3. Ensure the model `ollama/glm-4.6:cloud` is available

## License

This project is open source. See LICENSE file for details.
