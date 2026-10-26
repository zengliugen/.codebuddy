---
name: csharp-code-review
description: C# 代码审查入口技能。当用户要求审查 C# 代码（未提交变更、.cs 文件、目录/程序集、代码片段）时触发。本技能只负责识别触发场景并调度 csharp-code-review Agent，不执行实际审查逻辑。审查入口规则（.codebuddy/lib/csharp/rules/csharp-code-review/RULE.mdc）始终生效，负责路由到本技能；子规则（质量/注释/Bug/架构/报告）由 Agent 按需加载，不全局生效。调用时直接将用户指定的目标路径或代码片段传递给 Agent，无需预扫描或预分析。
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

## 审查模式速查
Agent 依据输入类型选择四种审查模式之一（完整流程见 `../../agents/csharp-code-review.md`）：

| 模式 | 触发条件 | 输入获取方式 |
|------|---------|-------------|
| 模式 A — Git 变更 | 用户要求"审查未提交的变更/本次改动/diff" | `git diff` / `git status` 获取变更文件与内容 |
| 模式 B — 单个文件 | 用户指定 `.cs` 文件路径 | 读取目标文件 |
| 模式 C — 目录/程序集 | 用户指定目录或程序集 | Glob 收集目录下 `.cs` 文件，逐个审查 |
| 模式 D — 代码片段 | 用户粘贴代码 | 直接审查对话中的片段 |

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 本技能的唯一职责
- 触发场景
- 工作流程
- 报告产物与保留策略
- 辅助脚本
- 检查清单
- 参考

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 2 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 3 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
