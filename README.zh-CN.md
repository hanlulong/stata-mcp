# Stata MCP 扩展 for VS Code、Cursor 和 Antigravity

[![en](https://img.shields.io/badge/lang-English-red.svg)](./README.md)
[![cn](https://img.shields.io/badge/语言-中文-yellow.svg)](./README.zh-CN.md)
[![VS Code Marketplace](https://vsmarketplacebadges.dev/version-short/DeepEcon.stata-mcp.svg?label=VS%20Code)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)
[![VS Code Installs](https://vsmarketplacebadges.dev/installs-short/DeepEcon.stata-mcp.svg?label=VS%20Code%20installs)](https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp)
[![Open VSX](https://img.shields.io/open-vsx/v/DeepEcon/stata-mcp?label=Open%20VSX)](https://open-vsx.org/extension/DeepEcon/stata-mcp)
[![Open VSX Downloads](https://img.shields.io/open-vsx/dt/DeepEcon/stata-mcp?label=Open%20VSX%20downloads)](https://open-vsx.org/extension/DeepEcon/stata-mcp)
[![GitHub Downloads](https://img.shields.io/github/downloads/hanlulong/stata-mcp/total.svg)](https://github.com/hanlulong/stata-mcp/releases)
[![GitHub License](https://img.shields.io/github/license/hanlulong/stata-mcp)](https://github.com/hanlulong/stata-mcp/blob/main/LICENSE) 


此扩展通过[模型上下文协议（MCP）](https://modelcontextprotocol.io/docs/getting-started/intro)为 Visual Studio Code、Cursor 和 Antigravity IDE 提供 Stata 集成。支持 [GitHub Copilot](https://github.com/features/copilot)、[Cursor](https://www.cursor.com/)、[Antigravity](https://antigravity.google/)、[Cline](https://github.com/cline/cline)、[Claude Code](https://claude.com/product/claude-code) 或 [Codex](https://github.com/openai/codex) 等 AI 工具进行智能 Stata 开发。

## 功能特性

- **运行 Stata 命令**：直接从编辑器执行选中部分或整个 .do 文件
- **实时输出**：在编辑器中即时查看 Stata 结果
- **语法高亮**：完全支持 Stata .do、.ado、.mata 和 .doh 文件的语法
- **AI 助手集成**：通过 MCP 提供上下文帮助和代码建议
- **跨平台**：支持 Windows、macOS 和 Linux
- **多会话并行执行**：同时运行多个 Stata 会话，支持 AI 编程工具

## 演示

观看此扩展如何使用 Cursor（或 VS Code/Antigravity）和 AI 辅助增强您的 Stata 工作流程：

![Stata MCP 扩展演示](images/demo_2x.gif)

**[🎬 完整视频版本](https://github.com/hanlulong/stata-mcp/raw/main/images/demo.mp4)** &nbsp;&nbsp;|&nbsp;&nbsp; **[📄 查看生成的 PDF 报告](docs/examples/auto_report.pdf)**

<sub>*演示提示："编写并执行 Stata do 文件，确保在所有情况下都使用完整的绝对文件路径。加载 auto 数据集（webuse auto）并为每个变量生成汇总统计信息。识别并提取数据集中的关键特征，制作相关图表并保存在名为 plots 的文件夹中。进行回归分析以检查汽车价格的主要决定因素。将所有输出导出到 LaTeX 文件并编译。自动解决任何编译错误，并确保 LaTeX 编译时间不超过 10 秒。作为工作流程的一部分，应识别并解决所有代码错误。"*</sub>

## 系统要求

- 您的计算机上已安装 Stata 17 或更高版本
- [UV](https://github.com/astral-sh/uv) 包管理器（自动安装，或根据需要手动安装）

## 安装

> **注意：** 初始安装需要设置依赖项，可能需要最多 2 分钟完成。请在此一次性设置过程中保持耐心。所有后续运行将立即启动。

1. 打开 **VS Code**、**Cursor** 或 **Antigravity**
2. 打开扩展视图（`Ctrl+Shift+X` / `Cmd+Shift+X`）
3. 搜索 **"Stata MCP"**
4. 点击 **安装**

完成 — 扩展会自动启动 MCP 服务，状态栏会显示 **"Stata"**。

<details>
<summary><strong>其它安装方式</strong> — 命令行、.vsix 文件、Open VSX</summary>

#### 命令行安装

```bash
# VS Code
code --install-extension DeepEcon.stata-mcp

# Cursor
cursor --install-extension DeepEcon.stata-mcp

# Antigravity（从 Open VSX 注册表安装）
antigravity --install-extension DeepEcon.stata-mcp
```

#### 从本地 .vsix 文件安装

从 [发布页面](https://github.com/hanlulong/stata-mcp/releases) 下载 `stata-mcp-<version>.vsix`，然后：

```bash
code        --install-extension path/to/stata-mcp-0.5.2.vsix
cursor      --install-extension path/to/stata-mcp-0.5.2.vsix
antigravity --install-extension path/to/stata-mcp-0.5.2.vsix
```

……或在界面中：扩展视图 → **…** 菜单 → **从 VSIX 安装…** → 选择下载的文件。

#### 注册表

- VS Code 市场：<https://marketplace.visualstudio.com/items?itemName=DeepEcon.stata-mcp>
- Open VSX（Cursor / Antigravity）：<https://open-vsx.org/extension/DeepEcon/stata-mcp>

</details>

从 0.1.8 版本开始，该扩展集成了名为 `uv` 的快速 Python 包安装器来设置环境。如果在您的系统上找不到 uv，扩展将尝试自动安装它。

## ⚡ 连接您的 AI 助手

扩展运行起来（状态栏显示 **"Stata"**）之后，本地 MCP 服务监听在：

- **`http://localhost:4000/mcp-streamable`** — Streamable HTTP（推荐给现代客户端）
- `http://localhost:4000/mcp` — SSE（旧版兼容）

### 📋 一次粘贴完成配置

把下面的代码块粘贴给任意支持 MCP 的助手 — **Claude Code**、**OpenAI Codex**、**Cursor AI**、**Copilot Chat** 等都可以。在 GitHub 上把鼠标悬停在代码框上，点右上角的复制图标即可一键复制。

```text
Set up the Stata MCP server for me. Endpoint: http://localhost:4000/mcp-streamable — setup guide: https://github.com/hanlulong/stata-mcp#detailed-configurations — verify by confirming the stata_run_selection tool is available.
```

助手会按图索骥：读配置指南、识别自己是哪类客户端、写入对应配置（或运行对应的 CLI 命令），需要时自动重启。

想手动配置？展开下方的 **详细配置** 查看每个客户端的说明。

## 使用方法

### 运行 Stata 代码

1. 打开一个 Stata .do 文件
2. 使用以下方式运行命令：
   - **运行选中部分**：选中 Stata 代码并按 `Ctrl+Shift+Enter`（Mac 上为 `Cmd+Shift+Enter`），或点击编辑器工具栏中的播放按钮
   - **运行文件**：按 `Ctrl+Shift+D`（Mac 上为 `Cmd+Shift+D`）运行整个 .do 文件，或点击工具栏中的运行全部按钮
   - **停止执行**：按 `Ctrl+Shift+C`（Mac 上为 `Cmd+Shift+C`）停止正在运行的命令
   - **重启会话**：点击编辑器工具栏中的重启按钮或使用命令面板（"Stata: Restart Session"）重置 Stata 会话。这将清除所有内存中的数据、全局宏和程序——等同于关闭并重新打开 Stata
   - **交互模式**：点击编辑器工具栏中的图表按钮在交互浏览器窗口中运行代码
3. 在 Stata 输出面板中查看输出

> **Cursor/Antigravity 用户注意**：工具栏按钮可能默认隐藏。要显示它们：
> 1. 点击编辑器标题栏中的 **...** （三个点）菜单
> 2. 选择 **"Configure Icon Visibility"**（配置图标可见性）
> 3. 启用您想要看到的 Stata 按钮（运行选中、运行文件、停止、查看数据、重启会话、交互模式）

### 数据查看器

访问数据查看器以检查您的 Stata 数据集：

1. 点击编辑器工具栏中的**查看数据**按钮（第四个按钮，表格图标）
2. 以表格格式查看您当前的数据集
3. **筛选数据**：使用 Stata `if` 条件查看数据子集
   - 示例：`price > 5000 & mpg < 30`
   - 在筛选框中输入条件并点击"应用"
   - 点击"清除"以移除筛选并查看所有数据

### 图形显示选项

控制图形的显示方式：

1. **自动显示图形**：生成图形时自动显示（默认：启用）
   - 在扩展设置中禁用：`stata-vscode.autoDisplayGraphs`
2. **选择显示方式**：
   - **VS Code webview**（默认）：图形显示在 VS Code 内的面板中
   - **外部浏览器**：图形在默认网页浏览器中打开
   - 在扩展设置中更改：`stata-vscode.graphDisplayMethod`

## 详细配置

<details>
<summary><strong>扩展设置</strong></summary>

通过 VS Code 设置自定义扩展行为。访问这些设置：
- **VS Code/Cursor/Antigravity**：文件 > 首选项 > 设置（或 `Ctrl+,` / `Cmd+,`）
- 搜索"Stata MCP"以查找所有扩展设置

### 核心设置

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.stataPath` | Stata 安装目录的路径 | 自动检测 |
| `stata-vscode.stataEdition` | 要使用的 Stata 版本（MP、SE、BE） | `mp` |
| `stata-vscode.autoStartServer` | 扩展激活时自动启动 MCP 服务器 | `true` |

### 服务器设置

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.mcpServerHost` | MCP 服务器的主机 | `localhost` |
| `stata-vscode.mcpServerPort` | MCP 服务器的端口 | `4000` |
| `stata-vscode.forcePort` | 即使端口已被使用也强制使用指定端口 | `false` |

### 图形设置

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.autoDisplayGraphs` | Stata 命令生成图形时自动显示 | `true` |
| `stata-vscode.graphDisplayMethod` | 选择图形显示方式：`vscode`（webview 面板）或 `browser`（外部浏览器） | `vscode` |

### 日志文件设置

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.logFileLocation` | Stata 日志文件的位置：`dofile`（与 .do 文件相同的目录）、`parent`（.do 文件的父目录）、`workspace`（VS Code 工作区根目录）、`extension`（扩展目录中的 logs 文件夹）或 `custom`（用户指定的目录） | `extension` |
| `stata-vscode.customLogDirectory` | Stata 日志文件的自定义目录（仅当 logFileLocation 设置为 `custom` 时使用） | 空 |

### 高级设置

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.runFileTimeout` | "运行文件"操作的超时时间（秒） | `600`（10 分钟） |
| `stata-vscode.runSelectionTimeout` | "运行选择"和交互式窗口命令的超时时间（秒） | `600`（10 分钟） |
| `stata-vscode.debugMode` | 在输出面板中显示详细的调试信息 | `false` |

### 工作目录设置

控制运行 .do 文件时 Stata 使用的目录：

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.workingDirectory` | 运行 .do 文件时的工作目录：`dofile`（与 .do 文件相同）、`parent`（.do 文件的父目录）、`workspace`（VS Code 工作区根目录）、`extension`（扩展目录中的 logs 文件夹）、`custom`（用户指定）或 `none`（不更改目录） | `dofile` |
| `stata-vscode.customWorkingDirectory` | 自定义工作目录路径（仅当 workingDirectory 设置为 `custom` 时使用） | 空 |

**示例：** 如果您的项目结构是 `project/code/analysis.do`，而您的 do 文件期望从 `project/` 运行，请将 `workingDirectory` 设置为 `parent`。

### MCP 输出设置

这些设置控制通过 MCP 协议返回给 AI 助手（LLM）的 Stata 输出，有助于减少 token 使用量：

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.resultDisplayMode` | MCP 返回的输出模式：`compact`（过滤冗余输出以节省 token）或 `full`（返回完整输出） | `compact` |
| `stata-vscode.maxOutputTokens` | MCP 输出的最大 token 数（0 = 无限制）。大输出将保存到文件并返回路径 | `10000` |

**Compact 模式过滤内容：**
- 循环代码回显（foreach/forvalues/while 块）- 仅保留实际输出
- 程序定义和 Mata 块
- 命令回显和续行符（仅适用于 `run_file`）
- 详细消息如 "(N real changes made)" 和 "(N missing values generated)"

### 多会话设置

启用并行 Stata 执行，每个会话拥有独立的状态（数据、变量、宏）。

| 设置 | 描述 | 默认值 |
|------|------|--------|
| `stata-vscode.multiSession` | 启用多会话模式以支持并行 Stata 执行 | `true` |
| `stata-vscode.maxSessions` | 最大并发会话数（1-100） | `100` |
| `stata-vscode.sessionTimeout` | 会话空闲超时时间（秒）。超时后会话将自动销毁 | `3600` |

**注意：** 每个会话需要约 200-300 MB 内存。请检查您的 Stata 许可证是否支持并发实例。

<br>

</details>
<details>
<summary><strong>GitHub Copilot</strong></summary>

[GitHub Copilot](https://github.com/features/copilot) 从 VS Code 1.102 版本开始支持 MCP（模型上下文协议）。您可以将 Stata MCP 服务器连接到 Copilot，实现 AI 驱动的 Stata 开发。

### 配置

1. **安装 Stata MCP 扩展**（在 VS Code 中，参见上面的[安装](#安装)部分）

2. **启动 Stata MCP 服务器**：当您打开安装了扩展的 VS Code 时，服务器应自动启动。通过检查状态栏（应显示"Stata"）来验证其是否正在运行。

3. **将 Stata MCP 服务器添加到 Copilot**：您可以按工作区或全局配置 MCP 服务器。

   **选项 A：按工作区配置**

   在工作区根目录创建 `.vscode/mcp.json` 文件：
   ```json
   {
     "servers": {
       "stata-mcp": {
         "type": "http",
         "url": "http://localhost:4000/mcp-streamable"
       }
     }
   }
   ```

   **选项 B：全局配置（所有工作区）**

   1. 打开命令面板（Ctrl+Shift+P / Cmd+Shift+P）
   2. 输入 **"MCP: Open User Configuration"** 并选择
   3. 在 `mcp.json` 文件中添加 Stata MCP 服务器：
      ```json
      {
        "servers": {
          "stata-mcp": {
            "type": "http",
            "url": "http://localhost:4000/mcp-streamable"
          }
        }
      }
      ```

   > 如果 VS Code 版本较旧不支持 Streamable HTTP，改用 `"type": "sse"` + `http://localhost:4000/mcp`。

   用户级 `mcp.json` 文件位置：
   - **Windows**: `%APPDATA%\Code\User\mcp.json`
   - **macOS**: `~/Library/Application Support/Code/User/mcp.json`
   - **Linux**: `~/.config/Code/User/mcp.json`

4. **重新加载 VS Code** 以应用配置。

5. GitHub Copilot 现在可以访问 Stata 工具并可以帮助您：
   - 编写和执行 Stata 命令
   - 分析您的数据
   - 生成可视化图表
   - 调试 Stata 代码
   - 创建统计报告

### 验证连接

1. 打开 GitHub Copilot Chat（Ctrl+Shift+I / Cmd+Shift+I）
2. 输入 `@mcp` 查看可用的 MCP 工具
3. Stata 工具（`stata_run_selection`、`stata_run_file`）应该会显示

### 故障排除

如果 Copilot 无法识别 Stata MCP 服务器：
1. 验证 VS Code 版本为 1.102 或更高版本
2. 验证 MCP 服务器正在运行（状态栏应显示"Stata"）
3. 检查 `.vscode/mcp.json` 是否存在且内容正确
4. 尝试重启 VS Code
5. 检查扩展输出面板（查看 > 输出 > Stata MCP）是否有任何错误
6. 确保您组织的 Copilot 策略已启用 MCP（如适用）

<br>

</details>
<details>
<summary><strong>Claude Code</strong></summary>

[Claude Code](https://claude.com/product/claude-code) 是 Anthropic 的官方 AI 编程助手，可在 VS Code、Cursor 和 Antigravity 中使用。按照以下步骤配置 Stata MCP 服务器：

### 安装

1. **安装 Stata MCP 扩展**（在 VS Code、Cursor 或 Antigravity 中，参见上面的[安装](#安装)部分）

2. **启动 Stata MCP 服务器**：当您打开安装了扩展的 IDE 时，服务器应自动启动。通过检查状态栏（应显示"Stata"）来验证其是否正在运行。

### 配置

一旦 Stata MCP 服务器运行，配置 Claude Code 以连接到它：

1. 打开您的终端或命令面板

2. 运行以下命令以添加 Stata MCP 服务器：
   ```bash
   claude mcp add --transport http stata-mcp http://localhost:4000/mcp-streamable --scope user
   ```

   > 较旧版本（2026 年之前）的 Claude Code 可能不识别 `--transport http`。在那些版本上请改用 `--transport sse` + `http://localhost:4000/mcp`。Claude Code 现在把 SSE 视为旧版传输 — 有 `http` 就优先用 `http`。

3. 重启您的 IDE

4. Claude Code 现在可以访问 Stata 工具并可以帮助您：
   - 编写和执行 Stata 命令
   - 分析您的数据
   - 生成可视化图表
   - 调试 Stata 代码
   - 创建统计报告

### 验证连接

要验证 Claude Code 是否正确连接到 Stata MCP 服务器：

1. 打开一个 Stata .do 文件或创建一个新文件
2. 请求 Claude Code 帮助完成 Stata 任务（例如，"加载 auto 数据集并显示汇总统计信息"）
3. Claude Code 应该能够执行 Stata 命令并显示结果

### 故障排除

如果 Claude Code 无法识别 Stata MCP 服务器：
1. 验证 MCP 服务器正在运行（状态栏应显示"Stata"）
2. 检查您是否使用正确的 URL 运行了 `claude mcp add` 命令
3. 尝试重启您的 IDE
4. 检查扩展输出面板（查看 > 输出 > Stata MCP）是否有任何错误
5. 确保没有端口冲突（默认端口为 4000）

<br>

</details>
<details>
<summary><strong>Claude Desktop</strong></summary>

[Claude Desktop](https://claude.ai/download) 可以连接到本扩展暴露的远程 MCP 服务。配置之前请确认 Stata MCP 扩展已安装，状态栏显示 **"Stata"**。

**选项 A（推荐）：作为自定义连接器添加**

1. 打开 Claude Desktop → **Settings** → **Connectors** → **Add custom connector**
2. 名称：`Stata MCP`
3. URL：`http://localhost:4000/mcp-streamable`
4. 保存并重启 Claude Desktop

不需要包装器，不需要编辑配置文件，也不需要装 Python 或 Node。这是 Anthropic 目前官方推荐的添加远程 MCP 服务器的方法。

**选项 B：JSON 配置 + stdio 包装器**（如果您更喜欢改 `claude_desktop_config.json`）

Anthropic 的 JSON 配置目前还不接受远程 URL，需要本地 stdio 包装器。最简单的是 [`mcp-remote`](https://www.npmjs.com/package/mcp-remote)，只要有 Node 就能零安装运行：

1. 打开配置文件：
   - **macOS**：`~/Library/Application Support/Claude Desktop/claude_desktop_config.json`
   - **Windows**：`%APPDATA%\Claude Desktop\claude_desktop_config.json`

2. 追加下面这段（如已有 `mcpServers` 对象，合并进去）：
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "http://localhost:4000/mcp-streamable"]
       }
     }
   }
   ```

3. 重启 Claude Desktop，Stata 工具会出现在可用工具列表中。

<br>

</details>
<details>
<summary><strong>OpenAI Codex</strong></summary>

您可以将此扩展与 [OpenAI Codex](https://github.com/openai/codex) 一起使用 — CLI 和所有 IDE 扩展共用同一份 `~/.codex/config.toml`。Codex CLI **0.46.0+**（2025 年 10 月）原生支持 HTTP 传输的 MCP 服务器，不再需要任何包装器。直接在终端执行：

```bash
codex mcp add stata-mcp --url http://localhost:4000/mcp-streamable
```

或手动把这段追加到 `~/.codex/config.toml`（Windows 上是 `%USERPROFILE%\.codex\config.toml`）：

```toml
[mcp_servers.stata-mcp]
url = "http://localhost:4000/mcp-streamable"
```

然后重启 Codex，`stata_run_selection` 和 `stata_run_file` 就会出现在工具列表中。

> **传输格式说明。** Codex 只支持 MCP 的 *Streamable HTTP* 传输（单端点 `/mcp-streamable`）。扩展的老版 SSE 端点（`/mcp`）是为 GitHub Copilot 等老客户端准备的 — 不要把 Codex 指向它。

### Codex 配置故障排除

如果 Codex 看不到 Stata 工具：
1. 确认 MCP 服务器正在运行（状态栏显示 "Stata"） — 可以 `curl -s http://localhost:4000/health` 验证
2. 确认 `codex --version` 是 **0.46.0** 或更新。老版本仍需 `mcp-proxy` 包装器（见下方备选方案）。
3. 确认 `~/.codex/config.toml` 存在并包含上面的 `[mcp_servers.stata-mcp]` 段落
4. 执行 `codex mcp list` — 应该能看到 `stata-mcp` 已注册
5. 改完配置后重启 Codex（CLI 或 IDE）
6. 查看扩展输出面板（查看 → 输出 → *Stata*）有无服务端错误
7. 确认没有端口冲突（默认 4000 — 可通过 `stata-vscode.mcpServerPort` 改）

<details>
<summary>被困在 Codex &lt; 0.46.0？</summary>

无法升级时，可以用 [`mcp-proxy`](https://github.com/modelcontextprotocol/mcp-proxy) 作为 stdio 包装器：

```bash
# 如果没装 uv：
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# Windows：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```toml
[mcp_servers.stata-mcp]
command = "uvx"
args = ["mcp-proxy", "http://localhost:4000/mcp"]
```

</details>

<br>

</details>
<details>
<summary><strong>Cline</strong></summary>

1. 打开您的 [Cline](https://github.com/cline/cline) MCP 设置文件：
   - **macOS**：`~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Windows**：`%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Linux**：`~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

2. 添加 Stata MCP 服务器配置：
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "url": "http://localhost:4000/mcp-streamable"
       }
     }
   }
   ```

   Cline 会根据 URL 自动识别传输类型 — 不需要 `transport` 字段。如果确实需要 SSE，把 URL 改成 `http://localhost:4000/mcp` 即可。

3. 如果文件已包含其他 MCP 服务器，只需将 `"stata-mcp"` 条目添加到现有的 `"mcpServers"` 对象中。

4. 保存文件并重启 VS Code。

您还可以通过 VS Code 设置配置 Cline：
```json
"cline.mcpSettings": {
  "stata-mcp": {
    "url": "http://localhost:4000/mcp-streamable"
  }
}
```

### Cline 配置故障排除

如果 Cline 无法识别 Stata MCP 服务器：
1. 验证 MCP 服务器正在运行（状态栏应显示"Stata"）
2. 检查配置文件是否存在且内容正确
3. 尝试重启 VS Code
4. 检查扩展输出面板（查看 > 输出 > Stata MCP）是否有任何错误

<br>

</details>
<details>
<summary><strong>Cursor</strong></summary>

该扩展自动配置 [Cursor](https://www.cursor.com/) MCP 集成。要验证其是否正常工作：

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
         "url": "http://localhost:4000/mcp-streamable"
       }
     }
   }
   ```

   Cursor 会根据 URL 自动识别传输类型 — 不需要 `transport` 字段。它会先尝试 Streamable HTTP，服务器支持的话回退到 SSE。

3. 如果文件已包含其他 MCP 服务器，只需将 `"stata-mcp"` 条目添加到现有的 `"mcpServers"` 对象中。

4. 保存文件并重启 Cursor。

### Cursor 配置故障排除

如果 Cursor 无法识别 Stata MCP 服务器：
1. 验证 MCP 服务器正在运行
2. 检查配置文件是否存在且内容正确
3. 尝试重启 Cursor
4. 确保与其他正在运行的应用程序没有端口冲突

<br>

</details>
<details>
<summary><strong>Python 环境管理</strong></summary>

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
2. 按照[故障排除指南中的干净重装步骤](docs/troubleshooting.zh-CN.md)重新安装扩展。

<br>

</details>

## 故障排除

遇到问题？完整的故障排除指南 —— Windows / macOS / Linux 的干净重装步骤、常见的 Python 和 UV 问题、Stata 版本不匹配、以及提交 GitHub issue 时需要附上的信息 —— 请见 [docs/troubleshooting.zh-CN.md](docs/troubleshooting.zh-CN.md)。

## Star 历史

[![Star 历史图表](https://api.star-history.com/svg?repos=hanlulong/stata-mcp&type=Date)](https://star-history.com/#hanlulong/stata-mcp&Date)

## 许可证

MIT

## 致谢

由 Lu Han 创建，
由 [OpenEcon.ai](https://openecon.ai/) 发布
