# 故障排除

如果您遇到 Stata MCP 扩展相关的问题，请按照以下步骤执行干净的重新安装。

← [返回主 README](../README.zh-CN.md)

## Windows

1. 关闭所有 VS Code/Cursor/Antigravity 窗口
2. 打开任务管理器（Ctrl+Shift+Esc）：
   - 转到"进程"标签
   - 查找任何正在运行的 Python 或 `uvicorn` 进程
   - 选择每个进程并点击"结束任务"

3. 删除扩展文件夹：
   - 按 Win+R，输入 `%USERPROFILE%\.vscode\extensions` 并按回车
   - 删除文件夹 `deepecon.stata-mcp-0.x.x`（其中 x.x 是版本号）
   - 对于 Cursor：路径为 `%USERPROFILE%\.cursor\extensions`
   - 对于 Antigravity：路径为 `%USERPROFILE%\.antigravity\extensions`

4. 手动安装 UV（如果需要）：
   ```powershell
   # 以管理员身份打开 PowerShell 并运行：
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

5. 重启计算机（推荐但可选）

6. 从市场安装最新版本的扩展

## macOS/Linux

1. 关闭所有 VS Code/Cursor/Antigravity 窗口

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
   # 对于 Antigravity：
   rm -rf ~/.antigravity/extensions/deepecon.stata-mcp-0.x.x
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

## 额外的故障排除提示

- 如果您看到关于 Python 或 UV 未找到的错误，请确保它们在系统 PATH 中：
  - Windows：在开始菜单中输入"环境变量"并添加安装路径
  - macOS/Linux：将路径添加到您的 `~/.bashrc`、`~/.zshrc` 或等效文件

- 如果您遇到权限错误：
  - Windows：以管理员身份运行您的 IDE
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

## 提交问题

在 GitHub 上打开问题时，请提供：
- 来自输出面板的完整错误消息（查看 -> 输出 -> Stata-MCP）
- 您的操作系统和版本
- VS Code/Cursor/Antigravity 版本
- Python 版本（`python --version`）
- UV 版本（`uv --version`）
- 重现问题的步骤
- 任何相关的日志文件或屏幕截图
- 适用的 MCP 配置文件内容

这些详细信息将帮助我们更快识别并解决问题。您可以在以下位置打开问题：[GitHub Issues](https://github.com/hanlulong/stata-mcp/issues)
