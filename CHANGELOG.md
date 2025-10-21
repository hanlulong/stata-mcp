# Changelog

All notable changes to the Stata MCP extension will be documented in this file.

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
