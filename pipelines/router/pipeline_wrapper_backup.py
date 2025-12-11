#!/usr/bin/env python3
"""
agent_multitool - LLM-powered MCP Router with streaming
Includes complete MCP JSON-RPC endpoints
"""

import json
import logging
import os
import asyncio
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
    description=f"LLM-powered MCP Tool Router on port {AGENT_PORT}",
    docs_url="/docs"
)

# ==================== API MODELS ====================

class PipelineRequest(BaseModel):
    pipeline_name: str
    parameters: Dict[str, Any] = {}

class RouterRequest(BaseModel):
    input: str
    stream: bool = True

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
        """Ollama streaming using native API"""
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
                    f"{self.base_url}/api/chat",
                    json=data,
                    headers=headers
                ) as response:
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                chunk_data = json.loads(line)
                                content = chunk_data.get("message", {}).get("content", "")
                                if content:
                                    yield json.dumps({
                                        "provider": "ollama",
                                        "content": content,
                                        "model": self.model
                                    })
                                elif chunk_data.get("done"):
                                    # Stream finished
                                    break
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                yield json.dumps({
                    "error": f"Connection to Ollama failed: {str(e)}",
                    "model": self.model
                })

# ==================== MAIN ROUTER ====================

class EnhancedHaystackRouter:
    """Enhanced router with LLM streaming"""
    
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
        
        logger.info(f"agent_multitool initialized on port {AGENT_PORT}")
    
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
    
    async def route_request_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """Main streaming routing"""
        
        yield json.dumps({
            "stage": "start",
            "request": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "via": "agent_multitool",
            "port": AGENT_PORT
        })
        
        try:
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

# Global router instance
router = None

def get_router():
    global router
    if router is None:
        router = EnhancedHaystackRouter()
    return router

# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": AGENT_NAME,
        "version": AGENT_VERSION,
        "port": AGENT_PORT,
        "description": "LLM-powered MCP Tool Router",
        "endpoints": {
            "health": f"/api/health",
            "router": f"/api/router",
            "mcp": "/mcp",
            "mcp_stream": "/mcp/stream",
            "docs": "/docs"
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": AGENT_NAME,
        "port": AGENT_PORT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/router")
async def route_request(request: RouterRequest):
    """Main router endpoint with streaming"""
    current_router = get_router()
    
    async def generate():
        async for chunk in current_router.route_request_stream(request.input):
            yield f"data: {chunk}\n\n"
        yield f"data: {json.dumps({'stage': 'complete'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# ==================== MCP JSON-RPC ENDPOINTS ====================

@app.post("/mcp")
async def mcp_handler(request: dict):
    """MCP JSON-RPC endpoint"""
    try:
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
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "agent_multitool",
                        "version": "1.0.0"
                    }
                }
            }
        
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "tool_router",
                            "description": "LLM-powered tool routing with streaming support",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "input": {"type": "string", "description": "User input to route"}
                                },
                                "required": ["input"]
                            }
                        }
                    ]
                }
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "tool_router":
                current_router = get_router()
                user_input = arguments.get("input", "")
                
                # Collect streaming response
                result_chunks = []
                async for chunk in current_router.route_request_stream(user_input):
                    chunk_data = json.loads(chunk)
                    result_chunks.append(chunk_data)
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_chunks, indent=2)
                            }
                        ]
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
    current_router = get_router()
    
    async def generate():
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        yield f"data: {json.dumps({'event': 'start', 'method': method, 'id': request_id})}\n\n"
        
        if method == "tools/call" and params.get("name") == "tool_router":
            user_input = params.get("arguments", {}).get("input", "")
            
            async for chunk in current_router.route_request_stream(user_input):
                yield f"data: {json.dumps({'event': 'chunk', 'data': json.loads(chunk)})}\n\n"
        
        yield f"data: {json.dumps({'event': 'complete'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/mcp")
async def mcp_info():
    """MCP server info"""
    return {
        "name": "agent_multitool",
        "version": "1.0.0",
        "description": "LLM-powered MCP Tool Router",
        "endpoints": {
            "mcp": "/mcp (JSON-RPC)",
            "mcp_stream": "/mcp/stream (SSE)",
            "api": "/api/* (REST API)"
        }
    }

# OpenAI-compatible endpoints
@app.post("/v1/chat/completions")
async def openai_compatible_chat(request: dict):
    """OpenAI-compatible chat completions"""
    try:
        current_router = get_router()
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
        current_router = get_router()
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

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting {AGENT_NAME} on port {AGENT_PORT}")
    uvicorn.run(
        "pipeline_wrapper:app",
        host="0.0.0.0",
        port=AGENT_PORT,
        reload=False,
        log_level="info"
    )
