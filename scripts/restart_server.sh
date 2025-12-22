#!/bin/bash
# Graceful server restart script
# This script restarts the Stata MCP server without disrupting active MCP connections too harshly

SRC_DIR="$(dirname "$0")/.."
PORT=4000

# Detect extension directory - check VS Code first (baseline), then Cursor
if [ -d "$HOME/.vscode/extensions/deepecon.stata-mcp-0.4.0" ]; then
    EXTENSION_DIR="$HOME/.vscode/extensions/deepecon.stata-mcp-0.4.0"
    echo "Using VS Code extension directory"
elif [ -d "$HOME/.cursor/extensions/deepecon.stata-mcp-0.4.0" ]; then
    EXTENSION_DIR="$HOME/.cursor/extensions/deepecon.stata-mcp-0.4.0"
    echo "Using Cursor extension directory"
else
    echo "ERROR: Extension not found in VS Code or Cursor"
    echo "Please install the extension first."
    exit 1
fi

echo "=== Stata MCP Server Graceful Restart ==="

# 1. Copy updated source files
echo "1. Copying updated source files..."
cp "$SRC_DIR/src/stata_mcp_server.py" "$EXTENSION_DIR/src/"
cp "$SRC_DIR/src/session_manager.py" "$EXTENSION_DIR/src/"
cp "$SRC_DIR/src/stata_worker.py" "$EXTENSION_DIR/src/"
cp "$SRC_DIR/src/api_models.py" "$EXTENSION_DIR/src/"
cp "$SRC_DIR/src/output_filter.py" "$EXTENSION_DIR/src/"
cp "$SRC_DIR/src/utils.py" "$EXTENSION_DIR/src/"
echo "   Files copied."

# 2. Send SIGTERM for graceful shutdown (not SIGKILL)
echo "2. Sending graceful shutdown signal..."
pkill -TERM -f "stata_mcp_server.py" 2>/dev/null || echo "   No server running."
sleep 3

# 3. Verify port is free
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "   Port still in use, waiting..."
    sleep 2
fi

# 4. Start new server with all settings
echo "3. Starting new server..."
cd "$EXTENSION_DIR"

# Create logs directory if it doesn't exist
mkdir -p "$EXTENSION_DIR/logs"

# Start server with all relevant settings
nohup python3 src/stata_mcp_server.py \
    --port $PORT \
    --stata-path /Applications/StataNow \
    --stata-edition mp \
    --log-file "$EXTENSION_DIR/logs/stata_mcp_server.log" \
    --log-file-location extension \
    --result-display-mode compact \
    --max-output-tokens 10000 \
    --log-level DEBUG \
    --multi-session \
    --max-sessions 8 \
    > /tmp/stata_mcp_restart.log 2>&1 &

echo "4. Waiting for server to start..."
sleep 8

# 5. Verify server is running
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "=== Server restarted successfully on port $PORT ==="
    curl -s http://localhost:$PORT/health | head -1
else
    echo "=== ERROR: Server failed to start ==="
    tail -20 /tmp/stata_mcp_restart.log
fi
