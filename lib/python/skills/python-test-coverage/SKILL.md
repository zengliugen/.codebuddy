---
name: python-test-coverage
description: Python 测试覆盖率采集技能（在被测代码的运行环境中执行，并校验测试确实跑过）。当用户要求"统计测试覆盖率"、"跑一下覆盖率"、"coverage report"、"看看扩展代码的测试覆盖情况"、"这次改动有没有测试覆盖"、或需要验证新增代码是否被测试覆盖时触发。用应用环境的解释器执行测试（被测代码需要框架等运行依赖），coverage 装在工具环境通过 PYTHONPATH 注入；测试用逐文件显式传路径而非 discover（后者会静默漏测）。关键设计是断言实际执行用例数大于零——用错环境时用例会全部跳过而测试框架仍返回成功、覆盖率报 0%，看起来像"代码确实没覆盖"，比报错更难发现。报告落项目侧缓存目录。
license: MIT
compatibility: 需要 python-env 技能建好的工具环境（含 coverage），以及项目自身可用的应用解释器（能 import ok）。无需 Agent。
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
| 拥有的任务 | 在应用环境中执行测试并采集真实覆盖率，同时校验测试确实执行过 |
| 输出 | 退出码 + 终端报告；`--json` 时输出结构化摘要（含执行数、跳过数、报告正文） |
| 排除 | 不编写测试；不修改源码；不做代码审查；不承担 lint（那是 `python-lint` 的职责） |
| 前提 | `python-env` 的工具环境已 ensure；应用解释器可用（能 `import ok`）；项目侧 `python_coverage.config` 存在 |

## 两个关键设计

### 1. 在被测代码的运行环境中执行

| 环境 | 用途 | 原因 |
|------|------|------|
| 应用环境（项目 `.venv`） | **执行测试** | 被测代码需要框架、GUI 等运行依赖 |
| 工具环境（`.codebuddy.project/envs/python`） | 提供 coverage | 只需一个覆盖率工具 |

coverage 通过 `PYTHONPATH` 注入应用环境使用（两环境同为 cp312 时 ABI 兼容，实测通过）。

### 2. 断言实际执行用例数 > 0

用没装运行依赖的解释器跑测试，用例会全部被 `skipIf` 跳过，而测试框架**仍返回退出码 0**。
实测输出：

```
Ran 7 tests in 0.000s
OK (skipped=7)
CoverageWarning: No data was collected.
退出码: 0
TOTAL   30   30   10   0   0%
```

看起来像「代码确实没被覆盖」，实际是「测试根本没跑」。因此脚本解析执行数与跳过数，
全部跳过即退出 3 并明确说明原因。

## 测试收集方式

**逐文件显式传路径**，不用 `unittest discover`：

```python
for f in sorted((root / test_root).rglob("Test*.py")):
    files.append(f)
# 然后 python -m unittest <每个文件>
```

`discover` 只递归含 `__init__.py` 的包，缺该文件的子目录会被静默跳过且仍报成功。
项目 `run_tests.ps1` 已按逐文件方式实现，本技能与其口径一致。

## 配置项

路径：`.codebuddy.project/configs/skills/python/python-test-coverage/config.json`
（索引逻辑名 `python_coverage.config`）

| 键 | 必需 | 说明 |
|----|------|------|
| `version` | 是 | 配置版本 |
| `test_runner` | 是 | `unittest` 或 `pytest` |
| `test_root` | 是 | 测试根目录，相对项目根 |
| `source` | 是 | 覆盖率分母（如 `["extensions"]`），不含测试自身 |
| `branch` | 否 | 是否采集分支覆盖，默认 `true` |
| `fail_under` | 否 | 覆盖率阈值；`0` 表示不作为门禁 |
| `report_formats` | 否 | 报告格式，如 `["term-missing", "json"]` |

## 参考文献

| 文件 | 内容 |
|------|------|
| `references/guide.md` | 执行链路详解、有效性校验原理、双根语义、报告解读、故障排查 |

## 使用边界

**不适用**：

- 只跑测试不采集覆盖率（直接 `python -m unittest`）
- 编写或修复测试代码
- 代码审查

## 技能包结构

| 目录 | 用途 |
|------|------|
| `scripts/` | `run_coverage.py` |
| `references/` | 执行与排查细则 |
| `agents/` | 接口契约与平台适配元数据 |
| `evals/` | 触发用例与评测报告 |
| `reports/` | 风险画像与信任报告 |
