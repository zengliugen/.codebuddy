---
name: vcs-git-merge
description: Git 合并占位技能（空实现）。当用户要求合并 Git 分支（"git merge"、"合并分支"、"把 XX 合到 main"，或由 vcs-router 技能路由）时触发。当前未实现 git merge 流程，本技能仅返回提示，不执行任何 git 操作。不支持 git rebase、git cherry-pick 等非 merge 操作。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式

`Production` —— 团队复用技能。当前为**空实现占位**，未实现 Git 合并流程，不承载任何合并逻辑。

## 与 vcs-router 的关系

`vcs-router` 是版本控制操作的统一入口，识别到 `merge` 操作且当前目录为 Git 仓库时，会路由到本技能（路由逻辑保持不变）。本技能作为 Git 合并路由目标的**占位实现**存在，仅用于保证路由链路完整，不执行实际合并。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | 无。当前为空实现，不执行任何 Git 合并流程 |
| 输出 | 一条固定提示：当前未实现 git merge 流程 |
| 排除 | 所有 `git merge` / `git rebase` / `git cherry-pick` / `git revert` / `git stash` / 分支操作等 |
| 操作规范 | 入口与强制路由见 `.codebuddy/rules/vcs/vcs-router/RULE.mdc`；Git 合并占位说明见同目录子规则 `git-merge-spec.mdc` |

## 行为定义

当 vcs-router 路由到本技能，或用户直接要求合并 Git 分支时：

1. **不执行**任何 Git 命令（不执行 `git merge`、`git diff`、`git status` 等）。
2. **不触发**代码审查、安全检查等任何前置流程。
3. 仅向用户返回提示：

   > 当前未实现 git merge 流程，git-merge 技能为空实现占位。如需合并分支，可手动执行 `git merge <分支>`，或联系配置维护者启用该操作。

## 检查清单

- [ ] 是否已确认本技能当前为空实现，未执行任何 Git 命令？
- [ ] 是否仅返回固定提示，未越权执行合并或任何前置流程？

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 占位说明与契约细节 | 1 |
| `evals/` | 触发评估用例与语义配置 | 2 |
| `reports/` | 质量与风险评估报告（信任报告等） | 2 |
| `agents/` | 接口契约 | 1 |
