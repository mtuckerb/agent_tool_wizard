FROM python:3.11-slim

# System dependencies
RUN apt-get update && \
    apt-get install -y \
    curl \
    wget \
    build-essential \
    ca-certificates \
    gnupg \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18 LTS for better compatibility
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.localexec PATH=/home/agent/.cargo/bin:$PATH"

# Install bun (JavaScript runtime)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

# Create directories for tools
RUN mkdir -p /opt/tools /opt/mcp-servers /opt/mcp-custom

# Create our own MCP scripts
RUN tee /opt/mcp-custom/package_manager.py > /dev/null << 'EOF'
#!/usr/bin/env python3
"""
MCP Server for Package Management Tools
Supports: uv, uvx, bun, npm, npx, pip
"""

import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

# MCP Server implementation
class PackageManagerMCPServer:
    def __init__(self):
        self.tools = [
            {
                "name": "uv_run",
                "description": "Execute uv commands",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "uv command to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "command arguments"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "uvx_run",
                "description": "Execute uvx commands (run Python applications)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "package to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "arguments"}
                    },
                    "required": ["package"]
                }
            },
            {
                "name": "bun_run",
                "description": "Execute bun commands",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "bun command to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "command arguments"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "npm_run",
                "description": "Execute npm commands",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "npm command to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "command arguments"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "npx_run",
                "description": "Execute npx commands",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "package to run via npx"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "arguments"}
                    },
                    "required": ["package"]
                }
            },
            {
                "name": "list_packages",
                "description": "List installed packages from various managers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "manager": {"type": "string", "enum": ["uv", "npm", "bun", "pip"], "description": "package manager to query"}
                    }
                }
            }
        ]
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        return self.tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name == "uv_run":
                return await self._run_command("uv", [arguments["command"]] + arguments.get("args", []))
            elif name == "uvx_run":
                return await self._run_command("uvx", [arguments["package"]] + arguments.get("args", []))
            elif name == "bun_run":
                return await self._run_command("bun", [arguments["command"]] + arguments.get("args", []))
            elif name == "npm_run":
                return await self._run_command("npm", [arguments["command"]] + arguments.get("args", []))
            elif name == "npx_run":
                return await self._run_command("npx", [arguments["package"]] + arguments.get("args", []))
            elif name == "list_packages":
                manager = arguments.get("manager", "pip")
                if manager == "uv":
                    return await self._run_command("uv", ["pip", "list"])
                elif manager == "npm":
                    return await self._run_command("npm", ["list", "--depth=0"])
                elif manager == "bun":
                    return await self._run_command("bun", ["pm", "ls"])
                elif manager == "pip":
                    return await self._run_command("pip", ["list"])
                else:
                    return {"error": f"Unknown manager: {manager}"}
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _run_command(self, cmd: str, args: List[str]) -> Dict[str, Any]:
        try:
            process = await asyncio.create_subprocess_exec(
                cmd, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "success": process.returncode == 0
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }

async def main():
    server = PackageManagerMCPServer()
    
    # MCP JSON-RPC server loop
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                continue
            
            request = json.loads(line.strip())
            method = request.get("method")
            request_id = request.get("id")
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "package-manager", "version": "1.0.0"}
                    }
                }
            elif method == "tools/list":
                tools = await server.list_tools()
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools}
                }
            elif method == "tools/call":
                name = request["params"]["name"]
                arguments = request["params"].get("arguments", {})
                result = await server.call_tool(name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            
            print(json.dumps(response), flush=True)
            
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": str(e)}
            }
            print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
EOF

RUN chmod +x /opt/mcp-custom/package_manager.py

# Python dependencies for application
RUN pip install --upgrade pip
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Set work directory
WORKDIR /app

# Create agent_multitool user and directories
RUN useradd -m -u 1000 agent && \
    mkdir -p /data /opt/tools /opt/mcp-servers /opt/mcp-custom /home/agent/.config && \
    chown -R agent:agent /data /opt/tools /opt/mcp-servers /opt/mcp-custom /home/agent /app

# Set up proper environment for agent user
RUN echo 'export HOME=/home/agent' >> /home/agent/.bashrc && \
    echo 'export PATH=/root/.cargo/bin:/root/.bun/bin:/usr/local/bin:$PATH' >> /home/agent/.bashrc

# Switch to agent user
USER agent

# Set environment variables
ENV HOME=/home/agent
ENV AGENT_NAME=agent_multitool
ENV AGENT_VERSION=1.0.0
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.cargo/bin:/root/.bun/bin:/usr/local/bin:$PATH"

# Copy application code
COPY pipelines/ ./pipelines/
COPY mcp_custom_dev_tools.py /app/
COPY entrypoint.sh /app/entrypoint.sh

# Make entrypoint executable
USER root
RUN chmod +x /app/entrypoint.sh
RUN chown -R agent .
USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:1417/api/health || exit 1

# Expose ports
EXPOSE 1417

CMD ["/app/entrypoint.sh"]
