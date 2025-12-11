#!/usr/bin/env python3
"""
Enhanced agent_multitool - LLM-powered MCP Router with full MCP integration
Includes complete MCP JSON-RPC endpoints and actual tool integration
"""

import json
import logging
import os
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, List
from dataclasses import dataclass
import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Port configuration (from environment)
AGENT_PORT = int(os.getenv("AGENT_PORT", "1417"))
AGENT_NAME = os.getenv("AGENT_NAME", "agent_multitool")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1.0.0")

# ==================== FASTAPI APP ====================

app = FastAPI(
    title=f"{AGENT_NAME}",
    version=AGENT_VERSION,
    description=f"Enhanced LLM-powered MCP Tool Router with full integration",
    docs_url="/docs"
)

# ==================== API MODELS ====================

class PipelineRequest(BaseModel):
    pipeline_name: str
    parameters: Dict[str, Any] = {}

class RouterRequest(BaseModel):
    input: str
    stream: bool = True
    use_tools: bool = False

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    server_name: Optional[str] = None

# ==================== LLM CLIENT ====================

@dataclass
class LLMConfig:
    provider: str = "openai"
    base_url: Optional[str] = None
    model: str = "gpt-3.5-turbo"
    api_key: Optional[str] = None

class StreamingLLMClient:
    """Streaming LLM client for multiple providers"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.provider = config.provider.lower()
        self.base_url = config.base_url
        self.model = config.model
        self.api_key = config.api_key or os.getenv(f"{self.provider.upper()}_API_KEY")
        
        # Default URLs
        if not self.base_url:
            if self.provider == "openai":
                self.base_url = "https://api.openai.com/v1"
            elif self.provider == "anthropic":
                self.base_url = "https://api.anthropic.com"
            elif self.provider == "ollama":
                self.base_url = "http://localhost:11434/v1"
    
    async def chat_completion_stream(self, messages: List[Dict], temperature: float = 0.1) -> AsyncGenerator[str, None]:
        """Stream chat completion from configured LLM provider"""
        
        if self.provider == "openai":
            async for chunk in self._openai_stream(messages, temperature):
                yield chunk
        elif self.provider == "ollama":
            async for chunk in self._ollama_stream(messages, temperature):
                yield chunk
        else:
            yield json.dumps({"error": f"Unsupported provider: {self.provider}"})
            return
    
    async def _openai_stream(self, messages: List[Dict], temperature: float):
        """OpenAI SSE streaming"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", 
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk_data = json.loads(line[6:])
                            content = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield json.dumps({
                                    "provider": "openai",
                                    "content": content,
                                    "model": self.model
                                })
                        except json.JSONDecodeError:
                            continue
    
    async def _ollama_stream(self, messages: List[Dict], temperature: float):
        """Ollama streaming"""
        headers = {"Content-Type": "application/json"}
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=data,
                    headers=headers
                ) as response:
                    buffer = ""
                    async for chunk in response.aiter_bytes():
                        buffer += chunk.decode('utf-8', errors='ignore')
                        lines = buffer.split('\n')
                        buffer = lines[-1]
                        
                        for line in lines[:-1]:
                            if line:
                                try:
                                    chunk_data = json.loads(line)
                                    content = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield json.dumps({
                                            "provider": "ollama",
                                            "content": content,
                                            "model": self.model
                                        })
                                except json.JSONDecodeError:
                                    continue
            except Exception as e:
                yield json.dumps({
                    "error": f"Connection to Ollama failed: {str(e)}",
                    "model": self.model
                })

# ==================== MCP CLIENT ====================

