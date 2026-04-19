# Troubleshooting

If you encounter issues with the Stata MCP extension, follow these steps to perform a clean reinstallation.

← [Back to main README](../README.md)

## Windows

1. Close all VS Code/Cursor/Antigravity windows
2. Open Task Manager (Ctrl+Shift+Esc):
   - Go to the "Processes" tab
   - Look for any running Python or `uvicorn` processes
   - Select each one and click "End Task"

3. Remove the extension folder:
   - Press Win+R, type `%USERPROFILE%\.vscode\extensions` and press Enter
   - Delete the folder `deepecon.stata-mcp-0.x.x` (where x.x is the version number)
   - For Cursor: The path is `%USERPROFILE%\.cursor\extensions`
   - For Antigravity: The path is `%USERPROFILE%\.antigravity\extensions`

4. Install UV manually (if needed):
   ```powershell
   # Open PowerShell as Administrator and run:
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

5. Restart your computer (recommended but optional)

6. Install the latest version of the extension from the marketplace

## macOS/Linux

1. Close all VS Code/Cursor/Antigravity windows

2. Kill any running Python processes:
   ```bash
   # Find Python processes
   ps aux | grep python
   # Kill them (replace <PID> with the process numbers you found)
   kill -9 <PID>
   ```

3. Remove the extension folder:
   ```bash
   # For VS Code:
   rm -rf ~/.vscode/extensions/deepecon.stata-mcp-0.x.x
   # For Cursor:
   rm -rf ~/.cursor/extensions/deepecon.stata-mcp-0.x.x
   # For Antigravity:
   rm -rf ~/.antigravity/extensions/deepecon.stata-mcp-0.x.x
   ```

4. Install UV manually (if needed):
   ```bash
   # Using curl:
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Or using wget:
   wget -qO- https://astral.sh/uv/install.sh | sh
   ```

5. Restart your terminal or computer (recommended but optional)

6. Install the latest version of the extension from the marketplace

## Additional Troubleshooting Tips

- If you see errors about Python or UV not being found, make sure they are in your system's PATH:
  - Windows: Type "Environment Variables" in the Start menu and add the installation paths
  - macOS/Linux: Add the paths to your `~/.bashrc`, `~/.zshrc`, or equivalent

- If you get permission errors:
  - Windows: Run your IDE as Administrator
  - macOS/Linux: Check folder permissions with `ls -la` and fix with `chmod` if needed

- If the extension still fails to initialize:
  1. Open the Output panel (View -> Output)
  2. Select "Stata-MCP" from the dropdown
  3. Check the logs for specific error messages
  4. If you see Python-related errors, try manually creating a Python 3.11 virtual environment:
     ```bash
     # Windows
     py -3.11 -m venv .venv

     # macOS/Linux
     python3.11 -m venv .venv
     ```

- For persistent issues:
  1. Check your system's Python installation: `python --version` or `python3 --version`
  2. Verify UV installation: `uv --version`
  3. Make sure you have Python 3.11 or later installed
  4. Check if your antivirus software is blocking Python or UV executables

- If you're having issues with a specific Stata edition:
  1. Make sure the selected Stata edition (MP, SE, or BE) matches what's installed on your system
  2. Try changing the `stata-vscode.stataEdition` setting to match your installed version
  3. Restart the extension after changing settings

## Reporting an Issue

When opening an issue on GitHub, please provide:
- The complete error message from the Output panel (View -> Output -> Stata-MCP)
- Your operating system and version
- VS Code/Cursor/Antigravity version
- Python version (`python --version`)
- UV version (`uv --version`)
- Steps to reproduce the issue
- Any relevant log files or screenshots
- The content of your MCP configuration file if applicable

This detailed information will help us identify and fix the issue more quickly. You can open issues at: [GitHub Issues](https://github.com/hanlulong/stata-mcp/issues)
