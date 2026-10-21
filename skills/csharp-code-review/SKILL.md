---
name: csharp-code-review
description: C# 代码审查入口技能。当用户要求审查 C# 代码（未提交变更、.cs 文件、目录/程序集、代码片段）时触发。本技能只负责识别触发场景并调度 csharp-code-review Agent，不执行实际审查逻辑。审查入口规则（.codebuddy/rules/csharp-code/RULE.mdc）始终生效，负责路由到本技能；子规则（质量/注释/Bug/架构/报告）由 Agent 按需加载，不全局生效。调用时直接将用户指定的目标路径或代码片段传递给 Agent，无需预扫描或预分析。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.1"
---

## 运行模式

`Production` —— 团队复用技能，入口轻量，审查逻辑全部委托给 `csharp-code-review` Agent。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | C# 代码审查的触发识别与 Agent 调度 |
| 输出 | 审查报告文件（`check_logs/*.md`）+ 对话内审查摘要 |
| 排除 | 非 C# 代码审查、代码修改（仅用户明确要求才由 Agent 进入修复模式） |

## 本技能的唯一职责

**本技能只负责两件事：**

1. **触发识别**：判断用户请求是否属于 C# 代码审查（五维：质量规范 / 注释合规 / 格式合规 / Bug 边界 / 架构性能）。
2. **调度 Agent**：将用户的目标路径或代码片段原样传递给 `csharp-code-review` Agent 执行审查。

**禁止行为：**

- 禁止在本技能内直接执行审查逻辑（读取规则、分析代码、运行工具）。
- 禁止预扫描目录、预分析文件列表、筛选哪些文件该审查。
- 禁止预判审查结果。

## 触发场景

当用户出现以下意图时触发：

| 意图 | 示例 |
|------|------|
| 审查 Git 变更 | "审查这次未提交的变更"、"review 下今天的改动" |
| 审查单个文件 | "审查 MyClass.cs"、"检查 MyClass.cs 有没有问题" |
| 审查目录/程序集 | "审查 MyModule 程序集"、"扫描 MyModule 包代码质量" |
| 审查代码片段 | "帮我看下这段代码"（附代码） |
| 修复审查问题 | "把审查报告的 error 都修掉"（Agent 进入修复模式） |

不触发：纯功能开发、纯注释生成/修正（走 `csharp-comment-generator`）、非 C# 语言。

## 审查模式速查

Agent 依据输入类型选择四种审查模式之一（完整流程见 `agents/csharp-code-review/csharp-code-review.md`）：

| 模式 | 触发条件 | 输入获取方式 |
|------|---------|-------------|
| 模式 A — Git 变更 | 用户要求"审查未提交的变更/本次改动/diff" | `git diff` / `git status` 获取变更文件与内容 |
| 模式 B — 单个文件 | 用户指定 `.cs` 文件路径 | 读取目标文件 |
| 模式 C — 目录/程序集 | 用户指定目录或程序集 | Glob 收集目录下 `.cs` 文件，逐个审查 |
| 模式 D — 代码片段 | 用户粘贴代码 | 直接审查对话中的片段 |

## 工作流程

### 阶段一：识别触发

- 判断用户请求是否命中上述触发场景。
- 确认目标为 C# 代码（`.cs` 文件、含 C# 的目录、粘贴的 C# 片段、C# 变更）。
- 若用户同时要求"审查并修复"，仍正常触发，由 Agent 在报告后按修复模式处理。

### 阶段二：调度 Agent

- 将用户的**目标路径或代码片段**原样传递给 `csharp-code-review` Agent。
- 不附加任何预分析结论，不修改用户的请求内容。

### 阶段三：确认输出

- 审查由 Agent 完成，报告写入 `.codebuddy.project/caches/skills/csharp-code-review/check_logs/`。
- 对话展示由 Agent 输出的审查摘要。
- 若 Agent 未正常输出，按 Agent 返回的说明跟进。

## 报告产物与保留策略

- 审查报告写入 `.codebuddy.project/caches/skills/csharp-code-review/check_logs/`（`.md`，已 git 忽略）。
- **保留策略**：提交前门禁每次提交都会生成 1 份报告，`check_logs/` 会持续累积。建议仅保留最近
  **30 次**或关键节点报告（如提交门禁、修复前后对比），其余删除或归档；该目录已被 `.gitignore`
  忽略，清理不影响版本控制与迁移包。批量清理可执行 `.codebuddy.project/cleanup-caches.cmd`。

## 辅助脚本

| 脚本 | 用途 |
|------|------|
| `scripts/collect_review_targets.py` | 收集本次门禁审查目标：`git status` 中的 M/A/R/C/U 变更 + **未跟踪的 `.cs` 新文件**（`git diff` 看不到），并按**技能内 `config.json` 的 `exclude_patterns`**（项目配置，当前含生成代码目录、三方库、审查范围外目录）排除；供门禁派发提示词直接使用。默认排除清单与 `csharp-format-checker/config.json` 的 `exclude_dirs` 保持同一口径，新增排除项须同步更新 |

```bash
python .codebuddy/skills/csharp-code-review/scripts/collect_review_targets.py [--json]
```

## 检查清单

- [ ] 是否属于 C# 代码审查触发场景？
- [ ] 目标是否为 C# 代码（或含 C# 的变更/目录）？
- [ ] 是否已将目标路径/代码片段原样传递给 Agent？
- [ ] 是否未在本技能内执行审查逻辑？
- [ ] 子规则是否由 Agent 按需读取（不全局生效），入口规则始终生效？

## 参考

| 文件 | 内容 |
|------|------|
| `agents/interface.yaml` | 输入/输出/排除契约 |
| `.codebuddy/rules/csharp-code/RULE.mdc` | 审查规则入口（始终生效，负责路由到本技能；子规则由 Agent 读取） |
| `.codebuddy/agents/csharp-code-review/csharp-code-review.md` | 审查 Agent 定义 |
