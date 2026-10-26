---
name: csharp-format-checker
description: C# 代码格式检查与修复技能（基于 dotnet format + 项目根 .editorconfig）。当用户要求"检查/扫描 C# 代码格式"、"执行 dotnet format"、"格式化 C# 代码"、"代码风格是否符合规范"、或把格式检查作为提交前步骤时触发。使用 dotnet format 工具按项目根目录 .editorconfig 规则检查 C# 代码格式，默认 check 模式只检查不修改文件（--verify-no-changes，可配合 git diff 查看将变更内容），支持 fix 模式落盘应用格式修改；忽略目录由项目侧配置文件（索引逻辑名 `format_checker.config`，位于 .codebuddy.project/configs/skills/csharp/csharp-format-checker/config.json）指定，排除三方插件与生成代码目录（既不会被检查也不会被修改）。调用时将用户指定的目录或文件路径直接传递给技能脚本执行，禁止预先扫描或手动判断文件列表。
license: MIT
compatibility: 需要 .NET SDK 6.0+（dotnet format 已内置于 SDK；已在 .NET 10.0.400 环境验证）。无需额外 Agent，由 CodeBuddy Code 直接执行脚本。
metadata:
  author: zengliugen
  version: "0.1"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，需通过触发评估和输出风险检查。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 按项目根 `.editorconfig` 规则，用 dotnet format 检查/修复 C# 代码格式（默认只检查不修改，输出退出码与报告）；并提供工作区行尾合规检测（`check_eol.py`） |
| 输出 | 退出码（0 无格式问题 / 2 check 模式存在待格式化文件；`check_eol.py`：0 合规 / 1 有异常 / 3 配置环境不可用）+ `check_logs/` 下 `.md` 摘要与 `.log` 完整输出 |
| 排除 | 实际不执行任何"修改源码"之外的操作：不检查非 C# 内容、不修改配置声明的忽略目录内文件、不承担注释规范检查（见 `csharp-comment-checker`） |
| 前提 | 项目根存在 `.editorconfig`；工作区（`.slnx`/`.sln`/`.csproj`）可被 dotnet format 加载；本机 .NET SDK 可用；行尾检测另需位于 git 仓库内 |

## 规则文件（格式标准）
本技能**不内置格式规范**，格式标准即项目根目录的 `.editorconfig` 文件：

- 检查范围仅覆盖该文件声明的文件类型（本项目为 `[*.cs]`）。
- `root = true` 使配置对项目根下全部 `.cs` 生效；如存在下级 `.editorconfig` 会被 dotnet format 自动按最近者优先合并。
- 修改 `.editorconfig` 后重新运行即可生效，无需改动技能。

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/guide.md` | 执行细节：快速上手、目标路径传递规则、结果文件强制要求、忽略目录配置、执行流程、边界排除、检查清单 |
| `references/config-guide.md` | 项目侧配置项定义（`exclude_dirs`、扫描范围、工程定位）与索引登记 |
| `references/h1-integration.md` | **提交门禁集成**：如何接入 `vcs-git-commit` 的 H1 暂存前钩子（命令、退出码、`--changed-from-file` vs `--changed`、报告复用、范围口径、与审查门禁的分工） |

> **H1 集成说明归属本技能**：`vcs` 包只定义「如何执行一个外部校验命令」的通用机制，
> 不包含任何 C# / dotnet 细节。本技能在提交门禁中的调用方式由 `references/h1-integration.md`
> 自述，项目侧 `git-commit/project-config.md` §4 的步骤行按该文档编写。

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 快速上手
- 前置规则：直接传递目标路径，禁止预分析
- 强制规则：必须生成结果文件
- 忽略目录配置（三方插件保护）
- 执行流程
- 边界排除（不触发/不支持）
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南、配置说明与 H1 集成） | 4 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 2 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 5 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
