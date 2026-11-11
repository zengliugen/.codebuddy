# 项目规则统一模式规范

<!-- pack-ref-ok: csharp-code, csharp-comment, csharp-lsp, csharp-test, csharp-test-coverage, python-code, python-comment, python-test, python-env, python-lint, python-test-coverage, unity-pipeline, yao-meta-skill, grilling, vcs-router, vcs-commit, vcs-git-commit, vcs-svn-commit, vcs-git-merge, vcs-svn-merge —— 本文件是「引擎规则全景表」，如实登记各包规则的结构与规模；引用的是规则清单而非运行时调用。 -->

本项目 `.codebuddy/rules/<name>/` 下所有规则遵循统一结构，评估重组时必须对照本规范。

## 目录结构

```
rules/<name>/
├── RULE.mdc              # 入口规则（始终生效 或 条件触发）
└── <sub>-spec.mdc        # 子规则（按需加载，0..n 个）
```

## 入口 RULE.mdc 规范

### frontmatter

```yaml
---
description: <一句话说明规则用途与生效方式>
alwaysApply: true        # 入口规则与底线规范一律 true；规范规则一律 false
enabled: true
updatedAt: <ISO 时间戳>
provider:
---
```

- **`paths` 一律不写**。触发语义只有两种：常驻（`alwaysApply: true`）与被显式读取（`alwaysApply: false`）。
- **入口规则**（`<技能名>.entry.mdc`）必须 `alwaysApply: true`：它的职责是「提醒必须走技能」，
  与当前操作哪个文件无关。
- **规范规则 / 子规则**必须 `alwaysApply: false`：由入口规则或技能显式读取，自带触发条件会形成
  双份注入或永不生效两种失效。
- **底线规范**（无对应技能）`alwaysApply: true`，并同步压缩正文（见 `core-rule-governance`
  的 `classification-spec.mdc` §3.1）。

### 内容结构

1. **概述段**：一句话说明规则用途、生效方式（始终生效/触发）、子规则按需加载。
2. **强制条款**（核心底线/强制入口规则）：始终生效的不可妥协条款，**必须留在入口**。
3. **子规则路由表**：`| 场景 | 子规则文件 | 内容 |` 表格，列明每个子规则的加载时机。
4. **加载机制说明**：说明子规则均为 `alwaysApply: false`、何时读取、位于同目录。

## 子规则规范

### frontmatter

```yaml
---
description: <说明子规则内容与加载时机>
alwaysApply: false
enabled: true
updatedAt: <ISO 时间戳>
provider:
---
```

### 内容要求

- 仅承载详细规范，由技能/Agent 执行对应操作时显式读取。**不写 `paths`**。
- 子规则间主题独立、边界清晰；内容过小的子规则应合并（见 `merge-criteria.md`）。

## 命名约定

| 元素 | 规范 | 示例 |
|------|------|------|
| 目录名 | `<name>` 与对应技能同名 | `csharp-code-review`、`vcs-router` |
| 入口文件 | `RULE.mdc`（固定） | `RULE.mdc` |
| 子规则 | `<主题>-spec.mdc` 或 `<主题>.mdc` | `quality-spec.mdc`、`compliance.mdc` |

## 项目规则全景

规则分三类（治理规则见 `rules/core/core-rule-governance/`）：

| 类型 | 文件名 | 触发方式 |
|---|---|---|
| **入口规则** | `<技能名>.entry.mdc` | `alwaysApply: true`（禁止 `paths`） |
| **规范规则** | `RULE.mdc`（有对应技能） | `alwaysApply: false`，由技能加载（禁止 `paths`） |
| **底线规范** | `RULE.mdc`（无对应技能） | `alwaysApply: true`（禁止 `paths`） |

| 规则 | 包 | 类型 | 触发方式 | 子规范 |
|---|---|---|---|---|
| `core-engine` | core | 底线规范 | `alwaysApply: true` | 3 |
| `core-init` | core | 入口 | `alwaysApply: true` | 0 |
| `core-language` | core | 底线规范 | `alwaysApply: true` | 1 |
| `core-project-guide` | core | 底线规范 | `alwaysApply: true` | 5 |
| `core-rule-governance` | core | 底线规范 | `alwaysApply: true` | 3 |
| `core-tooling` | core | 底线规范 | `alwaysApply: true` | 5 |
| `csharp-code-review` | csharp | 入口 + 规范 | `alwaysApply: true / 规范 false` | 6 |
| `csharp-comment` | csharp | 入口 + 规范 | `alwaysApply: true / 规范 false` | 5 |
| `csharp-format-checker` | csharp | 入口 | `alwaysApply: true` | 0 |
| `csharp-lsp` | csharp | 入口 | `alwaysApply: true` | 0 |
| `csharp-test` | csharp | 底线规范 | `alwaysApply: true` | 3 |
| `csharp-test-coverage` | csharp | 入口 | `alwaysApply: true` | 0 |
| `python-code-review` | python | 入口 + 规范 | `alwaysApply: true / 规范 false` | 4 |
| `python-comment` | python | 入口 + 规范 | `alwaysApply: true / 规范 false` | 1 |
| `python-env` | python | 入口 | `alwaysApply: true` | 0 |
| `python-lint` | python | 入口 | `alwaysApply: true` | 0 |
| `python-test` | python | 底线规范 | `alwaysApply: true` | 2 |
| `python-test-coverage` | python | 入口 | `alwaysApply: true` | 0 |
| `tool-cmd-script-writing` | tool | 入口 | `alwaysApply: true` | 0 |
| `tool-engine-sync` | tool | 入口 | `alwaysApply: true` | 0 |
| `tool-export-zipped-dir` | tool | 入口 | `alwaysApply: true` | 0 |
| `tool-rule-consolidation` | tool | 入口 | `alwaysApply: true` | 0 |
| `tool-session-lesson-distill` | tool | 入口 | `alwaysApply: true` | 0 |
| `unity-pipeline` | unity-pipeline | 入口 + 规范 | `alwaysApply: true / 规范 false` | 1 |
| `vcs-engine-commit` | vcs | 底线规范 | `alwaysApply: true` | 1 |
| `vcs-commit` | vcs | 规范规则 | `alwaysApply: false` | 2 |
| `vcs-git-commit` | vcs | 规范规则 | `alwaysApply: false` | 1 |
| `vcs-svn-commit` | vcs | 规范规则 | `alwaysApply: false` | 1 |
| `vcs-git-merge` | vcs | 规范规则 | `alwaysApply: false` | 1 |
| `vcs-svn-merge` | vcs | 规范规则 | `alwaysApply: false` | 1 |
| `vcs-router` | vcs | 入口 + 规范 | `alwaysApply: true / 规范 false` | 0 |
| `yao-meta-skill` | yao-meta-skill | 入口 + 规范 | `alwaysApply: true / 规范 false` | 0 |

