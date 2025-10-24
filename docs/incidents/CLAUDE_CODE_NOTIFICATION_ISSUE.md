# Claude Code Notification Display Issue

## Summary

The Stata MCP server **IS** correctly sending progress notifications via the MCP protocol, but **Claude Code is NOT displaying them** in its UI. This is a client-side UI issue, not a server-side problem.

## Evidence

### 1. Server is Sending Notifications

From the server logs at `/Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.3.4/logs/stata_mcp_server.log`:

```
2025-10-23 11:09:53,315 - sse_starlette.sse - DEBUG - chunk: b'event: message\r\ndata: {"method":"notifications/message","params":{"level":"notice","logger":"stata-mcp","data":"⏱️  20s elapsed / 600s timeout\n\n(📁 Inspecting Stata log for new output...)"},"jsonrpc":"2.0"}\r\n\r\n'

2025-10-23 11:09:59,319 - sse_starlette.sse - DEBUG - chunk: b'event: message\r\ndata: {"method":"notifications/message","params":{"level":"notice","logger":"stata-mcp","data":"⏱️  26s elapsed / 600s timeout\n\n📝 Recent output:\nProgress: Completed iteration 20 of  at 11:09:53"},"jsonrpc":"2.0"}\r\n\r\n'

2025-10-23 11:10:05,322 - sse_starlette.sse - DEBUG - chunk: b'event: message\r\ndata: {"method":"notifications/message","params":{"level":"notice","logger":"stata-mcp","data":"⏱️  32s elapsed / 600s timeout\n\n📝 Recent output:\nProgress: Completed iteration 30 of  at 11:10:03"},"jsonrpc":"2.0"}\r\n\r\n'
```

**Notifications sent every 6 seconds during the 70-second execution:**
- ⏱️  14s elapsed
- ⏱️  20s elapsed (with Stata output)
- ⏱️  26s elapsed (with "Progress: Completed iteration 20")
- ⏱️  32s elapsed (with "Progress: Completed iteration 30")
- ⏱️  38s elapsed
- ⏱️  44s elapsed (with "Progress: Completed iteration 40")
- ⏱️  50s elapsed
- ⏱️  56s elapsed (with "Progress: Completed iteration 50")
- ⏱️  62s elapsed (with "Progress: Completed iteration 60")
- ⏱️  68s elapsed
- ✅ Execution completed in 72.0s

### 2. MCP SDK Client CAN See Notifications

When testing with the official MCP Python SDK client (`test_mcp_streamable_client.py`), notifications ARE received and displayed:

```
2025-10-23 09:01:16,202 - mcp.client.streamable_http - DEBUG - SSE message: root=JSONRPCNotification(method='notifications/message', params={'level': 'notice', 'logger': 'stata-mcp', 'data': '▶️  Starting Stata execution: test_mcp_client.do'}, jsonrpc='2.0')

2025-10-23 09:01:18,203 - mcp.client.streamable_http - DEBUG - SSE message: root=JSONRPCNotification(method='notifications/message', params={'level': 'notice', 'logger': 'stata-mcp', 'data': '⏱️  2s elapsed / 10s timeout\n\n(📁 Inspecting Stata log for new output...)'}, jsonrpc='2.0')
```

### 3. Protocol Compliance

The notifications follow the correct MCP protocol format:
- **Method**: `notifications/message` (correct per MCP spec)
- **Params**: `{"level": "notice", "logger": "stata-mcp", "data": "..."}`
- **Transport**: SSE (Server-Sent Events) with proper chunking
- **Event type**: `event: message` (correct for MCP over SSE)

## Root Cause

**Claude Code does not display `notifications/message` in its UI during tool execution.**

Possible reasons:
1. Claude Code's UI may not be designed to show real-time notifications
2. Notifications might be received but buffered until tool execution completes
3. The Claude Code client might only process and display the final `result` response
4. UI design decision to keep the interface clean during execution

## What Works

1. ✅ Server correctly sends notifications via SSE
2. ✅ Official MCP SDK clients can receive and display notifications
3. ✅ Final results are displayed correctly in Claude Code
4. ✅ All MCP protocol standards are being followed

## What Doesn't Work

1. ❌ Claude Code UI does not show progress notifications during execution
2. ❌ Users cannot see real-time progress updates while tools are running

## Recommendations

### For Stata MCP Server (No Changes Needed)

The server implementation is correct. No changes are required on the server side.

### For Claude Code Users

Currently, there is no workaround. Progress notifications are being sent correctly, but Claude Code's UI simply doesn't display them. You will need to:

1. **Wait patiently** - The tool is still executing, just without visible progress
2. **Check server logs** - You can monitor progress in the server logs if needed:
   ```bash
   tail -f /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.3.4/logs/stata_mcp_server.log
   ```

### For Claude Code Development Team

Consider implementing one of these solutions:

1. **Add a progress indicator** - Show streaming notifications in the UI during tool execution
2. **Add a status line** - Display the most recent notification in a status bar
3. **Add a progress panel** - Create an expandable panel to show execution logs
4. **Add notification badges** - Show a count of unread notifications during execution

## Testing Commands

To verify notifications are being sent:

```bash
# Monitor server logs in real-time
tail -f /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.3.4/logs/stata_mcp_server.log | grep "notifications/message"

# Test with official MCP SDK client (shows notifications work)
.venv/bin/python test_mcp_streamable_client.py
```

## Conclusion

This is **not a bug in the Stata MCP server**. The server is functioning correctly and sending notifications according to the MCP specification. This is a **feature request for Claude Code** to display real-time progress notifications in its UI.
