# csharp-comment-generator 触发评估用例集

本文件定义 `csharp-comment-generator` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与职责边界。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | 为 `MyClass.cs` 添加注释 | 模式 A（全量） |
| ST-02 | 检查 `MyLogic.cs` 的注释是否符合项目规范 | 模式 A（检查修正） |
| ST-03 | 按照项目注释规范补全 `MyManager.cs` 缺失的注释 | 模式 A（补全） |
| ST-04 | 修正 `MyDataConfig.cs` 已有注释中的质量问题 | 模式 A（修正） |
| ST-05 | 根据 `check_logs/xxx.json` 报告修复 MyClass.cs 的注释问题 | 模式 B（报告驱动） |
| ST-06 | 先用 checker 检查一遍，再根据报告修复所有问题 | 模式 B（强制链路） |
| ST-07 | 这个文件里的英文注释改成中文 | 模式 A（非中文修正） |
| ST-08 | 为 `MyClass.cs` 中 `SwitchState` 方法相关的代码添加注释 | 模式 A（部分处理） |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 检查 MyClass.cs 的注释是否合规（只要报告） | `csharp-comment-checker`（仅检查） |
| SN-02 | 扫描 MyModule 目录注释合规性 | `csharp-comment-checker` |
| SN-03 | 为 utils.ts 添加注释 | 不触发（非 .cs） |
| SN-04 | 帮我重写这个类的逻辑 | 通用 Agent（代码逻辑） |
| SN-05 | 审查这次未提交的变更 | `csharp-code-review` |
| SN-06 | 写一个登录界面 | 通用功能开发 |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但需要正确分流的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | 检查并修正这个文件的注释 | 可能误入 checker | 先 checker（检查）→ 本技能（修正）→ checker（验证），走强制链路 |
| NN-02 | 为这个 C# 文件补注释，不用先检查 | 可能跳过检查 | 可走 generator（添加）→ checker（验证），但验证环节不可省略 |
| NN-03 | 这段代码注释好像有问题 | 语义模糊 | 若仅咨询 → checker 检查；若要求修正 → 链路执行 |
| NN-04 | 帮我加注释顺便看下代码逻辑有没有问题 | 混入审查 | 注释走本技能，逻辑审查走 `csharp-code-review`，按优先级拆分 |

## 判定标准

- **召回率**：`ST-01` 至 `ST-08` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-06` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-04` 能正确分流，不跳过强制链路环节。
