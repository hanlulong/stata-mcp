# Long Execution HTTP Timeout Issue

**Date:** October 22, 2025
**Status:** ❌ **Critical Issue Identified**
**Affects:** Scripts running longer than ~10-11 minutes

---

## Problem Summary

**Claude Code disconnects from long-running MCP sessions**, causing the response to never be received even though the server successfully completes the execution.

### Evidence

**Script:** `run_LP_analysis.do`
**Execution Time:** 662.9 seconds (11 minutes, 3 seconds)
**Result:** ❌ Claude Code stuck in "Galloping..." state indefinitely

**Server Log Timeline:**
```
18:12:22 - Started execution (timeout: 1200s / 20 min)
18:23:25 - Script completed successfully
18:23:25 - "Got event: http.disconnect. Stop streaming." ← CLIENT DISCONNECTED!
18:23:25 - Tried to send response chunk (TOO LATE - connection already closed)
18:23:25 - Two client sessions disconnected
18:23:40+ - SSE pings continue from OTHER connections
```

### Root Cause

**HTTP Connection Timeout:**
When a script runs for more than ~10-11 minutes:

1. ✅ Server executes script correctly
2. ✅ Server captures all output
3. ❌ **Claude Code's HTTP client times out** waiting for response
4. ❌ Client sends `http.disconnect` event
5. ❌ Server SSE stream closes
6. ✅ Script continues running and completes
7. ❌ Server tries to send response to **closed connection**
8. ❌ **Claude Code never receives the result**
9. ❌ UI stays stuck in "Galloping..." state forever

---

## Why Short Scripts Work

**Test Script:** `test_timeout.do`
**Execution Time:** 70.4 seconds (1 minute, 10 seconds)
**Result:** ✅ Works perfectly

**No `http.disconnect` events** in the logs for short executions!

---

## Current Code Behavior

### Progress Updates (Lines 1349-1393)

The code DOES have progress tracking:

```python
# Check if it's time for an update
if current_time - last_update_time >= update_interval:
    # Read new log content
    progress_update = f"\n*** Progress update ({elapsed_time:.0f} seconds) ***\n"
    progress_update += "\n".join(meaningful_lines[-10:])
    result += progress_update  # ← Accumulates in string, sent only at END
```

**Problem:** Progress is accumulated in the `result` string but **not sent to client** until script completes.

### Current Architecture

```
┌─────────────┐
│ Claude Code │ (HTTP client with ~10-11 minute timeout)
└──────┬──────┘
       │ MCP Request
       ▼
┌─────────────────┐
│ FastAPI Server  │
│   (SSE Stream)  │
└───────┬─────────┘
        │ Calls run_stata_file()
        ▼
┌────────────────────┐
│  run_stata_file()  │
│  - Runs script     │
│  - Accumulates     │
│    output in       │
│    'result' string │
│  - Returns at end  │
└────────┬───────────┘
         │ After 662.9 seconds
         ▼
┌─────────────────┐
│  MCP Handler    │ ← Tries to send response
│  Returns via    │ ← But connection ALREADY CLOSED!
│  SSE            │
└─────────────────┘
```

---

## Attempted Workarounds (Won't Work)

### ❌ 1. Increase Timeout on Server
- Server timeout is 1200 seconds (20 minutes) - already plenty
- Problem is **client-side HTTP timeout**, not server timeout

### ❌ 2. Increase Client Timeout
- Claude Code's HTTP client timeout is not configurable by us
- Likely set by Claude's infrastructure (10-11 minutes seems reasonable for HTTP)

### ❌ 3. Make Script Faster
- Some scripts genuinely need > 10 minutes
- User can't control execution time for complex analyses

---

## Potential Solutions

### Solution 1: Streaming Progress Updates (Recommended)

Send progress messages via SSE **during execution** to keep connection alive.

**Pros:**
- Keeps HTTP connection alive
- User sees real-time progress
- No response size limits
- Better UX

**Cons:**
- Requires significant refactoring
- Need to change `run_stata_file()` to accept SSE stream
- MCP handler needs to support streaming responses

**Implementation:**
```python
async def run_stata_file_streaming(file_path, timeout, sse_stream):
    # ... start execution ...

    while stata_thread.is_alive():
        # Check for progress
        if current_time - last_update_time >= update_interval:
            # Send progress via SSE
            await sse_stream.send({
                "type": "progress",
                "content": progress_update
            })

        # Check for timeout
        if elapsed_time > MAX_TIMEOUT:
            break

    # Send final result
    await sse_stream.send({
        "type": "result",
        "content": final_result
    })
```

### Solution 2: Keep-Alive Pings

Send SSE pings or empty progress messages **from the MCP handler** while waiting for `run_stata_file()` to complete.

**Pros:**
- Simpler to implement
- Doesn't require changing `run_stata_file()`
- Keeps connection alive

**Cons:**
- User doesn't see actual progress
- Still waiting without feedback
- Need to make `run_stata_file()` async or run in background task

**Implementation:**
```python
async def handle_run_file_mcp(request):
    # Start execution in background
    task = asyncio.create_task(run_stata_file_async(file_path, timeout))

    # Send keep-alive messages while waiting
    while not task.done():
        # Send ping every 30 seconds
        await sse_stream.send_ping()
        await asyncio.sleep(30)

    # Get result and send final response
    result = await task
    return ToolResponse(status="success", result=result)
```

### Solution 3: Job Queue System

For very long scripts, return immediately with a job ID and let client poll for results.

**Pros:**
- No timeout issues
- Can handle arbitrarily long scripts
- Client can disconnect and reconnect

**Cons:**
- Completely different architecture
- Requires persistent job storage
- More complex UX
- Not compatible with current MCP protocol

---

## Recommended Immediate Fix

**Hybrid Approach: Send Progress via SSE**

1. **Modify MCP handler** to run `run_stata_file()` in async background task
2. **Monitor progress** by checking log file size/content
3. **Send SSE progress messages** every 30-60 seconds
4. **Send final result** when complete

This keeps the connection alive while maintaining current architecture with minimal changes.

**Files to modify:**
- `src/stata_mcp_server.py` (lines ~1714-1776) - MCP handler for `stata_run_file`
- Make `run_stata_file()` run in executor or convert to async

---

## Test Case

**To reproduce:**
```python
# Run a script that takes > 10 minutes
mcp.tools.stata_run_file(
    file_path="/path/to/long_script.do",
    timeout=1200
)
```

**Expected:** Should complete and return results
**Actual:** Claude Code disconnects at ~11 minutes, never receives response

---

## Workaround for Users (Temporary)

Until fixed, for scripts > 10 minutes:

1. **Split long scripts** into smaller chunks (< 10 min each)
2. **Use VS Code extension** directly (not MCP/Claude Code)
3. **Run Stata directly** and check log files
4. **Monitor log files** manually while Claude Code is "Galloping"

---

## Impact

**Severity:** High
**Affected Users:** Anyone running scripts > 10 minutes via Claude Code MCP
**Workaround Available:** Yes (run via VS Code extension instead of MCP)
**Fix Priority:** High (architectural change required)

---

## Related Issues

- Timeout feature works correctly (tested with 12s, 30s timeouts)
- Short scripts (< 10 min) work perfectly
- Server-side timeout (20 min) is adequate
- Problem is **client HTTP timeout**, not server timeout

---

**Status:** Issue documented, solution identified, awaiting implementation
