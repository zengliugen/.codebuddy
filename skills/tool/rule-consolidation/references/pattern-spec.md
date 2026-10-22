# 项目规则统一模式规范

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
| `bash-command-shape` | alwaysApply: true | 2 | Bash 命令形状规范（避免复合命令判定与风险分级造成无谓询问） |
| `codebuddy-engine-vcs` | paths: `"**/.codebuddy/**"` | 1 | 引擎仓库提交归属（.codebuddy 自身独立仓库，与项目仓库分开提交） |
| `codebuddy-project-config` | paths: `"**/.codebuddy/**"` | 1 | 项目配置隔离（外置到项目侧、索引登记、示例泛化、事实标注） |
| `engine-maintenance` | paths: `"**/.codebuddy/**"` | 2 | 引擎维护一致性（登记表与引用同步、重构验收） |
| `csharp-code` | alwaysApply: true | 5 | 审查规范 |
| `csharp-comment` | alwaysApply: true | 5 | 注释规范 |
| `csharp-lsp` | paths: `"**/*.cs"` | 0 | 单文件（内容少，无独立加载场景） |
| `csharp-test` | paths: `"**/Tests/**"` | 3 | 测试代码规范（命名/编排/验收） |
| `language` | alwaysApply: true | 1 | 语言编码规范 |
| `project-guide` | alwaysApply: true | 5 | 项目指导（**项目事实，迁移时整体重写**） |
| `unity-pipeline` | alwaysApply: true | 1 | Unity 操作规范 |
| `vcs-router` | alwaysApply: true | 4 | 提交规范（仅 Git；审查门禁已并入 `git-commit/references/project-config.md`，不在本规则目录） |

> **注**：`bash-command-shape` 常驻（`alwaysApply: true`，约 2.3 KB），核心底线压进入口、分级细则下沉子规则，是为让规则在构造命令时真正生效的必要代价。
>
> **注**：`codebuddy-engine-vcs` 与 `codebuddy-project-config` 触发面相同（均为 `.codebuddy/**`），但职责不同——
> 前者管「提交到哪个仓库」（引擎仓库 vs 项目仓库），后者管「内容如何写」（外置配置、索引登记、事实标注）。评估规则结构时勿将两者合并。
> 项目侧文件的生成由 `codebuddy-init` 技能负责。
