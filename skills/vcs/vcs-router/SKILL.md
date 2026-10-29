---
name: vcs-router
description: 版本控制操作统一入口（路由技能）。当用户要求提交代码（"提交代码"、"提交一下"、"帮我 commit"、"git commit"、"svn commit" 等）或执行其他版本控制操作（如合并 "git merge"、"svn merge"）时触发，识别操作类型（commit/merge 等）并检测当前目录是 Git 仓库还是 SVN 工作副本，路由到对应的 vcs-<vcs>-<op> 执行技能（两个 commit 已实现 / 两个 merge 当前为占位空实现）。仅负责识别与路由，不执行实际操作，也不承载操作规范。不支持 amend、rebase、cherry-pick、revert、stash、分支与标签、svn update/revert/switch 等非路由类操作。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "2.2"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，需通过触发评估和输出风险检查。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 识别操作类型（commit/merge 等）与当前目录的版本控制类型（Git / SVN / 都不是），将请求路由到对应的 `vcs-<vcs>-<op>` 技能 |
| 输出 | 路由结果（版本控制类型 + 操作类型 + 目标技能 + 目标是否存在），不产生实际操作 |
| 排除 | 实际执行操作、操作摘要生成、安全授权、代码审查（由目标技能承担） |
| 前提 | 目标技能存在且可路由：`vcs-git-commit` / `vcs-svn-commit`（已实现）、`vcs-git-merge` / `vcs-svn-merge`（占位空实现） |

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 通用基础技能说明
- 路由规则
- VCS 写操作互斥锁（多会话防冲突）
- 排除边界
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 2 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 4 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 6 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
