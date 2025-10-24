# Changelog

All notable changes to the Stata MCP extension will be documented in this file.

## [0.3.4] - 2025-10-23

### Added
- **Dual Transport Support**: Server now supports both SSE and Streamable HTTP transports
  - Legacy SSE endpoint: `http://localhost:4000/mcp` (backward compatible)
  - New Streamable HTTP endpoint: `http://localhost:4000/mcp-streamable` (recommended)
  - Implements JSON-RPC 2.0 protocol for Streamable HTTP
  - Supports methods: `initialize`, `tools/list`, `tools/call`
  - Single endpoint consolidates communication (no separate send/receive channels)
  - Better error handling and connection management
  - See `DUAL_TRANSPORT.md` for detailed documentation and migration guide
  - Lines 2558-2763 in `stata_mcp_server.py`

### Fixed
- **MCP "Unknown tool" error**: Fixed critical MCP registration error
  - Root cause: `/run_file` endpoint was returning `StreamingResponse` instead of regular `Response`
  - Solution: Split into two endpoints - `/run_file` (regular Response for MCP) and `/run_file/stream` (SSE for HTTP clients)
  - MCP tool registration now works correctly with fastapi-mcp
  - Lines 1673-1822 in `stata_mcp_server.py`

- **Timeout feature for "Run File" operations**: Fixed critical bug where timeout parameter was ignored
  - Changed REST API endpoint from `@app.post` to `@app.get` (line 1643 in `stata_mcp_server.py`)
  - Root cause: FastAPI POST endpoints don't automatically bind query parameters
  - Solution: GET endpoints automatically map function parameters to query string parameters
  - Now correctly respects `stata-vscode.runFileTimeout` setting from VS Code configuration
  - Tested and verified with 12-second and 30-second timeouts - triggers exactly on time

### Updated
- **Python package dependencies**: Updated to latest stable versions
  - fastapi: 0.115.12 → 0.119.1
  - uvicorn: 0.34.0 → 0.38.0
  - fastapi-mcp: 0.3.4 → 0.4.0
  - mcp: Added 1.18.0 (was missing)
  - pandas: 2.2.3 → 2.3.3
  - Updated `src/requirements.txt` for automatic installation by extension

### Improved
- **MCP Streaming Support**: Implemented real-time progress streaming for long-running Stata executions
  - Sends MCP log messages every ~10 seconds with execution progress and recent output (lines 2830-3008)
  - Sends MCP progress notifications for visual progress indicators
  - Monitors Stata log file and streams last 3 lines of new output
  - Prevents Claude Code HTTP timeout (~11 minutes) by keeping connection alive
  - Uses the official Streamable HTTP transport plus MCP's `send_log_message()` / `send_progress_notification()` APIs with `logging/setLevel` support and a default `notice` log level for progress updates
  - Automatically enabled for all `stata_run_file` calls via MCP protocol
  - Falls back gracefully to non-streaming mode if errors occur

- **Session cleanup**: Added Stata state cleanup on script start
  - `program drop _all` and `macro drop _all` to prevent state pollution from interrupted executions
  - Prevents "program 1while already defined r(110)" errors

### Verified
- **Multi-stage timeout termination**: Confirmed all 3 termination stages work correctly
  - Stage 1: Graceful Stata `break` command
  - Stage 2: Aggressive thread `_stop()` method
  - Stage 3: Forceful process kill via `pkill -f stata`
- **Timeout precision**: 100% accurate timing (12.0s and 30.0s timeouts triggered exactly)
- **Both endpoints work**: REST API (VS Code extension) and MCP (LLM calls) both support timeout

### Technical Details
- Timeout implementation logic (lines 972-1342) was always correct and well-designed
- Issue was purely in parameter binding at the API layer
- MCP endpoint was unaffected (already working correctly)
- See `TIMEOUT_FIX_SUMMARY.md` and `FINAL_TIMEOUT_TEST_RESULTS.md` for complete analysis

## [0.3.3] - 2025-10-21

### Fixed
- **Mac-specific graph export issues**: Resolved critical graphics-related errors on macOS
  - Fixed JVM crash (SIGBUS) when exporting graphs to PNG in daemon threads
  - Root cause: Stata's embedded JVM requires main thread initialization on Mac
  - Solution: One-time PNG initialization at server startup (lines 230-265 in `stata_mcp_server.py`)
  - Windows/Linux users unaffected (different JVM architecture)

### Improved
- **Mac Dock icon suppression**: Server no longer appears in Mac Dock during operation
  - Dual approach: NSApplication activation policy + Java headless mode
  - Lines 36-49: AppKit NSApplication.setActivationPolicy to hide Python process
  - Lines 199-204: JAVA_TOOL_OPTIONS headless mode to prevent JVM Dock icon
  - Completely transparent to users - no visual interruption

### Technical Details
- JVM initialization creates minimal dataset (2 obs, 1 var) and exports 10×10px PNG
- Runs once at startup with minimal overhead (~100ms)
- Prevents daemon thread crashes for all subsequent graph exports
- Headless mode set before PyStata config.init() to prevent GUI context creation
- Non-fatal fallback behavior if initialization fails
- See `tests/MAC_SPECIFIC_ANALYSIS.md` and `tests/DOCK_ICON_FIX_SUMMARY.md` for technical details

## [0.3.0] - 2025-01-XX

### Added
- Initial release with major improvements
- MCP server for Stata integration
- Interactive mode support
- Graph export and display capabilities
- Data viewer functionality

## Earlier Versions

See git commit history for details on versions 0.2.x and earlier.
