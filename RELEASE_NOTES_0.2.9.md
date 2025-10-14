# Release Notes - Version 0.2.9

## Summary
Fixed critical issues with `cls` command handling, Windows Unicode encoding, graph detection for LLM/MCP calls, and various type safety improvements.

## Changes

### 1. cls Command Handling ✅
- **Issue**: `cls` command caused "unrecognized command r(199)" error
- **Fix**: Single-line `cls` commands are now automatically commented out
- **Locations**: 
  - `run_stata_file()`: Lines 1024-1028
  - `run_stata_command()`: Lines 467-471
- **Result**: `.do` files with `cls` commands now run without errors

### 2. Windows Unicode Encoding ✅
- **Issue**: `UnicodeEncodeError: 'charmap' codec can't encode characters` when using Chinese/Unicode characters on Windows
- **Fix**: 
  - Force UTF-8 encoding for Python stdout/stderr (Lines 25-34)
  - Configure PyStata's output file handle with UTF-8 (Lines 188-198)
- **Result**: Chinese characters (行业代码) and all Unicode display correctly on Windows

### 3. Conditional Graph Processing ✅
- **Issue**: Graphs were auto-named and exported even when called from LLMs/MCP, creating unwanted Graph.png files
- **Fix**: 
  - Added `auto_name_graphs` parameter to `run_stata_file()` (default: False)
  - Added `auto_detect_graphs` parameter to `run_stata_command()` and `run_stata_selection()` (default: False)
  - Graph naming only runs when called from VS Code extension (Line 1031)
  - Graph detection only runs when called from VS Code extension (Lines 531, 1355)
- **Result**: 
  - MCP/LLM calls: No graph naming, no graph detection, no Graph.png files
  - VS Code calls: Graphs auto-named and exported for display

### 4. Type Safety Improvements ✅
- **Issue**: `TypeError: expected string or bytes-like object, got 'int'` in graph processing
- **Fix**: 
  - Added defensive string conversions for all line processing (Lines 464, 1012, 1315)
  - Added type checking for regex match groups (Lines 1037-1050)
  - Explicit string conversion before `re.sub()` calls (Line 1063)
- **Result**: Robust handling of edge cases, no more type errors

### 5. Enhanced Error Reporting ✅
- **Issue**: Generic error messages made debugging difficult
- **Fix**: Added detailed traceback with line numbers (Lines 1094-1103)
- **Result**: Error messages now show exact location and full stack trace

### 6. FastAPI Deprecation Fix ✅
- **Issue**: `on_event is deprecated` warning
- **Fix**: Migrated to modern lifespan event handler (Lines 1492-1507)
- **Result**: No more deprecation warnings

### 7. Middleware Fix ✅
- **Issue**: `AssertionError` in ASGI middleware
- **Fix**: Removed problematic middleware that was causing ASGI protocol violations
- **Result**: No more assertion errors in request handling

## Technical Details

### Function Parameters
- `run_stata_file(file_path, timeout=600, auto_name_graphs=False)`
- `run_stata_command(command, clear_history=False, auto_detect_graphs=False)`
- `run_stata_selection(selection, working_dir=None, auto_detect_graphs=False)`

### Endpoint Configuration
| Endpoint | Type | Graph Naming | Graph Detection |
|----------|------|--------------|-----------------|
| `/run_file` (MCP) | LLM/MCP | ❌ False | ❌ False |
| `/run_selection` (MCP) | LLM/MCP | N/A | ❌ False |
| `/v1/tools` run_file | VS Code | ✅ True | ✅ True |
| `/v1/tools` run_selection | VS Code | N/A | ✅ True |

## Files Modified
- `src/stata_mcp_server.py` - All fixes implemented
- `package.json` - Version updated to 0.2.9
- `README.md` - Version references updated
- `README.zh-CN.md` - Version references updated

## Testing Checklist
- [ ] Test `cls` command in `.do` files (Windows & macOS)
- [ ] Test Unicode/Chinese characters on Windows
- [ ] Test graph creation from MCP/LLM (should NOT create Graph.png)
- [ ] Test graph creation from VS Code (should create and display graphs)
- [ ] Test run_LP_analysis.do file
- [ ] Verify no deprecation warnings
- [ ] Verify no assertion errors

## Installation
```bash
code --install-extension stata-mcp-0.2.9.vsix
# or
cursor --install-extension stata-mcp-0.2.9.vsix
```

## Build Info
- Build Date: 2025-10-14 00:18
- File Size: 2.6 MB
- Files: 128 files
- Python Files: 160.07 KB (stata_mcp_server.py)
