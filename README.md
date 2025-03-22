# Stata MCP Extension for VS Code and Cursor

![Stata MCP Extension](images/logo.png)

This extension provides Stata integration for Visual Studio Code and Cursor IDE using the Model Context Protocol (MCP). It allows you to:

- Run Stata commands directly from VS Code or Cursor
- Execute selections or entire .do files
- Quickly view Stata output in the editor
- Integration with AI assistants through the MCP protocol
- Enhanced AI coding experience in Cursor IDE with Stata context

## Requirements

- Stata installed on your machine (Stata 14 or higher recommended)
- Python 3.11 or higher
- The `fastapi-mcp` package will be automatically installed if needed
- For Cursor integration: Cursor IDE with MCP support

## Installation

Install this extension from the VS Code Marketplace or by searching for "Stata MCP" in the Extensions view.

For Cursor users:
1. Download the .vsix file from the latest release
2. Install with: `cursor --install-extension stata-mcp-0.0.1.vsix`

## Testing on Different Platforms

If you want to test this extension on different platforms before publishing:

1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/yourusername/stata-mcp.git
   cd stata-mcp
   npm install
   ```

2. Run the platform compatibility test:
   ```bash
   npm run test:platform
   ```

3. Run the functional tests (requires Stata):
   ```bash
   npm run test:extension
   ```

4. Package the extension:
   ```bash
   npm run package
   ```

5. Install the extension manually in VS Code:
   - In VS Code, go to Extensions view
   - Click on the "..." menu in the top-right of the Extensions view
   - Select "Install from VSIX..."
   - Navigate to and select the .vsix file created in the previous step

## Features

### Run Stata Commands

- **Run Selection**: Select Stata code and press `Ctrl+Shift+Enter` (or `Cmd+Shift+Enter` on Mac)
- **Run File**: Press `Ctrl+Shift+D` (or `Cmd+Shift+D` on Mac) to run the entire .do file

### Syntax Highlighting

Full syntax highlighting for Stata .do and .ado files, including:
- Commands
- Functions
- Operators
- Macros
- Comments
- Strings

### AI Assistant Integration

The extension includes an MCP server that enables AI assistants like Cursor, GitHub Copilot, and others to interact with Stata, providing:

- Contextual help with Stata commands
- Code generation based on your data
- Smart suggestions for data analysis

### Cursor-Specific Features

When used with Cursor IDE, this extension provides:
- AI-powered Stata code completion
- Contextual understanding of your Stata datasets
- Enhanced documentation and help while coding
- Intelligent error correction suggestions

## Configuration

Access extension settings through VS Code settings:

- **Stata Path**: Path to your Stata installation directory 
- **MCP Server Host**: Host for the MCP server (default: localhost)
- **MCP Server Port**: Port for the MCP server (default: 4000)
- **Auto Start Server**: Automatically start MCP server on extension activation
- **Always Use Webview**: Use webview for output instead of output channel
- **Auto Configure MCP**: Automatically configure MCP for AI assistants

## Virtual Environment

The extension uses a virtual environment with Python 3.11 to run the MCP server. This ensures compatibility and isolation from your system Python installation. The virtual environment is automatically created and configured when you install the extension.

If you need to manually set up the virtual environment:

```bash
cd <extension-folder>
python3.11 -m venv .venv
.venv/bin/pip install fastapi uvicorn pydantic mcp
.venv/bin/pip install git+https://github.com/tadata-org/fastapi_mcp.git
```

## How to Use

1. Install the extension
2. Set your Stata path in the extension settings (or let it detect automatically)
3. Open a Stata .do file
4. Run commands using the keyboard shortcuts or context menu
5. View results in the output panel

### For AI Integration

The extension automatically sets up the MCP configuration for AI assistants. You may need to restart your Cursor application after installation to enable Stata integration.

## Troubleshooting

### Server Not Starting

If the MCP server doesn't start:
1. Check if you have Python 3.11 installed (`python3.11 --version`)
2. Verify the Stata path in settings
3. Check if port 4000 is already in use (you can change the port in settings)
4. Look at the Stata Output channel in VS Code for error messages

### Virtual Environment Issues

If there are issues with the virtual environment:
1. Delete the `.venv` directory in the extension folder
2. Run `npm run postinstall` to recreate the virtual environment
3. Restart VS Code

### Connection Issues

If AI assistants can't connect to Stata:
1. Verify the MCP server is running (use "Stata: Test MCP Server Connection" command)
2. Check the MCP configuration at `~/.cursor/mcp.json` (or the equivalent for your OS)
3. Restart Cursor to apply the changes

## License

MIT 