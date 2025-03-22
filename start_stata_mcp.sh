#!/bin/bash
# Launcher script for Stata MCP server

# Activate virtual environment
source .venv/bin/activate

# Run the server with explicit Python path
python stata_mcp_server.py "$@"
