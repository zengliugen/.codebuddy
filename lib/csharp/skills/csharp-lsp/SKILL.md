---
name: csharp-lsp
description: C# 语言服务器（csharp-ls）环境检查与 LSP 代码智能调用技能。先执行环境检查（确认 csharp-ls 语言服务器已安装、csharp-lsp@codebuddy-plugins-official 插件已启用），再调用 LSP 工具（goToDefinition / findReferences / hover / goToImplementation / documentSymbol / workspaceSymbol / prepareCallHierarchy / incomingCalls / outgoingCalls）获取 C# 代码智能。使用场景：操作或引用 .cs 文件时，需要跳转定义、查找引用、悬停类型信息、查看接口实现、获取文件/工作区符号结构、查看函数调用链/调用层级；或需要诊断 csharp-lsp 插件是否生效。当用户询问 csharp-lsp 是否可用、编辑 C# 报错"LSP 不可用"、或要求检查 C# 代码智能环境时，应主动调用本技能。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.2"
---

# C# LSP（csharp-lsp）技能

本技能封装 `csharp-lsp@codebuddy-plugins-official` 插件的完整使用流程。触发约束见规则
`.codebuddy/rules/csharp/csharp-lsp/RULE.mdc`（按需加载，操作 `.cs` 文件时注入）。

## 1. 环境检查（使用前执行，含本地缓存）

处理 C# 代码前，先运行环境检查脚本，确认语言服务器与插件均就绪：

```bash
python .codebuddy/skills/csharp/csharp-lsp/scripts/check_env.py --project .
```

> **本地缓存机制**：检查全部通过后，脚本会将结果连同环境指纹写入
> 项目侧 `.codebuddy.project/caches/skills/csharp-lsp/.cache/` 下的缓存文件（按项目隔离，已 git 忽略）。
> 在 **24 小时有效期**内且环境指纹（csharp-ls 可执行文件路径/修改时间、
> 插件安装清单修改时间与版本、三处 settings.json 修改时间/大小）未变化时，
> 脚本直接复用上次通过结论，跳过重复检查，并提示"缓存命中"。
> 装/卸插件、修改 settings.json、升级 csharp-ls 等任何环境变化都会使指纹失效自动重查；
> **失败结果不缓存**，修复后重跑即立即重查。如需强制重查，加 `--no-cache`：
>
> ```bash
> python .codebuddy/skills/csharp/csharp-lsp/scripts/check_env.py --project . --no-cache
> ```

脚本检查三个维度并输出中文结论（退出码 0 表示就绪）：

| 检查项 | 判定依据 | 失败时的修复指引 |
|--------|---------|------------------|
| **csharp-ls 安装检查** | `csharp-ls` 是否在 PATH（或 dotnet 全局工具列表） | `dotnet tool install --global csharp-ls`（需 .NET SDK 6.0+），安装后重启 CodeBuddy Code |
| **插件安装检查** | `~/.codebuddy/plugins/installed_plugins.json` 中 `csharp-lsp@codebuddy-plugins-official` 存在记录 | 执行 `/plugin install csharp-lsp@codebuddy-plugins-official` |
| **插件开启检查** | 项目/用户 `settings.json` 的 `enabledPlugins` 中插件值为 `true` | 编辑 `.codebuddy/settings.json`，添加 `"enabledPlugins": { "csharp-lsp@codebuddy-plugins-official": true }`，重启 |
| 插件加载验证（提示级） | 插件缓存目录 `.in_use/` 存在进程标记 | 上述通过但无标记时重启 CodeBuddy Code |

### 1.1 动态验证（环境检查通过后）

环境检查只是静态确认，最终以 LSP 工具实测为准。对任一 `.cs` 文件调用一次
`documentSymbol`（`line`/`character` 可传 `1`），若返回符号信息则插件真实生效；若返回 `No LSP server configured for file
type: .cs`，则插件未加载，需重启 CodeBuddy Code 后重试。

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

## 3. 调用约定

- **语义查询优先 LSP + 交叉验证**：定位符号定义、引用关系、接口实现等语义查询，优先调用 LSP 操作；LSP 返回空结果时**必须**再用 `Grep` 交叉验证，禁止直接采信"无引用"结论（csharp-ls 对部分程序集索引不可靠，实测会出现假阴性；受影响程序集按目标项目实测确认）。
- **已知索引盲区可 Grep 优先**：对已知 LSP 索引不可靠的程序集/区域，可直接 `Grep` 优先，避免白跑 LSP；必要时再以 LSP 补充确认。
- **简单检索直接 Grep**：纯字符串检索（如"某标识符出现在哪些文件"）无需进入本技能，直接使用 `Grep`，避免完整 LSP 链路开销。注意 `Grep` 按行去重——同一行多处引用只报 1 行，需改代码时补查同行其余出现位置。
- **搜索范围**：`Grep` 与 LSP 查询必须同时覆盖 `Assets/` 与 `Packages/` 两个目录（如 `grep -rn "符号" Assets Packages --include="*.cs"`），禁止只搜其一；非 `.cs` 文件中的引用（场景、配置）需显式扩展 `--include`。
- **不重复调用**：若上下文已掌握目标符号信息（已读过定义文件），无需额外调用 LSP。
- **失败降级**：LSP 调用失败（工具报错/超时）时，回退 `Grep`/`Read` 继续任务，不阻塞流程。
- **与既有规则的关系**：本技能只负责代码智能查询，不替代 `csharp-code`（审查）、`csharp-comment`（注释）、`unity-pipeline`（编译/测试）。

## 4. 故障排查速查

| 症状 | 原因 | 处理 |
|------|------|------|
| `Executable not found in $PATH` | csharp-ls 未安装 | 重跑环境检查，执行安装命令 |
| `No LSP server configured for file type: .cs` | 插件未加载/未启用 | 检查 enabledPlugins 后重启 CodeBuddy Code |
| LSP 操作超时 | csharp-ls 首次索引大工程 | 稍后重试；csharp-ls 冷启动后索引即驻留 |
