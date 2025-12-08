#!/usr/bin/env bash
set -e

# Start Hayhooks REST in background
hayhooks run &

# Start Hayhooks MCP server in foreground
hayhooks mcp run
