# vcs-router 触发评估用例集

本文件定义 `vcs-router` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与 `agents/interface.yaml` 的契约。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能（路由后再转到 `<vcs>-<op>`）。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | 提交代码 | 识别 commit → 检测 Git 仓库 → 路由 git-commit |
| ST-02 | 提交一下 | 同上 |
| ST-03 | 帮我 commit | 同上 |
| ST-04 | git commit | 用户指定 Git → 路由 git-commit |
| ST-05 | 提交到 git | 路由 git-commit |
| ST-06 | 合并分支 | 识别 merge → 检测 Git 仓库 → 路由 git-merge（占位） |
| ST-07 | git merge | 识别 merge → 路由 git-merge（占位） |
| ST-08 | 把 dev 合到 main | 识别 merge → 路由 git-merge（占位） |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 审查这次未提交的变更 | `csharp-code-review` |
| SN-02 | 为 GameLoader.cs 补注释 | `csharp-comment-generator` |
| SN-03 | 提交表单/提交报告 | 不触发（非版本控制上下文） |
| SN-04 | 编译这个项目 | `unity-pipeline` |
| SN-05 | 帮我跳转到某方法定义 | `csharp-lsp` |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但应正确分流的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | git rebase dev | 可能是 commit/merge | 不触发（rebase 被排除） |
| NN-02 | 回滚刚才的提交 | 可能是提交 | 不触发（revert/stash 被排除） |
| NN-03 | 提交代码并推送 | 可能一并推送 | 提交路由到 git-commit，推送强制分离需单独指令 |
| NN-04 | 检查当前目录是什么版本控制 | 可能是通用咨询 | 本技能可检测 VCS 类型（检测是路由的一部分），但若用户只要答案无操作，直接告知即可 |

## 判定标准

- **召回率**：`ST-01` 至 `ST-08` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-05` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-04` 正确分流，不越权执行非路由操作。
