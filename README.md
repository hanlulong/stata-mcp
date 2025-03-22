# Stata MCP Extension for VS Code and Cursor

![Stata MCP Extension](images/logo.png)

This extension provides Stata integration for Visual Studio Code and Cursor IDE using the Model Context Protocol (MCP).

## Installation Options

### 1. VS Code Marketplace (Recommended)

The extension is available on the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)

- Open VS Code
- Go to Extensions (Ctrl+Shift+X or Cmd+Shift+X)
- Search for "Stata MCP" or "DeepEcon"
- Click Install

### 2. Cursor Extension Store

- Open Cursor
- Go to Extensions (Ctrl+Shift+X or Cmd+Shift+X)
- Search for "Stata MCP" or "DeepEcon"
- Click Install

### 3. Manual Installation

If you need a specific version or can't access the marketplace:

1. Download the `.vsix` file from the [Releases](https://github.com/hanlulong/stata-mcp/releases) page
2. Install in VS Code:
   - Open VS Code
   - Go to Extensions view (Ctrl+Shift+X or Cmd+Shift+X)
   - Click on the "..." menu in the top-right
   - Select "Install from VSIX..."
   - Navigate to and select the downloaded .vsix file

3. Install in Cursor:
   - Open a terminal or command prompt
   - Run: `cursor --install-extension path/to/stata-mcp.vsix`
   - Restart Cursor after installation

## Requirements

- Stata installed on your machine (Stata 14 or higher recommended)
- Python 3.11 or higher

## Features

- Run Stata commands directly from VS Code or Cursor
- Execute selections or entire .do files
- View Stata output in the editor
- AI assistant integration through MCP
- Enhanced coding experience with Stata context

## Usage

1. Install the extension
2. Set your Stata path in the settings (or let it auto-detect)
3. Open a Stata .do file
4. Run commands using keyboard shortcuts or the context menu

### Keyboard Shortcuts

- **Run Selection**: Ctrl+Shift+Enter (or Cmd+Shift+Enter on Mac)
- **Run File**: Ctrl+Shift+D (or Cmd+Shift+D on Mac)

## Support

For issues or questions, please file an issue on the [GitHub repository](https://github.com/hanlulong/stata-mcp/issues).

## License

MIT 