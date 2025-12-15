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
                self.base_url = "http://localhost:11434"
    
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
        
        # Convert messages format to Ollama format
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"System: {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n\n"
            elif msg["role"] == "assistant":
                prompt += f"Assistant: {msg['content']}\n\n"
        
        # Add final prompt for assistant response
        prompt += "Assistant: "
        
        data = {
            "model": self.model,
            "prompt": prompt.strip(),
            "stream": True,
            "options": {
                "temperature": temperature
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=data,
                    headers=headers
                ) as response:
                    full_response = ""
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk_data = json.loads(line)
                                if "response" in chunk_data:
                                    content = chunk_data["response"]
                                    full_response += content
                                    yield json.dumps({
                                        "provider": "ollama",
                                        "content": content,
                                        "model": self.model
                                    })
                                if chunk_data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    # Return complete response at the end for parsing
                    yield json.dumps({
                        "provider": "ollama",
                        "content": "",
                        "model": self.model,
                        "complete": full_response
                    })
                    
            except Exception as e:
                yield json.dumps({
                    "error": f"Connection to Ollama failed: {str(e)}",
                    "model": self.model
                })

class LLMHealthChecker:
    """Health checking for LLM providers with retry logic"""
    
    def __init__(self, llm_client: StreamingLLMClient):
        self.llm_client = llm_client
        self.retry_delays = [300, 900, 1800]  # ms
    
    async def check_llm_availability(self) -> Dict[str, Any]:
        """Check if LLM provider is available with retry logic"""
        for attempt, delay_ms in enumerate([0] + self.retry_delays):
            if attempt > 0:
                await asyncio.sleep(delay_ms / 1000)
            
            try:
                # Simple health check message
                test_messages = [
                    {"role": "user", "content": "test"}
                ]
                
                # Try to get first chunk of response
                async for chunk_str in self.llm_client.chat_completion_stream(test_messages):
                    chunk = json.loads(chunk_str)
                    if chunk.get("content") or chunk.get("error"):
                        return {
                            "available": True,
                            "provider": self.llm_client.provider,
                            "model": self.llm_client.model,
                            "attempt": attempt + 1
                        }
                    break
                    
            except Exception as e:
                if attempt == len(self.retry_delays):
                    # Final attempt failed
                    return {
                        "available": False,
                        "provider": self.llm_client.provider,
                        "model": self.llm_client.model,
                        "error": str(e),
                        "attempts_made": attempt + 1
                    }
                continue
        
        return {
            "available": False,
            "provider": self.llm_client.provider,
            "model": self.llm_client.model,
            "error": "No response received",
            "attempts_made": len(self.retry_delays) + 1
        }
    
    async def call_with_retry(self, messages: List[Dict], temperature: float = 0.1) -> AsyncGenerator[str, None]:
        """Call LLM with automatic retry logic"""
        for attempt, delay_ms in enumerate([0] + self.retry_delays):
            if attempt > 0:
                yield json.dumps({
                    "retry": {
                        "attempt": attempt + 1,
                        "delay_ms": delay_ms,
                        "provider": self.llm_client.provider
                    }
                })
                await asyncio.sleep(delay_ms / 1000)
            
            try:
                async for chunk in self.llm_client.chat_completion_stream(messages, temperature):
                    yield chunk
                return
            except Exception as e:
                if attempt == len(self.retry_delays):
                    # Final attempt failed
                    yield json.dumps({
                        "error": {
                            "message": f"LLM unavailable after {attempt + 1} attempts",
                            "provider": self.llm_client.provider,
                            "model": self.llm_client.model,
                            "final_error": str(e),
                            "attempts_made": attempt + 1
                        }
                    })
                    return
                continue

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
            
            # Read response more robustly - handle multi-line/large responses
            response_buffer = b""
            while True:
                chunk = await process.stdout.read(8192)  # Read in larger chunks
                if not chunk:
                    break
                response_buffer += chunk
                
                # Try to parse what we have so far
                try:
                    # Find the end of a complete JSON response (newline terminated)
                    response_str = response_buffer.decode().strip()
                    if response_str.endswith('\n'):
                        response_str = response_str.rstrip('\n')
                    if response_str:
                        logger.info(f"Parsing {len(response_str)} bytes from {server_name}.{tool_name}")
                        response = json.loads(response_str)
                        
                        # Check if this looks like an image response and handle appropriately
                        result = response.get("result", {})
                        if self._is_large_image_response(result):
                            logger.warning(f"Large image response detected from {server_name}.{tool_name} ({len(response_str)} bytes)")
                            # Truncate image data for practical use
                            if "content" in result and isinstance(result["content"], list):
                                for content_item in result["content"]:
                                    if isinstance(content_item, dict) and "image" in content_item:
                                        image_data = content_item.get("image", "")
                                        if len(image_data) > 1000:  # If image is large
                                            content_item["image"] = image_data[:1000] + "...[truncated]"
                                            content_item["image_size"] = len(image_data)
                                            content_item["image_format"] = "base64"
                                        break
                        
                        return response
                except json.JSONDecodeError:
                    # Not a complete JSON yet, continue reading
                    pass
                except Exception as e:
                    logger.error(f"Error parsing response from {server_name}.{tool_name}: {e}")
                    continue
                
                # Safety check to prevent infinite reading
                if len(response_buffer) > 10 * 1024 * 1024:  # 10MB limit
                    raise Exception("Response too large")
                    
            # Final attempt to parse the buffer
            try:
                response_str = response_buffer.decode().strip()
                if response_str:
                    logger.info(f"Final parse attempt for {len(response_str)} bytes from {server_name}.{tool_name}")
                    response = json.loads(response_str)
                    return response
                else:
                    raise Exception("Empty response from server")
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse response: {e}")
                
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_name}: {e}")
            raise
    
    def _is_large_image_response(self, result: Dict[str, Any]) -> bool:
        """Check if the response contains large image data"""
        try:
            if "content" in result and isinstance(result["content"], list):
                for content_item in result["content"]:
                    if isinstance(content_item, dict):
                        # Check for common image fields
                        for field in ["image", "image_data", "base64", "image_base64"]:
                            if field in content_item:
                                image_data = content_item.get(field, "")
                                if isinstance(image_data, str) and len(image_data) > 50000:  # 50KB threshold
                                    return True
            return False
        except Exception:
            return False
    
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
        self.health_checker = LLMHealthChecker(self.llm_client)
        
        # Initialize MCP client
        self.mcp_client = MCPClient(self.config)
        
        logger.info(f"Enhanced agent_multitool initialized on port {AGENT_PORT}")
    
    async def initialize(self):
        """Initialize the router and MCP servers with LLM health check"""
        # Check LLM availability first but don't fail startup
        logger.info("Performing LLM health check...")
        health_result = await self.health_checker.check_llm_availability()
        
        if health_result.get("available", False):
            logger.info(f"✅ LLM health check passed: {health_result.get('provider')}:{health_result.get('model')}")
        else:
            logger.warning(f"⚠️  LLM health check failed: {health_result.get('error', 'Unknown error')}")
            logger.warning(f"    Provider: {health_result.get('provider')}")
            logger.warning(f"    Model: {health_result.get('model')}")
            logger.warning(f"    Continuing with MCP initialization...")
        
        # Initialize MCP servers regardless of LLM status
        try:
            await self.mcp_client.initialize_servers()
            tools = await self.mcp_client.list_tools()
            logger.info(f"✅ MCP initialization complete: {len(tools)} servers, {sum(len(t) for t in tools.values())} tools")
        except Exception as e:
            logger.error(f"❌ MCP initialization failed: {e}")
            raise e
    
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
    
    async def route_request_stream(self, user_input: str, use_tools: bool = False, use_tokens: bool = None) -> AsyncGenerator[str, None]:
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
                async for chunk in self._route_with_tools(user_input, use_tokens=use_tokens):
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
    
    async def _route_with_tools(self, user_input: str, use_tokens: bool = None) -> AsyncGenerator[str, None]:
        """Route request with MCP tool integration"""
        
        yield json.dumps({
            "stage": "tool_discovery",
            "message": "Discovering available tools"
        })
        
        # Get available tools
        tools = await self.mcp_client.list_tools()
        
        # Minimal data for token efficiency when called via tool_router
        if use_tokens:
            yield json.dumps({
                "stage": "tools_discovered",
                "total_tools": sum(len(server_tools) for server_tools in tools.values())
            })
        else:
            yield json.dumps({
                "stage": "tools_discovered",
                "servers": list(tools.keys()),
                "total_tools": sum(len(server_tools) for server_tools in tools.values())
            })
        
        # Select and execute the appropriate tool
        tool_to_execute = await self._select_tool_for_query(user_input, tools)
        
        if tool_to_execute:
            # Handle different return formats from selection methods
            if len(tool_to_execute) == 3:
                # New LLM format: (server_name, tool_name, json_body) 
                # or legacy format: (server_name, tool_name, extracted_url)
                server_name, tool_name, third_element = tool_to_execute
                
                if isinstance(third_element, dict):
                    # New LLM format with JSON body
                    tool_args = third_element
                    selection_reason = "Tool and JSON body automatically selected based on user query"
                elif isinstance(third_element, str):
                    # Legacy format with URL string
                    tool_args = {"url": third_element}
                    selection_reason = "Tool and URL selected by keyword matching"
                else:
                    tool_args = {}
                    selection_reason = "Tool selected with empty arguments"
                    
            elif len(tool_to_execute) == 2:
                # Simple fallback format: (server_name, tool_name)
                server_name, tool_name = tool_to_execute
                tool_args = {}
                selection_reason = "Tool selected by keyword matching"
            else:
                # Invalid return format
                yield json.dumps({
                    "stage": "error",
                    "error": "Invalid tool selection format"
                })
                return
            
            yield json.dumps({
                "stage": "tool_selection",
                "selected_tool": f"{server_name}.{tool_name}",
                "intent": "Tool automatically selected based on user query"
            })
            
            # Execute the tool
            try:
                result = await self.mcp_client.call_tool(server_name, tool_name, tool_args)
                
                if use_tokens:
                    # Minimal output for token efficiency
                    yield json.dumps({
                        "stage": "tool_result",
                        "server": server_name,
                        "tool": tool_name,
                        "result": result.get("result", {})
                    })
                else:
                    # Full output for router API
                    yield json.dumps({
                        "stage": "tool_result",
                        "server": server_name,
                        "tool": tool_name,
                        "result": result.get("result", {}),
                        "execution_info": {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "execution_time": "immediate"
                        }
                    })
                
                yield json.dumps({
                    "stage": "complete",
                    "result": {
                        "response": f"Successfully executed {tool_name} from {server_name}",
                        "tool_result": result.get("result", {}),
                        "service": AGENT_NAME,
                        "port": AGENT_PORT
                    }
                })
                
            except Exception as e:
                yield json.dumps({
                    "stage": "error",
                    "error": f"Tool execution failed: {str(e)}"
                })
        else:
            # No specific tool found, use LLM response
            if use_tokens:
                # Token-efficient LLM response with retry logic
                messages = [
                    {"role": "system", "content": "You are a helpful assistant. Be concise."},
                    {"role": "user", "content": user_input}
                ]
                
                full_response = ""
                error_encountered = False
                
                async for chunk_str in self.health_checker.call_with_retry(messages):
                    chunk = json.loads(chunk_str)
                    
                    if "error" in chunk:
                        error_encountered = True
                        yield chunk
                    elif "retry" in chunk:
                        yield chunk
                    else:
                        content = chunk.get("content", "")
                        full_response += content
                        yield json.dumps({
                            "stage": "llm_streaming",
                            "content": content,
                            "provider": chunk.get("provider")
                        })
                
                if error_encountered:
                    yield json.dumps({
                        "stage": "complete",
                        "result": {
                            "error": "LLM service unavailable after retries"
                        }
                    })
                else:
                    yield json.dumps({
                        "stage": "complete",
                        "result": {
                            "response": full_response.strip()
                        }
                    })
            else:
                # Full LLM response with tools awareness
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
    
    async def _select_tool_for_query_llm(self, user_input: str, tools: Dict[str, List[dict]]) -> Optional[tuple]:
        """LLM-powered intelligent tool selection based on user query"""
        
        logger.info(f"LLM-based tool selection for query: '{user_input}'")
        
        # Get server metadata from config for context
        mcp_config = self.config.get("mcpServers", {})
        
        # Create enhanced tools description with server-level keywords and descriptions
        tools_description = []
        for server_name, server_tools in tools.items():
            server_config = mcp_config.get(server_name, {})
            server_keywords = server_config.get("keywords", [])
            server_description = server_config.get("description", "")
            
            for tool in server_tools:
                tool_description = tool.get("description", "")
                input_schema = tool.get("inputSchema", {})
                full_description = f"{tool_description}"
                if server_description:
                    full_description = f"{server_description}. {tool_description}"
                
                # Include server-level keywords for context
                keywords_str = ""
                if server_keywords:
                    keywords_str = f" (keywords: {', '.join(server_keywords)})"
                
                tools_description.append({
                    "name": f"{server_name}.{tool['name']}",
                    "description": full_description,
                    "server": server_name,
                    "tool": tool['name'],
                    "keywords": server_keywords,
                    "inputSchema": input_schema,
                    "context": f"{full_description}{keywords_str}"
                })
        
        # LLM system prompt for tool selection with JSON body construction
        system_prompt = f"""You are an intelligent tool selector. Analyze the user query and select the best tool from the available options, then construct the appropriate JSON request body.

Available tools:
{json.dumps([{"name": t["name"], "description": t["context"], "keywords": t["keywords"], "inputSchema": t["inputSchema"]} for t in tools_description], indent=2)}

Instructions:
1. Analyze the user's intent and match it with the most relevant tool
2. Consider when the user mentions keywords like "obsidian", "note", "vault", "notes", "list my obsidian vault" - select obsidian tools
3. Consider when the user mentions "time", "current time", "what time" - select time tools  
4. Consider when the user mentions "fetch", "curl", "web", "url" - select web tools
5. **IMAGE GENERATION: When user mentions "create", "generate", "image", "picture", "draw", "make", "art", "visual" - ALWAYS select nano-banana.generate_image, NOT configuration tools**
6. **CRITICAL: nano-banana.generate_image is for CREATING images, nano-banana.configure_gemini_token is ONLY for API setup**
7. Each tool has associated keywords that indicate what it's good for
8. Construct the JSON request body based on the tool's inputSchema and the user's intent
9. **CRITICAL: For web/fetch/curl tools - ALWAYS extract URLs from the user query**
10. URLs will be in format like "https://example.com" or "http://example.com" - extract them exactly as provided
11. **For nano-banana.generate_image: json_body MUST include the "prompt" field with the image description**
12. Respond with EXACTLY one of these formats:
   - If you found a tool: {{"selected_tool": "server.tool_name", "json_body": {{construct appropriate JSON}}, "reason": "brief reason"}}
   - If no tool matches: {{"selected_tool": null, "json_body": {{}}, "reason": "no matching tool found"}}

For the json_body:
- Use the tool's inputSchema as a guide
- **For curl/fetch tools: json_body MUST include the extracted URL in the "url" field**
- **For nano-banana.generate_image: json_body MUST include the "prompt" field with the image description**
- Fill in parameters that can be inferred from the user query
- For empty parameters, use sensible defaults or empty strings
- For boolean parameters, use true/false
- For array parameters, use [] or appropriate values

Examples of expected outputs:
For "fetch https://tuckerbradford.com": {{"selected_tool": "curl.fetch", "json_body": {{"url": "https://tuckerbradford.com"}}, "reason": "User wants to fetch a webpage"}}
For "what time is it": {{"selected_tool": "current-time.current_time", "json_body": {{}}, "reason": "User wants current time"}}
For "create an image of a cat": {{"selected_tool": "nano-banana.generate_image", "json_body": {{"prompt": "a cat"}}, "reason": "User wants to generate an image"}}
For "generate a picture of a house": {{"selected_tool": "nano-banana.generate_image", "json_body": {{"prompt": "a house"}}, "reason": "User wants to create an image"}}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Select the best tool and construct JSON body for this request: '{user_input}'"}
        ]
        
        try:
            # Get LLM response for tool selection
            llm_response = ""
            is_complete = False
            
            async for chunk_str in self.llm_client.chat_completion_stream(messages, temperature=0.1):
                chunk = json.loads(chunk_str)
                
                # Check if this is the completion marker from Ollama
                if chunk.get("complete"):
                    llm_response = chunk.get("complete", "")
                    is_complete = True
                    break
                
                content = chunk.get("content", "")
                llm_response += content
            
            # Parse LLM response
            response_data = json.loads(llm_response.strip())
            selected_tool = response_data.get("selected_tool")
            json_body = response_data.get("json_body", {})
            reason = response_data.get("reason", "")
            
            if selected_tool:
                # Parse server.tool format
                if "." in selected_tool:
                    server_name, tool_name = selected_tool.split(".", 1)
                    logger.info(f"LLM selected tool '{selected_tool}' with JSON body {json_body} because: {reason}")
                    return server_name, tool_name, json_body
                else:
                    logger.error(f"LLM returned invalid tool format: {selected_tool}")
                    return None
            else:
                logger.info(f"LLM found no matching tool: {reason}")
                return None
                
        except Exception as e:
            logger.error(f"LLM tool selection failed: {e}")
            # Fallback to keyword-based selection using server metadata
            return await self._select_tool_for_query_config_keywords(user_input, tools)
    
    async def _select_tool_for_query_config_keywords(self, user_input: str, tools: Dict[str, List[dict]]) -> Optional[tuple]:
        """Keyword-based tool selection using config server metadata"""
        
        user_input_lower = user_input.lower()
        
        # Get server metadata from config
        mcp_config = self.config.get("mcpServers", {})
        
        # Match against server keywords
        for server_name, server_tools in tools.items():
            server_config = mcp_config.get(server_name, {})
            server_keywords = server_config.get("keywords", [])
            
            # Check if any server keywords match the user query
            if any(keyword in user_input_lower for keyword in server_keywords):
                logger.info(f"Query matches server '{server_name}' keywords: {server_keywords}")
                
                # Special handling for curl server - extract URL
                if server_name == 'curl' and any(keyword in user_input_lower for keyword in ['fetch', 'curl', 'http', 'web', 'url']):
                    for tool in server_tools:
                        tool_name_lower = tool['name'].lower()
                        if 'curl' in tool_name_lower or 'fetch' in tool_name_lower:
                            # Extract URL for curl tools
                            import re
                            url_patterns = [
                                r'https?://[^\s\)]+',  # URLs not ending in )
                                r'https?://[^\s\(]+',  # URLs not ending in (
                                r'https?://[^\s,\.]+',  # URLs not ending in , or .
                            ]
                            extracted_url = None
                            for pattern in url_patterns:
                                match = re.search(pattern, user_input)  # Don't use .lower() here
                                if match:
                                    extracted_url = match.group(0)
                                    logger.info(f"🔗 Extracted URL for {server_name}.{tool['name']}: {extracted_url}")
                                    break
                            if extracted_url:
                                return server_name, tool['name'], {"url": extracted_url}
                            else:
                                return server_name, tool['name'], {}
                
                # Return first available tool from matching server
                if server_tools:
                    return server_name, server_tools[0]['name']
        
        return None
    
    async def _select_tool_for_query_keywords(self, user_input: str, tools: Dict[str, List[dict]]) -> Optional[tuple]:
        """Fallback keyword-based tool selection"""
        
        user_input_lower = user_input.lower()
        
        # Get routing keywords from config
        routing_config = self.config.get("toolRouting", {})
        keywords = routing_config.get("keywords", {})
        tool_patterns = routing_config.get("toolPatterns", {})
        
        # Time-related queries
        time_keywords = keywords.get("time", ['time', 'current time', 'what time', 'now'])
        if any(keyword in user_input_lower for keyword in time_keywords):
            for server_name, server_tools in tools.items():
                for tool in server_tools:
                    tool_name_lower = tool['name'].lower()
                    if 'time' in tool_name_lower:
                        return server_name, tool['name']
        
        # Obsidian/knowledge queries - Load from config
        obsidian_keywords = keywords.get("obsidian", [
            'obsidian', 'note', 'notes', 'vault', 'knowledge', 
            'search notes', 'find notes', 'list notes', 'list my obsidian vault'
        ])
        
        if any(keyword in user_input_lower for keyword in obsidian_keywords):
            obsidian_patterns = tool_patterns.get("obsidian", {})
            search_actions = obsidian_patterns.get("search_actions", ['search', 'find', 'look for'])
            list_actions = obsidian_patterns.get("list_actions", ['list', 'show', 'browse', 'view'])
            tool_keywords = obsidian_patterns.get("tool_keywords", ['search', 'list', 'get', 'browse'])
            
            for server_name, server_tools in tools.items():
                if 'obsidian' in server_name.lower():
                    if any(list_word in user_input_lower for list_word in list_actions):
                        for tool in server_tools:
                            tool_name_lower = tool['name'].lower()
                            if any(action in tool_name_lower for action in tool_keywords):
                                return server_name, tool['name']
                    elif any(search_word in user_input_lower for search_word in search_actions):
                        for tool in server_tools:
                            tool_name_lower = tool['name'].lower()
                            if 'search' in tool_name_lower:
                                return server_name, tool['name']
                    if server_tools:
                        return server_name, server_tools[0]['name']
        
        # Web/fetch queries - Load from config
        web_keywords = keywords.get("web", ['fetch', 'curl', 'http', 'web', 'url'])
        if any(keyword in user_input_lower for keyword in web_keywords):
            has_curl_tools = any(
                any('curl' in tool['name'].lower() or 'fetch' in tool['name'].lower() 
                    for tool in server_tools)
                for server_tools in tools.values()
            )
            
            if has_curl_tools:
                for server_name, server_tools in tools.items():
                    for tool in server_tools:
                        tool_name_lower = tool['name'].lower()
                        if 'curl' in tool_name_lower or 'fetch' in tool_name_lower:
                            import re
                            url_patterns = [
                                r'https?://[^\s\)]+',  # URLs not ending in )
                                r'https?://[^\s\(]+',  # URLs not ending in (
                                r'https?://[^\s,\.]+',  # URLs not ending in , or .
                            ]
                            extracted_url = None
                            for pattern in url_patterns:
                                match = re.search(pattern, user_input)  # Don't use .lower() here
                                if match:
                                    extracted_url = match.group(0)
                                    break
                            return server_name, tool['name'], extracted_url
        
        return None

    async def _select_tool_for_query(self, user_input: str, tools: Dict[str, List[dict]]) -> Optional[tuple]:
        """Intelligent tool selection - Image keywords first, then LLM, then general keywords fallback"""
        
        # Try image generation keywords first (highest priority)
        image_result = await self._select_tool_for_query_image_keywords(user_input, tools)
        if image_result:
            return image_result
        
        # Try LLM-based selection
        try:
            llm_result = await self._select_tool_for_query_llm(user_input, tools)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.warning(f"LLM tool selection failed, falling back to keywords: {e}")
        
        # Fallback to general keyword-based selection
        return await self._select_tool_for_query_keywords(user_input, tools)
    
    async def _select_tool_for_query_image_keywords(self, user_input: str, tools: Dict[str, List[dict]]) -> Optional[tuple]:
        """High-priority image generation detection"""
        user_input_lower = user_input.lower()
        
        # Image generation queries - HIGHEST PRIORITY
        image_keywords = ['create', 'generate', 'image', 'picture', 'draw', 'make', 'art', 'visual', 'photo', 'painting']
        if any(keyword in user_input_lower for keyword in image_keywords):
            for server_name, server_tools in tools.items():
                if 'nano-banana' in server_name.lower():
                    for tool in server_tools:
                        if tool['name'] == 'generate_image':
                            # Extract the prompt from the user query
                            prompt = user_input  # Use full query as prompt
                            logger.info(f"🎨 Image keyword detection: selected nano-banana.generate_image with prompt: '{prompt}'")
                            return server_name, tool['name'], {"prompt": prompt}
        
        return None

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
            
            # Add the built-in tool_router tool
            all_tools.append({
                "name": "tool_router",
                "description": "Intelligently select and route to the best available tool based on user intent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_query": {
                            "type": "string",
                            "description": "The user's request or question"
                        },
                        "available_tools": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of available tools to consider (auto-populated)"
                        }
                    },
                    "required": ["user_query"]
                }
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
            
            # Handle special case for tool_router BEFORE checking for dot format
            if tool_name == "tool_router":
                user_query = arguments.get("user_query", "")
                
                # Get available tools for routing logic
                tools = await current_router.mcp_client.list_tools()
                tool_to_execute = await current_router._select_tool_for_query(user_query, tools)
                
                if tool_to_execute:
                    # Handle different return formats from selection methods
                    if len(tool_to_execute) == 3:
                        # New LLM format: (server_name, tool_name, json_body) 
                        # or legacy format: (server_name, tool_name, extracted_url)
                        server_name, tool_name_param, third_element = tool_to_execute
                        
                        if isinstance(third_element, dict):
                            # New LLM format with JSON body
                            tool_args = third_element
                            execution_reason = "Tool and JSON body automatically selected based on user query"
                            logger.info(f"✅ Using LLM-generated JSON body: {tool_args}")
                        elif isinstance(third_element, str):
                            # Legacy format with URL string
                            tool_args = {"url": third_element}
                            execution_reason = "Tool and URL selected by keyword matching"
                            logger.info(f"✅ Using legacy URL extraction: {tool_args}")
                        else:
                            tool_args = {}
                            execution_reason = "Tool selected with empty arguments"
                            logger.info(f"⚠️  Using empty arguments (third_element type: {type(third_element)})")
                    else:
                        # Simple fallback format: (server_name, tool_name)
                        server_name, tool_name_param = tool_to_execute
                        tool_args = {}
                        execution_reason = "Tool selected by keyword matching"
                        logger.info(f"⚠️  Using simple format without third element: {tool_to_execute}")
                    
                    logger.info(f"🎯 TOOL EXECUTION: server={server_name}, tool={tool_name_param}, args={tool_args}, reason={execution_reason}")
                    
                    try:
                        # Execute the selected tool with constructed arguments
                        result = await current_router.mcp_client.call_tool(
                            server_name, 
                            tool_name_param, 
                            tool_args
                        )
                        
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Tool Router executed {tool_name_param} from {server_name} {execution_reason}: {json.dumps(result.get('result', {}), indent=2)}"
                                    }
                                ]
                            }
                        }
                    except Exception as e:
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Tool Router selected {tool_name_param} from {server_name} but execution failed: {str(e)}"
                                    }
                                ]
                            }
                        }
                else:
                    # No tool selected, fall back to simple LLM response
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Tool Router processed query: '{user_query}'. No specific MCP tool was selected. Query requires LLM assistance."
                                }
                            ]
                        }
                    }
            
            # Parse server.tool format for normal tools (but NOT for tool_router)
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

# Startup event to initialize router
@app.on_event("startup")
async def startup_event():
    """Initialize router on startup"""
    try:
        global router
        router = EnhancedHaystackRouter()
        await router.initialize()
        logger.info("✅ Router initialized successfully on FastAPI startup")
    except Exception as e:
        logger.error(f"❌ Router initialization failed on startup: {e}")
        raise e

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup MCP connections on shutdown"""
    global router
    if router:
        await router.mcp_client.cleanup()
        logger.info("Enhanced agent_multitool shutdown complete")

