# Stata MCP 扩展 v0.2.5

## 新功能

- **归档文件夹管理**：通过从版本控制中移除归档文件夹来改进仓库组织
- **增强日志记录**：更好的日志文件管理和调试功能
- **性能改进**：优化的扩展启动和服务器通信
- **错误修复**：各种稳定性改进和问题解决方案
- **文档更新**：改进的 README 和配置指导

## 之前的版本

### v0.2.4
- **Stata 版本选择**：用户现在可以通过 `stata-vscode.stataEdition` 设置在 Stata MP、SE 和 BE 版本之间进行选择
- **增强用户控制**：为安装了多个 Stata 版本的环境提供更多灵活性
- **改进文档**：添加了版本特定配置和故障排除的指导
- **更好的用户体验**：简化了具有特定 Stata 版本要求的用户的工作流程

## 安装

下载最新版本的发布包 (`stata-mcp-0.2.5.vsix`) 并通过以下方式安装：

```bash
code --install-extension path/to/stata-mcp-0.2.5.vsix
```

或通过 VS Code 的扩展视图 > ... 菜单 > "从 VSIX 安装..."

对于 Cursor：
```bash
cursor --install-extension path/to/stata-mcp-0.2.5.vsix
```

## 文档

完整文档可在 [README.md](https://github.com/hanlulong/stata-mcp/blob/main/README.md) 文件中找到。