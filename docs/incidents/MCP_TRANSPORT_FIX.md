# MCP Transport Fix - Separate Server Instances

## Problem

When sharing a single MCP server instance between SSE and HTTP transports:
1. Requests come through `/mcp-streamable` (HTTP transport)
2. Tool executes using `mcp.server.request_context.session`
3. Session is from SSE transport (managed by fastapi_mcp)
4. Notifications sent via `session.send_log_message()` go to SSE transport
5. Claude Code listening on HTTP transport never receives them

## Solution

Create **separate MCP server instances** for each transport:

```python
# SSE Transport (via fastapi_mcp)
mcp_sse = FastApiMCP(app, ...)  # Manages SSE at /mcp

# HTTP Transport (pure MCP SDK)
from mcp.server import Server
http_server = Server("Stata MCP Server - HTTP")

# Register tools on HTTP server
@http_server.call_tool()
async def stata_run_file_http(name: str, arguments: dict):
    # Tool implementation
    pass

# Create HTTP session manager with dedicated server
http_session_manager = StreamableHTTPSessionManager(
    app=http_server,  # Uses its own server, not shared
    ...
)
```

This ensures:
- HTTP requests → HTTP server → HTTP sessions → notifications via HTTP
- SSE requests → SSE server → SSE sessions → notifications via SSE

No cross-contamination!
