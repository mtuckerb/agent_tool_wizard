#!/usr/bin/env python3
"""
MCP Server for Development Tools
Utilizes package managers (uv, uvx, bun, npm, npx) as environment resources
to provide intelligent development tools to the LLM.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

class DevelopmentToolsMCPServer:
    def __init__(self):
        # These are the actual MCP tools the LLM can choose from
        self.tools = [
            {
                "name": "create_python_project",
                "description": "Create a new Python project with uv, setting up virtual environment and dependencies",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the Python project"},
                        "template": {"type": "string", "enum": ["fastapi", "flask", "django", "basic"], "default": "basic", "description": "Project template to use"},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Initial dependencies to install"}
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "create_nodejs_project", 
                "description": "Create a new Node.js project with package manager setup and dependencies",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the Node.js project"},
                        "package_manager": {"type": "string", "enum": ["npm", "bun"], "default": "npm", "description": "Package manager to use"},
                        "template": {"type": "string", "enum": ["express", "react", "vue", "basic"], "default": "basic", "description": "Project template"},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Initial dependencies"}
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "install_python_package",
                "description": "Install Python packages using uv or pip (automatically chooses best available)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "packages": {"type": "array", "items": {"type": "string"}, "description": "Packages to install"},
                        "dev": {"type": "boolean", "default": false, "description": "Install as development dependencies"},
                        "project_path": {"type": "string", "description": "Project directory (defaults to current)"}
                    },
                    "required": ["packages"]
                }
            },
            {
                "name": "install_nodejs_package",
                "description": "Install Node.js packages using npm or bun (automatically chooses best available)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "packages": {"type": "array", "items": {"type": "string"}, "description": "Packages to install"},
                        "dev": {"type": "boolean", "default": false, "description": "Install as development dependencies"},
                        "package_manager": {"type": "string", "enum": ["npm", "bun"], "description": "Force specific package manager"}
                    },
                    "required": ["packages"]
                }
            },
            {
                "name": "run_python_command",
                "description": "Execute Python script or command in the appropriate environment",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Python command or script to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                        "project_path": {"type": "string", "description": "Project directory"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "run_nodejs_command",
                "description": "Execute Node.js script or command using appropriate package manager",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Node.js command or script to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                        "package_manager": {"type": "string", "enum": ["npm", "bun"], "description": "Force specific package manager"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "execute_package_binary",
                "description": "Run any package binary (uvx, npx, bunx) for one-time execution without installation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Package to execute"},
                        "command": {"type": "string", "description": "Binary command to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments for the command"}
                    },
                    "required": ["package"]
                }
            },
            {
                "name": "list_project_dependencies",
                "description": "List all dependencies and their versions for the current project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_type": {"type": "string", "enum": ["python", "nodejs", "auto"], "default": "auto", "description": "Project type to check"},
                        "project_path": {"type": "string", "description": "Project directory path"}
                    }
                }
            }
        ]
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        return self.tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name == "create_python_project":
                return await self._create_python_project(**arguments)
            elif name == "create_nodejs_project":
                return await self._create_nodejs_project(**arguments)
            elif name == "install_python_package":
                return await self._install_python_package(**arguments)
            elif name == "install_nodejs_package":
                return await self._install_nodejs_package(**arguments)
            elif name == "run_python_command":
                return await self._run_python_command(**arguments)
            elif name == "run_nodejs_command":
                return await self._run_nodejs_command(**arguments)
            elif name == "execute_package_binary":
                return await self._execute_package_binary(**arguments)
            elif name == "list_project_dependencies":
                return await self._list_project_dependencies(**arguments)
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

# Minimal MCP Server implementation
async def main():
    server = DevelopmentToolsMCPServer()
    
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
                        "serverInfo": {"name": "development-tools", "version": "1.0.0"}
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
