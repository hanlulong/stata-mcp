# Stata MCP 扩展 for VS Code 和 Cursor

[![en](https://img.shields.io/badge/lang-English-red.svg)](./README.md)
[![cn](https://img.shields.io/badge/语言-中文-yellow.svg)](./README.zh-CN.md)
[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code-Marketplace-blue)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)
![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/i/deepecon.stata-mcp.svg)
![GitHub all releases](https://img.shields.io/github/downloads/hanlulong/stata-mcp/total.svg)
[![GitHub license](https://img.shields.io/github/license/hanlulong/stata-mcp)](https://github.com/hanlulong/stata-mcp/blob/main/LICENSE) 


此扩展通过模型上下文协议（MCP）为 Visual Studio Code 和 Cursor IDE 提供 Stata 集成。该扩展允许您：

- 直接从 VS Code 或 Cursor 运行 Stata 命令
- 执行选中部分或整个 .do 文件
- 在编辑器中实时查看 Stata 输出
- 通过 MCP 协议获得 AI 助手集成
- 使用 Cursor 或 Cline 体验增强的 AI 编程
- 选择您的 Stata 版本（MP、SE 或 BE）

## 功能特性

- **运行 Stata 命令**：直接从编辑器执行选中部分或整个 .do 文件
- **语法高亮**：完全支持 Stata .do、.ado、.mata 和 .doh 文件的语法
- **AI 助手集成**：通过 MCP 提供上下文帮助和代码建议
- **跨平台**：支持 Windows、macOS 和 Linux
- **自动检测 Stata**：自动查找您的 Stata 安装
- **实时输出**：在编辑器中即时查看 Stata 结果

## 演示

观看此扩展如何使用 Cursor（或 VS Code）和 AI 辅助增强您的 Stata 工作流程：

![Stata MCP 扩展演示](images/demo_2x.gif)

**[🎬 完整视频版本](https://github.com/hanlulong/stata-mcp/raw/main/images/demo.mp4)** &nbsp;&nbsp;|&nbsp;&nbsp; **[📄 查看生成的 PDF 报告](examples/auto_report.pdf)**

<sub>*演示提示："编写并执行 Stata do 文件，确保在所有情况下都使用完整的绝对文件路径。加载 auto 数据集（webuse auto）并为每个变量生成汇总统计信息。识别并提取数据集中的关键特征，制作相关图表并保存在名为 plots 的文件夹中。进行回归分析以检查汽车价格的主要决定因素。将所有输出导出到 LaTeX 文件并编译。自动解决任何编译错误，并确保 LaTeX 编译时间不超过 10 秒。作为工作流程的一部分，应识别并解决所有代码错误。"*</sub>

> **寻找其他 Stata 集成？**
> - 使用 Stata 与 Notepad++ 和 Sublime Text 3？请看[这里](https://github.com/sook-tusk/Tech_Integrate_Stata_R_with_Editors)
> - 在 Claude Desktop 中使用 Stata MCP 而不安装此扩展？请看[这里](https://github.com/SepineTam/stata-mcp)
> - 通过 Jupyter 使用 Stata？请看[这里](https://github.com/hanlulong/stata-mcp/blob/main/docs/jupyter-stata.md)

## 系统要求

- 您的计算机上已安装 Stata 17 或更高版本
- [UV](https://github.com/astral-sh/uv) 包管理器（自动安装，或根据需要手动安装）

## 安装

> **注意：** 初始安装需要设置依赖项，可能需要最多 2 分钟完成。请在此一次性设置过程中保持耐心。所有后续运行将立即启动。

### VS Code 安装

#### 选项 1：从 VS Code 市场安装

直接从 [VS Code 市场](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp) 安装此扩展。

```bash
code --install-extension DeepEcon.stata-mcp
```

或：
1. 打开 VS Code
2. 转到扩展视图（Ctrl+Shift+X）
3. 搜索 "Stata MCP"
4. 点击"安装"

#### 选项 2：从 .vsix 文件安装

1. 从[发布页面](https://github.com/hanlulong/stata-mcp/releases)下载扩展包 `stata-mcp-0.2.5.vsix`。
2. 使用以下方法之一安装：

```bash
code --install-extension path/to/stata-mcp-0.2.5.vsix
```

或：
1. 打开 VS Code
2. 转到扩展视图（Ctrl+Shift+X）
3. 点击右上角的"..."菜单
4. 选择"从 VSIX 安装..."
5. 导航并选择下载的 .vsix 文件

### Cursor 安装

1. 从[发布页面](https://github.com/hanlulong/stata-mcp/releases)下载扩展包 `stata-mcp-0.2.5.vsix`。
2. 使用以下方法之一安装：

```bash
cursor --install-extension path/to/stata-mcp-0.2.5.vsix
```

或：
1. 打开 Cursor
2. 转到扩展视图
3. 点击"..."菜单
4. 选择"从 VSIX 安装"
5. 导航并选择下载的 .vsix 文件

从 0.1.8 版本开始，该扩展集成了名为 `uv` 的快速 Python 包安装器来设置环境。如果在您的系统上找不到 uv，扩展将尝试自动安装它。

## 扩展设置

您可以通过 VS Code 设置自定义扩展行为：

- `stata-vscode.stataPath`：Stata 安装目录的路径
- `stata-vscode.mcpServerHost`：MCP 服务器的主机（默认：localhost）
- `stata-vscode.mcpServerPort`：MCP 服务器的端口（默认：4000）
- `stata-vscode.autoStartServer`：扩展激活时自动启动 MCP 服务器（默认：true）
- `stata-vscode.debugMode`：在输出面板中显示详细的调试信息（默认：false）
- `stata-vscode.forcePort`：即使端口已被使用，也强制 MCP 服务器使用指定端口（默认：false）
- `stata-vscode.clineConfigPath`：Cline 配置文件的自定义路径（可选，默认为标准位置）
- `stata-vscode.runFileTimeout`："运行文件"操作的超时时间（秒）（默认：600 秒/10 分钟）
- `stata-vscode.stataEdition`：要使用的 Stata 版本（MP、SE、BE）- 默认：MP
- `stata-vscode.logFileLocation`：Stata 日志文件的位置 - 'extension'（扩展目录中的 logs 文件夹）、'workspace'（与 .do 文件相同的目录）或 'custom'（用户指定的目录）- 默认：extension
- `stata-vscode.customLogDirectory`：Stata 日志文件的自定义目录（仅当 logFileLocation 设置为 'custom' 时使用）

## 使用方法

1. 打开一个 Stata .do 文件
2. 使用以下方式运行命令：
   - **运行选中部分**：选中 Stata 代码并按 `Ctrl+Shift+Enter`（Mac 上为 `Cmd+Shift+Enter`）
   - **运行文件**：按 `Ctrl+Shift+D`（Mac 上为 `Cmd+Shift+D`）运行整个 .do 文件
3. 在编辑器面板中查看输出
4. **选择 Stata 版本**：在扩展设置中选择您首选的 Stata 版本（MP、SE 或 BE）

## 日志文件管理

该扩展在运行 Stata .do 文件时会自动创建日志文件。您可以控制这些日志文件的保存位置：

1. **扩展目录**（默认）：日志文件保存在扩展目录内的 `logs` 文件夹中，保持您的工作空间整洁
2. **工作空间目录**：日志文件保存在与您的 .do 文件相同的目录中（原始行为）
3. **自定义目录**：日志文件保存到您指定的目录

要更改此设置：
1. 打开 VS Code/Cursor 设置
2. 搜索 "Stata MCP"
3. 找到"日志文件位置"并选择您首选的选项
4. 如果使用"自定义目录"，还要设置"自定义日志目录"路径

## 工作原理

该扩展创建一个本地 MCP 服务器，将您的编辑器连接到 Stata，实现：

1. **命令执行**：运行 Stata 命令并即时查看结果
2. **上下文感知**：AI 助手理解您的 Stata 数据和命令
3. **增强生产力**：获得智能代码建议和文档

## Cursor MCP 配置

该扩展自动配置 Cursor MCP 集成。要验证其是否正常工作：

1. 打开 Cursor
2. 按 `Ctrl+Shift+P`（Mac 上为 `Cmd+Shift+P`）打开命令面板
3. 输入"Stata: 测试 MCP 服务器连接"并按回车
4. 如果服务器正确连接，您应该看到成功消息

### Cursor 配置文件路径

Cursor MCP 配置文件的位置因操作系统而异：

- **macOS**：
  - 主要位置：`~/.cursor/mcp.json`
  - 替代位置：`~/Library/Application Support/Cursor/User/mcp.json`

- **Windows**：
  - 主要位置：`%USERPROFILE%\.cursor\mcp.json`
  - 替代位置：`%APPDATA%\Cursor\User\mcp.json`

- **Linux**：
  - 主要位置：`~/.cursor/mcp.json`
  - 替代位置：`~/.config/Cursor/User/mcp.json`

### 手动 Cursor 配置

如果您需要手动配置 Cursor MCP：

1. 创建或编辑 MCP 配置文件：
   - **macOS/Linux**：`~/.cursor/mcp.json`
   - **Windows**：`%USERPROFILE%\.cursor\mcp.json`

2. 添加 Stata MCP 服务器配置：
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

3. 如果文件已包含其他 MCP 服务器，只需将 `"stata-mcp"` 条目添加到现有的 `"mcpServers"` 对象中。

4. 保存文件并重启 Cursor。

### Cursor 配置故障排除

如果 Cursor 无法识别 Stata MCP 服务器：
1. 验证 MCP 服务器正在运行
2. 检查配置文件是否存在且内容正确
3. 尝试重启 Cursor
4. 确保与其他正在运行的应用程序没有端口冲突

## Cline MCP 配置


1. 打开您的 Cline MCP 设置文件：
   - **macOS**：`~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Windows**：`%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Linux**：`~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

2. 添加 Stata MCP 服务器配置：
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

3. 如果文件已包含其他 MCP 服务器，只需将 `"stata-mcp"` 条目添加到现有的 `"mcpServers"` 对象中。

4. 保存文件并重启 VS Code。

您还可以通过 VS Code 设置配置 Cline：
```json
"cline.mcpSettings": {
  "stata-mcp": {
    "url": "http://localhost:4000/mcp",
    "transport": "sse"
  }
}
```

### Cline 配置故障排除

如果 Cline 无法识别 Stata MCP 服务器：
1. 验证 MCP 服务器正在运行（状态栏应显示"Stata"）
2. 检查配置文件是否存在且内容正确
3. 尝试重启 VS Code
4. 检查扩展输出面板（查看 > 输出 > Stata MCP）是否有任何错误

## Claude Desktop MCP 配置

您可以通过 mcp-proxy 将此扩展与 Claude Desktop 一起使用：

1. 确保 Stata MCP 扩展已安装在 VS Code 或 Cursor 中并且当前正在运行，然后再尝试配置 Claude Desktop
2. 安装 mcp-proxy：
   ```bash
   # 使用 pip
   pip install mcp-proxy
   
   # 或使用 uv（更快）
   uv install mcp-proxy
   ```

3. 找到 mcp-proxy 的路径：
   ```bash
   # 在 Mac/Linux 上
   which mcp-proxy
   
   # 在 Windows（PowerShell）上
   (Get-Command mcp-proxy).Path
   ```

4. 通过编辑 MCP 配置文件来配置 Claude Desktop：

   **在 Windows**（通常位于 `%APPDATA%\Claude Desktop\claude_desktop_config.json`）：
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

   **在 macOS**（通常位于 `~/Library/Application Support/Claude Desktop/claude_desktop_config.json`）：
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
   将 `/path/to/mcp-proxy` 替换为您在第 3 步中找到的实际路径。

5. 重启 Claude Desktop

6. Claude Desktop 将自动发现可用的 Stata 工具，允许您直接从对话中运行 Stata 命令和分析数据。

> **注意：** 有一种替代方法可以在不安装此扩展的情况下在 Claude Desktop 中使用 Stata MCP。请看[这里](https://github.com/SepineTam/stata-mcp)。

## Python 环境管理

此扩展使用 [uv](https://github.com/astral-sh/uv)（一个在 Rust 中构建的快速 Python 包安装器）来管理 Python 依赖项。主要特性：

- 自动 Python 设置和依赖项管理
- 创建隔离的环境，不会与您的系统冲突
- 支持 Windows、macOS 和 Linux
- 比传统 pip 安装快 10-100 倍

**如果您在安装过程中遇到任何 UV 相关错误：**
1. 手动安装 UV：
   ```bash
   # Windows（以管理员身份运行 PowerShell）
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. 按照[故障排除](#常见安装问题)步骤重新安装扩展

从 0.1.8 版本开始，此扩展集成了快速的 Python 包安装器 [uv](https://github.com/astral-sh/uv) 来设置环境。如果在您的系统上找不到 uv，扩展将尝试自动安装它。

## 故障排除

如果您遇到扩展问题，请按照以下步骤执行干净重新安装：

### Windows

1. 关闭所有 VS Code/Cursor 窗口
2. 打开任务管理器（Ctrl+Shift+Esc）：
   - 转到"进程"标签
   - 查找任何正在运行的 Python 或 `uvicorn` 进程
   - 选择每个进程并点击"结束任务"

3. 删除扩展文件夹：
   - 按 Win+R，输入 `%USERPROFILE%\.vscode\extensions` 并按回车
   - 删除文件夹 `deepecon.stata-mcp-0.x.x`（其中 x.x 是版本号）
   - 对于 Cursor：路径为 `%USERPROFILE%\.cursor\extensions`

4. 手动安装 UV（如果需要）：
   ```powershell
   # 以管理员身份打开 PowerShell 并运行：
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

5. 重启计算机（推荐但可选）

6. 从市场安装最新版本的扩展

### macOS/Linux

1. 关闭所有 VS Code/Cursor 窗口

2. 终止任何正在运行的 Python 进程：
   ```bash
   # 查找 Python 进程
   ps aux | grep python
   # 终止它们（将 <PID> 替换为您找到的进程号）
   kill -9 <PID>
   ```

3. 删除扩展文件夹：
   ```bash
   # 对于 VS Code：
   rm -rf ~/.vscode/extensions/deepecon.stata-mcp-0.x.x
   # 对于 Cursor：
   rm -rf ~/.cursor/extensions/deepecon.stata-mcp-0.x.x
   ```

4. 手动安装 UV（如果需要）：
   ```bash
   # 使用 curl：
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # 或使用 wget：
   wget -qO- https://astral.sh/uv/install.sh | sh
   ```

5. 重启终端或计算机（推荐但可选）

6. 从市场安装最新版本的扩展

### 额外的故障排除提示

- 如果您看到关于 Python 或 UV 未找到的错误，请确保它们在系统 PATH 中：
  - Windows：在开始菜单中输入"环境变量"并添加安装路径
  - macOS/Linux：将路径添加到您的 `~/.bashrc`、`~/.zshrc` 或等效文件

- 如果您遇到权限错误：
  - Windows：以管理员身份运行 VS Code/Cursor
  - macOS/Linux：使用 `ls -la` 检查文件夹权限，如果需要，使用 `chmod` 修复

- 如果扩展仍然无法初始化：
  1. 打开输出面板（查看 -> 输出）
  2. 从下拉菜单中选择"Stata-MCP"
  3. 检查日志中的具体错误消息
  4. 如果您看到与 Python 相关的错误，请尝试手动创建 Python 3.11 虚拟环境：
     ```bash
     # Windows
     py -3.11 -m venv .venv

     # macOS/Linux
     python3.11 -m venv .venv
     ```

- 对于持续存在的问题：
  1. 检查您的系统 Python 安装：`python --version` 或 `python3 --version`
  2. 验证 UV 安装：`uv --version`
  3. 确保您已安装 Python 3.11 或更高版本
  4. 检查您的防病毒软件是否阻止 Python 或 UV 可执行文件

- 如果您遇到特定 Stata 版本的问题：
  1. 确保所选的 Stata 版本（MP、SE 或 BE）与系统上安装的版本匹配
  2. 尝试将 `stata-vscode.stataEdition` 设置更改为与已安装版本匹配
  3. 更改设置后重启扩展

在 GitHub 上打开问题时，请提供：
- 来自输出面板的完整错误消息（查看 -> 输出 -> Stata-MCP）
- 您的操作系统和版本
- VS Code/Cursor 版本
- Python 版本（`python --version`）
- UV 版本（`uv --version`）
- 重现问题的步骤
- 任何相关的日志文件或屏幕截图
- 适用的 MCP 配置文件内容

这些详细信息将帮助我们更快识别并解决问题。您可以在以下位置打开问题：[GitHub 问题](https://github.com/hanlulong/stata-mcp/issues)

## Star 历史

[![Star 历史图表](https://api.star-history.com/svg?repos=hanlulong/stata-mcp&type=Date)](https://star-history.com/#hanlulong/stata-mcp&Date)

## 许可证

MIT

## 致谢

由 Lu Han 创建
由 DeepEcon 发布