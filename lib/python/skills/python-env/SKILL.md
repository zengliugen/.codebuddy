---
name: python-env
description: Python 工具环境与应用解释器管理技能（基于 uv 与包内锁定文件）。当用户要求"建 Python 检查环境"、"装 ruff"、"检查 Python 环境是否就绪"、"重建工具环境"、"python-env ensure"、"python-env check"、"应用解释器在哪"、或提交前的 Python 检查因环境缺失而失败时触发。用一个只有两个依赖（ruff、coverage）的独立虚拟环境承载检查工具，与被检项目自身的运行环境物理隔离；依赖定义与锁定在引擎包内 lib/python/envs/（pyproject.toml 加 uv.lock），由 uv 物化到项目侧 .codebuddy.project/envs/python，删除后数秒可重建且支持离线。同时负责按四级顺序探测应用解释器（配置、VIRTUAL_ENV、项目根候选目录、启动器），每级都校验目标解释器能 import ok，避免"解释器能跑但测试全部跳过仍报成功"的静默失败。
license: MIT
compatibility: 需要 uv 0.4+（统一用 uv 创建与同步环境，python -m venv 后端已弃用）。无需 Agent，由 CodeBuddy Code 直接执行脚本。
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
| 拥有的任务 | 管理**工具环境**（只装 ruff 与 coverage，供静态检查与覆盖率使用）与**应用解释器探测**（供测试与覆盖率在被检项目的运行环境中执行） |
| 输出 | 退出码（0 就绪/成功 / 3 环境或配置不可用）+ 可选 JSON 状态；`ensure` 时输出 uv 的安装日志 |
| 排除 | 不安装被检项目的运行依赖（属项目负责人按上游流程完成）；不修改项目 `pyproject.toml` 与锁定文件；不执行任何检查本身（那是 `python-lint` 与 `python-test-coverage` 的职责） |
| 前提 | 可执行 `uv`；项目侧配置索引 `.codebuddy/project.index.json` 中含 `python_lint.config` 项 |

## 两层环境（不可混用）

| 层 | 位置 | 放什么 | 谁创建 |
|----|------|--------|--------|
| 应用环境 | 项目自身（如 `.venv`） | 项目运行依赖（框架、GUI、OCR 等） | 项目负责人（上游流程） |
| 工具环境 | `.codebuddy.project/envs/python` | 只放 ruff 与 coverage | 本技能的 `ensure` |

被测代码必须在**应用环境**中执行。用工具环境跑测试会因缺运行依赖让用例全部跳过，
而 `unittest` 对全跳过仍返回退出码 0（实测输出 `OK (skipped=7)`），看起来像通过。
因此本技能的探测逻辑**每一级都校验 `import ok`**，而非只判断文件是否存在。

## 子命令

| 子命令 | 行为 | 退出码 |
|--------|------|--------|
| `check [--json]` | 只读检测：应用解释器可见性 + 工具环境与锁一致性 | 0 就绪 / 3 缺失或过期 |
| `ensure [--force]` | 创建或更新工具环境（`--force` 删除重建） | 0 成功 / 3 失败 |
| `python` | 打印应用解释器绝对路径 | 0 / 3 未找到 |
| `tool` | 打印工具环境解释器与 ruff 路径 | 0 / 3 未就绪 |

## 锁定与一致性

依赖定义与锁定在包内 `lib/python/envs/`（`pyproject.toml` + `uv.lock`），随引擎入库；
本技能把它物化成项目侧实例。

一致性判定用 `uv sync --locked`，**不是** `--frozen`：

| 模式 | 锁与声明不一致时 | 结论 |
|------|-----------------|------|
| `--frozen` | **静默退出 0** | 不可用：改了依赖声明却不生效 |
| `--locked` | 退出 1 并明确报错 | 采用 |

## 参考文献

| 文件 | 内容 |
|------|------|
| `references/guide.md` | 四级探测顺序与判定详情、故障排查、重建与离线步骤、与相邻技能的分工 |

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)。

## 使用边界

**不适用**以下请求，直接处理即可：

- 安装项目运行依赖（用上游的 `pip install -r requirements.txt`）
- 单独升级某个工具（改包内 `pyproject.toml` 后 `uv lock`，再 `ensure`）

## 技能包结构

| 目录 | 用途 |
|------|------|
| `scripts/` | `env.py`：探测、创建、校验 |
| `references/` | 执行细则 |
| `agents/` | 接口契约与平台适配元数据 |
| `evals/` | 触发用例与评测报告 |
| `reports/` | 风险画像与信任报告 |
