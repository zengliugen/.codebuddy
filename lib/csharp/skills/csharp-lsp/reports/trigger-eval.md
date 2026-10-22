# csharp-lsp 触发评估记录（v1.2）

- **技能**：`csharp-lsp`（评估基线 v1.2，与当前包一致）
- **评估时间**：2026-09-04
- **评估方式**：静态判定（基于 `SKILL.md` frontmatter `description` 与 `agents/interface.yaml` `activation.triggers` 逐条比对）
- **评估集**：`evals/trigger-eval-cases.md`（应触发 10 条 / 不应触发 6 条 / 相近邻居 6 条）

> **版本说明**：本次为 v1.2 基线重跑，取代 2026-08-18 基于 v1.0 的旧记录（旧版已随 `incomingCalls`/`outgoingCalls` 触发词与 RULE 分流原则落地而失效）。本记录与当前包一致；后续 description / interface 再变更时应重跑并更新本文件。

## 一、召回率评估（应触发 10 条）

| 编号 | 命中依据 | 判定 |
|------|---------|------|
| ST-01 | description 场景覆盖"跳转定义" + 工具清单含 `goToDefinition` | 应触发 |
| ST-02 | description 场景覆盖"查找引用" + 工具清单含 `findReferences` | 应触发 |
| ST-03 | description 场景覆盖"悬停类型信息" + 工具清单含 `hover` | 应触发 |
| ST-04 | description 场景覆盖"查看接口实现" + 工具清单含 `goToImplementation` | 应触发 |
| ST-05 | description 场景覆盖"获取文件/工作区符号结构" + 工具清单含 `documentSymbol` | 应触发 |
| ST-06 | description 场景覆盖"工作区符号结构" + 工具清单含 `workspaceSymbol` | 应触发 |
| ST-07 | description 工具清单含 `incomingCalls`、"查看函数调用链/调用层级" + interface trigger `(查找|查|搜索|看看).*(引用|调用|被谁)` 覆盖"被谁调用" | 应触发 |
| ST-08 | description "查看函数调用链/调用层级" + interface trigger `(调用链|调用层级|调用树)` 覆盖 | 应触发 |
| ST-09 | description 覆盖"诊断 csharp-lsp 插件是否生效"、"询问 csharp-lsp 是否可用" + trigger `csharp-lsp.*(检查|生效|可用|不可用)` | 应触发 |
| ST-10 | description 显式覆盖报错场景 `编辑 C# 报错"LSP 不可用"` + trigger `LSP.*(不可用|报错|错误|失效)` | 应触发 |

**召回率：10/10 通过。** `incomingCalls`/`outgoingCalls` 已由工具清单、场景短语与正则 trigger 三层覆盖，不再依赖语义联想。

## 二、精确率评估（不应触发 6 条）

| 编号 | 边界判定依据 | 判定 |
|------|------------|------|
| SN-01 | 审查类任务：description 仅限代码智能查询，`boundary.exclusions` 明示"不替代 csharp-code" | 不触发 |
| SN-02 | 注释类任务：`exclusions` 明示"不替代 csharp-comment" | 不触发 |
| SN-03 | 编译校验任务：`exclusions` 明示"不检查 Unity 编译错误（由 unity-pipeline 的 recompile 负责）" | 不触发 |
| SN-04 | 提交任务：由 `vcs-router` 统一入口路由，description 无 commit 语义 | 不触发 |
| SN-05 | 纯字符串检索：RULE.mdc「查询方式分流原则」+ SKILL.md 调用约定"纯字符串检索直接 Grep" | 不触发 |
| SN-06 | 代码生成任务：与 LSP 代码智能无关，归属 luban | 不触发 |

**精确率：6/6 通过。** `SN-05` 依赖分流原则约束——该原则已落地于 RULE.mdc 与 SKILL.md，需保证两处不被删改。

## 三、边界安全评估（相近邻居 6 条）

| 编号 | 误路由风险 | 修复后 | 说明 |
|------|-----------|--------|------|
| NN-01 | 注释检查 → 误入本技能 | 低 | `exclusions` 明示不替代 csharp-comment-checker |
| NN-02 | 性能审查 → 误入 hover | 低 | 审查归 csharp-code-review |
| NN-03 | 统计搜索 → 误入 workspaceSymbol | 低 | 分流原则：统计类检索直接 Grep |
| NN-04 | 设计问答 → 误入类型查询 | 低 | description 无设计讨论语义 |
| NN-05 | 重构 → 误触发调用链 | 中 | description/interface 确含"调用链"关键词，存在词面命中风险；重构主路由应为 csharp-code-review，本技能仅作调用点定位辅助，需人工确认 |
| NN-06 | 文档链接 → 误入 goToDefinition | 低 | 无代码定位语义 |

**边界安全：无明显阻塞项。** `NN-05` 保留为"辅助工具"定位，属合理混用场景，不视为误路由；若后续出现实际误路由反馈，需评估将"重构+调用链"组合场景显式收窄。

## 四、结论

| 指标 | 结果 |
|------|------|
| 召回率 | 10/10 |
| 精确率 | 6/6 |
| 边界安全 | 通过（1 项合理混用） |
| 阻塞项 | 无 |
| 基线状态 | v1.2，与当前包一致 |

**说明**：本次评估为静态判定，未执行模型级 A/B 验证。若需更强的发布证据，可接入 `scripts/yao.py output-exec` 运行输出评估（需配置 provider-runner），本报告不包含该证据，标记为 `missing evidence`。

## 五、评估历史与维护约定

| 日期 | 基线 | 结果 | 备注 |
|------|------|------|------|
| 2026-08-18 | v1.0 | 召回 10/10、精确 6/6 | 首次评估；ST-07/08 当时依赖修复新增触发词，SN-05 依赖 RULE 分流原则落地 |
| 2026-09-04 | v1.2 | 召回 10/10、精确 6/6 | 基线重跑，证据与当前包一致 |

**维护约定**：此后凡修改 `SKILL.md` `description` 或 `agents/interface.yaml` `activation.triggers`，须同步重跑本评估并更新本记录；评估集用例增删须同步 `evals/trigger-eval-cases.md`。
