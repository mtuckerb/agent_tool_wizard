# Agent_Multitool Enhancement Recipe

## 🎯 Objective
Transform agent_multitool into a production-ready AI tools hub with full MCP integration and intelligent LLM routing.

## 📋 Project Overview
**Location**: `/home/mtuckerb/workspace/mtuckerb/agent_multitool/`  
**Type**: Local AI tools hub with REST API + MCP server  
**Core Tech**: FastAPI, Docker, MCP, OpenAI/Ollama integration  
**Current Version**: 1.1.0 (Production-Ready with Enhanced Router)

## 🔍 Implementation Status

### ✅ **COMPLETED - Production Ready**
- **Enhanced Tool Router**: Intelligent tool selection with URL extraction
  - Automatic URL parameter parsing from natural language queries
  - Format validation bypass for tool_router compatibility
  - Token-efficient streaming mode for production use
- **MCP Integration**: 28+ tools operational from 6 servers
  - current-time server: time queries, timestamp conversion
  - curl server: web requests with automatic URL extraction
  - tts: Text-to-speech with multiple voice options
  - gemini: AI image generation capabilities
  - All environment issues resolved (npm/UVX compatibility)
- **Docker Environment**: Node.js 18 LTS + stable build process
- **API Endpoints**: OpenAI-compatible + MCP JSON-RPC endpoints
- **Configuration**: Working config.json with multiple MCP servers

### 🚧 **REMAINING REQUIREMENTS**
- **LLM Availability Checking**: Startup validation with proper error codes
- **Retry Logic**: Exponential backoff (300,900,1800ms) for LLM failures
- **LLM-Driven Tool Selection**: Enhanced beyond current keyword matching
- **Structured JSON Response**: LLM tool selection with server.tool format

## 🔧 **Current Architecture**

### Enhanced Tool Router Features
```python
# URL Extraction Algorithm
if any(keyword in user_input_lower for keyword in ['fetch', 'curl', 'http', 'web', 'url']):
    url_patterns = [
        r'https?://[^\s\)]+',   # Standard URLs
        r'https?://[^\s\(]+',   # URLs not ending in (
        r'https?://[^\s,\.]+'    # URLs not ending in , or .
    ]
    # Automatically extracts URLs and passes as parameters
```

### Working MCP Tools
```bash
✅ current-time: current_time, relative_time, convert_timestamp
✅ curl: fetch web content with automatic URL extraction
✅ tts: generate_speech (10 voices, speed control)
✅ gemini: generate_image (AI image creation)
✅ web-crawler: Full website crawling capabilities
✅ Additional tools from configured MCP servers
```

### Production Deployment
```bash
# Build and Run
docker build -t agent_multitool .
docker run -d -p 1417:1417 --name agent_multitool \
  -v "$(pwd)/config.json:/app/config.json:ro" \
  -e LLM_PROVIDER=ollama \
  -e LLM_BASE_URL=http://10.1.0.75:11434 \
  -e LLM_MODEL=glm-4.6:cloud \
  agent_multitool:latest
```

### Testing Examples
```bash
# URL Extraction Test
curl -s http://localhost:1417/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"tool_router","arguments":{"user_query":"fetch http://tuckerbradford.com"}}}'

# Time Query Test  
curl -s http://localhost:1417/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tool_router","arguments":{"user_query":"What time is it?"}}}'
```

## 🎯 **Next Development Phase**

### Immediate Tasks (This Session)
1. **Update RECIPE.md** ✅ *In Progress*
2. **Implement LLM startup health checks**
   - Validate at least 1 LLM provider available
   - Exit with non-zero code if no LLMs available
   - Provide detailed error diagnostics
3. **Add retry logic with exponential backoff**
   - 300ms → 900ms → 1800ms retry sequence
   - Error response with diagnostics after final failure
4. **Enhance LLM-based tool selection**
   - Move beyond keyword matching to true LLM intelligence
   - Request structured JSON response from LLM
   - Minimum fields: tool_server, tool_name, tool_parameters

## 🔍 **Technical Debt & Known Issues**
- All original npm/UVX issues resolved ✅
- Format validation bypass implemented ✅  
- Token efficiency optimized ✅
- Production build environment stable ✅

## 📊 **Performance Metrics**
- **MCP Tools Available**: 28+ from 6 servers
- **Startup Time**: ~15-20 seconds (MCP server initialization)
- **Response Time**: Sub-second for cached tools
- **Memory Usage**: ~200-400MB base + MCP servers
- **Docker Image Size**: ~800MB (Node.js 18 LTS + dependencies)
