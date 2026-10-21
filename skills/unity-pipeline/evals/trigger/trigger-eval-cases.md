# unity-pipeline 触发评估用例集

本文件定义 `unity-pipeline` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description`。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能。

| 编号 | 用户 Prompt | 期望处理 |
|------|------------|---------|
| ST-01 | 打开 Unity 项目 | `unity open` |
| ST-02 | 启动这个 Unity 编辑器 | `unity open` |
| ST-03 | 重新编译并检查编译错误 | script recompile + script recompile_status |
| ST-04 | 运行编辑器测试 | test run（editor） |
| ST-05 | 运行 PlayMode 测试 | test run（playmode，异步轮询） |
| ST-06 | 对这段代码做方法重载 | script.methodreload reload / reload_editor |
| ST-07 | 在 Unity 里求值这段 C# | script eval / script eval_file |
| ST-08 | 保持编辑器存活别让它停 | editor set_auto_tick |
| ST-09 | 列出当前有哪些 Unity 实例 | unity pipeline list |
| ST-10 | 批量创建这些游戏对象并连线字段 | script run（构造器模式）或 job batch（事务化批处理） |
| ST-11 | 等游戏进入结束状态再截图 | job wait（服务端条件等待，同帧 on_met.capture） |
| ST-12 | 看下编辑器控制台有什么报错 | console get / console status |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 审查这次未提交的 C# 变更 | `csharp-code-review` |
| SN-02 | 为 GameLoader.cs 补全注释 | `csharp-comment-generator` |
| SN-03 | 检查这个 .cs 文件的注释是否合规 | `csharp-comment-checker` |
| SN-04 | 把 C# 变更提交到 git | `vcs-router` → `git-commit` |
| SN-05 | 帮我跳转到某方法定义 | `csharp-lsp` |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但应正确分流的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | 修改代码后想验证能不能编译 | 可能是评论/注释 | unity-pipeline script recompile 验证编译（正确） |
| NN-02 | 找一下代码里的性能问题 | 可能是测试 | `csharp-code-review`（架构/性能维度） |
| NN-03 | 测试代码逻辑对不对（不改代码） | 可能是单元测试 | 若指 Unity 测试 → unity-pipeline test run；若指代码审查 → csharp-code-review，需确认语境 |
| NN-04 | 打开 Unity 并自动跑一遍所有测试 | 单一操作 | 本技能：open → editor set_auto_tick → test run（多命令组合） |

## 判定标准

- **召回率**：`ST-01` 至 `ST-12` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-05` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-04` 正确分流，不越权执行非 Unity 操作。
