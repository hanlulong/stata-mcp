# Claude Desktop vs Claude Code: MCP Streaming Support

**Date:** October 23, 2025
**Question:** Does Claude Desktop support real-time streaming output better than Claude Code?

---

## Answer: **NO - Both have the same limitation**

Neither Claude Desktop nor Claude Code currently displays `notifications/message` in the chat interface during tool execution.

---

## Detailed Comparison

### Claude Desktop

**Transport:** SSE (Server-Sent Events)
**Endpoint:** `http://localhost:4000/mcp`
**Configuration:**
```json
{
  "stata-mcp": {
    "url": "http://localhost:4000/mcp",
    "transport": "sse"
  }
}
```

**Notification Behavior:**
- ✅ Receives `notifications/message` via SSE
- ❌ Does NOT display them in chat
- ⚠️  Can use OS-level notification servers (sounds/popups) as workaround

### Claude Code

**Transport:** HTTP Streamable (SSE over HTTP)
**Endpoint:** `http://localhost:4000/mcp-streamable`
**Configuration:** Via VSCode extension

**Notification Behavior:**
- ✅ Receives `notifications/message` via SSE chunks
- ❌ Does NOT display them in chat
- 🐛 **Issue #3174**: Notifications received but not displayed
- 🐛 **Issue #5960**: Only first streaming chunk shown

---

## What the Server Sends (Both Clients)

Your server sends identical notifications to both:

```json
{
  "method": "notifications/message",
  "params": {
    "level": "notice",
    "logger": "stata-mcp",
    "data": "⏱️  6s elapsed / 600s timeout\n\n📝 Recent output:\nProgress: Completed iteration 6"
  },
  "jsonrpc": "2.0"
}
```

**Frequency:** Every 6 seconds during execution
**Content:** Elapsed time + recent Stata output
**Total:** ~26 notifications for a 72-second execution

---

## MCP Specification

From MCP Spec 2025-06-18:

> "Clients **MAY**: Present log messages in the UI"

Both Claude Desktop and Claude Code **choose not to** implement this optional feature.

---

## Available Workarounds

### For Claude Desktop

**1. OS-Level Notifications**

Use a notification MCP server like `notifications-mcp-server`:
- Plays sounds when tasks start/complete
- Shows macOS Notification Center alerts
- Does NOT show progress during execution
- Only notifies at start/end

**2. Monitor Log File**

```bash
tail -f ~/.vscode/extensions/deepecon.stata-mcp-*/logs/test_timeout_mcp.log
```

### For Claude Code

**1. Monitor Log File** (same as above)

**2. Web Viewer** (if implemented)

Serve a web page showing live Stata output:
```bash
open http://localhost:4000/viewer?script=test_timeout.do
```

---

## Why Neither Client Shows Real-Time Output

### Technical Reason

**MCP Protocol:**
- Tools return a single final result (atomic)
- No mechanism for progressive tool responses
- Notifications are separate from tool results

**Client Implementation:**
- Both clients treat tool calls as "loading" states
- UI only updates when tool completes
- Notifications go to backend, not UI

### Business Reason

Anthropic likely wants to:
- Keep chat interface clean/focused
- Avoid overwhelming users with technical details
- Prioritize conversational flow

---

## What Actually Works

### ✅ MCP Python SDK

```python
async with ClientSession(..., logging_callback=my_callback) as session:
    result = await session.call_tool("stata_run_file", ...)
    # my_callback receives all 26 notifications in real-time!
```

**Why it works:** You explicitly register a callback function.

### ❌ Claude Desktop & Claude Code

No way to register a callback - they don't provide this UI feature.

---

## Recommendations

### Short Term: Document the Limitation

Add to your README:

```markdown
## Known Limitation: No Real-Time Progress Display

Due to limitations in Claude Desktop and Claude Code, Stata output only
appears after execution completes. Progress notifications are sent by the
server but not currently displayed.

**Workarounds:**
- Monitor log file: `tail -f logs/your_script_mcp.log`
- Use OS notifications (Claude Desktop only) for start/end alerts

**Future:** When Anthropic implements notification display (issue #3174),
real-time updates will work automatically without server changes.
```

### Medium Term: Build a Web Viewer

Create a simple web interface:

```python
@app.get("/viewer")
async def viewer(script: str):
    """Live view of Stata execution"""
    # Stream log file contents via SSE
    # Users open in browser alongside Claude
```

### Long Term: Wait for Anthropic

Track these issues:
- **anthropics/claude-code#3174** - Notification display
- **anthropics/claude-code#5960** - Streaming HTTP

When fixed, your server will work immediately (no changes needed).

---

## Summary

| Feature | Claude Desktop | Claude Code | MCP Python SDK |
|---------|---------------|-------------|----------------|
| Transport | SSE | HTTP Streamable | Both |
| Receives notifications | ✅ | ✅ | ✅ |
| Displays in chat | ❌ | ❌ | ✅ |
| OS notifications | ✅ (with plugin) | ❌ | N/A |
| Real-time output | ❌ | ❌ | ✅ |

**Conclusion:** Your server works correctly. Both Claude clients just don't display the notifications. Use Claude Desktop with OS notification plugin for start/end alerts, or build a web viewer for true real-time monitoring.
