# Changelog

All notable changes to the Stata MCP extension will be documented in this file.

## [0.4.1] - 2025-12-23

### Fixed
- **Session Management Robustness**: Improved error handling and thread safety in multi-session mode
  - Enhanced thread-safe session lifecycle management with proper RLock usage
  - Improved session cleanup and shutdown procedures
  - Better handling of concurrent session creation and destruction

- **Cross-Platform Compatibility**: Verified and improved Windows/Mac compatibility
  - Path normalization using forward slashes for Stata commands
  - Proper temp directory handling (TEMP/TMP on Windows, STATATMP on all platforms)
  - Java headless mode on Mac to prevent Dock icon during graph export

- **Error Handling**: Improved error handling throughout the extension
  - Better error messages for MCP endpoint failures
  - Graceful handling of user-cancelled executions
  - Proper cleanup in finally blocks for all execution paths

## [0.4.0] - 2025-12-22

### Added
- **Multi-Session Support**: Run multiple Stata sessions in parallel for concurrent execution
  - New settings:
    - `stata-vscode.multiSession`: Enable multi-session mode (default: true)
    - `stata-vscode.maxSessions`: Maximum concurrent sessions (default: 100)
    - `stata-vscode.sessionTimeout`: Session idle timeout in seconds (default: 3600 = 1 hour)
  - Command-line flags: `--multi-session`, `--max-sessions`, `--session-timeout`
  - Each session has isolated state (data, variables, macros)
  - Automatic session cleanup after idle timeout
  - Backward compatible: existing clients work without changes (uses default session)

- **Session Management API**: New endpoints for session control
  - `POST /sessions`: Create a new session
  - `GET /sessions`: List all active sessions
  - `GET /sessions/{session_id}`: Get session details
  - `DELETE /sessions/{session_id}`: Destroy a session
  - `POST /sessions/{session_id}/stop`: Stop execution in a session

- **Session-Aware Execution**: Endpoints now support `session_id` parameter
  - `/run_file?session_id=abc123`: Run file in specific session
  - `/run_selection?session_id=abc123`: Run selection in specific session

### Fixed
- **Windows Graph Display**: Fixed multiple issues preventing graph popup and display on Windows
  - URL decoding for graph names with special characters (spaces, etc.)
  - Line ending normalization (`\r\n` → `\n`) for Windows SSE streams and regex matching
  - Forward slash paths in all Stata graph export commands to avoid escape sequence issues
  - Low-level `_gr_list` API for reliable graph detection on Windows
  - Graph list reset before each command to only detect newly created graphs

- **Windows Socket Errors**: Suppressed non-critical IOCP socket errors (WinError 64, 995) that occurred when clients disconnected

- **Table Formatting**: Preserved spacing in Stata table output (removed aggressive space compression)

- **Log File Location**: Fixed `/v1/tools` endpoint to respect `logFileLocation` setting

### Technical
- New files: `src/stata_worker.py`, `src/session_manager.py`
- Uses Python multiprocessing with `spawn` method for process isolation
- Each worker has its own PyStata instance (pystata.config.init)
- Inter-process communication via `multiprocessing.Queue`
- Enhanced debug logging for Windows troubleshooting

## [0.3.8] - 2025-12-22

### Added
- **Log File Location Options**: Extended `logFileLocation` setting with new options
  - `dofile`: Save log files in the same directory as the .do file
  - `parent`: Save log files in the parent directory of the .do file
  - Now matches the options available in `workingDirectory` setting

### Changed
- Default log file location remains `extension` (logs folder in extension directory)

## [0.3.7] - 2025-12-21

### Added
- **Stop Execution**: New feature to cancel running Stata commands
  - Stop button in editor title bar (stop icon)
  - Right-click context menu option "Stata: Stop Execution"
  - Keyboard shortcut: `Cmd+Shift+C` (Mac) / `Ctrl+Shift+C` (Windows/Linux)
  - Status bar shows running state with spinner, click to stop
  - Uses Stata's native `StataSO_SetBreak()` function for clean interruption
  - New `/stop_execution` and `/execution_status` endpoints

- **Working Directory Settings**: Control where Stata runs when executing .do files
  - `stata-vscode.workingDirectory`: Choose from 6 options:
    - `dofile` (default): Same directory as the .do file
    - `parent`: Parent directory of the .do file
    - `workspace`: VS Code workspace root folder
    - `extension`: Logs folder in extension directory
    - `custom`: User-specified directory
    - `none`: Don't change directory
  - `stata-vscode.customWorkingDirectory`: Path for custom option

### Fixed
- **Output panel no longer steals focus on startup**: Removed auto-show of Stata output panel when IDE starts
  - Previously, the output panel would appear on every IDE/project startup, pushing terminal out of view
  - Now the output panel only appears when running Stata commands or explicitly requested
  - Improves experience for non-Stata projects

- **Stop Execution implementation fixed**: Corrected the stop mechanism for Stata commands
  - Removed dangerous process kill that would terminate the MCP server itself
  - Now uses only `StataSO_SetBreak()` which is the correct way to interrupt Stata running as an in-process library
  - Fixed potential deadlock by releasing execution lock before calling break function

## [0.3.6] - 2025-12-04

### Added
- **MCP Output Settings**: New settings to optimize token usage when AI assistants call Stata via MCP
  - `stata-vscode.resultDisplayMode`: Choose between `compact` (default) or `full` output mode
  - `stata-vscode.maxOutputTokens`: Limit output tokens (default: 10000, 0 = unlimited)
  - Large outputs are automatically saved to file with path returned instead

### Improved
- **Compact mode filtering**: Significantly reduces token usage for MCP returns
  - Filters loop code echoes (foreach/forvalues/while) while preserving actual output
  - Filters program definitions and Mata blocks
  - Filters command echoes and line continuations for `run_file` operations
  - Filters verbose messages like "(N real changes made)" and "(N missing values generated)"
  - Cleans up orphaned numbered lines with no content
  - Preserves all error messages and important output

### Fixed
- **Windows CRLF handling**: Normalized line endings to ensure regex patterns work correctly on Windows
- **Nested loop detection**: Fixed pattern to correctly identify nested loops with line numbers (e.g., `  2.     forvalues j = 1/2 {`)

## [0.3.5] - 2025-11-03

### Fixed
- **Java initialization messages suppressed**: Filtered out Java options messages from extension output
  - Added filter in stderr handlers to silently ignore "Picked up _JAVA_OPTIONS" and "Picked up JAVA_TOOL_OPTIONS" messages
  - These are informational messages from JVM, not actual errors
  - Updated `Logger.mcpServerError` in `extension.js` (lines 76-81)
  - Updated stderr handler in `start-server.js` (lines 267-272)
  - Changed to use `_JAVA_OPTIONS` instead of `JAVA_TOOL_OPTIONS` in `stata_mcp_server.py` (line 201)

- **Deprecated mount() method**: Updated to use new fastapi-mcp 0.4.0 API
  - Replaced deprecated `mcp.mount(mount_path="/mcp", transport="sse")` with `mcp.mount_sse(mount_path="/mcp")`
  - Eliminates DeprecationWarning message in extension output
  - Line 2828 in `stata_mcp_server.py`

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
