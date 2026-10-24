# python-test-coverage 执行细则

## 一、快速上手

```
# 采集（默认用应用解释器）
python scripts/run_coverage.py

# 结构化输出
python scripts/run_coverage.py --json

# 应用环境不可用时用工具环境（不保证被测代码能跑）
python scripts/run_coverage.py --tools

# 传参给 runner
python scripts/run_coverage.py -- -v
```

退出码：`0` 采集完成且用例确实执行 / `1` 测试失败 / `3` 环境、配置不可用或全部跳过。

## 二、执行链路

```
应用解释器（.venv/Scripts/python.exe）
  + PYTHONPATH=<工具环境>/Lib/site-packages
  + -m coverage run --branch --source=extensions
  + -m unittest <每个 Test*.py 文件>
```

三段各自的作用：

| 段 | 为什么 |
|----|--------|
| 应用解释器 | 被测代码需要框架、GUI、OCR 等运行依赖；工具环境没有这些 |
| PYTHONPATH 注入 | coverage 只在工具环境里有，注入后应用环境能 import 到它 |
| 逐文件传路径 | `discover` 会静默跳过无 `__init__.py` 的子目录且仍报成功 |

## 三、有效性校验的原理

用例被 `skipIf` 跳过时，测试框架的返回值仍是 0。实测对比：

| 环境 | 输出 | 退出码 | 覆盖率 |
|------|------|--------|--------|
| 应用 `.venv`（有 ok/PySide6） | `Ran 7 tests ... OK` | 0 | `TOTAL 30 语句 100%` |
| 系统 python 3.15（无 ok） | `Ran 7 tests ... OK (skipped=7)` | **0** | `TOTAL 30 语句 0%` |

第二行就是危险场景：退出码 0、无报错、覆盖率 0%——会被读成「代码没被覆盖」。
实际是「测试没跑」。

脚本在两处校验：

1. 解析 `Ran N tests` 与 `skipped=M`，计算 `executed = N - M`，`executed == 0` 即退出 3。
2. 检测输出中是否含 `No data was collected`，命中即退出 3。

## 四、双测试根

| 测试根 | 被测对象 | 通过意味着 | 允许修改 |
|--------|---------|-----------|---------|
| `tests/` | 上游框架行为 | 上游没被本地改动破坏 | 只新增，不得修改 |
| `extensions_tests/` | `extensions/` 下代码 | 扩展自身按预期工作 | 可自由增改 |

**结论不可混用**。本技能的 `test_root` 通常只配 `extensions_tests`——覆盖率分母是
`extensions/`，`tests/` 对分母无贡献。若要同时验证上游基线，另行跑 `run_tests.ps1`。

## 五、覆盖率数字的解读

### 分母是语句数，不是行数

`coverage report` 的 `TOTAL` 列是**语句数**（空行、注释、docstring 不算）。
本项目 `extensions/` 合计 **30 条语句**（文件行数 103，不是分母）。

### 样本量极小时不要看绝对值

30 条语句的基数下，删掉一个 `if` 分支就能让百分比跳 3~7 个点。判断标准应是：

- **新增代码是否被覆盖**（看 diff 覆盖，而非总数）
- **趋势**（需要历史留存；本技能默认落 caches，会被 `cleanup-caches` 清空，
  故不提供趋势对比）

### 分支覆盖与行覆盖的差

`--branch` 开启后，`if` 只走一个分支也会被判为未完全覆盖。
本项目开启分支覆盖（`branch: true`），因此 100% 行覆盖不等于 100% 分支覆盖。

## 六、报告落位

```
.codebuddy.project/caches/skills/python/python-test-coverage/check_logs/
```

**该目录会被 `cleanup-caches` 整体清空**，属临时产物。需要长期留存时应另行导出。

## 七、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `用例未真正执行（总数 N，跳过 N，实际执行 0）` | 应用环境缺运行依赖 | 按项目流程重建应用环境；或检查 `app_python` |
| `工具环境未就绪` | 未跑 `ensure` | 跑 `python-env` 的 `ensure` |
| `工具环境 site-packages 不存在` | 工具环境损坏 | `ensure --force` |
| `测试根下未找到 Test*.py` | `test_root` 配错或目录为空 | 检查配置与目录 |
| 覆盖率明显偏低 | 分母含未被测目录 | 检查 `source` 配置 |
| `No data was collected` | 测试未 import 被测模块 | 确认测试确实覆盖 `source` 下的代码 |

## 八、与相邻技能的分工

| 场景 | 用哪个 |
|------|--------|
| 跑测试看通过与否 | `run_tests.ps1` 或直接 `python -m unittest` |
| 看覆盖率 | 本技能 |
| 建工具环境 | `python-env` |
| 静态检查 | `python-lint` |
| 审查测试代码质量 | `python-code-review` |
