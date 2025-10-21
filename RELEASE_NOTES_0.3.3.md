# Release Notes - Version 0.3.3

**Release Date:** October 21, 2025

## Overview

Version 0.3.3 resolves critical Mac-specific graph export issues and improves user experience by eliminating visual distractions during server operation.

## Fixed Issues

### Mac Graph Export Crash (Critical)

**Problem:** MCP server crashed with SIGBUS error when exporting graphs to PNG on macOS.

**Root Cause:** Stata's embedded Java Virtual Machine (JVM) cannot initialize properly when first called from daemon threads on macOS. This is specific to Mac's `libstata-mp.dylib` implementation.

**Solution:**
- One-time PNG initialization at server startup in main thread
- Initializes JVM context before any daemon thread operations
- Minimal overhead (~100ms) at startup
- All subsequent graph exports work flawlessly

**Impact:** Mac users can now export PNG graphs without crashes.

### Mac Dock Icon Suppression (UX Improvement)

**Problem:** Python/Java processes appeared in Mac Dock during server operation, creating visual clutter.

**Root Cause:**
1. Python interpreter registers as GUI application
2. Stata's JVM creates GUI context during graph initialization

**Solution:**
- **Dual approach** for complete suppression:
  1. NSApplication activation policy set to "Accessory" mode
  2. Java headless mode (`-Djava.awt.headless=true`)
- Completely transparent - no user-visible changes
- Server functions normally without Dock presence

**Impact:** Cleaner user experience with no distracting icons.

## Technical Changes

### Code Modifications

**File:** `src/stata_mcp_server.py`

1. **Lines 36-49:** Python process Dock hiding
   ```python
   from AppKit import NSApplication
   app = NSApplication.sharedApplication()
   app.setActivationPolicy_(1)  # Accessory mode
   ```

2. **Lines 199-204:** Java headless mode configuration
   ```python
   os.environ['JAVA_TOOL_OPTIONS'] = '-Djava.awt.headless=true'
   config.init(stata_edition)
   ```

3. **Lines 230-265:** PNG export initialization
   - Creates minimal 2-observation dataset
   - Generates 10×10px PNG to initialize JVM
   - Automatic cleanup of temporary files

### Documentation

New comprehensive documentation in `tests/` directory:
- `MAC_SPECIFIC_ANALYSIS.md` - Technical deep-dive into JVM crash
- `DOCK_ICON_FIX_SUMMARY.md` - Complete Dock icon solution
- `FINAL_SUMMARY.md` - Overall project summary
- `README.md` - Test directory guide

## Platform Compatibility

- **macOS:** All fixes active, resolves critical issues
- **Windows:** No changes (issues don't exist on Windows)
- **Linux:** No changes (not affected)

All Mac-specific code is conditionally executed:
```python
if platform.system() == 'Darwin':
    # Mac-specific fixes
```

## Installation

```bash
code --install-extension stata-mcp-0.3.3.vsix
```

Or install via VS Code/Cursor extension marketplace (when published).

## Upgrade Notes

- **From 0.3.0-0.3.2:** Direct upgrade, no configuration changes needed
- **From 0.2.x:** Review updated README for any configuration changes

## Testing

All fixes verified through automated tests:
- ✓ PNG export in daemon threads (Mac)
- ✓ Multiple consecutive graph exports (Mac)
- ✓ Dock icon suppression (Mac)
- ✓ Cross-platform compatibility (Windows/Linux unaffected)

## Known Limitations

- None identified in this release

## Next Steps

After installation:
1. Restart VS Code/Cursor
2. Run Stata do-files with graph exports
3. Verify graphs export correctly
4. Confirm no Dock icons appear

## Credits

Special thanks to the testing and investigation that identified these Mac-specific issues.

## Support

- Issues: https://github.com/hanlulong/stata-mcp/issues
- Documentation: https://github.com/hanlulong/stata-mcp

---

**Full Changelog:** See [CHANGELOG.md](CHANGELOG.md) for complete version history.
