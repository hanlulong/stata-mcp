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

## Installation

### Manual Installation (Recommended)

1. Download the `.vsix` file from the [Releases](https://github.com/hanlulong/stata-mcp/releases) page
2. Install in VS Code:
   - Open VS Code
   - Go to Extensions view (Ctrl+Shift+X or Cmd+Shift+X)
   - Click on the "..." menu in the top-right of the Extensions view
   - Select "Install from VSIX..."
   - Navigate to and select the downloaded .vsix file

3. Install in Cursor:
   - Open a terminal or command prompt
   - Run: `cursor --install-extension path/to/stata-mcp.vsix`
   - Restart Cursor after installation

### VS Code Marketplace (Coming Soon)

The extension will be available in the VS Code Marketplace, where you can search for "Stata MCP".

### Cursor Extension Store (Coming Soon)

The extension will be available in the Cursor Extension Store, where you can search for "Stata MCP".

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

### Connection Issues

If AI assistants can't connect to Stata:
1. Verify the MCP server is running (use "Stata: Test MCP Server Connection" command)
2. Check the MCP configuration at `~/.cursor/mcp.json` (or the equivalent for your OS)
3. Restart Cursor to apply the changes

## License

MIT 