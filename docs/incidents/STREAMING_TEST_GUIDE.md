# MCP Streaming Test Guide

## Version: 0.3.4
**Date**: October 22, 2025

> ✅ **Note:** The MCP streaming wrapper is active. It now works alongside the official `fastapi_mcp` Streamable HTTP transport, emitting log/progress updates during `stata_run_file` execution.
> ℹ️ **Logging levels:** The server defaults to `notice` severity for progress logs and respects any `logging/setLevel` requests from the client.

---

## What Was Implemented

MCP streaming support has been added to `stata_run_file` to prevent Claude Code timeouts for long-running scripts (>11 minutes).

### Key Features:
1. **Real-time progress updates** every ~5 seconds
2. **MCP log messages** with elapsed time and recent Stata output
3. **MCP progress notifications** for visual progress bars
4. **Connection keep-alive** prevents HTTP timeout
5. **Automatic fallback** if streaming fails

---

## How to Test

### Test 1: Short Script (Verify Streaming Works)

Run the 3-minute test script in Claude Code:

```
Please run this Stata script via MCP:
stata-mcp - stata_run_file(
    file_path: "/path/to/stata-mcp/tests/test_keepalive.do",
    timeout: 300
)
```

**Expected behavior:**
- ▶️ Initial message: "Starting Stata execution: test_keepalive.do"
- ⏱️ Progress updates every ~5 seconds:
  - "10s elapsed / 300s timeout"
  - "20s elapsed / 300s timeout"
  - "30s elapsed / 300s timeout"
  - etc.
- 📝 Recent output from the script (last 3 lines)
- ✅ Final message: "Execution completed in X.Xs"
- Full result returned to Claude Code

### Test 2: Long Script (Verify >11 Minute Support)

Run the actual long-running script:

```
Please run this Stata script via MCP:
stata-mcp - stata_run_file(
    file_path: "/path/to/Lu_model_simulations/scripts/run_LP_analysis.do",
    timeout: 1200
)
```

**Expected behavior:**
- Script runs for ~11 minutes (650-660 seconds)
- Progress updates appear every ~5 seconds
- Claude Code shows "in progress" status (not stuck)
- **NO "Jitterbugging..." forever**
- **NO "http.disconnect" in server logs**
- Completes successfully with full output

---

## Monitoring Server Logs

Watch the streaming in action:

```bash
tail -f ~/.vscode/extensions/deepecon.stata-mcp-*/logs/stata_mcp_server.log | grep "📡"
```

**What to look for:**
- `📡 Starting MCP streaming for /path/to/file.do`
- `📄 Will monitor log file: /path/to/log.log`
- `📡 Streamed update: X new lines` (every ~5 seconds)
- `✅ Streaming complete - execution finished in X.Xs`

---

## Success Criteria

### ✅ Streaming Working Correctly:
1. Progress messages appear in Claude Code every ~5 seconds
2. Script completes even if >11 minutes
3. Claude Code receives final result (not stuck)
4. Server logs show `📡 Streamed update` messages
5. No "http.disconnect" errors

### ❌ If Streaming Not Working:
1. Claude Code stuck in "Jitterbugging..." forever
2. Server logs show "http.disconnect" at ~11 minutes
3. No progress messages appear
4. Script completes but Claude Code never receives result

---

## Technical Implementation

### Code Location:
[`stata_mcp_server.py` lines 2676-2858](stata_mcp_server.py:2676-2858)

### How It Works:
1. Intercepts `stata_run_file` MCP calls
2. Starts execution in background task
3. Monitors Stata log file every 5 seconds
4. Every ~5 seconds:
   - Reads new log output
   - Sends progress notification (numeric)
   - Sends log message (text with recent output)
5. Keeps SSE connection alive with data flow
6. Returns final result when complete

### MCP APIs Used:
- `session.send_log_message()` - Text messages to client
- `session.send_progress_notification()` - Numeric progress updates
- `mcp.server.request_context` - Access to session from tool handler

---

## Troubleshooting

### Problem: No streaming messages appear

**Check:**
1. Server restarted with new code?
   ```bash
   ps aux | grep stata_mcp_server.py
   ```
2. Correct version (0.3.4)?
   ```bash
   code --list-extensions | grep stata-mcp
   ```
3. Server logs for errors?
   ```bash
   tail -100 ~/.vscode/extensions/deepecon.stata-mcp-0.3.4/logs/stata_mcp_server.log
   ```

### Problem: Still times out at 11 minutes

**Check server logs for:**
- `❌ Error in streaming handler` - streaming failed, fell back to non-streaming
- `http.disconnect` - Claude Code disconnected before streaming could help

**Possible causes:**
- MCP session not accessible (fastapi-mcp version issue?)
- Exception in streaming code (check full traceback in logs)
- Claude Code client has hard timeout independent of server

---

## Next Steps if Test Fails

If streaming doesn't work:

1. **Check logs** for the exact error
2. **Verify MCP session access** - does `mcp.server.request_context` work?
3. **Test with simpler progress** - just send messages, no log reading
4. **Consider alternative**: Chunk the script into smaller runs with intermediate results

If it works partially (messages sent but still timeout):

1. **Reduce interval** from 30s to 10s
2. **Send more frequent pings** between progress updates
3. **Investigate Claude Code client** timeout settings

---

## Version History

- **0.3.4** (Oct 22, 2025): Added MCP streaming support
- **0.3.3** (Oct 21, 2025): Fixed Mac-specific graph issues
- **0.3.2** (Oct 20, 2025): Open VSX compatibility

---

**Status**: ✅ Implemented, compiled, installed
**Ready for testing**: Yes
**Test script available**: `tests/test_keepalive.do`
