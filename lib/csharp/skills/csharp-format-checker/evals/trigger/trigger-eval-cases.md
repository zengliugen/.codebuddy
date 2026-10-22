# csharp-format-checker 触发评估用例集

本文件定义 `csharp-format-checker` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与 `agents/interface.yaml` 的契约。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能，按 dotnet format + .editorconfig 检查/修复 C# 格式。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | 检查一下代码格式 | check 模式全量检查 |
| ST-02 | 帮我检查 Assets/Battle 下的代码格式 | check 模式 + `--path Assets/Battle` |
| ST-03 | 跑一下 dotnet format 看看有没有格式问题 | check 模式 |
| ST-04 | 看看 Game.csproj 的代码风格是否符合规范 | check 模式 + `--project Game.csproj` |
| ST-05 | 把代码格式化一下 | fix 模式（先确认范围后落盘） |
| ST-06 | 提交前帮我做一次格式检查 | check 模式（配合提交流程） |
| ST-07 | 检查格式时忽略三方插件的改动 | 依赖 `csharp-format-checker/config.json` 的 `exclude_dirs`，默认已忽略 |
| ST-08 | 把代码风格问题全部直接改掉 | fix 模式（触发后须先 AskUserQuestion 确认范围与影响再落盘） |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外，应路由到其他技能或直接回复。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 检查这些文件的注释是否符合规范 | `csharp-comment-checker` |
| SN-02 | 为注释质量差的代码补注释 | `csharp-comment-generator` |
| SN-03 | 审查这次未提交的变更 | `csharp-code-review` |
| SN-04 | 编译并跑一遍测试 | `unity-pipeline` |
| SN-05 | 把这个 Lua 脚本格式化 | 不触发（非 C# 格式范围） |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但**不应触发**（防止误路由）。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | 格式化我的 .md 文档 | 可能是代码格式 | 不触发（非 C# 文件） |
| NN-02 | 用 dotnet format 把 Assets/Plugins 也格式化 | 可能覆盖忽略目录 | 不触发（忽略目录不检查不修改，需先改配置） |
| NN-03 | 注释缩进不对，帮我修一下 | 可能当成格式问题 | 不触发（注释规范 → `csharp-comment-checker`） |

> 说明：涉及注释内容（缺失/语言/缩进引发的注释问题）统一归注释规范检查（`csharp-comment-checker`），本技能只处理 `.editorconfig` 格式规则；明确要求修改源码的修复请求（如 NN-04 原例"把代码风格问题全部直接改掉"）属于本技能的 fix 场景，已列入 ST-08（触发后须先经 AskUserQuestion 确认）。

## 判定标准

- **召回率**：`ST-01` 至 `ST-08` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-05` 与 `NN-01` 至 `NN-03` 均不路由到本技能。
- **边界安全**：修复类请求（ST-08）触发后必须先经 AskUserQuestion 确认，不越权直接落盘。
