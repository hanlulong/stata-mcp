# Progressive Output Implementation Approach

## Research Findings

### Claude Code Issues (Confirmed)

1. **Issue #3174**: MCP `notifications/message` received but not displayed
   - Status: Open, assigned
   - No workaround available
   - Claude Code silently discards notifications

2. **Issue #5960**: Streamable HTTP only shows first chunk
   - Subsequent streaming outputs don't appear
   - Suggestion: Use SSE transport (but we already are!)

### Current Server Behavior

We connect via HTTP Streamable (`/mcp-streamable`):
- ✅ Notifications sent via SSE chunks
- ✅ All 26 notifications logged
- ❌ Claude Code doesn't display them

## Potential Workarounds

### Approach 1: Include Output in Tool Response Text ✅

Instead of streaming during execution, **accumulate all output and return it in the final response**.

**Status:** ✅ **Already implemented!**

```python
# Final response includes all output
return {
    "content": [{
        "type": "text",
        "text": full_stata_output_with_all_iterations
    }],
    "isError": False
}
```

**Limitation:** User doesn't see anything until completion.

### Approach 2: Return Multiple Content Items

MCP tool responses can include **multiple content items**. What if we append content during execution?

```python
result_content = []

while not task.done():
    new_output = read_stata_log()
    if new_output:
        result_content.append({
            "type": "text",
            "text": f"[{elapsed}s] {new_output}"
        })

return {"content": result_content}
```

**Problem:** MCP tools must return atomically - can't update response mid-execution.

### Approach 3: Use Resources with Updates

Create a **dynamic resource** that updates during execution:

```python
# Register resource
@server.list_resources()
async def list_resources():
    return [Resource(
        uri="stata://execution/current",
        name="Current Stata Output",
        mimeType="text/plain"
    )]

# Update resource during execution
await server.send_resource_updated("stata://execution/current")
```

**Problem:** Claude Code would need to poll the resource, not automatic.

### Approach 4: Custom Status Display in Response

Format the final response to show **timeline of execution**:

```python
response = f"""
=== Stata Execution Timeline ===

[0s] ▶️  Started: test_timeout.do
[6s] ⏱️  Progress: Iteration 6 completed
[12s] ⏱️  Progress: Iteration 12 completed
...
[72s] ✅ Completed

=== Final Output ===
{full_stata_output}
"""
```

**Status:** ✅ Could implement easily
**Benefit:** Shows progression in final result
**Limitation:** Still not real-time

### Approach 5: Split Into Multiple Tool Calls

Break execution into chunks:

1. `stata_run_file_start()` - Returns handle
2. `stata_check_progress(handle)` - Returns current output
3. `stata_get_result(handle)` - Returns final output

**Problem:** Requires Claude Code to make multiple calls manually.

### Approach 6: Wait for Claude Code Fix

**This is the correct long-term solution.**

Your server already implements streaming correctly:
- ✅ Sends notifications every 6 seconds
- ✅ Includes recent output
- ✅ Uses proper MCP protocol
- ✅ Works with MCP Python SDK

## Recommended Implementation

### Immediate: Enhance Final Response (Approach 4)

Modify the tool response to include an execution timeline:

```python
# In the streaming wrapper
timeline = []

while not task.done():
    elapsed = time.time() - start_time
    new_output = read_stata_log()

    # Log for timeline
    timeline.append(f"[{elapsed:.0f}s] {new_output}")

    # Also send notification (for future when Claude Code fixes it)
    await send_log("notice", new_output)

# Include timeline in final response
final_output = f"""
## Execution Timeline
{chr(10).join(timeline)}

## Complete Output
{full_output}
"""

return {"content": [{"type": "text", "text": final_output}]}
```

This way:
- ✅ Users see what happened when
- ✅ Progressive information preserved
- ✅ Works today with current Claude Code
- ✅ No breaking changes when Claude Code adds notification support

### Medium-term: Document Limitation

Add to README:

```markdown
## Known Limitations

### Real-time Progress Display

Due to Claude Code issue #3174, progress notifications are not currently
displayed in the UI during execution. However, the final response includes
a complete timeline showing when each step occurred.

**Current behavior:**
- Execution runs in background
- Final response shows complete timeline
- Users can monitor log file for real-time updates

**Future:** When Claude Code implements notification display, real-time
updates will automatically appear without server changes.
```

### Long-term: Monitor Claude Code Issues

Track these issues:
- #3174 - Notification display
- #5960 - Streaming HTTP chunks

When fixed, your existing implementation will work immediately.

## Example Timeline Output

```
## Stata Execution: test_timeout.do

### Timeline
[0s]   ▶️  Execution started
[2s]   ⏱️  2s elapsed - Inspecting output...
[2s]   📝 Recent: display "Running 70 iterations..."
[8s]   ⏱️  8s elapsed
[14s]  ⏱️  14s elapsed
[14s]  📝 Recent: Progress: Completed iteration 10
[20s]  ⏱️  20s elapsed
[26s]  ⏱️  26s elapsed
[26s]  📝 Recent: Progress: Completed iteration 20
...
[72s]  ✅ Execution completed in 72.0s

### Complete Output
[Full Stata log output here]
```

This provides value even without real-time display!

## Implementation File

Modify: `/Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.3.4/src/stata_mcp_server.py`

Function: `execute_with_streaming` (around line 3164)

Add timeline accumulation and include in final response.