if __name__ == "__main__":
    import asyncio
    import sys
    
    async def startup_with_health_check():
        """Startup with LLM health check and proper exit on failure"""
        try:
            # Create router instance
            test_router = EnhancedHaystackRouter()
            
            # Perform health check
            logger.info("Performing LLM health check at startup...")
            health_result = await test_router.health_checker.check_llm_availability()
            
            if not health_result.get("available", False):
                error_msg = f"LLM provider {health_result.get('provider')} unavailable: {health_result.get('error', 'Unknown error')}"
                logger.error(error_msg)
                print(f"❌ FATAL: {error_msg}", file=sys.stderr)
                print(f"   Provider: {health_result.get('provider')}", file=sys.stderr)
                print(f"   Model: {health_result.get('model')}", file=sys.stderr)
                print(f"   Attempts made: {health_result.get('attempts_made', 'N/A')}", file=sys.stderr)
                sys.exit(1)
            
            logger.info(f"✅ LLM health check passed: {health_result.get('provider')}:{health_result.get('model')}")
            
            # Initialize MCP servers
            await test_router.mcp_client.initialize_servers()
            tools = await test_router.mcp_client.list_tools()
            logger.info(f"✅ MCP initialization complete: {len(tools)} servers, {sum(len(t) for t in tools.values())} tools")
            
            # Store in global router for API endpoints
            global router
            router = test_router
            
            # Start FastAPI server
            logger.info(f"🚀 Starting Enhanced {AGENT_NAME} on port {AGENT_PORT}")
            
        except Exception as e:
            error_msg = f"Startup failed: {str(e)}"
            logger.error(error_msg)
            print(f"❌ FATAL: {error_msg}", file=sys.stderr)
            sys.exit(1)
    
    # Run startup check
    asyncio.run(startup_with_health_check())
    
    # Start server if startup succeeded
    import uvicorn
    uvicorn.run(
        "enhanced_pipeline_wrapper:app",
        host="0.0.0.0",
        port=AGENT_PORT,
        reload=False,
        log_level="info"
    )
