# Notification Routing Bug - Root Cause Found

## TL;DR

**Notifications ARE being sent, but to the WRONG SESSION!** Claude Code is listening on the StreamableHTTP session, but notifications are routed to an SSE session. This is a session mismatch bug.

## The Evidence

### 1. Two Different Sessions Created

From logs at `11:09:07`:

```
2025-10-23 11:09:07,468 - mcp.server.sse - DEBUG - Created new session with ID: a9a08e1e-ba01-474b-9c87-5c2bf387008b
2025-10-23 11:09:07,469 - mcp.server.streamable_http_manager - INFO - Created new transport with session ID: fa53bae066fa4e8eab220462a6f2463a
```

**Two separate sessions:**
- SSE session: `a9a08e1e-ba01-474b-9c87-5c2bf387008b`
- StreamableHTTP session: `fa53bae066fa4e8eab220462a6f2463a`

### 2. Tool Call Came Through StreamableHTTP

```
2025-10-23 11:09:33,302 - fastapi_mcp.server - DEBUG - Extracted HTTP request info from context: POST /mcp-streamable
```

Claude Code sent the tool call to `/mcp-streamable`.

### 3. Notifications Sent to SSE Session

```
2025-10-23 11:09:33,304 - sse_starlette.sse - DEBUG - chunk: b'event: message\r\ndata: {"method":"notifications/message",...
```

All notifications are being sent as SSE chunks, which go to the SSE session.

### 4. Request Context Returns Wrong Session

From `stata_mcp_server.py:3009`:

```python
session = getattr(ctx, "session", None)
...
await session.send_log_message(...)  # This sends to SSE session!
```

When the tool executes, `mcp.server.request_context.session` returns the **SSE session** (`a9a08e1e...`), not the **StreamableHTTP session** (`fa53bae0...`).

## The Root Cause

**We created a separate `StreamableHTTPSessionManager` that's isolated from fastapi-mcp's session management.**

From `stata_mcp_server.py:2843`:

```python
# Create the MCP HTTP session manager (from official SDK)
http_session_manager = StreamableHTTPSessionManager(
    app=mcp.server,
    event_store=None,
    json_response=False,  # ✓ Enable SSE streaming
    stateless=False,
)
```

This creates a **parallel** session management system. When requests come through `/mcp-streamable`:

1. ✅ They're handled by `http_session_manager` (StreamableHTTP session `fa53bae0...`)
2. ❌ But `mcp.server.request_context` still points to the SSE session (`a9a08e1e...`)
3. ❌ Notifications go to the SSE session, not the StreamableHTTP session
4. ❌ Claude Code is listening on StreamableHTTP, never receives notifications

## The Flow Diagram

```
Claude Code
    |
    | POST /mcp-streamable (tool call)
    v
StreamableHTTPSessionManager
session: fa53bae066fa4e8eab220462a6f2463a
    |
    v
Tool Execution
mcp.server.request_context.session -> a9a08e1e-ba01-474b-9c87-5c2bf387008b (WRONG!)
    |
    v
Notifications sent to SSE session
    |
    v
SSE Transport (a9a08e1e-ba01-474b-9c87-5c2bf387008b)
    |
    v
❌ Claude Code never receives (listening on fa53bae0...)
```

## Why Our Test Client Worked

Our `test_mcp_streamable_client.py` **DID** receive notifications because it:
1. Made a POST request to `/mcp-streamable`
2. Established a separate GET connection for SSE listening
3. The SDK client handles both connections and merges the streams

But Claude Code expects notifications to come through the SAME StreamableHTTP POST connection.

## The Fix

We need to use **fastapi-mcp's built-in HTTP transport** instead of creating a separate StreamableHTTPSessionManager. According to fastapi-mcp docs:

```python
# Instead of manually creating StreamableHTTPSessionManager
# Use fastapi-mcp's built-in method:
mcp.mount_http()
```

This will ensure:
1. Only ONE session is created per connection
2. Request context points to the correct session
3. Notifications are routed to the same connection that made the request

## Alternative Fix

If we must use a custom StreamableHTTPSessionManager, we need to:
1. **Update the request context** when requests come through `/mcp-streamable`
2. Ensure `mcp.server.request_context.session` points to the StreamableHTTP session, not SSE

## Verification Command

To see the session mismatch:

```bash
grep -E "Created new|session ID|POST /mcp-streamable" \
  /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.3.4/logs/stata_mcp_server.log | \
  grep -A 5 -B 5 "11:09:07"
```

## Conclusion

**This IS a server-side bug!** The notifications are being sent to the wrong session. Claude Code cannot see them because it's listening on a different session than where notifications are being sent.

**Action Required:** Fix the session routing so notifications go to the StreamableHTTP session when requests come through `/mcp-streamable`.
