# Installing Stata MCP v0.3.4 - Timeout Fix

**Version:** 0.3.4
**Build Date:** October 22, 2025
**Package:** `stata-mcp-0.3.4.vsix`
**Size:** 2.7 MB

## What's New in v0.3.4

✅ **Fixed:** Timeout feature now works correctly for "Run File" operations
- Changed REST API endpoint from POST to GET for proper parameter binding
- Timeout parameter is now correctly extracted from VS Code settings
- Verified with tests: 12-second and 30-second timeouts trigger exactly on time

## Installation Instructions

### Method 1: Install via VS Code UI (Recommended)

1. **Open VS Code, Cursor, or Antigravity**

2. **Open Extensions view**
   - Click the Extensions icon in the sidebar (or press `Cmd+Shift+X` on Mac, `Ctrl+Shift+X` on Windows)

3. **Install from VSIX**
   - Click the `...` (More Actions) menu at the top of the Extensions view
   - Select "Install from VSIX..."
   - Navigate to: `/path/to/stata-mcp/stata-mcp-0.3.4.vsix`
   - Click "Install"

4. **Reload VS Code**
   - Click "Reload Now" when prompted, or restart VS Code

### Method 2: Install via Command Line

```bash
# For VS Code
code --install-extension /path/to/stata-mcp/stata-mcp-0.3.4.vsix

# For Cursor
cursor --install-extension /path/to/stata-mcp/stata-mcp-0.3.4.vsix
```

## Verifying Installation

1. **Check Extension Version**
   - Open Extensions view
   - Search for "Stata MCP"
   - Verify version shows **0.3.4**

2. **Check Timeout Setting**
   - Open Settings (`Cmd+,` or `Ctrl+,`)
   - Search for "stata timeout"
   - You should see: **Stata-vscode: Run File Timeout**
   - Default: 600 seconds (10 minutes)

## Testing the Timeout Feature

### Step 1: Create a Test Script

Create a file called `test_timeout.do`:

```stata
* Test long-running script
display "Starting long test at: " c(current_time)

clear
set obs 100
gen x = _n

* Loop for 2 minutes (120 seconds)
forvalues i = 1/120 {
    sleep 1000
    if mod(`i', 10) == 0 {
        display "Iteration `i' at " c(current_time)
    }
}

display "Completed at: " c(current_time)
```

### Step 2: Configure Short Timeout

1. Open VS Code Settings
2. Search for "stata timeout"
3. Set **Stata-vscode: Run File Timeout** to: **30** (30 seconds)

### Step 3: Run the Test

1. Open `test_timeout.do` in VS Code
2. Right-click → "Stata: Run File" (or use command palette)
3. **Expected Result:**
   - Script should run for about 30 seconds
   - Should stop at around iteration 30
   - Should show timeout message in output

### Step 4: Check Output

You should see something like:
```
Starting long test at: HH:MM:SS
Iteration 10 at HH:MM:SS
Iteration 20 at HH:MM:SS
Iteration 30 at HH:MM:SS

*** TIMEOUT: Execution exceeded 30 seconds (0.5 minutes) ***
*** ERROR: Operation timed out after 30 seconds ***
```

## Timeout Settings

### Recommended Values

| Use Case | Timeout (seconds) | Timeout (minutes) |
|----------|-------------------|-------------------|
| Quick scripts | 30-60 | 0.5-1 min |
| Data processing | 300-600 | 5-10 min |
| Long simulations | 1800-3600 | 30-60 min |
| No limit (default) | 600 | 10 min |

### Configuring Timeout

**Via UI:**
1. File → Preferences → Settings (or Code → Settings on Mac)
2. Search: "stata timeout"
3. Modify: **Stata-vscode: Run File Timeout**
4. Value in seconds (e.g., 30 for 30 seconds)

**Via settings.json:**
```json
{
  "stata-vscode.runFileTimeout": 30
}
```

## What Gets Fixed

### Before v0.3.4 (BROKEN)
- Timeout parameter was **ignored**
- Scripts always ran with 600-second (10 minute) timeout
- Custom timeout values from settings had **no effect**

### After v0.3.4 (FIXED)
- Timeout parameter is **correctly received**
- Scripts respect the configured timeout value
- Timeout triggers at exact expected time
- Multi-stage termination works properly

## Technical Details

### Changes Made

**File:** `src/stata_mcp_server.py` (Line 1643)

**Change:**
```python
# Before
@app.post("/run_file", ...)

# After
@app.get("/run_file", ...)
```

**Why:** FastAPI GET endpoints automatically bind function parameters to query parameters, while POST endpoints expect request body by default.

### How Timeout Works

1. **Polling:** Checks every 0.5 seconds if timeout exceeded
2. **Termination:** Uses 3-stage approach:
   - Stage 1: Send Stata `break` command (graceful)
   - Stage 2: Force thread stop (aggressive)
   - Stage 3: Kill Stata process (forceful)
3. **Error Handling:** Returns clear timeout error message

## Troubleshooting

### Timeout Still Not Working?

1. **Verify version:**
   ```
   Check Extensions → Stata MCP → Version should be 0.3.4
   ```

2. **Restart VS Code completely**
   - Close all VS Code windows
   - Reopen VS Code

3. **Check server is running:**
   - Look for "Stata MCP Server" process
   - Check server logs in extension output panel

4. **Test with curl:**
   ```bash
   curl -s "http://localhost:4000/run_file?file_path=/path/to/test.do&timeout=12"
   ```

### Server Won't Start?

1. Check Python version: `python3 --version` (need 3.8+)
2. Check dependencies: `pip3 install fastapi uvicorn pydantic`
3. Check Stata path in settings

## Documentation

- [TIMEOUT_FIX_SUMMARY.md](TIMEOUT_FIX_SUMMARY.md) - Technical implementation details
- [FINAL_TIMEOUT_TEST_RESULTS.md](FINAL_TIMEOUT_TEST_RESULTS.md) - Complete test results
- [README.md](README.md) - Full extension documentation

## Support

- **Issues:** https://github.com/hanlulong/stata-mcp/issues
- **Documentation:** https://github.com/hanlulong/stata-mcp

---

**Enjoy the working timeout feature! 🎉**

_Built on: October 22, 2025_
_Version: 0.3.4_
_Status: Production Ready ✅_
