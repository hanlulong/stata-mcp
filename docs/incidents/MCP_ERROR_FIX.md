# MCP "Unknown tool: http://apiserver" Error - RESOLVED

> ✅ **Note:** The MCP streaming wrapper now operates alongside the official `fastapi_mcp` Streamable HTTP transport, emitting progress/log updates while `stata_run_file` executes.

## Problem
After implementing SSE streaming for the `/run_file` endpoint, the MCP tool `stata_run_file` started returning:
```
Error: Unknown tool: http://apiserver
```

## Root Cause
The issue was caused by changing the `/run_file` endpoint to return `StreamingResponse` instead of `Response`.

FastAPI-MCP automatically converts HTTP endpoints into MCP tools, but it expects endpoints to return JSON-serializable responses, not streaming responses. When the endpoint returned `StreamingResponse`, the MCP protocol couldn't properly serialize the tool, causing the registration to fail.

## Solution
Created TWO separate endpoints:

### 1. `/run_file` - MCP-Compatible Endpoint (Line 1750)
```python
@app.get("/run_file", operation_id="stata_run_file", response_class=Response)
async def stata_run_file_endpoint(
    file_path: str,
    timeout: int = 600
) -> Response:
    """Run a Stata .do file and return the output (MCP-compatible endpoint)"""
    result = run_stata_file(file_path, timeout=timeout)
    formatted_result = result.replace("\\n", "\n")
    return Response(content=formatted_result, media_type="text/plain")
```

**Purpose**:
- Used by MCP clients (Claude Code, Claude Desktop, etc.)
- Returns complete output after execution finishes
- Blocking operation - waits for Stata to finish
- JSON-serializable response
- Includes MCP streaming via log messages (~5-second intervals) built on top of the official transport with `logging/setLevel` support

### 2. `/run_file/stream` - SSE Streaming Endpoint (Line 1785)
```python
@app.get("/run_file/stream")
async def stata_run_file_stream_endpoint(
    file_path: str,
    timeout: int = 600
):
    """Run a Stata .do file and stream the output via Server-Sent Events (SSE)"""
    return StreamingResponse(
        stata_run_file_stream(file_path, timeout),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

**Purpose**:
- Used by HTTP clients (browsers, curl, custom clients)
- Streams real-time progress updates every 2 seconds
- Non-blocking - yields events while execution continues
- SSE format: `data: ...\n\n`
- Hidden from MCP tool list (excluded in FastApiMCP config)

## Configuration Changes

### MCP Exclusion List (Line 2801)
Added the streaming endpoint to the exclusion list:
```python
exclude_operations=[
    "call_tool_v1_tools_post",
    "health_check_health_get",
    "view_data_endpoint_view_data_get",
    "get_graph_graphs_graph_name_get",
    "clear_history_endpoint_clear_history_post",
    "interactive_window_interactive_get",
    "stata_run_file_stream_endpoint_run_file_stream_get"  # NEW
]
```

## Testing Results

### ✅ SSE Streaming Endpoint (`/run_file/stream`)
```bash
curl -N "http://localhost:4000/run_file/stream?file_path=/path/to/test.do"
```

**Output**:
```
data: Starting execution of test_streaming.do...

data: Executing... 2.0s elapsed

data: Executing... 4.0s elapsed

data: Executing... 6.1s elapsed

data: [Final output streamed in chunks]

data: *** Execution completed ***
```

✅ Real-time updates every 2 seconds
✅ Immediate feedback
✅ SSE format compliance

### ✅ MCP Endpoint (`/run_file`)
```python
# Via MCP protocol
stata_run_file(file_path="/path/to/test.do", timeout=600)
```

✅ MCP tool properly registered
✅ Compatible with Claude Code/Desktop
✅ Returns complete output
✅ Includes MCP streaming (~5s intervals) for keep-alive via official transport APIs

## Benefits of This Architecture

### For MCP Clients (LLMs)
- **Reliable**: Standard Response format works with all MCP clients
- **Streaming**: MCP log messages provide progress updates (~5s intervals) at `notice` level by default
- **Compatible**: No special client requirements

### For HTTP Clients (Browsers/Tools)
- **Real-time**: See output as it happens (2s intervals)
- **Responsive**: Immediate feedback on execution status
- **Standards-based**: W3C SSE specification

### Development Benefits
- **Separation of concerns**: MCP and HTTP clients use appropriate endpoints
- **Backward compatible**: Existing MCP clients work without changes
- **Future-proof**: Can enhance streaming without breaking MCP

## Usage Guide

### For MCP Clients (Claude Code, etc.)
Use the `stata_run_file` tool normally - no changes needed:
```python
stata_run_file(
    file_path="/path/to/analysis.do",
    timeout=1200
)
```

### For HTTP/Browser Clients
Use the `/run_file/stream` endpoint for real-time updates:
```javascript
const eventSource = new EventSource('/run_file/stream?file_path=/path/to/file.do');

eventSource.onmessage = (event) => {
    console.log('Progress:', event.data);
    // Update UI with real-time progress
};
```

### For curl/Command Line
```bash
# Streaming (real-time):
curl -N "http://localhost:4000/run_file/stream?file_path=/path/to/file.do"

# Regular (wait for completion):
curl "http://localhost:4000/run_file?file_path=/path/to/file.do&timeout=600"
```

## Files Modified
- `src/stata_mcp_server.py`:
  - Line 1673-1748: `stata_run_file_stream()` async generator
  - Line 1750-1783: `/run_file` endpoint (MCP-compatible)
  - Line 1785-1822: `/run_file/stream` endpoint (SSE streaming)
  - Line 2808: Added exclusion for streaming endpoint

## Status
✅ **FIXED AND TESTED**

Date: 2025-10-22
Version: 0.3.4
Fixed By: Separating MCP and SSE streaming endpoints
