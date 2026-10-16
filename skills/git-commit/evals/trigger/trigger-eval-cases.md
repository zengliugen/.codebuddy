# git-commit 触发评估用例集

本文件定义 `git-commit` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与 `agents/interface.yaml` 的契约。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | git commit | 提交 Git 变更 |
| ST-02 | 提交到 git | 提交 Git 变更 |
| ST-03 | 提交代码 | 提交 Git 变更（vcs-router 路由后） |
| ST-04 | 帮我 commit 一下 | 提交 Git 变更 |
| ST-05 | /commit | 提交 Git 变更（技能命令入口） |
| ST-06 | 提交这次 C# 变更（含审查门禁） | 提交 + 触发 csharp-code-review |
| ST-07 | 提交代码，跳过审查 | 提交（跳过审查，需确认理由） |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 把 C# 变更合并到 main | `git-merge`（占位） |
| SN-02 | git rebase 到 dev 分支 | 不触发（rebase 被排除） |
| SN-03 | 帮我做分支切换 | 不触发（分支操作被排除） |
| SN-04 | 提交报告表单 | 不触发（非版本控制上下文） |
| SN-05 | 审查这次未提交的变更 | `csharp-code-review` |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但应正确分流的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | svn commit | 本技能 | 不触发（vcs-router 检测非 Git 仓库后终止并提示） |
| NN-02 | 推送到远程 | 本技能 | 提交与推送分离；推送需用户单独指令，非 git-commit 触发场景 |
| NN-03 | 回滚刚才的提交 | 本技能 | `git revert`/`git reset` 被排除，不路由 |
| NN-04 | 提交代码顺便推送 | 本技能 | 触发提交，但推送强制分离，需单独指令 |

## 判定标准

- **召回率**：`ST-01` 至 `ST-07` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-05` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-04` 正确分流，不越权执行非提交操作。
- **审查门禁说明**：审查门禁为项目配置驱动（机制见 `references/project-config.md` §2，参数见项目侧 project-config.md §2），作为 H1 阶段（阶段五）首个步骤执行；默认文件模式 `.cs` + 审查技能 `csharp-code-review`；默认行为下 `ST-06` 判定仍成立。
