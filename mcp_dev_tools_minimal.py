#!/usr/bin/env python3
"""
Minimal MCP Server for Development Tools
Core architecture: Package managers as environment resources, intelligent tools as MCP endpoints
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

class DevelopmentToolsMCPServer:
    def __init__(self):
        # Intelligent development tools that the LLM can choose from
        self.tools = [
            {
                "name": "create_python_project",
                "description": "Create a new Python project with modern tooling (uv, pip)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the Python project"},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Initial dependencies"}
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "create_nodejs_project",
                "description": "Create a new Node.js project with modern tooling (npm, bun)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the Node.js project"},
                        "package_manager": {"type": "string", "enum": ["npm", "bun"], "default": "npm"},
                        "dependencies": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "install_packages",
                "description": "Install packages across different ecosystems (Python/Node.js)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ecosystem": {"type": "string", "enum": ["python", "nodejs"], "description": "Package ecosystem"},
                        "packages": {"type": "array", "items": {"type": "string"}, "description": "Packages to install"},
                        "dev": {"type": "boolean", "default": false, "description": "Install as dev dependencies"}
                    },
                    "required": ["ecosystem", "packages"]
                }
            },
            {
                "name": "run_command",
                "description": "Execute commands using appropriate package managers (uv, npm, bun)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"},
                        "ecosystem": {"type": "string", "enum": ["python", "nodejs"], "description": "Target ecosystem"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"}
                    },
                    "required": ["command", "ecosystem"]
                }
            },
            {
                "name": "list_dependencies",
                "description": "List installed dependencies for the current project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ecosystem": {"type": "string", "enum": ["python", "nodejs", "auto"], "default": "auto"}
                    }
                }
            }
        ]
    
    async def list_tools(self):
        return self.tools
    
    async def call_tool(self, name, arguments):
        try:
            if name == "create_python_project":
                return await self._create_python_project(**arguments)
            elif name == "create_nodejs_project":
                return await self._create_nodejs_project(**arguments)
            elif name == "install_packages":
                return await self._install_packages(**arguments)
            elif name == "run_command":
                return await self._run_command(**arguments)
            elif name == "list_dependencies":
                return await self._list_dependencies(**arguments)
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _create_python_project(self, project_name, dependencies=None):
        try:
            # Create project directory
            Path(project_name).mkdir(exist_ok=True)
            
            # Create pyproject.toml
            pyproject_content = f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "0.1.0"
description = ""
'''
            
            with open(f"{project_name}/pyproject.toml", "w") as f:
                f.write(pyproject_content)
            
            # Create src directory
            Path(f"{project_name}/src").mkdir(exist_ok=True)
            Path(f"{project_name}/src/__init__.py").touch()
            
            # Install dependencies if specified
            if dependencies:
                deps = " ".join(dependencies)
                result = await self._execute_command("pip", ["install"] + dependencies)
                return {
                    "success": True,
                    "message": f"Created Python project '{project_name}'",
                    "dependencies": dependencies,
                    "install_result": result
                }
            
            return {
                "success": True,
                "message": f"Created Python project '{project_name}'",
                "path": str(Path(project_name).absolute())
            }
        except Exception as e:
            return {"error": f"Failed to create Python project: {str(e)}"}
    
    async def _create_nodejs_project(self, project_name, package_manager="npm", dependencies=None):
        try:
            Path(project_name).mkdir(exist_ok=True)
            
            # Initialize based on package manager
            if package_manager == "bun":
                result = await self._execute_command("bun", ["init"], cwd=project_name)
            else:
                result = await self._execute_command("npm", ["init", "-y"], cwd=project_name)
            
            # Install dependencies
            if dependencies and result.get("success", False):
                deps = " ".join(dependencies)
                if package_manager == "bun":
                    install_result = await self._execute_command("bun", ["install"] + dependencies, cwd=project_name)
                else:
                    install_result = await self._execute_command("npm", ["install"] + dependencies, cwd=project_name)
            else:
                install_result = {"success": True, "message": "No dependencies specified"}
            
            return {
                "success": True,
                "message": f"Created Node.js project '{project_name}' using {package_manager}",
                "package_manager": package_manager,
                "dependencies": dependencies
            }
        except Exception as e:
            return {"error": f"Failed to create Node.js project: {str(e)}"}
    
    async def _install_packages(self, ecosystem, packages, dev=False):
        try:
            if ecosystem == "python":
                # Try uv first, fallback to pip
                uv_result = await self._execute_command("uv", ["--version"])
                if uv_result.get("success"):
                    cmd = ["uv", "pip", "install"] + packages
                    if dev:
                        cmd.append("--dev")
                    return await self._execute_command(*cmd)
                else:
                    cmd = ["pip", "install"] + packages
                    if dev:
                        cmd.append("--dev")
                    return await self._execute_command(*cmd)
            
            elif ecosystem == "nodejs":
                # Detect package manager
                if Path("bun.lockb").exists():
                    pm = "bun"
                else:
                    pm = "npm"
                
                if pm == "bun":
                    cmd = ["bun", "install"] + packages
                    if dev:
                        cmd.append("--dev")
                else:
                    cmd = ["npm", "install"] + packages
                    if dev:
                        cmd.append("--save-dev")
                
                return await self._execute_command(*cmd)
            
            else:
                return {"error": f"Unknown ecosystem: {ecosystem}"}
        
        except Exception as e:
            return {"error": f"Failed to install packages: {str(e)}"}
    
    async def _run_command(self, command, ecosystem, args=None):
        try:
            cmd_args = args or []
            
            if ecosystem == "python":
                full_cmd = ["python", command] + cmd_args
            elif ecosystem == "nodejs":
                # Detect package manager
                npm_result = await self._execute_command("npm", ["--version"])
                bun_result = await self._execute_command("bun", ["--version"])
                
                if bun_result.get("success") and command in ["run", "start", "test"]:
                    full_cmd = ["bun", command] + cmd_args
                elif npm_result.get("success") and command in ["run", "start", "test"]:
                    full_cmd = ["npm", command] + cmd_args
                else:
                    full_cmd = ["npm", "run", command] + cmd_args
            else:
                return {"error": f"Unknown ecosystem: {ecosystem}"}
            
            return await self._execute_command(*full_cmd)
        
        except Exception as e:
            return {"error": f"Failed to run command: {str(e)}"}
    
    async def _list_dependencies(self, ecosystem="auto"):
        try:
            if ecosystem == "auto":
                # Auto-detect
                if Path("pyproject.toml").exists() or Path("requirements.txt").exists():
                    ecosystem = "python"
                elif Path("package.json").exists():
                    ecosystem = "nodejs"
                else:
                    return {"error": "Could not detect project type"}
            
            if ecosystem == "python":
                pip_result = await self._execute_command("pip", ["list"])
                if pip_result.get("success"):
                    return {
                        "success": True,
                        "ecosystem": "python",
                        "dependencies": pip_result.get("stdout", "")
                    }
            
            elif ecosystem == "nodejs":
                if Path("bun.lockb").exists():
                    result = await self._execute_command("bun", ["pm", "ls"])
                    pm = "bun"
                else:
                    result = await self._execute_command("npm", ["list", "--depth=0"])
                    pm = "npm"
                
                if result.get("success"):
                    return {
                        "success": True,
                        "ecosystem": "nodejs",
                        "package_manager": pm,
                        "dependencies": result.get("stdout", "")
                    }
            
            return {"error": f"Could not list {ecosystem} dependencies"}
        
        except Exception as e:
            return {"error": f"Failed to list dependencies: {str(e)}"}
    
    async def _execute_command(self, *cmd, cwd=None):
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
                "command": " ".join(cmd)
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "command": " ".join(cmd)
            }

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
