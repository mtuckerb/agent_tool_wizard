# agent_multitool - Production-Ready AI Tools Hub

A powerful AI tools hub with LLM-powered routing and full MCP (Model Context Protocol) integration - transforming from basic LLM responses to actual tool execution.

## 🎯 Key Features

- **🤖 LLM-First Tool Selection**: Intelligent routing based on tool descriptions
- **🔧 Real Tool Execution**: Beyond chat - actual package management, development tools, services
- **📦 Package Manager Integration**: uv, uvx, bun, npm, npx as environment resources  
- **⚡ Streaming Workflow**: Real-time tool discovery, selection, and execution
- **🏗️ Multi-Provider Ready**: Designed for future proxy architecture
- **🐳 Production Container**: Dockerized with proper environment setup

## 🔄 Enhanced AI Workflow

```
User Query → Tool Discovery → LLM Selection → Tool Execution → Result
     ↓              ↓              ↓              ↓         ↓
"What time is it?"  →  [time_tools]  →  "current-time.get"  →  [tool call]  →  "3:30 PM EST"
```

**Two-Pass Architecture:**
1. **Discovery**: Router finds available MCP tools with descriptions
2. **Selection**: LLM chooses best tool based on user query  
3. **Execution**: Router executes selected tool with proper arguments
4. **Response**: Tool result returned to user

## 🚀 Quick Start

### 1. Build and Run Enhanced Container

```bash
# Build the enhanced image
docker build -t agent_multitool:enhanced -f Dockerfile.enhanced .

# Run with MCP configuration
docker run -d --name agent_multitool \
  -p 1417:1417 \
  -v $(pwd)/config.json:/app/config.json \
  -e LLM_PROVIDER=ollama \
  -e LLM_BASE_URL=http://10.1.0.75:11434 \
  -e LLM_MODEL=glm-4.6:cloud \
  agent_multitool:enhanced
```

### 2. Test Tool Integration

#### Health Check
```bash
curl -s http://localhost:1417/api/health | jq .
```

#### Tool Discovery (MCP Protocol)
```bash
curl -s -X POST http://localhost:1417/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"list-1","method":"tools/list"}' | jq .
```

#### Tool Execution (Server.Tool Format)
```bash
curl -s -X POST http://localhost:1417/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":"call-1", 
    "method":"tools/call",
    "params":{
      "name":"development-tools.create_python_project",
      "arguments":{"project_name":"myapp","dependencies":["fastapi","sqlalchemy"]}
    }
  }' | jq .
```

#### Streaming with Intelligence
```bash
curl -s -X POST http://localhost:1417/api/router \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Create a Python project with authentication",
    "stream": true,
    "use_tools": true
  }' --no-buffer
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                      │
├─────────────────────────────────────────────────────────┤
│  API Router (Enhanced Pipeline Wrapper)                │
│  ├── Tool Discovery                                     │
│  ├── LLM-Based Selection                                │
│  └── Execution Coordination                             │
├─────────────────────────────────────────────────────────┤
│              MCP Server Integration                     │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Package Tools  │  │  Business Logic │              │
│  │  (Env Resources)│  │  (MCP Endpoints)│              │
│  └─────────────────┘  └─────────────────┘              │
│        uv, npm, bun          create_project, etc.        │
├─────────────────────────────────────────────────────────┤
│                Package Managers (Environment)            │
│  • uv & uvx  • npm & npx  • bun  (in container PATH)   │
├─────────────────────────────────────────────────────────┤
│                    Ollama LLM                           │
│              glm-4.6:cloud (or any model)               │
└─────────────────────────────────────────────────────────┘
```

## 📋 Configuration

### MCP Server Configuration (config.json)

The system reads mcpServers from config.json and executes commands with proper args and env:

```json
{
  "mcpServers": {
    "current-time": {
      "command": "npx",
      "args": ["@mcpcentral/mcp-time"],
      "env": {},
      "enabled": true
    },
    "filesystem": {
      "command": "npx", 
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app"],
      "env": {},
      "enabled": true
    },
    "development-tools": {
      "command": "python3",
      "args": ["/app/mcp_custom_dev_tools.py"],
      "env": {
        "PATH": "/root/.cargo/bin:/root/.bun/bin:/usr/local/bin:/usr/bin:/bin"
      },
      "cwd": "/app",
      "enabled": true
    }
  }
}
```

### Environment Variables

