# Stata MCP Extension for VS Code and Cursor

[![en](https://img.shields.io/badge/lang-English-red.svg)](./README.md)
[![cn](https://img.shields.io/badge/语言-中文-yellow.svg)](./README.zh-CN.md)
[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code-Marketplace-blue)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)
![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/i/deepecon.stata-mcp.svg)
![GitHub all releases](https://img.shields.io/github/downloads/hanlulong/stata-mcp/total.svg)
[![GitHub license](https://img.shields.io/github/license/hanlulong/stata-mcp)](https://github.com/hanlulong/stata-mcp/blob/main/LICENSE) 


This extension provides Stata integration for Visual Studio Code and Cursor IDE using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro).

The extension allows you to:

- Run Stata commands directly from VS Code or Cursor
- Execute selections or entire .do files
- View Stata output in the editor in real-time
- Get AI assistant integration through the MCP protocol
- Experience enhanced AI coding with [Cursor](https://www.cursor.com/), [Cline](https://github.com/cline/cline), [Claude Code](https://claude.com/product/claude-code), or [Codex](https://github.com/openai/codex)
- Choose your Stata edition (MP, SE, or BE)

## Features

- **Run Stata Commands**: Execute selections or entire .do files directly from your editor
- **Syntax Highlighting**: Full syntax support for Stata .do, .ado, .mata, and .doh files
- **AI Assistant Integration**: Contextual help and code suggestions via [MCP](https://modelcontextprotocol.io/)
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
> - Use Stata via Jupyter? See [here](https://github.com/hanlulong/stata-mcp/blob/main/docs/jupyter-stata.md)


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

1. Download the extension package `stata-mcp-0.3.3.vsix` from the [releases page](https://github.com/hanlulong/stata-mcp/releases).
2. Install using one of these methods:

```bash
code --install-extension path/to/stata-mcp-0.3.3.vsix
```

Or:
1. Open VS Code
2. Go to Extensions view (Ctrl+Shift+X)
3. Click on "..." menu in the top-right
4. Select "Install from VSIX..."
5. Navigate to and select the downloaded .vsix file

### Cursor Installation

1. Download the extension package `stata-mcp-0.3.3.vsix` from the [releases page](https://github.com/hanlulong/stata-mcp/releases).
2. Install using one of these methods:

```bash
cursor --install-extension path/to/stata-mcp-0.3.3.vsix
```

Or:
1. Open Cursor
2. Go to Extensions view
3. Click on the "..." menu
4. Select "Install from VSIX"
5. Navigate to and select the downloaded .vsix file

Starting with version 0.1.8, the extension integrates a fast Python package installer called `uv` to set up the environment. If uv is not found on your system, the extension will attempt to install it automatically.

## Usage

### Running Stata Code

1. Open a Stata .do file
2. Run commands using:
   - **Run Selection**: Select Stata code and press `Ctrl+Shift+Enter` (or `Cmd+Shift+Enter` on Mac), or click the first button (▶️) in the editor toolbar
   - **Run File**: Press `Ctrl+Shift+D` (or `Cmd+Shift+D` on Mac) to run the entire .do file, or click the second button in the toolbar
   - **Interactive Mode**: Select Stata code and click the 📊 button in the editor toolbar to run the selection in an interactive window, or click without selection to run the entire file
3. View output in the editor panel or interactive window

### Data Viewer

Access the data viewer to inspect your Stata dataset:

1. Click the **View Data** button (fourth button, table icon) in the editor toolbar
2. View your current dataset in a table format
3. **Filter data**: Use Stata `if` conditions to view subsets of your data
   - Example: `price > 5000 & mpg < 30`
   - Type your condition in the filter box and click "Apply"
   - Click "Clear" to remove the filter and view all data

### Graph Display Options

Control how graphs are displayed:

1. **Auto-display graphs**: Graphs are automatically shown when generated (default: enabled)
   - Disable in Extension Settings: `stata-vscode.autoDisplayGraphs`
2. **Choose display method**:
   - **VS Code webview** (default): Graphs appear in a panel within VS Code
   - **External browser**: Graphs open in your default web browser
   - Change in Extension Settings: `stata-vscode.graphDisplayMethod`

### Stata Edition Selection

Select your preferred Stata edition (MP, SE, or BE) in the Extension Settings

## Detailed Configurations

<details>
<summary><strong>Extension Settings</strong></summary>

Customize the extension behavior through VS Code settings. Access these settings via:
- **VS Code/Cursor**: File > Preferences > Settings (or `Ctrl+,` / `Cmd+,`)
- Search for "Stata MCP" to find all extension settings

### Core Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `stata-vscode.stataPath` | Path to Stata installation directory | Auto-detected |
| `stata-vscode.stataEdition` | Stata edition to use (MP, SE, BE) | `mp` |
| `stata-vscode.autoStartServer` | Automatically start MCP server when extension activates | `true` |

### Server Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `stata-vscode.mcpServerHost` | Host for MCP server | `localhost` |
| `stata-vscode.mcpServerPort` | Port for the MCP server | `4000` |
| `stata-vscode.forcePort` | Force the specified port even if it's already in use | `false` |

### Graph Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `stata-vscode.autoDisplayGraphs` | Automatically display graphs when generated by Stata commands | `true` |
| `stata-vscode.graphDisplayMethod` | Choose how to display graphs: `vscode` (webview panel) or `browser` (external browser) | `vscode` |

### Log File Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `stata-vscode.logFileLocation` | Location for Stata log files: `extension` (logs folder in extension directory), `workspace` (same directory as .do file), or `custom` (user-specified directory) | `extension` |
| `stata-vscode.customLogDirectory` | Custom directory for Stata log files (only used when logFileLocation is set to `custom`) | Empty |

### Advanced Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `stata-vscode.runFileTimeout` | Timeout in seconds for 'Run File' operations | `600` (10 minutes) |
| `stata-vscode.debugMode` | Show detailed debug information in output panel | `false` |
| `stata-vscode.clineConfigPath` | Custom path to Cline configuration file (optional) | Auto-detected |

### How to Change Settings

1. Open VS Code/Cursor settings (`Ctrl+,` or `Cmd+,`)
2. Search for "Stata MCP"
3. Modify the desired settings
4. Restart the extension or reload the window if prompted

<br>

</details>
<details>
<summary><strong>Log File Management</strong></summary>

The extension automatically creates log files when running Stata .do files. You can control where these log files are saved:

### Log File Locations

1. **Extension Directory** (default): Log files are saved in a `logs` folder within the extension directory, keeping your workspace clean
2. **Workspace Directory**: Log files are saved in the same directory as your .do file (original behavior)
3. **Custom Directory**: Log files are saved to a directory you specify

### Changing Log File Location

1. Open VS Code/Cursor settings (`Ctrl+,` or `Cmd+,`)
2. Search for "Stata MCP"
3. Find "Log File Location" (`stata-vscode.logFileLocation`) and select your preferred option:
   - `extension`: Save to extension directory (default)
   - `workspace`: Save to same directory as .do file
   - `custom`: Save to a custom directory
4. If using "Custom Directory", also set "Custom Log Directory" (`stata-vscode.customLogDirectory`) path

### Benefits of Each Option

- **Extension Directory**: Keeps your project workspace clean and organized
- **Workspace Directory**: Log files stay with your .do files for easy reference
- **Custom Directory**: Centralize all logs in one location across projects

<br>

</details>
<details>
<summary><strong>Claude Code</strong></summary>

[Claude Code](https://claude.com/product/claude-code) is Anthropic's official AI coding assistant available in VS Code and Cursor. Follow these steps to configure the Stata MCP server:

### Installation

1. **Install the Stata MCP extension** in VS Code or Cursor (see [Installation](#installation) section above)

2. **Start the Stata MCP server**: The server should start automatically when you open VS Code/Cursor with the extension installed. Verify it's running by checking the status bar (should show "Stata").

### Configuration

Once the Stata MCP server is running, configure Claude Code to connect to it:

1. Open your terminal or command palette

2. Run the following command to add the Stata MCP server:
   ```bash
   claude mcp add --transport sse stata-mcp http://localhost:4000/mcp --scope user
   ```

3. Restart VS Code or Cursor

4. Claude Code will now have access to Stata tools and can help you:
   - Write and execute Stata commands
   - Analyze your data
   - Generate visualizations
   - Debug Stata code
   - Create statistical reports

### Verifying the Connection

To verify Claude Code is properly connected to the Stata MCP server:

1. Open a Stata .do file or create a new one
2. Ask Claude Code to help with a Stata task (e.g., "Load the auto dataset and show summary statistics")
3. Claude Code should be able to execute Stata commands and show results

### Troubleshooting

If Claude Code is not recognizing the Stata MCP server:
1. Verify the MCP server is running (Status bar should show "Stata")
2. Check that you ran the `claude mcp add` command with the correct URL
3. Try restarting VS Code or Cursor
4. Check the extension output panel (View > Output > Stata MCP) for any errors
5. Ensure there are no port conflicts (default port is 4000)

<br>

</details>
<details>
<summary><strong>Claude Desktop</strong></summary>

You can use this extension with [Claude Desktop](https://claude.ai/download) through [mcp-proxy](https://github.com/modelcontextprotocol/mcp-proxy):

1. Make sure the Stata MCP extension is installed in VS Code or Cursor and currently running before attempting to configure Claude Desktop
2. Install [mcp-proxy](https://github.com/modelcontextprotocol/mcp-proxy):
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

<br>

</details>
<details>
<summary><strong>OpenAI Codex</strong></summary>

You can use this extension with [OpenAI Codex](https://github.com/openai/codex) through [mcp-proxy](https://github.com/modelcontextprotocol/mcp-proxy):

1. Make sure the Stata MCP extension is installed in VS Code or Cursor and currently running before attempting to configure Codex
2. Install [mcp-proxy](https://github.com/modelcontextprotocol/mcp-proxy):
   ```bash
   # Using pip
   pip install mcp-proxy

   # Or using uv (faster)
   uv install mcp-proxy
   ```

3. Configure Codex by editing the config file at `~/.codex/config.toml`:

   **On macOS/Linux** (`~/.codex/config.toml`):
   ```toml
   # Stata MCP Server (SSE Transport)
   [mcp_servers.stata-mcp]
   command = "mcp-proxy"
   args = ["http://localhost:4000/mcp"]
   ```

   **On Windows** (`%USERPROFILE%\.codex\config.toml`):
   ```toml
   # Stata MCP Server (SSE Transport)
   [mcp_servers.stata-mcp]
   command = "mcp-proxy"
   args = ["http://localhost:4000/mcp"]
   ```

4. If the file already contains other MCP servers, just add the `[mcp_servers.stata-mcp]` section.

5. Restart Codex or VS Code/Cursor

6. Codex will automatically discover the available Stata tools, allowing you to run Stata commands and analyze data directly from your conversations.

### Troubleshooting Codex Configuration

If Codex is not recognizing the Stata MCP server:
1. Verify the MCP server is running (Status bar should show "Stata")
2. Check that the configuration file exists at `~/.codex/config.toml` with the correct content
3. Ensure mcp-proxy is installed: `pip list | grep mcp-proxy` or `which mcp-proxy`
4. Try restarting VS Code or Cursor
5. Check the extension output panel (View > Output > Stata MCP) for any errors
6. Ensure there are no port conflicts (default port is 4000)

<br>

</details>
<details>
<summary><strong>Cline</strong></summary>

1. Open your [Cline](https://github.com/cline/cline) MCP settings file:
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

<br>

</details>
<details>
<summary><strong>Cursor</strong></summary>

The extension automatically configures [Cursor](https://www.cursor.com/) MCP integration. To verify it's working:

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

<br>

</details>

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

- If you're having issues with a specific Stata edition:
  1. Make sure the selected Stata edition (MP, SE, or BE) matches what's installed on your system
  2. Try changing the `stata-vscode.stataEdition` setting to match your installed version
  3. Restart the extension after changing settings

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

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hanlulong/stata-mcp&type=Date)](https://star-history.com/#hanlulong/stata-mcp&Date)

## License

MIT

## Credits

Created by Lu Han,
Published by [DeepEcon.ai](https://deepecon.ai/)
