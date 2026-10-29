# grilling 变更记录

> **本文件由引擎仓库维护，不是上游内容。** 上游原文仅作语义对照，正文以本仓库为准。

本包维护档位：**本地维护分支**（`packs.json` 分类「third-party（本地维护）」；`agents/interface.yaml`
的 `source.origin` 为 `local`、`editable` 为 `full`）。与只读 vendor 不同，**允许本地改造**。

## 记录规范

- 一个变更一节，**按时间倒序**，标题为 `## YYYY-MM-DD 主题`。
- 每节写明**为什么改**，而不只是改了什么——只记措辞调整的不写。
- 纯错别字修订不单独成节，并入当次相关小节或在提交摘要中说明。
- 同类改动若数量或范围发生变化，可另用表格汇总，但细节仍留在对应日期小节。

## 改动前必读

1. 本包是**纯方法论技能**：不产出代码、不写文件、不跑脚本。改动优先级为「调调用方用法」>「改正文」。
2. 正文措辞与其触发评测**强耦合**——改描述或关键词后必须重跑评测，不得为过测而删用例。
3. 本包 `requires` 为空，正文点名其它包组件会触发引擎跨包引用校验；需要举例时用泛化表述。
4. 改完跑 `check_manifest.py` 与 `pack_install.py status`，均须退出码 0。

## 相对上游的本地改动

以下内容**均为本仓库产出，上游没有**：

| 范围 | 改动 |
|---|---|
| 结构调整 | 删除上游的 `grill-me` 转发入口，触发关键词合并至本技能 |
| 正文 | `SKILL.md` 中文化与重写：设计树逐轮诘问方法论、使用边界、技能包结构 |
| 参考文档 | `references/` 新增设计树方法论细则与 CodeBuddy 落地约定 |
| 评测 | `evals/` 补齐语义配置、六组触发用例、回归历史与评测说明 |
| 治理产物 | `reports/` 补齐风险画像、质量记分卡、门禁结果、信任报告、Skill IR |
| 失败案例 | `failures/` 记录十条已知失败，区分「可调参」与「方法性缺陷」 |
| 元数据 | `manifest.json` 治理元数据（production 档）；`interface.yaml` 改 `origin=local`、`editable=full` |

## 评测基线

盲测 `post_freeze` 精确率 0.667、召回 0.400，已作为回归基线落盘。改动触发词或 `description` 后
须重跑并与此基线比对。

## 2026-10-29 文档归位：PATCHES.md 与 references/cli-changelog.md 合并到根目录

| 项 | 内容 |
|---|---|
| 文件 | 新增根目录 `CHANGELOG.md`；删除 `PATCHES.md` 与 `references/cli-changelog.md` |
| 原因 | 同一类信息散在两处、文件名不一致，且不同包的记录文件放法各异（有的在根目录、有的在 `references/`），检索与维护都要先猜位置 |
| 补丁 | 维护档位、改动前必读、改动清单、变更记录合并为单一 `CHANGELOG.md`，置于技能根目录 |
| 边界 | 只搬内容不改语义；引擎 `README.md` 的 vendor 表引用同步更新 |

## 2026-10-23 转为本地维护并中文化

| 项 | 内容 |
|----|------|
| 原因 | 上游正文为英文，与本项目「人类可读文本一律中文」的底线直接冲突；本包不产出需与上游逐字比对的评测快照，语义忠实度可由本地 `evals/` 保障 |
| 结构调整 | 删除上游 `grill-me` 转发入口，触发关键词合并至本技能；同步 `packs.json`、引擎 `README.md` 与 `pack_install` 注释 |
| 正文 | `SKILL.md` 中文化与重写：设计树逐轮诘问方法论、使用边界、技能包结构 |
| 参考文档 | `references/` 新增 `design-tree-method.md`（方法论细则）与 `project-integration.md`（CodeBuddy 落地约定） |
| 评测 | `evals/` 补齐 `semantic_config.json`、六组触发用例（含 blind/final holdout）、回归历史与评测说明 |
| 治理产物 | `reports/` 补齐风险画像、质量记分卡、门禁结果、信任报告、Skill IR |
| 失败案例 | `failures/known-failures.md` 记录十条已知失败，区分「可调参」与「方法性缺陷」 |
| 元数据 | `manifest.json` 治理元数据（production 档，owner zengliugen）；`interface.yaml` 改 `origin=local`、`editable=full` 并加 `maintenance_note` |
| 验证 | validate / trust / conformance / skill-ir / resource_boundary / governance 全部退出码 0；盲测 post_freeze 精确率 0.667、召回 0.400，已作为回归基线 |

## 2026-10-23 提问轮次明确走工具

| 项 | 内容 |
|----|------|
| 文件 | `SKILL.md` |
| 问题 | 原文对「每轮提问必须经工具提交」表述不够明确，易被理解为可输出纯文本问题块 |
| 补丁 | 明确每轮经 `AskUserQuestion` 提交，并给出工具容量约束（单次问题数与选项数上限）与超限时的拆分做法 |
| 升级注意 | 该约束同时由本项目规则层（工具调用纪律）要求；若上游改写该段，须保持「必须经工具」这一点不被弱化 |

## 已知取舍：治理档位下调

| 项 | 内容 |
|----|------|
| 现象 | 治理档位由 `governed` 主动下调为 `production` |
| 原因 | 脚本原先要求正文含英文边界标记才给 90 分，与本项目语言底线冲突 |
| 选择 | 保语言，接受档位下调 |
| 后续 | 2026-10-29 起 `governance_check.py` 补入中文边界词等价匹配，该取舍已不再必要；本包实测 90/100 |

## 本包不需要「上游是否已修」的判断

与只读 vendor 不同，本包已转本地维护，**不存在需要判断「上游修了没有」的场景**。
上游原文仅作语义对照：升级比对时看的是「上游新增的方法论要点是否需要吸收」，
而不是「上游是否修掉了我们的补丁」。
