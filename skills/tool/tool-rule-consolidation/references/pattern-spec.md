# 项目规则统一模式规范

<!-- pack-ref-ok: csharp-code, csharp-comment, csharp-lsp, csharp-test, csharp-test-coverage, python-code, python-comment, python-test, python-env, python-lint, python-test-coverage, unity-pipeline, yao-meta-skill, grilling, vcs-router, vcs-git-commit —— 本文件是「引擎规则全景表」，如实登记各包规则的结构与规模；引用的是规则清单而非运行时调用。 -->

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
alwaysApply: true        # 或 alwaysApply: false + paths（条件触发）
enabled: true
updatedAt: <ISO 时间戳>
provider:
---
```

- **全局规范**（如语言、Unity 操作）用 `alwaysApply: true`。
- **条件规范**（如操作 `.cs` 文件时生效）用 `alwaysApply: false` + `paths`（如 `"**/*.cs"`）。

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

- 仅承载详细规范，由技能/Agent 执行对应操作时显式读取（或随入口 `paths` 一起注入）。
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
| **入口规则** | `<技能名>.entry.mdc` | `alwaysApply` 或 `paths` |
| **规范规则** | `RULE.mdc`（有对应技能） | `alwaysApply: false`，由技能加载 |
| **底线规范** | `RULE.mdc`（无对应技能） | 允许 `alwaysApply: true` |

| 规则 | 包 | 类型 | 触发方式 | 子规范 |
|---|---|---|---|---|
| `core-init` | core | 入口 | `paths: **/.codebuddy/**` | 0 |
| `core-engine` | core | 底线规范 | `paths: **/.codebuddy/**` | 3 |
| `core-language` | core | 底线规范 | `alwaysApply` | 1 |
| `core-project-guide` | core | 底线规范 | `alwaysApply` | 5 |
| `core-rule-governance` | core | 底线规范 | `alwaysApply` | 3 |
| `core-tooling` | core | 底线规范 | `alwaysApply` | 5 |
| `csharp-code-review` | csharp | 入口 | `paths: **/*.cs` | 5 |
| `csharp-comment` | csharp | 入口 | `alwaysApply` | 5 |
| `csharp-format-checker` | csharp | 入口 | `paths: **/*.cs` | 0 |
| `csharp-lsp` | csharp | 入口 | `paths: **/*.cs` | 0 |
| `csharp-test-coverage` | csharp | 入口 | `paths: **/Tests/**` | 0 |
| `csharp-test` | csharp | 底线规范 | `paths: **/Tests/**` | 3 |
| `python-code-review` | python | 入口 | `paths: **/*.py` | 4 |
| `python-comment` | python | 入口 | `paths: **/*.py` | 1 |
| `python-env` | python | 入口 | `paths: **/.codebuddy/**` | 0 |
| `python-lint` | python | 入口 | `paths: **/*.py` | 0 |
| `python-test-coverage` | python | 入口 | `paths: **/tests/**` | 0 |
| `python-test` | python | 底线规范 | `paths: **/tests/**/*.py, **/extensions_tests/**/*.py` | 2 |
| `tool-cmd-script-writing` | tool | 入口 | `paths: **/*.{cmd,bat}` | 0 |
| `tool-engine-sync` | tool | 入口 | `paths: **/.codebuddy/**` | 0 |
| `tool-export-zipped-dir` | tool | 入口 | `paths: **/.codebuddy/**` | 0 |
| `tool-rule-consolidation` | tool | 入口 | `paths: **/.codebuddy/**` | 0 |
| `tool-session-lesson-distill` | tool | 入口 | `paths: **/.codebuddy/**` | 0 |
| `unity-pipeline` | unity-pipeline | 入口 | `alwaysApply` | 1 |
| `vcs-git-commit` | vcs | 入口 | `paths: **/*` | 3 |
| `vcs-git-merge` | vcs | 入口 | `paths: **/*` | 1 |
| `vcs-router` | vcs | 入口 | `alwaysApply` | 0 |
| `vcs-engine-commit` | vcs | 底线规范 | `paths: **/.codebuddy/**` | 1 |
| `yao-meta-skill` | yao-meta-skill | 入口 | `alwaysApply` | 0 |

> 合计 29 条：入口 21、底线规范 8。**无「有技能对应的规范规则」**——规范全部随技能走，
> 不单独成规则，避免规范与技能双份维护。

> **注**：`core-rule-governance` 常驻（`alwaysApply: true`），不用 `paths`。它约束的是
> 「这条规则该不该建、该叫什么名字、该放在哪」，这个判断发生在写入规则文件**之前**；
> `paths` 是文件操作命中该路径后才注入的事后触发，赶不上决策点。

### 项目侧规则（`.codebuddy.project/rules/project/`）

项目专有规则与引擎侧**同构**（入口独占目录 + 规范目录），组件名统一加 `project-` 前缀，
由 `check_manifest.py` 项 10 校验。清单如下：

| 规则 | 类型 | 触发方式 | 对应技能 | 子规范 |
|---|---|---|---|---|
| `project-extension-capability-guard` | 入口 | `alwaysApply` | 同名技能 | 0 |
| `project-extension-capability` | 规范 | `alwaysApply: false`（技能加载） | 前缀 `project-extension-capability-guard` | 4 |
| `project-upstream-compat-guard` | 入口 | `alwaysApply` | 同名技能 | 0 |
| `project-upstream-compat` | 规范 | `alwaysApply: false`（技能加载） | 前缀 `project-upstream-compat-guard` | 2 |

> 合计 4 条：入口 2、规范 2。项目侧内容由项目自行管理，不登记 `lib/packs.json` 的
> `comps`（`project` 包的 `comps` 保持空），故项 8 与项 9 跳过它，由项 10 单独校验。

> **注**：`core-tooling` 常驻（`alwaysApply: true`）。它把「命令如何构造」「结果如何判定」「该问用户时怎么问」合到同一条规则下——三者都以单个工具调用为粒度，都必须在每次调用时生效。其中第三部分（第 11—14 条）规定所有面向用户的提问必须经 `AskUserQuestion` 发起，并明确该工具超时属临时失败、不得据此放弃；细则见 `ask-question-spec.mdc`。核心底线压进入口、分级细则与校验命令下沉子规则，是为让纪律在调用时真正生效的必要代价。
>
> **注**：`core-engine`（core）与 `vcs-engine-commit`（vcs）触发面相同（均为 `.codebuddy/**`），但**分包存放**：
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
> 底线型的子规则没有 `paths`、也没有技能去 Read，若 RULE 只写「详见 xx-spec」，
> 那份细则在实际运行中从不生效。评估规则结构时先判角色，再判该不该拆。
> 子规则不要挂 `paths`：`csharp-comment` 5 个子规则曾同挂 `**/*.cs`，合计 16.7 KB
> 在每次触碰 `.cs` 文件时全部注入，而其中大部分只在「扫描/修复注释」时才需要。