# Project Rules for stata-mcp

## Server Restart Protocol

**CRITICAL: Never use `pkill -f stata_mcp_server.py` directly!**

The MCP server runs on port 4000. Killing the server process incorrectly can terminate the current Claude Code session since Claude Code also connects to port 4000.

### To restart the MCP server:

Always use the restart script:
```bash
./scripts/restart_server.sh
```

This script:
1. Auto-detects VS Code, Cursor, or Antigravity extension directory
2. Copies updated source files to the installed extension
3. Sends graceful SIGTERM (not SIGKILL) to stop the server
4. Starts the server with correct settings
5. Verifies the server is running

### After modifying Python source files:

1. Run the restart script: `./scripts/restart_server.sh`
2. Test the server: `curl -s http://localhost:4000/health`
3. Recompile VSIX if needed: `npm run compile && vsce package`

## Package Building

When building the VSIX package:
1. Ensure all new Python modules are listed in `.vscodeignore` whitelist:
   - `!src/stata_mcp_server.py`
   - `!src/session_manager.py`
   - `!src/stata_worker.py`
   - `!src/api_models.py`
   - `!src/output_filter.py`
   - `!src/utils.py`
2. Run `npm run compile` to build TypeScript
3. Run `vsce package` to create the VSIX
4. Verify contents with `unzip -l stata-mcp-*.vsix | grep src/`

## Testing

- Unit tests: `python3 -m pytest tests/test_compact_filter.py -v`
- Server health: `curl -s http://localhost:4000/health`
- MCP tools: `curl -s -X POST http://localhost:4000/v1/tools -H "Content-Type: application/json" -d '{"tool": "stata_run_selection", "parameters": {"selection": "display 1+1"}}'`

## IDE Compatibility

The extension works with VS Code, Cursor, and Antigravity IDE. The restart script auto-detects which one is installed.
