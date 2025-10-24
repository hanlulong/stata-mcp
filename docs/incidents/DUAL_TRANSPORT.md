# Dual Transport Implementation

## Overview

As of version 0.3.4, stata-mcp now supports **dual transport access points** for maximum compatibility:

- **Legacy SSE Transport**: `http://localhost:4000/mcp` (backward compatible)
- **New Streamable HTTP Transport**: `http://localhost:4000/mcp-streamable` (recommended)

## Why Dual Transport?

The Model Context Protocol (MCP) has transitioned from Server-Sent Events (SSE) to Streamable HTTP as the preferred transport mechanism. The new Streamable HTTP transport offers:

- **Single endpoint model**: Eliminates the need for separate send/receive channels
- **Dynamic connection adaptation**: Behaves like standard HTTP for quick operations, streams for long-running tasks
- **Bidirectional communication**: Servers can send notifications and request information on the same connection
- **Simplified error handling**: All errors flow through one channel
- **Better scalability**: Reduced connection overhead compared to persistent SSE connections

Reference: [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)

## Configuration

### Option 1: SSE Transport (Recommended - Most Compatible)

For Claude Desktop, Claude Code, and most MCP clients:

```json
{
  "mcpServers": {
    "stata-mcp": {
      "url": "http://localhost:4000/mcp",
      "transport": "sse"
    }
  }
}
```

### Option 2: Streamable HTTP (Official MCP Transport)

For clients that support the official MCP Streamable HTTP transport:

```json
{
  "mcpServers": {
    "stata-mcp": {
      "url": "http://localhost:4000/mcp-streamable",
      "transport": "http"
    }
  }
}
```

**Note**: The `/mcp-streamable` endpoint is provided by `fastapi_mcp` and uses the official MCP Streamable HTTP transport. Most users should continue using the SSE transport at `/mcp` unless their client prefers HTTP streaming.

## Implementation Details

### Streamable HTTP Endpoint: `/mcp-streamable`

The new endpoint implements JSON-RPC 2.0 protocol and supports:

- Streams MCP log/progress updates every ~5 seconds during long-running `stata_run_file` executions.
- Built on FastAPI-MCP's official `StreamableHTTPSessionManager` in streaming (SSE) mode.

#### 1. Initialize
```bash
curl -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

Response:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "serverInfo": {
      "name": "Stata MCP Server",
      "version": "1.0.0"
    },
    "capabilities": {
      "tools": {},
      "logging": {}
    }
  }
}
```

#### 2. List Tools
```bash
curl -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

#### 3. Call Tool
```bash
curl -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "stata_run_selection",
      "arguments": {
        "selection": "display 2+2"
      }
    }
  }'
```

Response:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "4"
      }
    ]
  }
}
```

### SSE Endpoint: `/mcp`

The legacy SSE endpoint continues to work via the `fastapi-mcp` library. It automatically handles:
- Server-Sent Events streaming
- Separate message posting endpoint
- Keep-alive connections

## Testing Both Endpoints

### Test Streamable HTTP
```bash
# Initialize
curl -s -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# List tools
curl -s -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

# Run Stata code
curl -s -X POST http://localhost:4000/mcp-streamable \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"stata_run_selection","arguments":{"selection":"display 2+2"}}}'
```

### Test Legacy SSE
```bash
# Connect to SSE stream (will keep connection open)
curl http://localhost:4000/mcp
```

## Migration Path

### For New Installations
Use the Streamable HTTP transport at `/mcp-streamable` for best performance and future compatibility.

### For Existing Installations
Continue using the SSE transport at `/mcp` - it will remain supported for backward compatibility. Plan to migrate to Streamable HTTP when convenient.

### For Client Developers
Implement Streamable HTTP as the primary transport with SSE fallback:
1. Attempt connection to `/mcp-streamable` with `transport: "http"`
2. If unavailable, fall back to `/mcp` with `transport: "sse"`

## Server Logs

The server logs clearly identify which transport is being used:

**Streamable HTTP requests:**
```
📨 Streamable HTTP request: method=initialize, id=1
📨 Streamable HTTP request: method=tools/list, id=2
🔧 Streamable HTTP tool call: stata_run_selection, args={'selection': 'display 2+2'}
```

**SSE connections:**
```
MCP server listening at /mcp
MCP server mounted and initialized
```

## Technical Notes

1. **Shared Backend**: Both transports use the same underlying Stata execution logic (`run_stata_selection`, `run_stata_file`)
2. **JSON-RPC 2.0**: The Streamable HTTP endpoint implements full JSON-RPC 2.0 specification
3. **Error Handling**: Both transports return errors in their respective formats (JSON-RPC errors for Streamable HTTP, MCP errors for SSE)
4. **Timeouts**: Both support configurable timeouts for long-running operations (default: 600 seconds)

## Future Enhancements

Planned improvements for the Streamable HTTP endpoint:
- **Progressive streaming**: Send incremental output during long Stata operations
- **Cancellation support**: Clean operation termination for long-running jobs
- **Session resumption**: Reconnect and resume operations after network interruptions
- **Multiplexing**: Handle multiple concurrent requests on the same connection

## Version Compatibility

- **stata-mcp v0.3.4+**: Dual transport support (SSE + Streamable HTTP)
- **stata-mcp v0.3.3 and earlier**: SSE transport only at `/mcp`
- **MCP SDK 1.10.0+**: Streamable HTTP support
- **fastapi-mcp 0.4.0+**: Automatic SSE endpoint generation

## See Also

- [MCP Specification](https://modelcontextprotocol.io/)
- [Why MCP Deprecated SSE](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [stata-mcp README](README.md)
- [stata-mcp CHANGELOG](CHANGELOG.md)
