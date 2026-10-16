# csharp-lsp 触发评估用例集

本文件定义 `csharp-lsp` 技能的触发评估用例，按三桶分类：**应触发**（Should Trigger）、**不应触发**（Should Not Trigger）、**相近邻居**（Near Neighbor）。判定依据为 `SKILL.md` frontmatter 的 `description` 与 `agents/interface.yaml` 的 `activation.triggers`。

## 一、应触发（Should Trigger）

验证召回率：这类请求应路由到本技能。

| 编号 | 用户 Prompt | 期望操作 |
|------|------------|---------|
| ST-01 | 帮我跳转到 `GameEntrance.Start()` 的定义处 | `goToDefinition` |
| ST-02 | 看看 `GameLoader.LoadAll` 在哪些地方被引用 | `findReferences` |
| ST-03 | 悬停看一下 `IGame.InitializeAsync` 的类型签名 | `hover` |
| ST-04 | 找出实现了 `IGameDebugRpcServer` 接口的类 | `goToImplementation` |
| ST-05 | 列出这个 .cs 文件里的所有方法 | `documentSymbol` |
| ST-06 | 在工作区里搜索符号 `BattleController` 定义在哪个文件 | `workspaceSymbol` |
| ST-07 | 查一下 `StateMachine.TrySwitch` 是被谁调用的 | `incomingCalls` |
| ST-08 | 看看 `Tick` 方法内部调用了哪些方法 | `outgoingCalls` |
| ST-09 | csharp-lsp 插件是不是没生效？检查一下环境 | 环境检查 |
| ST-10 | 编辑 C# 时提示"LSP 不可用"怎么解决 | 环境检查 + 故障排查 |

## 二、不应触发（Should Not Trigger）

验证精确率：这类请求明显在技能边界外。

| 编号 | 用户 Prompt | 应路由到 |
|------|------------|---------|
| SN-01 | 审查这次未提交的 C# 变更 | `csharp-code-review` |
| SN-02 | 为 `GameLoader.cs` 补全注释 | `csharp-comment-generator` |
| SN-03 | 修改代码后重新编译并检查编译错误 | `unity-pipeline` |
| SN-04 | 把 C# 变更提交到 git | `vcs-router` → `git-commit` |
| SN-05 | 搜索所有包含字符串 "AssetBundle" 的 .cs 文件 | 直接 `Grep`（简单字符串检索，见分流原则） |
| SN-06 | 生成 Excel 数据表 C# 代码 | `com.code-philosophy.luban` |

## 三、相近邻居（Near Neighbor）

验证边界：看似相似但不应由本技能处理的请求。

| 编号 | 用户 Prompt | 潜在误路由 | 正确路由 |
|------|------------|-----------|---------|
| NN-01 | 检查这个 .cs 文件的注释是否符合规范 | 可能是代码智能查询 | `csharp-comment-checker` |
| NN-02 | 这段 C# 代码有什么性能问题 | 可能是 hover/类型查询 | `csharp-code-review`（架构维度） |
| NN-03 | 搜一下项目里有多少个 MonoBehaviour | 可能是 workspaceSymbol | 直接 `Grep` 统计 |
| NN-04 | 这个接口为什么要这样设计 | 可能是类型查询 | 不触发任何技能，正常对话回答 |
| NN-05 | 帮我重构这个方法，改成调用链更清晰 | 可能触发 incomingCalls | 重构类操作，先 `csharp-code-review` 审查思路；若需定位调用点可辅助本技能 |
| NN-06 | 输出一个跳转定义到 Unity 文档链接 | 可能是 goToDefinition | 不触发技能，直接给出文档链接 |

## 判定标准

- **召回率**：`ST-01` 至 `ST-10` 全部路由到本技能。
- **精确率**：`SN-01` 至 `SN-06` 均不路由到本技能。
- **边界安全**：`NN-01` 至 `NN-06` 不误路由，或仅作为辅助工具参与（`NN-05`）。
