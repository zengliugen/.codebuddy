---
name: git-commit
description: Git 提交执行技能。当用户要求提交 Git 代码（"git commit"、"提交到 git"，或由 vcs-router 技能路由）时触发，分析 Git 变更并生成标准化提交摘要，提交前按项目配置自动触发代码审查门禁（默认 C# 变更，error 级别问题阻塞提交）。不支持 amend、rebase、cherry-pick、revert、stash、merge、分支操作。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.10"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，需通过触发评估和输出风险检查。

## 与 vcs-router 的关系
`vcs-router` 是提交操作的**统一入口**：用户提交请求先由 vcs-router 检测仓库类型并路由，本技能作为 Git 仓库的**提交执行者**。用户显式指定 Git 上下文（如"git commit"）时，本技能也可直接触发。

提交规范入口与强制路由条款定义在 `.codebuddy/rules/vcs/vcs-router/RULE.mdc`（始终生效），详细规范按需加载自同目录子规则：`common-commit-spec.mdc`（提交摘要）、`common-submission-safety-spec.mdc`（授权与安全）、`git-commit-spec.mdc`（Git 特定安全约束）。本技能执行时遵循上述规则，本文件仅保留 Git 特定流程与命令。

**提交前审查门禁不在规则目录**：其**机制**由本技能 `references/project-config.md` §2 承载，**参数**由项目侧配置（经索引 `git_commit.project_config` 定位）承载；作为 §3 H1 暂存前的**首个步骤**执行（见阶段五）。

**项目可配置项（均外置到项目侧 `.codebuddy.project/`，经 `.codebuddy/project.index.json` 定位）**：提交摘要确定性参数（type 枚举、subject/scope 长度、subject 语言）见索引逻辑名 `git_commit.config`；流程级配置（scope 规则、审查门禁参数、钩子步骤取值）见逻辑名 `git_commit.project_config`。目标项目只改项目侧配置，不改本技能与规则文件。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | Git 仓库的 `git commit` 标准化提交流程（变更分析 → 提交计划 → 项目专有钩子 → 安全检查 → 用户授权 → 执行提交） |
| 输出 | 符合 `<type>(<scope>): <subject>` 格式的提交，附带安全检查与代码审查证据 |
| 排除 | `git commit --amend`、`git rebase`、`git cherry-pick`、`git revert`、`git stash`、分支操作、`git merge` |
| 提交规范 | `.codebuddy/rules/vcs/vcs-router/RULE.mdc`（入口+强制路由，始终生效）与同目录子规则（`common-commit-spec`、`common-submission-safety-spec`、`git-commit-spec`，按需加载）；审查门禁机制见本技能 `references/project-config.md` §2（参数见项目侧 `project-config.md`） |

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/commit-spec.md` | 提交摘要详细规范：近似 type 区分规则、subject 正确/错误示例、提交正文、提交信息的传入方式（`-F` 文件传参、`@` 污染成因）、多模块拆分与编排顺序 |
| `references/submission-safety.md` | 安全规范：提交/推送发起权（按项目配置）、授权要求、提交推送分离、敏感信息检查、.gitignore 检查流程 |
| `references/project-config.md` | **引擎侧机制**：§2 审查门禁机制（触发时机/审查对象/派发要素/阻塞规则）、§3 钩子步骤字段语义与执行规则。**项目参数**外置到项目侧（索引 `git_commit.project_config`） |
| 项目侧 `skills/git-commit/config.json` | 提交摘要确定性配置：type 枚举、subject_max_len、scope_max_len、subject_language（索引 `git_commit.config`） |
| `references/vcs-lock.md` | 多会话防冲突：VCS 写操作互斥锁机制、命令用法、暂存区校验，集成到阶段七 |

接口契约定义在 `agents/interface.yaml`，包含输入/输出/排除的完整契约。

---

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 工作流程
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 6 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 2 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 6 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
