# Stata MCP Extension

![Stata MCP Extension](images/logo.png)

[![GitHub license](https://img.shields.io/github/license/hanlulong/stata-mcp)](https://github.com/hanlulong/stata-mcp/blob/main/LICENSE)
[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code-Marketplace-blue)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)

This extension provides Stata integration for Visual Studio Code and Cursor IDE using the Model Context Protocol (MCP).

## Features

- **Run Stata Commands**: Execute selections or entire .do files directly from your editor
- **Syntax Highlighting**: Full syntax support for Stata .do and .ado files
- **AI Assistant Integration**: Contextual help and code suggestions via MCP
- **Cross-platform**: Works on Windows, macOS, and Linux

## Installation

### VS Code
```bash
code --install-extension DeepEcon.stata-mcp
```

### Cursor
```bash
cursor --install-extension DeepEcon.stata-mcp
```

Or download the latest `.vsix` file from the [Releases](https://github.com/hanlulong/stata-mcp/releases) page.

## Requirements

- Stata 14 or higher
- Python 3.11 or higher (automatically managed)
- For Cursor: Cursor IDE with MCP support

## Documentation

- [Full Documentation](README.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Command Line Usage](CLI_USAGE.md)
- [Contributing](CONTRIBUTING.md)

## How It Works

The extension creates a local MCP server that connects your editor to Stata, enabling:

1. **Command Execution**: Run Stata commands and see results instantly
2. **Context Awareness**: AI assistants understand your Stata data and commands
3. **Enhanced Productivity**: Get intelligent code suggestions and documentation

## Screenshots

*Coming soon*

## For Developers

```bash
# Clone the repository
git clone https://github.com/hanlulong/stata-mcp.git
cd stata-mcp

# Install dependencies
npm install

# Package the extension
npm run package
```

## License

MIT

## Credits

Created by Lu Han
Published by DeepEcon 