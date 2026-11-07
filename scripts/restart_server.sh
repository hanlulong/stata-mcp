#!/bin/bash
# Graceful server restart script
# This script restarts the Stata MCP server without disrupting active MCP connections too harshly

SRC_DIR="$(dirname "$0")/.."
PORT=4000

# Detect extension directory - check VS Code first (baseline), then Cursor, then Antigravity
# Picks the newest installed version in each IDE (version-sorted).
EXTENSION_DIR=""
for IDE_BASE in "$HOME/.vscode/extensions" "$HOME/.cursor/extensions" "$HOME/.antigravity/extensions"; do
    CANDIDATE=$(ls -d "$IDE_BASE"/deepecon.stata-mcp-* 2>/dev/null | sort -V | tail -1)
    if [ -n "$CANDIDATE" ] && [ -d "$CANDIDATE" ]; then
        EXTENSION_DIR="$CANDIDATE"
        echo "Using extension directory: $EXTENSION_DIR"
        break
    fi
done

if [ -z "$EXTENSION_DIR" ]; then
    echo "ERROR: Extension not found in VS Code, Cursor, or Antigravity"
    echo "Please install the extension first."
    exit 1
fi

echo "=== Stata MCP Server Graceful Restart ==="

# 1. Copy updated source files
echo "1. Copying updated source files..."
# Copy every server module (the server and worker also import graph_artifacts.py and smcl_parser.py)
cp "$SRC_DIR"/src/*.py "$EXTENSION_DIR/src/"
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

# Use the extension's own Python environment, falling back to python3
PY="$(cat "$EXTENSION_DIR/.python-path" 2>/dev/null)"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    PY=python3
fi
echo "   Using Python: $PY"

# Override with STATA_PATH=... STATA_EDITION=... if your Stata lives elsewhere
STATA_PATH="${STATA_PATH:-/Applications/StataNow}"
STATA_EDITION="${STATA_EDITION:-mp}"

# Start server with all relevant settings
nohup "$PY" src/stata_mcp_server.py \
    --port $PORT \
    --stata-path "$STATA_PATH" \
    --stata-edition "$STATA_EDITION" \
    --log-file "$EXTENSION_DIR/logs/stata_mcp_server.log" \
    --log-file-location extension \
    --result-display-mode compact \
    --max-output-tokens 10000 \
    --log-level DEBUG \
    --multi-session \
    --max-sessions 100 \
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
