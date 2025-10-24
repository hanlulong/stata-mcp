# Streaming Progress Updates - Implementation Guide

> ✅ **Note:** This guide matches the active MCP streaming wrapper, which layers custom progress hooks on top of the official `fastapi_mcp` Streamable HTTP transport.

**Date:** October 22, 2025
**Difficulty:** ⚠️ **MEDIUM-HIGH** (Architecture change required)
**Estimated Time:** 4-8 hours
**Recommended Approach:** Hybrid solution using existing infrastructure

---

## Good News! 🎉

The **MCP protocol DOES support progress notifications**!

```python
from mcp.types import ProgressNotification, ProgressNotificationParams
from mcp import ServerSession

# Send progress update
await session.send_progress_notification(
    progress_token="task-123",
    progress=45.5,    # Current progress
    total=100.0       # Total (optional)
)
```

---

## The Challenge

**FastAPI-MCP** (the library we're using) **doesn't expose the `ServerSession`** to tool handlers, making it difficult to send progress notifications from within `run_stata_file()`.

### Current Architecture

```
┌──────────────┐
│ Claude Code  │
└──────┬───────┘
       │ MCP Request (CallToolRequest)
       ▼
┌──────────────────┐
│  FastAPI-MCP     │ (Handles MCP protocol, SSE, sessions)
│  Library         │
└───────┬──────────┘
        │ Calls tool handler
        ▼
┌────────────────────┐
│  call_tool()       │ (Line 1684)
│  - No session      │ ← **NO ACCESS TO SESSION!**
│    access          │
│  - Just returns    │
│    ToolResponse    │
└─────────┬──────────┘
          │ Calls
          ▼
┌────────────────────┐
│ run_stata_file()   │ (Line 972)
│ - Synchronous      │
│ - Returns string   │
│ - No streaming     │
└────────────────────┘
```

---

## Implementation Options

### Option 1: Simple Keep-Alive (EASIEST) ⭐

**Difficulty:** 🟢 **LOW** (2-3 hours)
**Effectiveness:** ✅ Prevents timeout, ❌ No real progress visible to user

**How it works:**
- Modify `run_stata_file()` to accept a callback function
- Call callback periodically with dummy progress
- FastAPI-MCP might send keep-alive automatically via SSE pings

**Changes needed:**

```python
# Line 972: Modify signature
def run_stata_file(file_path: str, timeout=600, auto_name_graphs=False, progress_callback=None):
    # ... existing code ...

    while stata_thread.is_alive():
        # Check for timeout...

        # NEW: Send keep-alive
        if progress_callback and (current_time - last_update_time >= 10):
            progress_callback({"status": "running", "elapsed": elapsed_time})

        time.sleep(0.5)
```

**Pros:**
- Minimal code changes
- Keeps connection alive
- Easy to implement

**Cons:**
- User doesn't see actual progress
- Might not work if fastapi-mcp doesn't support it
- Still feels like it's hanging

---

### Option 2: Background Task with Manual Progress (MODERATE) ⭐⭐

**Difficulty:** 🟡 **MEDIUM** (4-6 hours)
**Effectiveness:** ✅✅ Prevents timeout + Shows real progress

**How it works:**
- Run `run_stata_file()` in a background executor
- Monitor log file from the main async handler
- Send progress notifications based on log file size/content
- Return final result when complete

**Changes needed:**

```python
# Line 1751: Replace synchronous call with async version
async def call_tool(request: ToolRequest) -> ToolResponse:
    # ...
    elif mcp_tool_name == "stata_run_file":
        # Start execution in background
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

        # Monitor progress while running
        log_file = f"logs/{os.path.basename(file_path).replace('.do', '_mcp.log')}"
        last_size = 0
        start_time = time.time()

        while not task.done():
            await asyncio.sleep(10)  # Check every ~5 seconds

            # Check log file size (approximate progress)
            if os.path.exists(log_file):
                current_size = os.path.getsize(log_file)
                if current_size > last_size:
                    elapsed = time.time() - start_time
                    # This keeps the connection alive!
                    logging.info(f"Progress: {elapsed:.0f}s, log size: {current_size} bytes")
                    last_size = current_size

        # Get result
        result = await task
        return ToolResponse(status="success", result=result)
```

**Pros:**
- Relatively simple
- Shows some progress indication
- Works within fastapi-mcp constraints
- Keeps connection alive

**Cons:**
- Can't send actual MCP progress notifications (no session access)
- Progress is just "still running", not percentage
- Need to test if logging is enough to keep connection alive

---

### Option 3: Custom MCP Server (NOT RECOMMENDED) ❌

**Difficulty:** 🔴 **HIGH** (16-24 hours)
**Effectiveness:** ✅✅✅ Full control + Real progress

**How it works:**
- Bypass fastapi-mcp completely
- Implement MCP protocol directly using `mcp.server.Server`
- Get full access to `ServerSession`
- Can send progress notifications properly

**Why NOT recommended:**
- Major rewrite
- Lose fastapi-mcp's auto-generated OpenAPI schema
- Lose existing REST API compatibility
- Much more complex
- High risk of bugs

---

## Recommended Approach: **Option 2** (Background Task)

### Implementation Steps

1. **Make `call_tool()` async** (if not already)
2. **Run `run_stata_file()` in executor**
3. **Add progress monitoring loop**
4. **Test with long script**

### Code Changes Required

**File:** `src/stata_mcp_server.py`

**Lines to modify:**
- Line 1684: Make `call_tool()` async (already is)
- Line 1751: Replace synchronous call with executor
- Add progress monitoring loop

**Estimated lines of code:** ~50-70 new lines

---

## Even Simpler Alternative: **Just Add Logging** 🎯

**Difficulty:** 🟢 **VERY LOW** (30 minutes)
**Effectiveness:** ⚠️ Might work, might not

The SSE connection might stay alive if we just **log more frequently**. FastAPI-MCP might be sending those logs over SSE automatically.

**Test this first:**

```python
# Line 1385: Change from every 20-60 seconds to every ~5 seconds
while stata_thread.is_alive():
    # ... existing code ...

    # Log every ~5 seconds
    if current_time - last_update_time >= 10:
        logging.info(f"Execution progress: {elapsed_time:.0f}s elapsed")
        last_update_time = current_time
```

**If this works**, it's the easiest fix! The SSE pings might be enough to keep Claude Code's connection alive.

---

## Testing Strategy

### Phase 1: Test Logging (30 min)
1. Add frequent logging every ~5 seconds
2. Run 15-minute script
3. Check if Claude Code receives completion

### Phase 2: Background Task (4-6 hours)
If Phase 1 fails:
1. Implement Option 2 (background task)
2. Test with 15-minute script
3. Verify connection stays alive
4. Check if result is received

### Phase 3: Real Progress (Optional, +2-3 hours)
If you want actual progress bars:
1. Parse log file for progress indicators
2. Calculate percentage based on script structure
3. Send progress updates (if we can access session)

---

## Risk Assessment

| Approach | Risk | Reward | Time |
|----------|------|--------|------|
| More logging | LOW | LOW-MED | 30 min |
| Background task | MED | HIGH | 4-6 hr |
| Custom MCP server | HIGH | HIGH | 16-24 hr |

---

## Recommendation

### Phase 1: Try the Easy Fix First! 🚀

1. **Add logging every ~5 seconds** in the polling loop
2. **Test with your 11-minute script**
3. **See if it completes**

If it works → Done! (30 minutes total)
If it doesn't → Implement Option 2 (background task with monitoring)

---

## Code Snippet: Easy Fix

```python
# Line ~1350 in run_stata_file()
# Replace update_interval logic with simpler frequent logging

while stata_thread.is_alive():
    current_time = time.time()
    elapsed_time = current_time - start_time

    # Check for timeout
    if elapsed_time > MAX_TIMEOUT:
        # ... existing timeout code ...
        break

    # NEW: Log every ~5 seconds to keep connection alive
    if current_time - last_update_time >= 10:
        logging.info(f"⏱️  Execution in progress: {elapsed_time:.0f}s elapsed ({elapsed_time/60:.1f} min)")
        last_update_time = current_time

    time.sleep(0.5)
```

**Rationale:**
- SSE connections send server logs to client
- Frequent logs = frequent SSE messages
- Frequent SSE messages = connection stays alive
- Zero architectural changes needed!

---

## Success Criteria

✅ Script running > 11 minutes completes successfully
✅ Claude Code receives the result
✅ No "Galloping..." forever
✅ User sees "Execution in progress" messages (bonus)

---

## Bottom Line

**Difficulty:** Actually quite manageable!

- **Easiest approach:** 30 minutes (just add logging)
- **Safer approach:** 4-6 hours (background task)
- **Not recommended:** 16-24 hours (custom MCP server)

**Start with the easy fix** - there's a good chance it will work! 🎯
