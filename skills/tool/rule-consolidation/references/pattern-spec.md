# 项目规则统一模式规范

<!-- pack-ref-ok: csharp-code, csharp-comment, csharp-lsp, csharp-test, unity-pipeline, yao-meta-skill, vcs-router, git-commit —— 本文件是「引擎规则全景表」，如实登记各包规则的结构与规模；引用的是规则清单而非运行时调用。 -->

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
| 目录名 | `<name>` 与对应技能同名 | `csharp-code`、`vcs-router` |
| 入口文件 | `RULE.mdc`（固定） | `RULE.mdc` |
| 子规则 | `<主题>-spec.mdc` 或 `<主题>.mdc` | `quality-spec.mdc`、`compliance.mdc` |

## 项目规则全景

| 规则目录 | 入口生效方式 | 子规则数 | 说明 |
|---------|-------------|---------|------|
| `codebuddy-engine` | paths: `"**/.codebuddy/**"` | 3 | 引擎内容维护（项目配置隔离、登记点同步、重构验收） |
| `codebuddy-tooling` | alwaysApply: true | 4 | 工具调用纪律（命令形状 + 结果校验：失败可能返回 {error} 对象而非抛错） |
| `vcs-codebuddy-engine` | paths: `"**/.codebuddy/**"` | 1 | 引擎仓库提交（只治引擎侧；submodule 与独立 git 检出两种形态） |
| `csharp-code` | alwaysApply: true | 5 | 审查规范 |
| `csharp-comment` | alwaysApply: true | 5 | 注释规范 |
| `csharp-lsp` | paths: `"**/*.cs"` | 0 | 单文件（内容少，无独立加载场景） |
| `csharp-test` | paths: `"**/Tests/**"` | 3 | 测试代码规范（命名/编排/验收） |
| `language` | alwaysApply: true | 1 | 语言编码规范 |
| `project-guide` | alwaysApply: true | 5 | 项目指导（**项目事实，迁移时整体重写**） |
| `unity-pipeline` | alwaysApply: true | 1 | Unity 操作规范 |
| `yao-meta-skill` | alwaysApply: true | 0 | 技能工程强制入口（创建/重构/审计技能必须走该技能）；可选包规则，未装包时不存在 |
| `vcs-router` | alwaysApply: true | 4 | 提交规范（仅 Git；审查门禁已并入 `git-commit/references/project-config.md`，不在本规则目录） |

> **注**：`codebuddy-tooling` 常驻（`alwaysApply: true`，入口约 2.5 KB）。它把「命令如何构造」与「结果如何判定」合到同一条规则下——两者共享同一前提（工具被拦下或做失败时都不抛异常，只改变返回值），且都必须在每次工具调用时生效。核心底线压进入口、分级细则与校验命令下沉子规则，是为让纪律在调用时真正生效的必要代价。
>
> **注**：`codebuddy-engine`（core）与 `vcs-codebuddy-engine`（vcs）触发面相同（均为 `.codebuddy/**`），但**分包存放**：
> 前者管「内容如何写、改完同步哪里」，属内容维护；后者管「提交到哪个仓库」，与 `vcs-router` 同属版本控制主题。
> 分包而非合并的原因有两条：一是避免 `core.requires` 与 `vcs.requires` 形成环（`vcs` 已依赖 `core`），
> 二是 `vcs-codebuddy-engine` 需要引用 `vcs-router`（同包引用比跨包引用更稳）。评估规则结构时勿将两者合并，也勿把后者移回 core。
> 项目侧文件的生成由 `codebuddy-init` 技能负责。
