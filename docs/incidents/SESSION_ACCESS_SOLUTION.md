# ✅ Solution Found: Accessing ServerSession in Tool Handlers!

**Date:** October 22, 2025
**Status:** 🎉 **SESSION ACCESS CONFIRMED**
**Difficulty:** 🟡 **MEDIUM** (4-6 hours with proper implementation)

---

## Discovery

After investigating the latest fastapi_mcp and MCP Python SDK, **we CAN access the ServerSession** in tool handlers!

### Key Finding

The MCP `Server` class has a `request_context` property that gives us access to the `ServerSession`:

```python
from mcp.shared.context import RequestContext

@dataclass
class RequestContext(Generic[SessionT, LifespanContextT]):
    request_id: RequestId
    meta: RequestParams.Meta | None
    session: SessionT              # ← THIS IS THE ServerSession!
    lifespan_context: LifespanContextT
```

---

## How to Access Session

### In fastapi-mcp Tool Handlers

```python
# Current fastapi-mcp code (from server.py)
@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]):
    # Get the request context
    request_context = mcp_server.request_context

    # Access the session!
    session = request_context.session  # ← ServerSession object!

    # Now you can send progress notifications!
    await session.send_progress_notification(
        progress_token=str(request_context.request_id),
        progress=50.0,
        total=100.0
    )
```

---

## Implementation for Stata MCP

### Option 1: Direct Access (Simplest)

Modify the tool handler to access session and send progress updates:

**File:** `src/stata_mcp_server.py` (Line ~1684)

```python
@app.post("/v1/tools", include_in_schema=False)
async def call_tool(request: ToolRequest) -> ToolResponse:
    try:
        # ... existing code ...

        # NEW: Try to get MCP server session if available
        mcp_session = None
        try:
            if hasattr(mcp, 'request_context'):
                ctx = mcp.request_context
                mcp_session = ctx.session
                request_id = ctx.request_id
        except Exception:
            # Not an MCP request, or context not available
            pass

        if mcp_tool_name == "stata_run_file":
            # ... existing parameter extraction ...

            # NEW: Run with progress callback
            if mcp_session:
                # Create progress callback
                async def send_progress(elapsed_seconds):
                    await mcp_session.send_progress_notification(
                        progress_token=str(request_id),
                        progress=elapsed_seconds,
                        total=timeout
                    )

                # Run with callback
                result = await run_stata_file_with_progress(
                    file_path, timeout, send_progress
                )
            else:
                # No session, run normally
                result = run_stata_file(file_path, timeout=timeout, auto_name_graphs=True)

        # ... rest of code ...
```

### Option 2: Background Task with Progress (Recommended)

Run Stata in background and send progress every 30 seconds:

```python
async def call_tool(request: ToolRequest) -> ToolResponse:
    # ... existing code ...

    if mcp_tool_name == "stata_run_file":
        # Get MCP session if available
        mcp_session = None
        request_id = None
        try:
            if hasattr(mcp, 'request_context'):
                ctx = mcp.request_context
                mcp_session = ctx.session
                request_id = ctx.request_id
        except:
            pass

        # Run Stata in background executor
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

        # Monitor and send progress while running
        start_time = time.time()
        while not task.done():
            await asyncio.sleep(30)  # Every 30 seconds

            elapsed = time.time() - start_time

            # Send progress notification if we have session
            if mcp_session:
                await mcp_session.send_progress_notification(
                    progress_token=str(request_id),
                    progress=elapsed,
                    total=timeout
                )

            # Also log for debugging
            logging.info(f"⏱️  Execution progress: {elapsed:.0f}s / {timeout}s")

        # Get final result
        result = await task

        return ToolResponse(status="success", result=result)
```

---

## Current fastapi-mcp Limitations

### Issue #228: Streaming Not Yet Supported

**Status:** Open issue (created Sept 17, 2025)
**Problem:** StreamingResponse doesn't work - all output delivered at once
**Impact:** Can't do true streaming (word-by-word output)