class MCPClient:
    """MCP client for connecting to MCP servers"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.servers = {}
        self.server_processes = {}
        
    async def initialize_servers(self):
        """Initialize all enabled MCP servers"""
        mcp_servers = self.config.get("mcpServers", {})
        
        for server_name, server_config in mcp_servers.items():
            if not server_config.get("enabled", True):
                continue
                
            try:
                await self._start_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to start MCP server {server_name}: {e}")
    
    async def _start_server(self, server_name: str, server_config: Dict[str, Any]):
        """Start a single MCP server"""
        command = server_config.get("command", [])
        args = server_config.get("args", [])
        env = server_config.get("env", {})
        
        # Merge with current environment
        server_env = os.environ.copy()
        server_env.update(env)
        
        logger.info(f"Starting MCP server {server_name}: {command} {' '.join(args)}")
        
        # Start the process
        process = await asyncio.create_subprocess_exec(
            *([command] + args),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=server_env
        )
        
        self.server_processes[server_name] = process
        
        # Initialize the server
        await self._initialize_server_connection(server_name, process)
    
    async def _initialize_server_connection(self, server_name: str, process):
        """Initialize connection to an MCP server"""
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "agent_multitool",
                    "version": "1.0.0"
                }
            }
        }
        
        # Send request
        request_json = json.dumps(init_request) + "\n"
        process.stdin.write(request_json.encode())
        await process.stdin.drain()
        
        # Read response (simplified for now)
        response_line = await process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.decode().strip())
                if "result" in response:
                    logger.info(f"MCP server {server_name} initialized successfully")
                    self.servers[server_name] = {
                        "process": process,
                        "capabilities": response["result"].get("capabilities", {})
                    }
                else:
                    logger.error(f"MCP server {server_name} initialization failed: {response}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode response from {server_name}: {e}")
    
    async def list_tools(self, server_name: Optional[str] = None) -> Dict[str, List[Dict]]:
        """List tools from MCP servers"""
        tools = {}
        
        servers_to_check = [server_name] if server_name else list(self.servers.keys())
        
        for name in servers_to_check:
            if name not in self.servers:
                continue
                
            process = self.servers[name]["process"]
            
            list_request = {
                "jsonrpc": "2.0",
                "id": f"list_tools_{name}",
                "method": "tools/list"
            }
            
            try:
                request_json = json.dumps(list_request) + "\n"
                process.stdin.write(request_json.encode())
                await process.stdin.drain()
                
                response_line = await process.stdout.readline()
                if response_line:
                    response = json.loads(response_line.decode().strip())
                    if "result" in response:
                        tools[name] = response["result"].get("tools", [])
                        
            except Exception as e:
                logger.error(f"Failed to list tools from {name}: {e}")
                tools[name] = []
        
        return tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on an MCP server"""
        if server_name not in self.servers:
            raise ValueError(f"Server {server_name} not available")
        
        process = self.servers[server_name]["process"]
        
        call_request = {
            "jsonrpc": "2.0",
            "id": f"call_{server_name}_{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            request_json = json.dumps(call_request) + "\n"
            process.stdin.write(request_json.encode())
            await process.stdin.drain()
            
            response_line = await process.stdout.readline()
            if response_line:
                response = json.loads(response_line.decode().strip())
                return response
            else:
                raise Exception("No response from server")
                
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_name}: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup all server processes"""
        for server_name, server_info in self.servers.items():
            process = server_info["process"]
            try:
                process.terminate()
                await process.wait()
                logger.info(f"Cleaned up MCP server {server_name}")
            except Exception as e:
                logger.error(f"Failed to cleanup {server_name}: {e}")
        
        self.servers.clear()
        self.server_processes.clear()

# ==================== ENHANCED ROUTER ====================

class EnhancedHaystackRouter:
    """Enhanced router with LLM streaming and MCP integration"""
    
    def __init__(self):
        # Load configuration
        self.config = self._load_config()
        
        # Initialize LLM client
        llm_config = LLMConfig(
            provider=os.getenv("LLM_PROVIDER", "openai"),
            base_url=os.getenv("LLM_BASE_URL"),
            model=os.getenv("LLM_MODEL", "gpt-3.5-turbo"),
            api_key=os.getenv("LLM_API_KEY")
        )
        self.llm_client = StreamingLLMClient(llm_config)
        
        # Initialize MCP client
        self.mcp_client = MCPClient(self.config)
        
        logger.info(f"Enhanced agent_multitool initialized on port {AGENT_PORT}")
    
    async def initialize(self):
        """Initialize the router and MCP servers"""
        await self.mcp_client.initialize_servers()
        tools = await self.mcp_client.list_tools()
        logger.info(f"Initialized {len(tools)} MCP servers with {sum(len(t) for t in tools.values())} tools")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load config from specified location"""
        config_path = Path(os.getenv("CONFIG_PATH", "/app/config.json"))
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                logger.info(f"Loaded config from {config_path}")
                return config
            else:
                logger.info(f"Config not found at {config_path}, using defaults")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        
        # Default config
        return {
            "llm": {
                "provider": os.getenv("LLM_PROVIDER", "openai"),
                "base_url": os.getenv("LLM_BASE_URL", ""),
                "model": os.getenv("LLM_MODEL", "gpt-3.5-turbo"),
                "api_key": os.getenv("LLM_API_KEY", "")
            },
            "mcpServers": {}
        }
    
    async def route_request_stream(self, user_input: str, use_tools: bool = False) -> AsyncGenerator[str, None]:
        """Main streaming routing with optional MCP tool integration"""
        
        yield json.dumps({
            "stage": "start",
            "request": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "via": "agent_multitool",
            "port": AGENT_PORT,
            "use_tools": use_tools
        })
        
        try:
            if use_tools:
                # Enhanced routing with tool integration
                async for chunk in self._route_with_tools(user_input):
                    yield chunk
            else:
                # Simple LLM routing
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_input}
                ]
                
                yield json.dumps({
                    "stage": "llm_processing",
                    "provider": self.llm_client.provider,
                    "model": self.llm_client.model
                })
                
                full_response = ""
                async for chunk_str in self.llm_client.chat_completion_stream(messages):
                    chunk = json.loads(chunk_str)
                    content = chunk.get("content", "")
                    full_response += content
                    
                    yield json.dumps({
                        "stage": "llm_streaming",
                        "content": content,
                        "provider": chunk.get("provider")
                    })
                
                yield json.dumps({
                    "stage": "complete",
                    "result": {
                        "response": full_response.strip(),
                        "service": AGENT_NAME,
                        "port": AGENT_PORT
                    }
                })
            
        except Exception as e:
            yield json.dumps({
                "stage": "error",
                "error": f"Processing failed: {str(e)}"
            })
    
    async def _route_with_tools(self, user_input: str) -> AsyncGenerator[str, None]:
        """Route request with MCP tool integration"""
        
        yield json.dumps({
            "stage": "tool_discovery",
            "message": "Discovering available tools"
        })
        
        # Get available tools
        tools = await self.mcp_client.list_tools()
        
        yield json.dumps({
            "stage": "tools_discovered",
            "servers": list(tools.keys()),
            "total_tools": sum(len(server_tools) for server_tools in tools.values())
        })
        
        # For now, just return the tools list
        # In a full implementation, you would use LLM to select and execute tools
        yield json.dumps({
            "stage": "tool_analysis",
            "message": "Available tools discovered",
            "tools": tools
        })
        
        # Get LLM response with tool awareness
        system_prompt = f"""You are a helpful assistant with access to the following tools:

Available MCP servers and tools:
{json.dumps(tools, indent=2)}

When the user asks for something that can be handled by these tools, mention that the tools are available.
For now, just provide a helpful response about what's possible."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        full_response = ""
        async for chunk_str in self.llm_client.chat_completion_stream(messages):
            chunk = json.loads(chunk_str)
            content = chunk.get("content", "")
            full_response += content
            
            yield json.dumps({
                "stage": "llm_with_tools",
                "content": content,
                "provider": chunk.get("provider")
            })
        
        yield json.dumps({
            "stage": "complete_with_tools",
            "result": {
                "response": full_response.strip(),
                "available_tools": tools,
                "service": AGENT_NAME,
                "port": AGENT_PORT
            }
        })

# Global router instance
router = None

async def get_router():
    global router
    if router is None:
        router = EnhancedHaystackRouter()
        await router.initialize()
    return router

# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": AGENT_NAME,
        "version": AGENT_VERSION,
        "port": AGENT_PORT,
        "description": "Enhanced LLM-powered MCP Tool Router",
        "endpoints": {
            "health": f"/api/health",
            "router": f"/api/router",
            "tools": "/api/tools",
            "tool_call": "/api/tools/call",
            "mcp": "/mcp",
            "mcp_stream": "/mcp/stream",
            "docs": "/docs"
        }
    }

@app.get("/api/health")
async def health_check():
    """Comprehensive health check"""
    try:
        current_router = await get_router()
        mcp_servers = list(current_router.mcp_client.servers.keys())
        
        return {
            "status": "healthy",
            "service": AGENT_NAME,
            "port": AGENT_PORT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mcp_servers": {
                "total": len(mcp_servers),
                "active": mcp_servers
            },
            "llm": {
                "provider": current_router.llm_client.provider,
                "model": current_router.llm_client.model
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.post("/api/router")
async def route_request(request: RouterRequest):
    """Main router endpoint with streaming and optional tool integration"""
    current_router = await get_router()
    
    async def generate():
        async for chunk in current_router.route_request_stream(request.input, request.use_tools):
            yield f"data: {chunk}\n\n"
        yield f"data: {json.dumps({'stage': 'complete'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/tools")
async def list_tools():
    """List all available tools from all MCP servers"""
    try:
        current_router = await get_router()
        tools = await current_router.mcp_client.list_tools()
        
        return {
            "servers": len(tools),
            "total_tools": sum(len(server_tools) for server_tools in tools.values()),
            "tools": tools
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tools/call")
async def call_tool(request: ToolCallRequest):
    """Call a specific tool on an MCP server"""
    try:
        current_router = await get_router()
        
        if not request.server_name:
            raise HTTPException(status_code=400, detail="server_name is required")
        
        result = await current_router.mcp_client.call_tool(
            request.server_name,
            request.tool_name,
            request.arguments
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== MCP JSON-RPC ENDPOINTS (Enhanced) ====================

@app.post("/mcp")
async def mcp_handler(request: dict):
    """Enhanced MCP JSON-RPC endpoint"""
    try:
        current_router = await get_router()
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {
                            "listChanged": True
                        }
                    },
                    "serverInfo": {
                        "name": "agent_multitool",
                        "version": "1.0.0"
                    }
                }
            }
        
        elif method == "tools/list":
            tools = await current_router.mcp_client.list_tools()
            all_tools = []
            
            for server_name, server_tools in tools.items():
                for tool in server_tools:
                    # Add server prefix to tool name
                    tool_name = f"{server_name}.{tool['name']}"
                    all_tools.append({
                        "name": tool_name,
                        "description": f"{tool['description']} (from {server_name})",
                        "inputSchema": tool.get("inputSchema", {})
                    })
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": all_tools
                }
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            # Parse server.tool format
            if "." in tool_name:
                server_name, clean_tool_name = tool_name.split(".", 1)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": f"Tool name must be in format 'server.tool', got: {tool_name}"
                    }
                }
            
            try:
                result = await current_router.mcp_client.call_tool(
                    server_name,
                    clean_tool_name,
                    arguments
                )
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result.get("result", {})
                }
                
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"Tool call failed: {str(e)}"
                    }
                }
        
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
            
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }

@app.post("/mcp/stream")
async def mcp_handler_stream(request: dict):
    """MCP JSON-RPC streaming endpoint"""
    current_router = await get_router()
    
    async def generate():
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        yield f"data: {json.dumps({'event': 'start', 'method': method, 'id': request_id})}\n\n"
        
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if "." in tool_name:
                server_name, clean_tool_name = tool_name.split(".", 1)
                
                try:
                    result = await current_router.mcp_client.call_tool(
                        server_name,
                        clean_tool_name,
                        arguments
                    )
                    
                    yield f"data: {json.dumps({'event': 'result', 'data': result.get('result', {})})}\n\n"
                    
                except Exception as e:
                    yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
            else:
                yield f"data: {json.dumps({'event': 'error', 'error': 'Invalid tool format'})}\n\n"
        
        yield f"data: {json.dumps({'event': 'complete'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# OpenAI-compatible endpoints (unchanged but using enhanced router)
@app.post("/v1/chat/completions")
async def openai_compatible_chat(request: dict):
    """OpenAI-compatible chat completions"""
    try:
        current_router = await get_router()
        messages = request.get("messages", [])
        
        full_response = ""
        async for chunk_str in current_router.llm_client.chat_completion_stream(messages):
            chunk = json.loads(chunk_str)
            content = chunk.get("content", "")
            full_response += content
        
        return {
            "id": f"chatcmpl-{datetime.now().timestamp()}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": current_router.llm_client.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant", 
                        "content": full_response.strip()
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models endpoint"""
    try:
        current_router = await get_router()
        return {
            "object": "list",
            "data": [
                {
                    "id": current_router.llm_client.model,
                    "object": "model",
                    "created": int(datetime.now().timestamp()),
                    "owned_by": current_router.llm_client.provider
                }
            ]
        }
    except Exception as e:
        return {"object": "list", "data": []}

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup MCP connections on shutdown"""
    global router
    if router:
        await router.mcp_client.cleanup()
        logger.info("Enhanced agent_multitool shutdown complete")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Enhanced {AGENT_NAME} on port {AGENT_PORT}")
    uvicorn.run(
        "enhanced_pipeline_wrapper:app",
        host="0.0.0.0",
        port=AGENT_PORT,
        reload=False,
        log_level="info"
    )