- `CONFIG_PATH`: Path to config.json (default: `/app/config.json`)
- `LLM_PROVIDER`: ollama, openai, anthropic (default: `openai`)
- `LLM_BASE_URL`: Base URL for LLM provider (default varies by provider)
- `LLM_MODEL`: Model name (default: varies by provider)
- `AGENT_PORT`: API port (default: `1417`)
- `AGENT_NAME`: Service name (default: `agent_multitool`)

## 🛠️ Available Tools

### High-Level Business Logic Tools
- **create_python_project**: Creates Python projects using uv/pip transparently
- **create_nodejs_project**: Creates Node.js projects using npm/bun automatically  
- **install_packages**: Cross-ecosystem package management
- **run_command**: Context-aware command execution
- **list_dependencies**: Project dependency analysis

### Community MCP Servers
- **current-time**: Date/time functionality
- **filesystem**: File operations and navigation
- **git**: Git repository operations  
- **curl**: HTTP/web requests
- **sequential-thinking**: Structured reasoning

### Environment Resources 
- **Package Managers**: uv, uvx, npm, npx, bun (environment variables, not user-facing)
- **Available to tools**: Used transparently by high-level tools

## 🌟 Integration Examples

### OpenAI-Compatible Clients
```bash
# Compatible with OpenWebUI, Letta, etc.
curl -X POST http://localhost:1417/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-4.6:cloud",
    "messages": [
      {"role": "user", "content": "Create a FastAPI app"}
    ]
  }'
```

### MCP Clients
```bash
# Compatible with Claude Code, Cline, MCP Inspector
# Server URL: http://localhost:1417/mcp
# Protocol: JSON-RPC over HTTP
# Tool Format: server.tool (proper MCP compliance)
```

### Intelligent Streaming
```bash
# Watch the workflow stages:
# tool_discovery → tools_discovered → tool_selection → tool_executing → result
curl -X POST http://localhost:1417/api/router \
  -H "Content-Type: application/json" \
  -d '{"input":"Help me build a web app","stream":true,"use_tools":true}' \
  --no-buffer
```

## 📊 Status

### ✅ Working Features

- **Enhanced Container**: Docker with package managers (uv, npm, bun)
- **MCP Integration**: Full protocol compliance with server.tool naming
- **LLM Routing**: Intelligent tool selection based on descriptions  
- **Streaming Workflow**: Real-time execution with stage notifications
- **Environment Setup**: Proper PATH and dependency management
- **OpenAI Compatibility**: Existing clients work seamlessly
- **Production Ready**: Error handling, logging, health checks

### 🚧 Development Focus

- **MCP Server Timeouts**: Some npm packages initialization can be slow
- **Module Directory**: Future support for user-defined custom MCP servers
- **Multi-Provider Proxy**: Planned architecture for advanced routing

### 🎯 Future Vision

- **Multi-Provider Proxy**: Route between different LLM and tool providers
- **Custom Module Directory**: Users can add home-built packages via volume mapping
- **Advanced Tool Selection**: More sophisticated LLM routing algorithms
- **Production Scaling**: Multi-instance deployment and load balancing

## 🛠️ Development

### Adding New MCP Servers

1. Add server to `config.json`:
```json
"my-tool": {
  "command": "python3",
  "args": ["/app/modules/my_tool.py"],
  "env": {"API_KEY": "key"},
  "enabled": true
}
```

2. The tool automatically appears for LLM selection
3. LLM can call `my-tool.function_name` based on user requests

### Module Directory (Planned)

Future architecture will support:
```bash
docker run -v /path/to/modules:/app/modules agent_multitool
```

Users can add custom MCP servers to `/modules/mypackage/` and reference them in config.

## 🔧 Troubleshooting

### MCP Servers Not Loading
- Check container logs: `docker logs agent_multitool`
- Verify command paths: `docker exec agent_multitool which npx`
- Environment variables: `docker exec agent_multitool env`

### Slow Initialization
- Some npm packages (current-time) can be slow to initialize
- Consider pre-building packages or using local alternatives
- Check network connectivity and npm registry access

### Tool Format Errors
- Use proper `server.tool` format: `development-tools.create_python_project`
- Check tool list: `curl http://localhost:1417/mcp -d '{"method":"tools/list"}'`

## 📈 Architecture Benefits

✅ **User-Friendly**: High-level semantic tools vs low-level commands  
✅ **Intelligent**: LLM chooses best tool based on descriptions  
✅ **Extensible**: Easy to add new MCP servers via config  
✅ **Production-Ready**: Proper error handling, logging, scaling  
✅ **Protocol Compliant**: Full MCP JSON-RPC implementation  
✅ **Future-Proof**: Ready for multi-provider proxy architecture  

## License

This project is open source. See LICENSE file for details.
