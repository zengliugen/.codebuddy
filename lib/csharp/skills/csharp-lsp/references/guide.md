# 详细流程与规则



本文件由 `SKILL.md` 拆分而来，承载完整执行细节；主文件只保留触发、契约与流程骨架。



## 2. LSP 操作使用指南
LSP 工具为按需加载工具（deferred tool），调用前先通过 `ToolSearch` 加载 `LSP` 工具。

| 场景 | 操作 | 说明 |
|------|------|------|
| 理解类/方法/属性定义 | `goToDefinition` | 从使用处跳转到定义处 |
| 修改符号前了解调用范围 | `findReferences` | 查看符号被引用的位置 |
| 查询类型信息与文档 | `hover` | 悬停获取类型签名 |
| 查看接口/抽象方法实现 | `goToImplementation` | 找实现类 |
| 了解文件内结构 | `documentSymbol` | 列出文件内所有符号 |
| 全局符号检索 | `workspaceSymbol` | 跨文件搜索符号 |
| 查看调用链节点 | `prepareCallHierarchy` | 获取指定位置的调用层级节点 |
| 谁调用了该函数 | `incomingCalls` | 向上追踪调用者 |
| 该函数调用了谁 | `outgoingCalls` | 向下追踪被调用者 |

**参数约定**：`filePath` 为绝对路径；`line` 与 `character` 均为 1-based（与编辑器显示一致）。所有操作（含无位置概念的 `documentSymbol`、`workspaceSymbol`）都必须传 `line` 与 `character`，无实际位置时可传 `1`。

## 4. 故障排查速查
| 症状 | 原因 | 处理 |
|------|------|------|
| `Executable not found in $PATH` | csharp-ls 未安装 | 重跑环境检查，执行安装命令 |
| `No LSP server configured for file type: .cs` | 插件未加载/未启用 | 检查 enabledPlugins 后重启 CodeBuddy Code |
| LSP 操作超时 | csharp-ls 首次索引大工程 | 稍后重试；csharp-ls 冷启动后索引即驻留 |