> 合计 32 个规则目录、21 条入口规则。**全库无 `paths`**：入口与底线规范一律常驻，
> 规范规则一律 `alwaysApply: false` 由入口或技能显式读取。
>
> `csharp-test`、`python-test` 虽与 `csharp-test-coverage`、`python-test-coverage` 同前缀，但两个覆盖率技能
> **只在文档里交叉引用其文件名，并不 Read 其子规则**，故按底线规范常驻。判断依据是
> **有没有技能真的去读取**，不是名称前缀是否相同。
> 合计 32 条：入口 21、底线规范 8、随技能走的规范规则 3。**无「有技能对应的规范规则」**——规范全部随技能走，
> 不单独成规则，避免规范与技能双份维护。

> **注**：`core-rule-governance` 常驻（`alwaysApply: true`）。它约束的是
> 「这条规则该不该建、该叫什么名字、该放在哪」，这个判断发生在写入规则文件**之前**，
> 任何按需触发都赶不上决策点。

### 项目侧规则（`.codebuddy.project/project-lib/<包名>/rules/`）

项目侧规则与引擎侧**完全同构**（入口独占目录 + 规范目录 + 包分组），组件名遵循同一条
`<包名>-` 前缀约定，由 `check_manifest.py` 项 8 与项 9 直接校验。组件落在
`.codebuddy.project/project-lib/<包名>/rules/` 下，路径形态与 `lib/<pack>/rules/` 一致，
详见 `classification-spec.mdc` §2.4。下表用通用占位名示意结构差异：

| 规则 | 类型 | 触发方式 | 对应技能 | 子规范 |
|---|---|---|---|---|
| `<包名>-guard` | 入口 | `alwaysApply` | 同名技能 | 0 |
| `<包名>` | 规范 | `alwaysApply: false`（技能加载） | 前缀 `<包名>-guard` | N |
| `<包名>-sync` | 入口 | `alwaysApply` | 同名技能 | 0 |

> 项目侧包登记在 `.codebuddy.project/project-lib/packs.json`，与引擎 `lib/packs.json`
> 结构同构；两表包名全局唯一、依赖单向（项目包 → 引擎包）。项 8、项 9、项 17 覆盖它。

> **注**：`core-tooling` 常驻（`alwaysApply: true`）。它把「命令如何构造」「结果如何判定」「该问用户时怎么问」合到同一条规则下——三者都以单个工具调用为粒度，都必须在每次调用时生效。其中第三部分（第 11—14 条）规定所有面向用户的提问必须经 `AskUserQuestion` 发起，并明确该工具超时属临时失败、不得据此放弃；细则见 `ask-question-spec.mdc`。核心底线压进入口、分级细则与校验命令下沉子规则，是为让纪律在调用时真正生效的必要代价。
>
> **注**：`core-engine`（core）与 `vcs-engine-commit`（vcs）主题相邻（都围绕 `.codebuddy/`），但**分包存放**：
> 前者管「内容如何写、改完同步哪里」，属内容维护；后者管「提交到哪个仓库」，与 `vcs-router` 同属版本控制主题。
> 分包而非合并的原因有两条：一是避免 `core.requires` 与 `vcs.requires` 形成环（`vcs` 已依赖 `core`），
> 二是 `vcs-engine-commit` 需要引用 `vcs-router`（同包引用比跨包引用更稳）。评估规则结构时勿将两者合并，也勿把后者移回 core。
> 项目侧文件的生成由 `core-init` 技能负责。


> **注**：`RULE.mdc` 有两种角色，判据是「有没有技能负责加载它的子规则」（见
> `core-rule-governance` 的 `classification-spec.mdc` §三）：
>
> | 角色 | 判据 | RULE 该写什么 |
> |---|---|---|
> | **索引型** | 包内有同名/前缀技能，技能会 Read 子规则 | 场景描述 + 路由表，**不写细则** |
> | **底线型** | 无技能加载 | **完整自足的底线判据**，子规则只放分级细则与正反例 |
>
> 底线型的子规则为 `alwaysApply: false` 且无 `paths`、也无技能去 Read，若 RULE 只写「详见 xx-spec」，
> 那份细则在实际运行中从不生效。评估规则结构时先判角色，再判该不该拆。
>
> 底线型由按需切换为常驻时，必须同步压缩正文（判据、操作要求、失败形态、路由表留在 RULE；
> 论证、命令样例、目录树、历史踩坑下移子规则）——具体判据见 `classification-spec.mdc` §3.1。
