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

脚本检查 csharp-ls 安装、插件安装记录、插件开启状态三个维度，输出中文结论（退出码 0 就绪）。
结果按环境指纹缓存 24 小时（指纹含 csharp-ls 路径/时间、插件清单、settings.json 时间），
环境变化自动失效，**失败不缓存**；强制重查加 `--no-cache`。
各维度判定依据与修复指引见 [references/guide.md](references/guide.md)。

**动态验证**：静态检查通过后，对任一 `.cs` 文件调用一次 `documentSymbol` 实测。
返回符号信息即插件真实生效；返回 `No LSP server configured for file type: .cs` 说明插件未加载，需重启。

## 3. 调用约定
- **语义查询优先 LSP + 交叉验证**：定位符号定义、引用关系、接口实现等语义查询，优先调用 LSP 操作；LSP 返回空结果时**必须**再用 `Grep` 交叉验证，禁止直接采信"无引用"结论（csharp-ls 对部分程序集索引不可靠，实测会出现假阴性；受影响程序集按目标项目实测确认）。
- **已知索引盲区可 Grep 优先**：对已知 LSP 索引不可靠的程序集/区域，可直接 `Grep` 优先，避免白跑 LSP；必要时再以 LSP 补充确认。
- **简单检索直接 Grep**：纯字符串检索（如"某标识符出现在哪些文件"）无需进入本技能，直接使用 `Grep`，避免完整 LSP 链路开销。注意 `Grep` 按行去重——同一行多处引用只报 1 行，需改代码时补查同行其余出现位置。
- **搜索范围**：`Grep` 与 LSP 查询必须同时覆盖 `Assets/` 与 `Packages/` 两个目录（如 `grep -rn "符号" Assets Packages --include="*.cs"`），禁止只搜其一；非 `.cs` 文件中的引用（场景、配置）需显式扩展 `--include`。
- **不重复调用**：若上下文已掌握目标符号信息（已读过定义文件），无需额外调用 LSP。
- **失败降级**：LSP 调用失败（工具报错/超时）时，回退 `Grep`/`Read` 继续任务，不阻塞流程。
- **与既有规则的关系**：本技能只负责代码智能查询，不替代 `csharp-code`（审查）、`csharp-comment`（注释）、`unity-pipeline`（编译/测试）。

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 2 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 3 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
