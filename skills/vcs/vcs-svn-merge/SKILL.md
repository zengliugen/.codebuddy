---
name: vcs-svn-merge
description: SVN 合并占位技能（空实现）。当用户要求把 SVN 分支/标签合并到工作副本（"svn merge"、"合并分支"、"把分支合到 trunk"，或由 vcs-router 技能路由）时触发。当前未实现 svn merge 流程，本技能仅返回提示，不执行任何 svn 操作。不支持 svn switch、svn relocate、分支与标签创建等非 merge 操作。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式

`Production` —— 团队复用技能。当前为**空实现占位**，未实现 SVN 合并流程，不承载任何合并逻辑。

## 与 vcs-router 的关系

`vcs-router` 是版本控制操作的统一入口，识别到 `merge` 操作且当前目录为 SVN 工作副本时，
会路由到本技能（路由逻辑保持不变）。本技能作为 SVN 合并路由目标的**占位实现**存在，
仅用于保证路由链路完整，不执行实际合并。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | 无。当前为空实现，不执行任何 SVN 合并流程 |
| 输出 | 一条固定提示：当前未实现 svn merge 流程 |
| 排除 | 所有 `svn merge` / `svn switch` / `svn relocate` / `svn update` / 分支与标签操作等 |
| 操作规范 | 入口与强制路由见 `.codebuddy/rules/vcs/vcs-router.entry/`；SVN 合并占位说明见 `rules/vcs/vcs-svn-merge/svn-merge-spec.mdc` |

## 行为定义

当 vcs-router 路由到本技能，或用户直接要求合并 SVN 分支/标签时：

1. **不执行**任何 SVN 命令（不执行 `svn merge`、`svn info`、`svn status` 等）。
2. **不触发**代码审查、安全检查等任何前置流程。
3. 仅向用户返回提示：

   > 当前未实现 svn merge 流程，vcs-svn-merge 技能为空实现占位。如需合并分支，可手动执行
   > `svn merge <源分支 URL> <目标工作副本路径>`，或联系配置维护者启用该操作。

## 检查清单

- [ ] 是否已确认本技能当前为空实现，未执行任何 SVN 命令？
- [ ] 是否仅返回固定提示，未越权执行合并或任何前置流程？

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 占位说明与契约细节 | 1 |
| `evals/` | 触发评估用例与语义配置 | 2 |
| `agents/` | 接口契约 | 1 |
