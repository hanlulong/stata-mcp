# MCP Streaming Diagnosis Report

**Date:** 2025-10-23
**Status:** ❌ Streaming NOT working - messages are buffered
**Tests Conducted:** 3

## Summary

The MCP streaming implementation is **NOT working** as intended. While the code infrastructure is in place to send log messages during execution, these messages are being **buffered** and only sent when the tool execution completes, rather than streaming in real-time.

## Test Results

### Test 1: HTTP Streamable Transport (manual HTTP)
- **File:** `test_http_streamable.py`
- **Endpoint:** `/mcp-streamable` (HTTP Streamable transport)
- **Result:** ✓ Messages received (5 log messages)
- **Issue:** All messages received at T=12.0s (execution time ~10s)
- **Conclusion:** Messages are buffered, not streamed

### Test 2: Timing Verification Test
- **File:** `test_streaming_timing.py`
- **Endpoint:** `/mcp-streamable`
- **Result:** ✗ Test timed out after 60s
- **Issue:** HTTP response never started streaming
- **Conclusion:** Response is completely buffered until execution completes

### Test 3: Official MCP SDK Client
- **File:** `test_mcp_sdk_client_fixed.py`
- **Endpoint:** `/mcp` (SSE transport)
- **Result:** ✗ No intermediate messages observed
- **Issue:** All output appeared at T=12.0s
- **Conclusion:** Confirms buffering issue with official client

## Root Cause Analysis

### Architecture

The server uses **fastapi_mcp** library which provides two transports:
1. **SSE Transport** at `/mcp` (old, for backward compatibility)
2. **HTTP Streamable Transport** at `/mcp-streamable` (new, MCP spec compliant)

### Implementation Flow

```python
# src/stata_mcp_server.py:2863
async def execute_with_streaming(*call_args, **call_kwargs):
    # ...

    # Define send_log function
    async def send_log(level: str, message: str):
        await session.send_log_message(
            level=level,
            data=message,
            logger="stata-mcp",
            related_request_id=request_id,
        )

    # Start tool execution as async task
    task = asyncio.create_task(
        original_execute(...)
    )

    # While task is running, send progress updates
    while not task.done():
        await asyncio.sleep(poll_interval)
        elapsed = time.time() - start_time

        if elapsed >= stream_interval:
            await send_log("notice", f"⏱️ {elapsed:.0f}s elapsed...")
            # ^^ This is called during execution

    # Wait for task to complete
    result = await task
    return result
```

### The Problem

1. `send_log()` calls `session.send_log_message()` during execution
2. These messages are **queued** by the session manager
3. The HTTP/SSE response **does not start** until the tool execution completes
4. All queued messages are **flushed at once** when returning the final result
5. Result: No real-time streaming

### Why This Happens

The fastapi_mcp library (or the MCP SDK's session manager) buffers all notifications until the response is ready to be sent. The response cannot start streaming until the original `execute_api_tool` function returns.

The issue is that `execute_with_streaming` is a **wrapper** around the tool execution, not a **replacement**. It waits for the tool to complete before returning, and only then does the response get sent.

## Configuration Attempts

The server tries to configure streaming mode:

```python
# src/stata_mcp_server.py:2829-2832
if getattr(mcp, "_http_transport", None):
    # Disable JSON-mode so notifications stream via SSE as soon as they are emitted
    mcp._http_transport.json_response = False
    logging.debug("Configured MCP HTTP transport for streaming responses")
```

**Status:** This configuration alone is insufficient to enable real-time streaming.

## What Works

✓ Server infrastructure (fastapi_mcp, MCP SDK)
✓ Tool execution
✓ Session management
✓ Notification queuing
✓ Message formatting
✓ SSE event delivery (at end)

## What Doesn't Work

✗ Real-time message streaming during execution
✗ Progressive SSE event delivery
✗ Keep-alive pings during long operations
✗ Immediate response start

## Possible Solutions

### Option 1: Separate Notification Channel ⭐ RECOMMENDED
Create a separate background task that opens an independent SSE stream for notifications, separate from the tool response stream.

**Pros:**
- Clean separation of concerns
- True real-time streaming
- Compatible with MCP protocol

**Cons:**
- More complex architecture
- Requires client to manage two streams

### Option 2: Custom StreamableHTTPSessionManager
Override or extend the fastapi_mcp session manager to start the response immediately and flush messages in real-time.

**Pros:**
- Single stream
- Follows MCP spec closely

**Cons:**
- Requires deep knowledge of fastapi_mcp internals
- May break with library updates

### Option 3: Direct SSE Response
Bypass the MCP SDK's session manager and implement direct SSE streaming for tool execution.

**Pros:**
- Full control over streaming
- Guaranteed real-time delivery

**Cons:**
- Breaks MCP protocol encapsulation
- More manual work
- Harder to maintain

### Option 4: Use Progress Tokens
Rely on MCP's `progressToken` mechanism instead of log messages.

**Pros:**
- Official MCP feature
- Designed for this purpose

**Cons:**
- May still be buffered
- Less flexible than log messages

## Impact on Users

- ❌ Users cannot see progress for long-running Stata scripts
- ❌ No feedback during 3+ minute operations
- ❌ Risk of timeout without visible progress
- ❌ Poor user experience for interactive work

## Next Steps

1. ✅ **COMPLETED:** Diagnose and confirm buffering issue
2. **TODO:** Research fastapi_mcp streaming capabilities
3. **TODO:** Prototype Solution Option 1 (separate notification channel)
4. **TODO:** Test with long-running Stata scripts (3+ minutes)
5. **TODO:** Verify real-time streaming works
6. **TODO:** Update documentation

## Related Files

- `src/stata_mcp_server.py:2860-3060` - execute_with_streaming wrapper
- `src/stata_mcp_server.py:2822-2832` - Transport configuration
- `test_http_streamable.py` - HTTP Streamable test
- `test_mcp_sdk_client_fixed.py` - Official SDK client test
- `test_streaming_timing.py` - Timing verification test

## MCP Specification References

- [Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http)
- [Server-Sent Events (SSE)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

## Conclusion

While the streaming infrastructure is in place, **messages are buffered rather than streamed in real-time**. To achieve true streaming, we need to either:
1. Modify how the SSE response is sent (start immediately, flush incrementally)
2. Implement a separate streaming channel for notifications
3. Work within fastapi_mcp's constraints and find a flush mechanism

**Recommendation:** Investigate fastapi_mcp's source code to understand if there's a flush mechanism or if we need to implement Option 1 (separate notification channel).
