[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/hanlulong-stata-mcp-badge.png)](https://mseep.ai/app/hanlulong-stata-mcp)

# Stata MCP Extension for VS Code and Cursor

[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code-Marketplace-blue)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)
[![GitHub license](https://img.shields.io/github/license/hanlulong/stata-mcp)](https://github.com/hanlulong/stata-mcp/blob/main/LICENSE)

This extension provides Stata integration for Visual Studio Code and Cursor IDE using the Model Context Protocol (MCP). The extension allows you to:

- Run Stata commands directly from VS Code or Cursor
- Execute selections or entire .do files
- View Stata output in the editor in real-time
- Get AI assistant integration through the MCP protocol
- Experience enhanced AI coding with Cursor or Cline

## Features

- **Run Stata Commands**: Execute selections or entire .do files directly from your editor
- **Syntax Highlighting**: Full syntax support for Stata .do, .ado, .mata, and .doh files
- **AI Assistant Integration**: Contextual help and code suggestions via MCP
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Automatic Stata Detection**: Automatically finds your Stata installation
- **Real-time Output**: See Stata results instantly in your editor

## Demo

Watch how this extension enhances your Stata workflow with Cursor (or VS Code) and AI assistance:

![Stata MCP Extension Demo](images/demo_2x.gif)

**[🎬 Full Video Version](https://github.com/hanlulong/stata-mcp/raw/main/images/demo.mp4)** &nbsp;&nbsp;|&nbsp;&nbsp; **[📄 View Generated PDF Report](examples/auto_report.pdf)**

<sub>*Demo prompt: "Write and execute Stata do-files, ensuring that full absolute file paths are used in all cases. Load the auto dataset (webuse auto) and generate summary statistics for each variable. Identify and extract key features from the dataset, produce relevant plots, and save them in a folder named plots. Conduct a regression analysis to examine the main determinants of car prices. Export all outputs to a LaTeX file and compile it. Address any compilation errors automatically, and ensure that LaTeX compilation does not exceed 10 seconds. All code errors should be identified and resolved as part of the workflow."*</sub>

> **Looking for other Stata integrations?**
> - Use Stata with Notepad++ and Sublime Text 3? See [here](https://github.com/sook-tusk/Tech_Integrate_Stata_R_with_Editors)
> - Use Stata MCP in Claude Desktop without installing this extension? See [here](https://github.com/SepineTam/stata-mcp)
> - Use Stata via Jupyter? See [here](https://github.com/hanlulong/stata-mcp/blob/main/jupyter-stata.md)


## Requirements

- Stata 17 or higher installed on your machine
- [UV](https://github.com/astral-sh/uv) package manager (automatically installed or can be installed manually if needed)

## Installation

> **Note:** Initial installation requires setting up dependencies which may take up to 2 minutes to complete. Please be patient during this one-time setup process. All subsequent runs will start instantly.

### VS Code Installation

#### Option 1: From VS Code Marketplace

Install this extension directly from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp).

```bash
code --install-extension DeepEcon.stata-mcp
```

Or:
1. Open VS Code
2. Go to Extensions view (Ctrl+Shift+X)
3. Search for "Stata MCP"
4. Click "Install"

#### Option 2: From .vsix file

1. Download the extension package `stata-mcp-0.2.1.vsix` from the [releases page](https://github.com/hanlulong/stata-mcp/releases).
2. Install using one of these methods:

```bash
code --install-extension path/to/stata-mcp-0.2.1.vsix
```

Or:
1. Open VS Code
2. Go to Extensions view (Ctrl+Shift+X)
3. Click on "..." menu in the top-right
4. Select "Install from VSIX..."
5. Navigate to and select the downloaded .vsix file

### Cursor Installation

1. Download the extension package `stata-mcp-0.2.2.vsix` from the [releases page](https://github.com/hanlulong/stata-mcp/releases).
2. Install using one of these methods:

```bash
cursor --install-extension path/to/stata-mcp-0.2.2.vsix
```

Or:
1. Open Cursor
2. Go to Extensions view
3. Click on the "..." menu
4. Select "Install from VSIX"
5. Navigate to and select the downloaded .vsix file

Starting with version 0.1.8, the extension integrates a fast Python package installer called `uv` to set up the environment. If uv is not found on your system, the extension will attempt to install it automatically.

## Extension Settings

You can customize the extension behavior through VS Code settings:

- `stata-vscode.stataPath`: Path to Stata installation directory
- `stata-vscode.mcpServerHost`: Host for MCP server (default: localhost)
- `stata-vscode.mcpServerPort`: Port for the MCP server (default: 4000)
- `stata-vscode.autoStartServer`: Automatically start MCP server when extension activates (default: true)
- `stata-vscode.debugMode`: Show detailed debug information in output panel (default: false)
- `stata-vscode.forcePort`: Force the MCP server to use the specified port even if it's already in use (default: false)
- `stata-vscode.clineConfigPath`: Custom path to Cline configuration file (optional, defaults to standard locations)
- `stata-vscode.runFileTimeout`: Timeout in seconds for 'Run File' operations (default: 600 seconds / 10 minutes)

## Usage

1. Open a Stata .do file
2. Run commands using:
   - **Run Selection**: Select Stata code and press `Ctrl+Shift+Enter` (or `Cmd+Shift+Enter` on Mac)
   - **Run File**: Press `Ctrl+Shift+D` (or `Cmd+Shift+D` on Mac) to run the entire .do file
3. View output in the editor panel

## How It Works

The extension creates a local MCP server that connects your editor to Stata, enabling:

1. **Command Execution**: Run Stata commands and see results instantly
2. **Context Awareness**: AI assistants understand your Stata data and commands
3. **Enhanced Productivity**: Get intelligent code suggestions and documentation


## Cursor MCP Configuration

The extension automatically configures Cursor MCP integration. To verify it's working:

1. Open Cursor
2. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac) to open the Command Palette
3. Type "Stata: Test MCP Server Connection" and press Enter
4. You should see a success message if the server is properly connected

### Cursor Configuration File Paths

The location of Cursor MCP configuration files varies by operating system:

- **macOS**:
  - Primary location: `~/.cursor/mcp.json`
  - Alternative location: `~/Library/Application Support/Cursor/User/mcp.json`

- **Windows**:
  - Primary location: `%USERPROFILE%\.cursor\mcp.json`
  - Alternative location: `%APPDATA%\Cursor\User\mcp.json`

- **Linux**:
  - Primary location: `~/.cursor/mcp.json`
  - Alternative location: `~/.config/Cursor/User/mcp.json`

### Manual Cursor Configuration

If you need to manually configure Cursor MCP:

1. Create or edit the MCP configuration file:
   - **macOS/Linux**: `~/.cursor/mcp.json`
   - **Windows**: `%USERPROFILE%\.cursor\mcp.json`

2. Add the Stata MCP server configuration:
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "url": "http://localhost:4000/mcp",
         "transport": "sse"
       }
     }
   }
   ```

3. If the file already contains other MCP servers, just add the `"stata-mcp"` entry to the existing `"mcpServers"` object.

4. Save the file and restart Cursor.

### Troubleshooting Cursor Configuration

If Cursor is not recognizing the Stata MCP server:
1. Verify the MCP server is running
2. Check that the configuration file exists with the correct content
3. Try restarting Cursor
4. Ensure there are no port conflicts with other running applications

## Cline MCP Configuration


1. Open your Cline MCP settings file:
   - **macOS**: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Windows**: `%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Linux**: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

2. Add the Stata MCP server configuration:
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "url": "http://localhost:4000/mcp",
         "transport": "sse"
       }
     }
   }
   ```

3. If the file already contains other MCP servers, just add the `"stata-mcp"` entry to the existing `"mcpServers"` object.

4. Save the file and restart VS Code.

You can also configure Cline through VS Code settings:
```json
"cline.mcpSettings": {
  "stata-mcp": {
    "url": "http://localhost:4000/mcp",
    "transport": "sse"
  }
}
```

### Troubleshooting Cline Configuration

If Cline is not recognizing the Stata MCP server:
1. Verify the MCP server is running (Status bar should show "Stata")
2. Check that the configuration file exists with the correct content
3. Try restarting VS Code
4. Check the extension output panel (View > Output > Stata MCP) for any errors

## Claude Desktop MCP Configuration

You can use this extension with Claude Desktop through mcp-proxy:

1. Make sure the Stata MCP extension is installed in VS Code or Cursor and currently running before attempting to configure Claude Desktop
2. Install mcp-proxy:
   ```bash
   # Using pip
   pip install mcp-proxy
   
   # Or using uv (faster)
   uv install mcp-proxy
   ```

3. Find the path to mcp-proxy:
   ```bash
   # On Mac/Linux
   which mcp-proxy
   
   # On Windows (PowerShell)
   (Get-Command mcp-proxy).Path
   ```

4. Configure Claude Desktop by editing the MCP config file:

   **On Windows** (typically at `%APPDATA%\Claude Desktop\claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "command": "mcp-proxy",
         "args": ["http://127.0.0.1:4000/mcp"]
       }
     }
   }
   ```

   **On macOS** (typically at `~/Library/Application Support/Claude Desktop/claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "command": "/path/to/mcp-proxy",
         "args": ["http://127.0.0.1:4000/mcp"]
       }
     }
   }
   ```
   Replace `/path/to/mcp-proxy` with the actual path you found in step 3.

5. Restart Claude Desktop

6. Claude Desktop will automatically discover the available Stata tools, allowing you to run Stata commands and analyze data directly from your conversations.

> **Note:** There is an alternative way to use Stata MCP in Claude Desktop without installing this extension. See [here](https://github.com/SepineTam/stata-mcp).

## Python Environment Management

This extension uses [uv](https://github.com/astral-sh/uv), a fast Python package installer built in Rust, to manage Python dependencies. Key features:

- Automatic Python setup and dependency management
- Creates isolated environments that won't conflict with your system
- Works across Windows, macOS, and Linux
- 10-100x faster than traditional pip installations

**If you encounter any UV-related errors during installation:**
1. Install UV manually:
   ```bash
   # Windows (PowerShell as Administrator)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Follow the [Troubleshooting](#common-installation-issues) steps to reinstall the extension

