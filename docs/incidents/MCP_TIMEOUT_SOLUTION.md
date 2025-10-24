# MCP Timeout Solution: Direct Tool Handler with Progress Notifications

**Date:** October 22, 2025
**Problem:** Claude Code disconnects after ~11 minutes, even with keep-alive logging
**Root Cause:** Python logging doesn't send data over SSE connection - only MCP messages do

---

## Problem Analysis

### What We Discovered

1. **Logging doesn't help**: `logging.info()` writes to log file, NOT to SSE connection
2. **SSE pings aren't enough**: The connection has pings every 15s, but Claude Code still times out
3. **Client-side timeout**: Claude Code has a hard ~660 second (11 minute) timeout for tool calls
4. **Architecture issue**: FastApiMCP uses internal HTTP requests, so we can't access MCP session

### Test Results

- Script duration: 650.9 seconds (10.8 minutes)
- Progress logs: Every 60 seconds (working correctly in log file)
- SSE pings: Every 15 seconds (working correctly)
- Result: **Still disconnects** at 10m51s - just before completion

**Conclusion**: Keep-alive logging approach doesn't work because logs don't go over the wire!

---

## Solution: Direct MCP Tool Handler

### Architecture Change

**Before (Current):**
```
Claude Code → MCP → fastapi-mcp → HTTP request → FastAPI endpoint → run_stata_file()
                                                    ↑
                                                    No session access!
```

**After (Proposed):**
```
Claude Code → MCP → Custom tool handler → run_stata_file_async()
                      ↑                          ↓
                      Has session access!   Send progress notifications
```

### Implementation

Register `stata_run_file` as a direct MCP tool instead of going through FastAPI endpoint:

```python
# After creating FastApiMCP
mcp = FastApiMCP(app, ...)
mcp.mount()

# Access the underlying MCP server
mcp_server = mcp.server

# Register custom handler for stata_run_file with progress support
@mcp_server.call_tool()
async def handle_stata_run_file_with_progress(
    name: str,
    arguments: dict
) -> list[types.TextContent]:
    if name != "stata_run_file":
        # Fallback to fastapi-mcp for other tools
        return await mcp._execute_api_tool(...)

    # Get session from request context
    ctx = mcp_server.request_context
    session = ctx.session
    request_id = ctx.request_id

    # Extract parameters
    file_path = arguments["file_path"]
    timeout = arguments.get("timeout", 600)

    # Run Stata in background
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    task = asyncio.get_event_loop().run_in_executor(
        executor,
        run_stata_file,
        file_path,
        timeout,
        True  # auto_name_graphs
    )

    # Send progress notifications every 60 seconds
    start_time = time.time()
    while not task.done():
        await asyncio.sleep(60)
        elapsed = time.time() - start_time

        # THIS IS THE KEY: Send progress over MCP connection!
        await session.send_progress_notification(
            progress_token=str(request_id),
            progress=elapsed,
            total=timeout
        )

        logging.info(f"📡 Sent progress notification: {elapsed:.0f}s / {timeout}s")

    # Get final result
    result = await task

    return [types.TextContent(type="text", text=result)]
```

---

## Alternative: Monkey-Patch fastapi-mcp

If we don't want to bypass fastapi-mcp entirely, we could monkey-patch its `_execute_api_tool` method to send progress notifications while waiting for long-running requests:

```python
# After mcp.mount()

original_execute = mcp._execute_api_tool

async def execute_with_progress(client, base_url, tool_name, arguments, operation_map):
    if tool_name == "stata_run_file":
        # Get session
        ctx = mcp.server.request_context
        session = ctx.session
        request_id = ctx.request_id

        # Start the request in background
        task = asyncio.create_task(
            original_execute(client, base_url, tool_name, arguments, operation_map)
        )

        # Send progress while waiting
        start_time = time.time()
        timeout = arguments.get("timeout", 600)

        while not task.done():
            await asyncio.sleep(60)
            elapsed = time.time() - start_time

            await session.send_progress_notification(
                progress_token=str(request_id),
                progress=elapsed,
                total=timeout
            )

        return await task
    else:
        return await original_execute(client, base_url, tool_name, arguments, operation_map)

mcp._execute_api_tool = execute_with_progress
```

---

## Recommended Approach

### Option 1: Monkey-Patch (Quickest - 1 hour)

**Pros:**
- Minimal code changes
- Keeps using FastAPI endpoints
- Easy to test

**Cons:**
- Relies on internals of fastapi-mcp
- Might break with updates

### Option 2: Custom Tool Handler (Clean - 3 hours)

**Pros:**
- Proper MCP implementation
- Full control over tool behavior
- Future-proof

**Cons:**
- More code to write
- Need to duplicate FastAPI endpoint logic

### Option 3: Fork fastapi-mcp (Long-term - 8+ hours)

**Pros:**
- Fix the root cause
- Can contribute back to project
- Benefits everyone

**Cons:**
- Time-consuming
- Need to maintain fork

---

## Next Steps

1. **Try Option 1 (Monkey-Patch)** first - quickest to implement and test
2. If it works, document it and use in production
3. If issues arise, move to Option 2 (Custom Handler)
4. Long-term: Consider contributing fix to fastapi-mcp

---

## Success Criteria

✅ Scripts running > 11 minutes complete successfully
✅ Claude Code receives final result
✅ Progress notifications sent every 60 seconds
✅ No "Jitterbugging..." forever
✅ Connection stays alive for duration of execution

---

## Code Location

**File to modify:** `src/stata_mcp_server.py`
**Line to add code after:** 2678 (after `mcp.mount()`)
**Estimated new lines:** 40-50 lines

---

## Testing Plan

1. Add monkey-patch code
2. Restart server
3. Run long script (run_LP_analysis.do, ~11 minutes)
4. Monitor server logs for "📡 Sent progress notification"
5. Verify Claude Code doesn't disconnect
6. Confirm final result is received

---

**Status:** Ready to implement Option 1 (Monkey-Patch)
