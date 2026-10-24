---
name: python-lint
description: Python 静态检查技能（基于 ruff，规则与范围全部由项目侧配置驱动）。当用户要求"检查 Python 代码问题"、"跑 ruff"、"ruff check"、"ruff format"、"格式化 Python 代码"、"Python 代码是否符合规范"、"lint Python"、或把 Python 静态检查作为提交前步骤时触发。用项目侧配置 python_lint.config 决定规则集（默认 E/F/I/D）、行宽、docstring 风格与检查范围，由脚本拼出 ruff 参数执行，不在门禁配置里重复一份参数；默认 check 模式只检查不修改，fix 模式落盘修可自动修的问题，format 系列按 ruff formatter 处理代码格式。检查范围通过同目录 collect_targets.py 按 git 变更清单收集，白名单锚定项目根下的自有代码目录。
license: MIT
compatibility: 需要 uv（工具环境由 python-env 技能创建）。无需 Agent，由 CodeBuddy Code 直接执行脚本。
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
| 拥有的任务 | 用 ruff 检查与格式化 Python 代码；提供"本次变更清单"供提交门禁使用 |
| 输出 | 退出码（0 通过 / 1 有违规 / 3 配置或环境不可用）+ 终端结果 + 可选 JSON 摘要 |
| 排除 | 不检查非 Python 文件；不承担语义审查（那属代码审查技能与 Agent）；不修改配置声明的范围之外的文件 |
| 前提 | 工具环境已由 `python-env` 的 `ensure` 创建；项目侧配置 `python_lint.config` 存在且完整 |

## 模式

| 模式 | 行为 | 用途 |
|------|------|------|
| `check` | `ruff check`，有违规退出 1 | 默认，人工检查 |
| `check --blocking` | 先自动修 import 排序 → 格式检查 → 规则检查，任一阻塞步非 0 即退出 1 | **提交门禁（H1）** |
| `fix` | `ruff check --fix` | 修可自动修的问题 |
| `format-check` | `ruff format --check` | 只检查格式不落盘 |
| `format` | `ruff format` | 落盘格式化 |

## 为什么参数由脚本拼、不在门禁配置里重复

ruff 的规则集、行宽、docstring 风格、目标版本全部来自 `python_lint.config`。若门禁配置
再写一份 CLI 参数，就会出现两套事实来源：改配置忘了改门禁，技能结论与门禁结论不一致。
因此门禁只调本脚本，规则与范围口径只有一处。

项目根 `pyproject.toml` **不放** `[tool.ruff]`：该文件属上游 lineage，改动会与上游合并冲突。

## 检查范围

范围由两段配置声明，语义与引擎既有审查收集脚本一致：

| 配置 | 语义 |
|------|------|
| `include_patterns` 非空 | 白名单模式（默认拒绝），只检查匹配的文件 |
| `include_patterns` 缺失或为空 | 黑名单模式（默认放行），仅按 `exclude_patterns` 排除 |
| 两者都空 | 报错退出（范围无法确定，不静默全量或全空） |

模式一律按**项目根相对路径**书写。收集脚本会把 git 的仓库相对路径换算为项目根相对路径，
因此**不需要为抵销仓库前缀而补** `**/` 前缀——带前缀会误匹配任意层级的同名目录。

## 参考文献

| 文件 | 内容 |
|------|------|
| `references/guide.md` | 配置项定义、模式与退出码、H1 集成方式、范围白名单的书写规则与实测依据 |

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)。

## 使用边界

**不适用**以下请求：

- 语义级代码审查（命名是否合理、逻辑是否有缺陷）——属代码审查技能
- 非 Python 文件的格式检查

## 技能包结构

| 目录 | 用途 |
|------|------|
| `scripts/` | `run_ruff.py`（执行）、`collect_targets.py`（变更清单收集） |
| `references/` | 配置与集成细则 |
| `agents/` | 接口契约与平台适配元数据 |
| `evals/` | 触发用例与评测报告 |
| `reports/` | 风险画像与信任报告 |
