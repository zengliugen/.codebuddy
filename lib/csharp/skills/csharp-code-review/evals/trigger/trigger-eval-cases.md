# csharp-code-review 触发评估用例集

本文件定义 `csharp-code-review` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与 `agents/interface.yaml` 的契约。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | 审查这次未提交的变更 | 模式 A（Git 变更） |
| ST-02 | review 下今天的改动 | 模式 A（Git 变更） |
| ST-03 | 审查 MyClass.cs | 模式 B（单文件） |
| ST-04 | 检查 MyClass.cs 有没有问题 | 模式 B（单文件） |
| ST-05 | 审查 MyModule 程序集 | 模式 C（目录/程序集） |
| ST-06 | 扫描 MyModule 包代码质量 | 模式 C（目录/程序集） |
| ST-07 | 帮我看下这段代码（附 C# 片段） | 模式 D（代码片段） |
| ST-08 | 把审查报告的 error 都修掉 | 修复模式 |
| ST-09 | 审查这次 Git 变更里有哪些隐患 | 模式 A + 侧重 Bug 维度 |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 写一个登录界面 | 通用功能开发 |
| SN-02 | 为 GameLoader.cs 补全注释 | `csharp-comment-generator` |
| SN-03 | 检查这个 .cs 文件的注释是否合规 | `csharp-comment-checker` |
| SN-04 | 帮我跳转到 GameEntrance.Start() 的定义处 | `csharp-lsp` |
| SN-05 | 修改代码后重新编译并检查编译错误 | `unity-pipeline` |
| SN-06 | 把 C# 变更提交到 git | `vcs-router` → `git-commit` |
| SN-07 | 这段 Lua 代码有什么问题 | 非 C#，不触发 |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但不应由本技能直接处理的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | 检查代码风格是否规范（C# 目录） | 本技能（质量/格式维度） | 本技能审查，格式维度复用 `csharp-format-checker`；若用户只想要格式检查，走 `csharp-format-checker` |
| NN-02 | 这段 C# 代码有什么性能问题 | 本技能（架构/性能维度） | 本技能审查，维度过滤为性能 |
| NN-03 | 帮我重构这个方法 | 可能是修复模式 | 重构属开发任务；如需审查重构方案可先审查，再按需修复 |
| NN-04 | 给这段代码加注释同时检查一下 | 注释生成或审查 | 拆分为 generator（注释）+ 本技能（审查），按用户优先级 |
| NN-05 | 帮我看看这段代码（非 C#，如 JSON） | 本技能 | 不触发，非 C# |

## 判定标准

- **召回率**：`ST-01` 至 `ST-09` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-07` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-05` 不误路由，或作为辅助工具参与。
