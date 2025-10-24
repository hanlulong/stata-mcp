# Final Diagnosis: MCP Streaming Issue

**Date:** 2025-10-23
**Status:** ✅ ROOT CAUSE IDENTIFIED

## The Problem

MCP streaming messages are **completely buffered** and delivered all at once after tool execution completes, rather than streaming in real-time.

## Test Evidence

Using `test_raw_http_timing.py`, we observed:
```
[ 12.0s] (+12.0s) Event #1
[ 12.0s] (+0.0s) Event #2
[ 12.0s] (+0.0s) Event #3
[ 12.0s] (+0.0s) Event #4
[ 12.0s] (+0.0s) Event #5
```

All events arrived at exactly T=12.0s (after 10s Stata execution + 2s overhead). **Zero streaming**.

## Root Cause

Found in `/Users/hanlulong/Library/Python/3.12/lib/python/site-packages/fastapi_mcp/transport/http.py` lines 95-122:

```python
async def handle_fastapi_request(self, request: Request) -> Response:
    # Capture the response from the session manager
    response_started = False
    response_status = 200
    response_headers = []
    response_body = b""  # ← BUFFER

    async def send_callback(message):
        nonlocal response_started, response_status, response_headers, response_body

        if message["type"] == "http.response.start":
            response_started = True
            response_status = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body += message.get("body", b"")  # ← ACCUMULATES ALL DATA

    # Delegate to the session manager
    await self._session_manager.handle_request(request.scope, request.receive, send_callback)

    # Convert the captured ASGI response to a FastAPI Response
    headers_dict = {name.decode(): value.decode() for name, value in response_headers}

    return Response(
        content=response_body,  # ← RETURNS EVERYTHING AT ONCE
        status_code=response_status,
        headers=headers_dict,
    )
```

**The Issue:**
1. `handle_fastapi_request()` buffers ALL response data in `response_body`
2. Returns a regular `Response` with all content at once
3. Should return a `StreamingResponse` that yields chunks as they arrive

## What We Fixed (But Wasn't Enough)

✅ Set `json_response=False` in `FastApiHttpSessionManager`:
```python
http_transport = FastApiHttpSessionManager(
    mcp_server=mcp.server,
    json_response=False,  # ✓ This enables SSE format
)
```

This makes the `StreamableHTTPSessionManager` send SSE events instead of JSON. **BUT** the events are still buffered by `handle_fastapi_request()`.

## The Real Problem

`fastapi_mcp` has a **fundamental design flaw** in `FastApiHttpSessionManager.handle_fastapi_request()`:
- It's designed to capture the entire ASGI response in memory
- Then convert it to a FastAPI `Response` object
- This breaks streaming because FastAPI's regular `Response` is not streamable

## Solution Options

### Option 1: Patch fastapi_mcp (Recommended)

Override `handle_fastapi_request()` to return a `StreamingResponse`:

```python
from fastapi.responses import StreamingResponse
import asyncio

class StreamingFastApiHttpSessionManager(FastApiHttpSessionManager):
    async def handle_fastapi_request(self, request: Request) -> StreamingResponse:
        await self._ensure_session_manager_started()

        if not self._session_manager:
            raise HTTPException(status_code=500, detail="Session manager not initialized")

        # Create a queue for streaming chunks
        chunk_queue = asyncio.Queue()
        response_started = False
        response_headers = []

        async def send_callback(message):
            nonlocal response_started, response_headers

            if message["type"] == "http.response.start":
                response_started = True
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    await chunk_queue.put(body)  # Stream chunks
                if not message.get("more_body", True):
                    await chunk_queue.put(None)  # Signal end

        # Start handling request in background
        async def handle_request():
            try:
                await self._session_manager.handle_request(
                    request.scope, request.receive, send_callback
                )
            except Exception as e:
                await chunk_queue.put(e)

        task = asyncio.create_task(handle_request())

        # Wait for response to start
        while not response_started:
            await asyncio.sleep(0.01)

        # Generator to yield chunks
        async def generate():
            while True:
                chunk = await chunk_queue.get()
                if chunk is None:
                    break
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk

        headers_dict = {name.decode(): value.decode() for name, value in response_headers}

        return StreamingResponse(
            content=generate(),
            headers=headers_dict,
        )
```

### Option 2: Use SSE Transport Instead

Fall back to the SSE transport (`/mcp`) which does stream properly, but is not the standard HTTP Streamable transport per MCP spec.

### Option 3: Report Bug to fastapi_mcp

This is a bug in the `fastapi_mcp` library. The `FastApiHttpSessionManager` should support streaming responses when `json_response=False`.

## Recommendation

Implement **Option 1** as a workaround until `fastapi_mcp` is fixed.

## Files to Modify

- `src/stata_mcp_server.py`: Replace `FastApiHttpSessionManager` with our patched `StreamingFastApiHttpSessionManager`

## Expected Outcome

After fix:
```
[  2.0s] (+2.0s) Event #1
[  8.0s] (+6.0s) Event #2
[ 12.0s] (+4.0s) Event #3 (final result)
```

Events arrive as they are generated, not all at once.