However, **progress notifications are different from streaming**:
- ✅ Progress notifications: Periodic updates about task status (SUPPORTED via session)
- ❌ Streaming responses: Continuous flow of output chunks (NOT SUPPORTED in fastapi-mcp)

For our use case (long-running Stata scripts), **progress notifications are sufficient**!

---

## Implementation Steps

### Step 1: Make Tool Handler Async and Get Session (1 hour)

```python
# Line 1684
async def call_tool(request: ToolRequest) -> ToolResponse:
    # Get MCP context if available
    mcp_session = None
    request_id = None
    try:
        ctx = mcp.request_context
        mcp_session = ctx.session
        request_id = ctx.request_id
    except:
        # Not an MCP call or context unavailable
        pass

    # Rest of handler...
```

### Step 2: Run Stata in Background Executor (2 hours)

```python
# For MCP calls with session, run async
if mcp_session:
    executor = ThreadPoolExecutor(max_workers=1)
    task = asyncio.get_event_loop().run_in_executor(
        executor, run_stata_file, file_path, timeout, True
    )

    # Monitor progress...
```

### Step 3: Send Progress Notifications (1 hour)

```python
while not task.done():
    await asyncio.sleep(30)
    elapsed = time.time() - start_time

    await mcp_session.send_progress_notification(
        progress_token=str(request_id),
        progress=elapsed,
        total=timeout
    )
```

### Step 4: Test and Debug (1-2 hours)

- Test with 15-minute script
- Verify Claude Code receives progress
- Ensure connection stays alive
- Check final result delivery

---

## Expected Behavior After Implementation

### Before (Current)
```
Claude Code: "Galloping..." (forever)
Server: Runs script, sends result to closed connection
User: Never sees result ❌
```

### After (With Progress Notifications)
```
Claude Code: "Galloping..."
Server: Sends progress every 30s → keeps connection alive
Claude Code: Sees progress updates (task still running)
Server: Finishes, sends result
Claude Code: Receives result ✅
User: Sees final output!
```

---

## Code Changes Summary

### Files to Modify
1. `src/stata_mcp_server.py`

### Lines to Change
- **Line ~1684**: Make `call_tool()` access MCP session
- **Line ~1751**: Run `run_stata_file()` in executor for MCP calls
- **Add**: Progress monitoring loop with `send_progress_notification()`

### Estimated Lines of Code
- ~80-100 new lines
- ~20 modified lines

---

## Alternative: Simpler Keep-Alive (30 minutes)

If you don't want to refactor for progress notifications yet, try this first:

```python
# In run_stata_file() polling loop (line ~1390)
while stata_thread.is_alive():
    # ... existing timeout check ...

    # NEW: Just log more frequently
    if current_time - last_update_time >= 30:
        logging.info(f"⏱️  Execution: {elapsed_time:.0f}s / {MAX_TIMEOUT}s")
        last_update_time = current_time

    time.sleep(0.5)
```

SSE pings and logs might be enough to keep the connection alive without any architectural changes!

---

## Recommendation

### Phase 1 (30 min): Try Simple Logging First
Add frequent logging every 30 seconds - might just work!

### Phase 2 (4-6 hours): Implement Progress Notifications
If Phase 1 doesn't work, implement the full solution with session access.

### Phase 3 (Optional): Add Percentage Progress
Parse Stata log to estimate completion percentage for better UX.

---

## Success Criteria

✅ Scripts running > 11 minutes complete successfully
✅ Claude Code receives final result
✅ No "Galloping..." forever
✅ (Bonus) User sees progress updates during execution

---

## References

### MCP Python SDK
- `mcp.shared.context.RequestContext` - Contains session
- `ServerSession.send_progress_notification()` - Send progress

### fastapi-mcp
- Issue #228 - Streaming limitation (doesn't affect progress notifications)
- `server.request_context` - Access to MCP context

### Our Codebase
- Line 1684: `call_tool()` handler
- Line 972: `run_stata_file()` function
- Line 1390: Polling loop (add logging here)

---

**Bottom Line:** The session IS accessible! Progress notifications ARE possible!

Implement Phase 1 first (simple logging), then Phase 2 if needed. 🚀
