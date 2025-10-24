# Streaming Output Solution for Claude Code

## Problem Statement

We want Stata output to appear **progressively in Claude Code** as it's generated, not just when execution completes.

## Current Situation

✅ **Server already sends progressive updates:**
- Reads Stata log file every 6 seconds
- Sends snippets via `send_log_message()`
- All notifications successfully sent via SSE

❌ **Claude Code doesn't display them:**
- No logging callback registered
- Notifications sent but not shown to user

## MCP Protocol Limitations

**MCP tools cannot stream responses.** From the MCP specification:
- Tool calls must return a single, final result
- No mechanism for partial/progressive results
- Tool response is atomic (all-or-nothing)

## Available MCP Mechanisms

### 1. Notifications (Current Approach)
```python
await session.send_log_message(
    level="notice",
    data="📝 Output: iteration 10 completed",
    logger="stata-mcp"
)
```

**Status:** ✅ Implemented, ❌ Claude Code doesn't display

### 2. Progress Notifications
```python
await session.send_progress_notification(
    progress_token=token,
    progress=elapsed,
    total=timeout,
    message="Current output..."
)
```

**Status:** ❌ Claude Code doesn't send `progressToken`

### 3. Resources (Not Applicable)
- Resources are for static/semi-static content
- Not designed for real-time streaming
- Would require Claude Code to poll repeatedly

## The Real Issue

**This is a Claude Code limitation, not an MCP or server limitation.**

Claude Code needs to:
1. Register a `logging_callback` to receive notifications, OR
2. Provide a `progressToken` to receive progress updates, OR
3. Implement a custom streaming mechanism

None of these are currently happening.

## Possible Solutions

### Solution 1: Wait for Claude Code Fix (Recommended)

**Action:** File bug report with Anthropic

**Evidence to include:**
- MCP Python SDK successfully receives all 26 notifications
- Server logs show notifications being sent
- Claude Code receives SSE stream but doesn't display

**Timeline:** Unknown (depends on Anthropic)

### Solution 2: Alternative Display Method

Since we can't stream to Claude Code's UI, we could:

**A. Include progressive output in final response:**
```python
# Accumulate output during execution
accumulated_output = []

while not task.done():
    # Read new output
    new_output = read_stata_log()
    accumulated_output.append(new_output)

    # Send as notification (won't display, but logged)
    await send_log("notice", new_output)

# Return ALL accumulated output in final result
return {"output": "\n".join(accumulated_output)}
```

**Status:** ✅ Already doing this (final response includes all output)

**B. Web-based viewer:**
- Serve Stata output via HTTP endpoint
- Provide URL in tool response
- User opens browser to see live output

**C. File-based monitoring:**
- Tell user where log file is
- User can `tail -f` the log file

### Solution 3: Custom Claude Code Extension

If Claude Code supports extensions/plugins, we could:
1. Create a Claude Code extension
2. Extension registers logging callback
3. Extension displays notifications in custom UI

**Status:** Unknown if Claude Code supports this

## Recommendation

### Short Term
**Accept current limitation and document it:**

```markdown
## Known Limitation

Due to a Claude Code client limitation, Stata output is only displayed after
execution completes. Progress notifications are sent by the server but not
currently displayed by Claude Code.

**Workaround:** Monitor the log file directly:
```bash
tail -f ~/.vscode/extensions/deepecon.stata-mcp-*/logs/your_script_mcp.log
```

### Medium Term
**File bug report with Anthropic:**

Title: "Claude Code doesn't display MCP logging notifications"

Description:
- MCP servers can send `notifications/message` during tool execution
- Claude Code receives these (verified in network logs)
- Claude Code doesn't display them to users
- Other MCP clients (Python SDK) work correctly

Expected: Notifications should appear in Claude Code UI
Actual: Only final tool result is shown

### Long Term
**When Claude Code is fixed:**
- No server changes needed!
- Our implementation already sends progressive updates
- Will automatically work when Claude Code registers logging callback

## Testing Evidence

### Proof Notifications Are Sent
```
Server Log:
2025-10-23 19:32:13 - MCP streaming log: ⏱️  6s elapsed
2025-10-23 19:32:13 - sse_starlette.sse - chunk: event: message
data: {"method":"notifications/message","params":{"level":"notice","data":"⏱️  6s..."}}
```

### Proof They Can Be Received
```
MCP Python SDK Test:
📢 [0.0s] Log [notice]: ▶️  Starting Stata execution
📢 [6.0s] Log [notice]: ⏱️  6s elapsed - iteration 6
... (26 notifications total)
✅ SUCCESS: All notifications received!
```

### Proof Claude Code Doesn't Display Them
```
Claude Code UI: (blank during execution)
                (only shows final result after 72 seconds)
```

## Conclusion

**The server is working correctly.** We:
- ✅ Read Stata log progressively
- ✅ Send updates every 6 seconds
- ✅ Include recent output snippets
- ✅ Use correct MCP protocol
- ✅ Verified with MCP Python SDK

**The issue is in Claude Code.** It needs to register a callback to receive and display the notifications we're already sending.

**No server changes can fix this** - it must be fixed in Claude Code's client implementation.
