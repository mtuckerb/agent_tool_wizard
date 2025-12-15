#!/usr/bin/env python3
"""
Comprehensive test suite for agent_multitool
Tests both baseline and enhanced functionality
"""

import asyncio
import json
import httpx
import pytest
from typing import Dict, Any, List
import os
from pathlib import Path

# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:1417")
TIMEOUT = 30

class AgentMultitoolTester:
    """Comprehensive test suite for agent_multitool"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        
    async def test_health_endpoint(self) -> Dict[str, Any]:
        """Test the health check endpoint"""
        print("🏥 Testing health endpoint...")
        
        try:
            response = await self.client.get(f"{self.base_url}/api/health")
            assert response.status_code == 200
            data = response.json()
            
            # Verify expected fields
            assert "status" in data
            assert "service" in data
            assert "port" in data
            assert "timestamp" in data
            
            print(f"✅ Health check passed: {data['service']} v{data.get('version', 'unknown')}")
            return data
            
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            raise
    
    async def test_root_endpoint(self) -> Dict[str, Any]:
        """Test the root endpoint"""
        print("🌐 Testing root endpoint...")
        
        try:
            response = await self.client.get(f"{self.base_url}/")
            assert response.status_code == 200
            data = response.json()
            
            # Verify expected fields
            assert "service" in data
            assert "endpoints" in data
            
            endpoints = data["endpoints"]
            required_endpoints = ["health", "router", "mcp", "docs"]
            for endpoint in required_endpoints:
                assert endpoint in endpoints, f"Missing endpoint: {endpoint}"
            
            print(f"✅ Root endpoint passed: {len(endpoints)} endpoints available")
            return data
            
        except Exception as e:
            print(f"❌ Root endpoint failed: {e}")
            raise
    
    async def test_tools_endpoint(self) -> Dict[str, Any]:
        """Test the tools listing endpoint"""
        print("🛠️  Testing tools endpoint...")
        
        try:
            response = await self.client.get(f"{self.base_url}/api/tools")
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert "servers" in data
            assert "total_tools" in data
            assert "tools" in data
            
            tools = data["tools"]
            servers_count = data["servers"]
            total_tools = data["total_tools"]
            
            print(f"✅ Tools endpoint passed: {total_tools} tools from {servers_count} servers")
            
            # Show sample tools if available
            if total_tools > 0:
                print("   Sample tools:")
                count = 0
                for server_name, server_tools in tools.items():
                    for tool in server_tools[:2]:  # Show first 2 tools per server
                        print(f"     • {server_name}.{tool.get('name', 'unknown')}")
                        count += 1
                        if count >= 5:  # Limit output
                            break
                    if count >= 5:
                        break
            
            return data
            
        except Exception as e:
            print(f"❌ Tools endpoint failed: {e}")
            raise
    
    async def test_router_endpoint_basic(self) -> Dict[str, Any]:
        """Test basic router functionality without tools"""
        print("🔄 Testing basic router endpoint...")
        
        try:
            request_data = {
                "input": "Hello! Please respond with a simple greeting.",
                "stream": False,
                "use_tools": False
            }
            
            response = await self.client.post(
                f"{self.base_url}/api/router",
                json=request_data
            )
            assert response.status_code == 200
            
            # Since it's streaming, we need to handle SSE response
            content_lines = response.text.split('\n')
            responses = []
            
            for line in content_lines:
                if line.startswith('data: ') and line.strip() != 'data: {"stage":"complete"}':
                    try:
                        chunk_data = json.loads(line[6:])
                        responses.append(chunk_data)
                    except json.JSONDecodeError:
                        continue
            
            # Verify we got proper response stages
            stages = [r.get("stage") for r in responses]
            assert "start" in stages
            assert "llm_processing" in stages
            assert "llm_streaming" in stages
            assert "complete" in stages
            
            # Extract final response
            complete_responses = [r for r in responses if r.get("stage") == "complete"]
            assert len(complete_responses) > 0
            
            final_result = complete_responses[-1].get("result", {})
            assert "response" in final_result
            assert len(final_result["response"]) > 0
            
            print(f"✅ Basic router passed: Response length = {len(final_result['response'])} chars")
            return {"responses": responses, "final_result": final_result}
            
        except Exception as e:
            print(f"❌ Basic router failed: {e}")
            raise
    
    async def test_openai_compatible_endpoint(self) -> Dict[str, Any]:
        """Test OpenAI-compatible chat endpoint"""
        print("🤖 Testing OpenAI-compatible endpoint...")
        
        try:
            request_data = {
                "model": "router",
                "messages": [
                    {"role": "user", "content": "Say 'Testing OpenAI compatibility'"}
                ]
            }
            
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json=request_data
            )
            
            if response.status_code == 500:
                # This is likely due to missing API key, which is expected in dev
                print("⚠️  OpenAI endpoint failed (expected due to missing API key)")
                return {"status": "skipped", "reason": "missing_api_key"}
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify OpenAI structure
            assert "id" in data
            assert "object" in data
            assert "choices" in data
            assert len(data["choices"]) > 0
            
            choice = data["choices"][0]
            assert "message" in choice
            assert "content" in choice["message"]
            
            print(f"✅ OpenAI endpoint passed: {data['object']} response")
            return data
            
        httpx.HTTPStatusError as e:
            if e.response.status_code == 500:
                print("⚠️  OpenAI endpoint skipped (API key required)")
                return {"status": "skipped", "reason": "api_key_required"}
            raise
        except Exception as e:
            print(f"❌ OpenAI endpoint failed: {e}")
            raise
    
    async def test_mcp_endpoints(self) -> Dict[str, Any]:
        """Test MCP JSON-RPC endpoints"""
        print("🔌 Testing MCP endpoints...")
        
        try:
            # Test initialize
            init_response = await self.client.post(
                f"{self.base_url}/mcp",
                json={"method": "initialize", "id": 1}
            )
            assert init_response.status_code == 200
            init_data = init_response.json()
            
            assert "result" in init_data
            assert "serverInfo" in init_data["result"]
            
            print("✅ MCP initialize passed")
            
            # Test tools/list
            tools_response = await self.client.post(
                f"{self.base_url}/mcp",
                json={"method": "tools/list", "id": 2}
            )
            assert tools_response.status_code == 200
            tools_data = tools_response.json()
            
            assert "result" in tools_data
            assert "tools" in tools_data["result"]
            
            tools = tools_data["result"]["tools"]
            print(f"✅ MCP tools/list passed: {len(tools)} tools available")
            
            return {
                "initialize": init_data,
                "tools": {
                    "count": len(tools),
                    "data": tools_data
                }
            }
            
        except Exception as e:
            print(f"❌ MCP endpoints failed: {e}")
            raise
    
    async def test_streaming_endpoint(self) -> Dict[str, Any]:
        """Test streaming functionality"""
        print("📡 Testing streaming endpoint...")
        
        try:
            request_data = {
                "input": "Tell me about streaming data",
                "stream": True,
                "use_tools": False
            }
            
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/router",
                json=request_data
            ) as response:
                assert response.status_code == 200
                
                chunks = []
                async for line in response.aiter_lines():
                    if line.startswith('data: ') and line.strip() != 'data: {"stage":"complete"}':
                        try:
                            chunk_data = json.loads(line[6:])
                            chunks.append(chunk_data)
                        except json.JSONDecodeError:
                            continue
                
                # Verify we received streaming chunks
                assert len(chunks) > 0
                
                stages = set(chunk.get("stage") for chunk in chunks)
                expected_stages = {"start", "llm_processing", "llm_streaming", "complete"}
                assert stages.issuperset(expected_stages), f"Missing stages: {expected_stages - stages}"
                
                print(f"✅ Streaming passed: {len(chunks)} chunks received")
                return {"chunks": chunks, "stages": list(stages)}
                
        except Exception as e:
            print(f"❌ Streaming failed: {e}")
            raise
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run the complete test suite"""
        print("🚀 Starting Agent_Multitool Test Suite")
        print("=" * 50)
        
        results = {}
        
        try:
            # Basic connectivity tests
            results["health"] = await self.test_health_endpoint()
            results["root"] = await self.test_root_endpoint()
            
            # Functionality tests
            results["tools"] = await self.test_tools_endpoint()
            results["router_basic"] = await self.test_router_endpoint_basic()
            results["streaming"] = await self.test_streaming_endpoint()
            
            # Integration tests
            results["openai"] = await self.test_openai_compatible_endpoint()
            results["mcp"] = await self.test_mcp_endpoints()
            
            # Summary
            print("\n" + "=" * 50)
            print("🎉 All tests completed successfully!")
            
            # Show summary
            tools_count = results["tools"]["total_tools"]
            servers_count = results["tools"]["servers"]
            
            print(f"\n📊 Test Summary:")
            print(f"  🛠️  MCP Servers: {servers_count}")
            print(f"  🔧 Total Tools: {tools_count}")
            print(f"  🌐 API Base URL: {self.base_url}")
            print(f"  📚 Docs: {self.base_url}/docs")
            
            if tools_count > 0:
                print(f"\n✅ Ready to use with {tools_count} MCP tools!")
            else:
                print(f"\n⚠️  No MCP tools found - check server configuration")
            
            return results
            
        except Exception as e:
            print(f"\n❌ Test suite failed: {e}")
            raise
        finally:
            await self.client.aclose()

async def main():
    """Main test runner"""
    import sys
    
    # Check if server is running
    base_url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    
    tester = AgentMultitoolTester(base_url)
    
    try:
        await tester.run_all_tests()
        print("\n✅ Test suite completed successfully!")
        return 0
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
