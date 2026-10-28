# 本包的本地改动索引

> **本文件由引擎仓库维护，不是上游内容。** 详细的逐条记录在 `references/cli-changelog.md`。

本包维护档位：**本地维护分支**（`packs.json` 分类「领域（本地维护）」；`agents/interface.yaml` 的
`source.origin` 为 `local`、`editable` 为 `full`）。

## 与「只读 vendor」的区别

| 项 | 只读 vendor | 本包（本地维护） |
|---|---|---|
| 正文语言 | 保留上游原文 | 已中文化，受语言规则约束 |
| 可否改造 | 仅最小可行性补丁 | 允许本地改造 |
| 与上游关系 | 需与上游逐字比对 | 正文以本仓库为准，无需逐字比对 |

## 改动记录在哪

| 内容 | 位置 |
|---|---|
| 相对上游保留的本地改动清单、版本同步要点（含命令改名、超时语义等） | `references/cli-changelog.md` |
| 当前维护档位与判据 | 本文 + `agents/interface.yaml` + 引擎 `README.md` 的 vendor 表 |

## 改动前必读

1. **`references/cli-changelog.md` 是唯一细节来源**，本文不复制其内容，只做入口索引。
2. 上游仍可能更新 `Documentation~/` 与 `Runtime/Common/CommandNames.cs`；升级时按 changelog 的
   「之后若再升级包」一节重放同步。
3. `reports/` 下是脚本生成产物，标题与字段名随生成器输出为英文，**不计入正文语言范围**；
   需要中文报告时改生成器，不要手改产物（会被下次生成覆盖）。
4. 不译之物：frontmatter 键名、命令名、JSON 字段名、路径——翻译即失效。
5. 改完跑 `python .codebuddy/scripts/check_manifest.py` 与 `pack_install.py status`，均须退出码 0。
