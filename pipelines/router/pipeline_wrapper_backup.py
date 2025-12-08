import json
import os
import logging
from typing import Dict, Any, List
from haystack.components.agents import Agent
from hayhooks import BasePipelineWrapper
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class PipelineWrapper(BasePipelineWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mcp_sessions: Dict[str, ClientSession] = {}

    def setup(self):
        # Hayhooks constructs the pipeline from YAML and passes it here
        # self.pipeline is already set on the wrapper instance.
        assert self.pipeline is not None

        # Get the Agent to add MCP tools
        agent: Agent = self.pipeline.get_component("router_agent")
        
        # Load MCP server configuration
        self._setup_mcp_tools(agent)

    def _setup_mcp_tools(self, agent: Agent):
        """Read MCP server config and add tools to the agent"""
        config_path = "/config/mcpServers.json"
        
        if not os.path.exists(config_path):
            logger.warning(f"MCP config not found at {config_path}")
            return
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            mcp_servers = config.get("mcpServers", {})
            logger.info(f"Loading {len(mcp_servers)} MCP servers from config")
            
            for server_name, server_config in mcp_servers.items():
                if not server_config.get("enabled", True):
                    logger.info(f"Skipping disabled MCP server: {server_name}")
                    continue
                
                try:
                    self._add_mcp_server_tools(agent, server_name, server_config)
                except Exception as e:
                    logger.error(f"Failed to add tools from MCP server {server_name}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")

    def _add_mcp_server_tools(self, agent: Agent, server_name: str, server_config: Dict[str, Any]):
        """Add tools from a single MCP server to the agent"""
        # Extract server configuration with flexible key names
        command = server_config.get("command") or server_config.get("cmd")
        args = server_config.get("args", [])
        env = server_config.get("env", {})
        cwd = server_config.get("cwd", None)
        transport_type = server_config.get("transportType", "stdio")
        
        if not command:
            logger.warning(f"MCP server {server_name} has no command, skipping")
            return
        
        if transport_type != "stdio":
            logger.warning(f"Only stdio transport is supported, skipping {server_name}")
            return
        
        try:
            # Create server parameters for MCP client
            from mcp.client.stdio import stdio_client
            from mcp import StdioServerParameters
            
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env or None,
                cwd=cwd
            )
            
            # Create MCP client session and keep it alive
            session_client = stdio_client(server_params)
            self.mcp_sessions[server_name] = session_client
            
            # Test connection and list tools
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def setup_tools():
                async with session_client as session:
                    # List available tools
                    tools_response = await session.list_tools()
                    tools = tools_response.tools
                    
                    logger.info(f"Found {len(tools)} tools in MCP server {server_name}")
                    
                    # Create Haystack-compatible tools for each MCP tool
                    for tool in tools:
                        self._create_haystack_tool_from_mcp_tool(agent, session, tool, server_name)
            
            loop.run_until_complete(setup_tools())
            loop.close()
                    
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}")

    def _create_haystack_tool_from_mcp_tool(self, agent: Agent, session, mcp_tool, server_name: str):
        """Create a Haystack-compatible tool from an MCP tool"""
        
        def make_mcp_tool_wrapper(tool_session, tool_name, session_key):
            def mcp_tool_wrapper(**kwargs):
                import asyncio
                
                # Use the stored session
                session_client = self.mcp_sessions[session_key]
                
                # Create new event loop if needed
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Run the async call_tool method
                async def call_tool_async():
                    async with session_client as session:
                        result = await session.call_tool(tool_name, kwargs)
                        return result.content[0].text if result.content else str(result)
                
                result = loop.run_until_complete(call_tool_async())
                return result
            return mcp_tool_wrapper
        
        # Create tool description
        description = mcp_tool.description or f"MCP tool {mcp_tool.name} from {server_name}"
        
        # Create the Haystack tool function
        tool_func = make_mcp_tool_wrapper(session, mcp_tool.name, server_name)
        
        # Add tool to agent using the expected API
        try:
            # Method 1: Try newer Haystack API
            agent.add_tool(
                tool=mcp_tool.name,
                description=description,
                tool_func=tool_func
            )
        except (TypeError, AttributeError):
            try:
                # Method 2: Try alternative API
                agent.add_tool(
                    name=mcp_tool.name,
                    description=description,
                    tool=tool_func
                )
            except (TypeError, AttributeError):
                # Method 3: Manual tool addition
                if hasattr(agent, 'tool_manager'):
                    agent.tool_manager.add_tool(mcp_tool.name, tool_func, description)
                else:
                    # Last resort: treat agent as dict-like
                    if not hasattr(agent, 'tools'):
                        agent.tools = {}
                    agent.tools[mcp_tool.name] = {
                        'function': tool_func,
                        'description': description
                    }
        
        logger.info(f"Added MCP tool {mcp_tool.name} from {server_name}")

    async def run_api(self, request):
        result = self.pipeline.run(data={"messages": request.messages})
        return {"replies": result["replies"]}

    async def run_chat_completion(self, model, messages, body):
        result = self.pipeline.run(data={"messages": messages})
        reply = result["replies"][-1]
        content = reply["content"] if isinstance(reply, dict) else reply
        return {
            "id": "chatcmpl-hayhooks-tool-router",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                }
            ],
        }