Starting with version 0.1.8, this extension integrates the fast Python package installer [uv](https://github.com/astral-sh/uv) to set up the environment. If uv is not found on your system, the extension will attempt to install it automatically.

## Troubleshooting

If you encounter issues with the extension, follow these steps to perform a clean reinstallation:

### Windows

1. Close all VS Code/Cursor windows
2. Open Task Manager (Ctrl+Shift+Esc):
   - Go to the "Processes" tab
   - Look for any running Python or `uvicorn` processes
   - Select each one and click "End Task"

3. Remove the extension folder:
   - Press Win+R, type `%USERPROFILE%\.vscode\extensions` and press Enter
   - Delete the folder `deepecon.stata-mcp-0.x.x` (where x.x is the version number)
   - For Cursor: The path is `%USERPROFILE%\.cursor\extensions`

4. Install UV manually (if needed):
   ```powershell
   # Open PowerShell as Administrator and run:
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

5. Restart your computer (recommended but optional)

6. Install the latest version of the extension from the marketplace

### macOS/Linux

1. Close all VS Code/Cursor windows

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

### Additional Troubleshooting Tips

- If you see errors about Python or UV not being found, make sure they are in your system's PATH:
  - Windows: Type "Environment Variables" in the Start menu and add the installation paths
  - macOS/Linux: Add the paths to your `~/.bashrc`, `~/.zshrc`, or equivalent

- If you get permission errors:
  - Windows: Run VS Code/Cursor as Administrator
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

When opening an issue on GitHub, please provide:
- The complete error message from the Output panel (View -> Output -> Stata-MCP)
- Your operating system and version
- VS Code/Cursor version
- Python version (`python --version`)
- UV version (`uv --version`)
- Steps to reproduce the issue
- Any relevant log files or screenshots
- The content of your MCP configuration file if applicable

This detailed information will help us identify and fix the issue more quickly. You can open issues at: [GitHub Issues](https://github.com/hanlulong/stata-mcp/issues)

## License

MIT

## Credits

Created by Lu Han
Published by DeepEcon