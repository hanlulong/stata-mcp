# Stata MCP Server Troubleshooting Guide

## Common Issues and Solutions

### Server Not Starting

If the MCP (Model Context Protocol) server doesn't start:

1. **Check Python Installation**: Ensure Python 3.11 is installed and available in your PATH.
   ```bash
   python3.11 --version
   ```

2. **Check Virtual Environment**: The extension creates a Python virtual environment in the extension directory.
   - If there are issues, delete the `.venv` directory and reinstall the extension.

3. **Port Conflicts**: The default port is 4000. If it's in use:
   - Change the port in the extension settings
   - Or terminate the process using the port (varies by OS)

4. **Stata Path Issues**: Verify your Stata path is correctly set in the extension settings.

### Connection Problems

If you're having trouble connecting to the MCP server:

1. **Test the Connection**: Use the command "Stata: Test MCP Server Connection" from the command palette.

2. **Check Logs**: Look at the "Stata" output channel in VS Code for specific error messages.

3. **Firewall Settings**: Ensure your firewall allows connections on the port being used.

4. **MCP Configuration**: If using with AI assistants, check that the MCP configuration is correct:
   - Windows: `C:\Users\[username]\.cursor\mcp.json`
   - macOS: `~/.cursor/mcp.json`
   - Linux: `~/.cursor/mcp.json`

### Python Dependency Issues

If there are issues with Python dependencies:

1. **Manual Installation**: You can manually install the required dependencies:
   ```bash
   pip install fastapi uvicorn pydantic fastapi-mcp
   ```

2. **Version Conflicts**: If you have conflicts with existing packages:
   - Use a dedicated virtual environment
   - Try an alternative Python version (3.9-3.11)

## Additional Debugging

For more detailed debugging:

1. **Enable Debug Mode**: Turn on the debug mode in extension settings.

2. **Check Server Logs**: Look for `stata_mcp_server.log` in the extension directory.

3. **Network Testing**: Test if you can connect to the server manually:
   ```bash
   curl http://localhost:4000/health
   ```

## Contact Support

If you continue to experience issues:

- File an issue on the GitHub repository
- Contact Lu Han (developer) for assistance

---

This extension uses the Model Context Protocol (MCP) to provide integration between Stata and AI assistants. 