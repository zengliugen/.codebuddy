# 本地改动记录（本地维护分支）

本包源出上游 grilling 1.0，自 2.0 起转为本项目**本地维护分支**，正文已中文化。
本文件记录相对上游的改动，便于日后与上游语义对照。

> 维护档位判据：`agents/interface.yaml` 的 `source.origin` 为 `local` 且 `editable` 为 `full`。
> 与 `lib/yao-meta-skill/`（只读 vendor）不同，本包**允许本地改造**，正文以本仓库为准。

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
| 验证 | validate / trust / conformance / skill-ir / resource_boundary / governance 全部退出码 0，governance 80/100；盲测 post_freeze 精确率 0.667、召回 0.400，已作为回归基线 |

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
| 原因 | 脚本要求正文含英文边界标记才给 90 分，与本项目语言底线冲突 |
| 选择 | 保语言，接受档位下调；该取舍已写入 `manifest.json` 与门禁结果 |
| 升级注意 | 上游若放宽该判据（不再要求英文标记），可重新评估是否升回 `governed` |

## 本包不需要「上游是否已修」的判断

与只读 vendor 不同，本包已转本地维护，**不存在需要判断「上游修了没有」的场景**。
上游原文仅作语义对照：升级比对时看的是「上游新增的方法论要点是否需要吸收」，
而不是「上游是否修掉了我们的补丁」。
