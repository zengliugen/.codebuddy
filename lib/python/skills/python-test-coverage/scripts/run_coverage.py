#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""python-test-coverage 执行脚本：采集真实覆盖率并校验测试确实执行过。

核心设计（两点都必须有，缺一即失去意义）：

1. **在被测代码的运行环境中执行**：
   覆盖率要在应用环境（项目的 .venv）里跑，而不是工具环境。被测代码需要框架、
   GUI、OCR 等运行依赖，用工具环境跑会因缺依赖让用例全部跳过。coverage 本身装在
   工具环境，通过 PYTHONPATH 注入应用环境使用（实测两环境同为 cp312 时 ABI 兼容）。

2. **断言实际执行用例数 > 0**：
   测试类常用 skipIf 跳过缺依赖的场景，全部跳过时测试框架**仍返回退出码 0**。
   实测：用没装 ok 的解释器跑 extensions_tests，输出 OK (skipped=7)、退出码 0、
   覆盖率报告 TOTAL 0%——看起来像「代码确实没被覆盖」，比报错更难发现。
   因此本脚本解析 runner 输出中的执行数与跳过数，全部跳过即退出 3。

测试收集用**逐文件显式传路径**，不用 unittest discover：
discover 只递归含 __init__.py 的包，缺该文件的子目录会被静默跳过且仍报成功。

用法：
    python run_coverage.py [--app | --tools] [--json] [-- <runner 附加参数>]

    --app（默认）  用应用解释器执行（推荐）
    --tools        用工具环境解释器执行（仅当应用环境不可用时）
    --json         以 JSON 输出摘要

退出码：
    0 —— 采集完成且用例确实执行
    1 —— 测试失败
    3 —— 环境、配置不可用，或用例全部跳过（有效性校验失败）
"""

import argparse
import json
import os
import re
import subprocess
import sys

# 配置在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "python_coverage.config"

# 配置中必需的键（缺失即报错，不静默回退内置默认值）
REQUIRED_CONFIG_KEYS = ("test_runner", "test_root", "source")

# 工具环境实例在项目侧的固定相对路径（引擎约定，全部项目一致，故不进索引）
TOOL_ENV_REL = os.path.join(".codebuddy.project", "envs", "python")

# 应用解释器探测的候选目录
APP_ENV_DIRS = (".venv", "venv", "env")

# 测试文件名模式（与 run_tests.ps1 的 -Filter Test*.py 一致）
TEST_FILE_PREFIX = "Test"


class CoverageError(RuntimeError):
    """环境或配置不可用时抛出；由 CLI 入口转为退出码 3。"""


class ValidityError(RuntimeError):
    """用例全部跳过等有效性问题；由 CLI 入口转为退出码 3。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def find_codebuddy_dir(start):
    """自 start 向上查找含 .codebuddy 子目录的目录，返回其绝对路径；找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _project_root_from_script():
    """自脚本位置向上查找项目根（含 .codebuddy 的目录）；找不到返回 None。

    脚本必然位于 <项目根>/.codebuddy/... 之下，这是**唯一可靠锚点**，与工作目录无关。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(current, ".codebuddy")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _project_root_from_cwd(start=None):
    """自 start（缺省当前工作目录）向上查找含 .codebuddy 的目录。"""
    current = os.path.abspath(start if start else os.getcwd())
    while True:
        if os.path.isdir(os.path.join(current, ".codebuddy")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_project_root(start=None):
    """定位项目根，找不到返回 None。

    判据：**以脚本自身位置为主，当前工作目录仅作一致性核对**。

    为什么不能 CWD 优先：向上查找会越过项目边界。实测在宿主仓库根运行脚本时命中上一层
    另一个项目的 .codebuddy，于是读的是那份引擎的索引与配置——报出的错误与本项目无关，
    或更糟：按错误的配置范围执行操作，而命令本身「成功」了。

    为什么仍要看 CWD：「多项目经目录链接共享同一份 .codebuddy」是受支持的用法，
    此时两侧 realpath 相同，采用 CWD 结果不改变语义。

    参数：
        start：CWD 核对的起点；缺省用当前工作目录

    返回：
        项目根绝对路径；两侧均未命中时返回 None（**不再回退到 start**：
        回退会让调用方无法区分「找到」与「没找到」，掩盖真实原因）
    """
    anchor = _project_root_from_script()
    cwd_root = _project_root_from_cwd(start)
    if anchor and cwd_root and os.path.realpath(anchor) == os.path.realpath(cwd_root):
        return cwd_root
    if anchor:
        if cwd_root:
            sys.stderr.write(
                "[提示] 当前目录向上命中的 .codebuddy 与脚本所属的不是同一份，已忽略：\n"
                "       忽略：%s\n       采用：%s\n" % (cwd_root, anchor))
        return anchor
    return cwd_root


def load_config(root):
    """经索引加载并校验 python_coverage.config；缺失即抛 CoverageError。"""
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise CoverageError("未能从项目根定位 .codebuddy 目录：%s" % root)
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise CoverageError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise CoverageError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise CoverageError("索引缺少配置项 files.%s.path：%s" % (CONFIG_CODENAME, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise CoverageError("索引 files.%s.path 必须为相对路径：%s" % (CONFIG_CODENAME, rel))
    config_path = os.path.normpath(os.path.join(root, rel))
    if not os.path.isfile(config_path):
        raise CoverageError("配置未找到：%s" % config_path)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise CoverageError("配置读取失败（%s）：%s" % (error, config_path))
    if not isinstance(config, dict):
        raise CoverageError("配置顶层必须是 JSON 对象：%s" % config_path)
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise CoverageError("配置缺少必需键：%s（%s）" % ("、".join(missing), config_path))
    return config


def venv_python(env_dir):
    """返回虚拟环境内的解释器路径（不校验存在性）。"""
    if os.name == "nt":
        return os.path.join(env_dir, "Scripts", "python.exe")
    return os.path.join(env_dir, "bin", "python")


def verify_app_python(python_path):
    """校验该解释器能 import ok（判定它确实是应用运行环境）。"""
    if not python_path or not os.path.isfile(python_path):
        return False, "路径不存在"
    try:
        result = subprocess.run(
            [python_path, "-c", "import ok"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, "执行失败：%s" % error
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        return False, "import ok 失败（%s）" % (lines[-1] if lines else "未知原因")
    return True, "import ok 通过"


def detect_app_python(root, config):
    """按四级顺序探测应用解释器，每级都校验 import ok。"""
    attempts = []
    configured = (config.get("app_python") or "").strip() if isinstance(config, dict) else ""
    if configured:
        candidate = configured if os.path.isabs(configured) else os.path.join(root, configured)
        ok, detail = verify_app_python(candidate)
        attempts.append((candidate, ok, detail))
        if ok:
            return os.path.normpath(candidate)
    venv_env = (os.environ.get("VIRTUAL_ENV") or "").strip()
    if venv_env:
        candidate = venv_python(venv_env)
        ok, detail = verify_app_python(candidate)
        attempts.append((candidate, ok, detail))
        if ok:
            return os.path.normpath(candidate)
    for name in APP_ENV_DIRS:
        candidate = venv_python(os.path.join(root, name))
        ok, detail = verify_app_python(candidate)
        attempts.append((candidate, ok, detail))
        if ok:
            return os.path.normpath(candidate)
    lines = ["未找到可用的应用解释器（需能 import ok）："]
    for path, ok, detail in attempts:
        lines.append("  - %s -> %s（%s）" % (path or "（无）", "通过" if ok else "失败", detail))
    raise CoverageError("\n".join(lines))


def tool_env_python(root):
    """返回工具环境解释器路径；不存在即抛 CoverageError。"""
    path = venv_python(os.path.join(root, TOOL_ENV_REL))
    if not os.path.isfile(path):
        raise CoverageError(
            "工具环境未就绪：%s\n       请先运行 python-env 技能的 ensure 子命令。" % path)
    return path


def tool_site_packages(root):
    """返回工具环境的 site-packages 路径（用于 PYTHONPATH 注入）。"""
    if os.name == "nt":
        return os.path.join(root, TOOL_ENV_REL, "Lib", "site-packages")
    return os.path.join(root, TOOL_ENV_REL, "lib", "python3.12", "site-packages")


def collect_test_files(root, test_root):
    """递归收集 Test*.py，返回项目根相对路径清单（逐文件显式传路径）。"""
    from pathlib import Path

    base = Path(root) / test_root
    if not base.is_dir():
        raise CoverageError("测试根不存在：%s" % base)
    files = sorted(p for p in base.rglob(TEST_FILE_PREFIX + "*.py") if p.is_file())
    return [str(p.relative_to(root)).replace("\\", "/") for p in files]


def parse_unittest_output(text):
    """从 unittest 输出解析 (执行总数, 跳过数)。

    unittest 输出形如：
        Ran 7 tests in 0.001s
        OK (skipped=7)
        FAILED (failures=1, errors=2, skipped=3)
    """
    total = 0
    match = re.search(r"Ran (\d+) tests?", text)
    if match:
        total = int(match.group(1))
    skipped = 0
    match = re.search(r"skipped=(\d+)", text)
    if match:
        skipped = int(match.group(1))
    return total, skipped


def parse_pytest_output(text):
    """从 pytest 输出解析 (通过+跳过总数, 跳过数)，用于执行数校验。"""
    passed = skipped = 0
    match = re.search(r"(\d+) passed", text)
    if match:
        passed = int(match.group(1))
    match = re.search(r"(\d+) skipped", text)
    if match:
        skipped = int(match.group(1))
    return passed + skipped, skipped


def build_runner_command(test_runner, test_root, test_files, extra_args):
    """构造 runner 命令（覆盖率由外层 coverage run 包裹）。"""
    if test_runner == "unittest":
        return ["-m", "unittest"] + test_files + extra_args
    if test_runner == "pytest":
        return ["-m", "pytest", test_root] + extra_args
    raise CoverageError("配置 test_runner 取值非法：%s（应为 unittest 或 pytest）" % test_runner)


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="python-test-coverage 覆盖率采集")
    parser.add_argument("--tools", action="store_true", help="用工具环境解释器执行（默认用应用解释器）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出摘要")
    args, extra = parser.parse_known_args()
    if extra and extra[0] == "--":
        extra = extra[1:]

    root = find_project_root(os.getcwd())
    if not root:
        print("[FAIL] 未找到项目根（含 .codebuddy 的目录）。请确认 .codebuddy 引擎完整。",
              file=sys.stderr)
        return 3

    try:
        config = load_config(root)
        test_runner = config["test_runner"]
        test_root = config["test_root"]
        source = config.get("source") or []
        if not isinstance(source, list) or not source:
            raise CoverageError("配置 source 必须是非空列表")
        branch = bool(config.get("branch", True))
        report_formats = config.get("report_formats") or ["term-missing"]

        test_files = collect_test_files(root, test_root)
        if not test_files:
            raise CoverageError("测试根下未找到 %s*.py：%s" % (TEST_FILE_PREFIX, test_root))

        if args.tools:
            python = tool_env_python(root)
            pythonpath = ""
        else:
            python = detect_app_python(root, config)
            pythonpath = tool_site_packages(root)
            if not os.path.isdir(pythonpath):
                raise CoverageError("工具环境 site-packages 不存在：%s" % pythonpath)

        env = dict(os.environ)
        if pythonpath:
            existing = env.get("PYTHONPATH") or ""
            env["PYTHONPATH"] = pythonpath + (os.pathsep + existing if existing else "")

        coverage_args = ["-m", "coverage", "run"]
        if branch:
            coverage_args.append("--branch")
        for item in source:
            coverage_args.append("--source=%s" % item)
        runner_cmd = build_runner_command(test_runner, test_root, test_files, extra)

        command = [python] + coverage_args + runner_cmd

        try:
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=1800,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CoverageError("执行覆盖率采集失败：%s" % error)

        output = ((result.stdout or "") + (result.stderr or "")).strip()

        # 有效性校验：用例必须真的执行过
        if test_runner == "unittest":
            total, skipped = parse_unittest_output(output)
        else:
            total, skipped = parse_pytest_output(output)
        executed = max(total - skipped, 0)

        if "No data was collected" in output or executed == 0:
            raise ValidityError(
                "用例未真正执行（总数 %d，跳过 %d，实际执行 %d）。\n"
                "       常见原因：应用环境缺运行依赖（import ok 失败），或用例被 skipIf 全部跳过。\n"
                "       这不是「代码没被覆盖」，而是测试没有运行——请先修复环境。\n"
                "       原始输出：\n%s" % (total, skipped, executed, output))

        if result.returncode != 0:
            if args.json:
                print(json.dumps({"ok": False, "stage": "test", "returncode": result.returncode,
                                  "total": total, "skipped": skipped, "output": output},
                                 ensure_ascii=False, indent=2))
            else:
                print("[未通过] 测试失败（总数 %d，跳过 %d，执行 %d）" % (total, skipped, executed))
                print(output)
            return 1

        # 生成报告
        report_args = ["-m", "coverage", "report"]
        if "term-missing" in report_formats:
            report_args.append("-m")
        report_output = ""
        try:
            report = subprocess.run(
                [python] + report_args, cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=300,
            )
            report_output = ((report.stdout or "") + (report.stderr or "")).strip()
        except (OSError, subprocess.SubprocessError) as error:
            report_output = "报告生成失败：%s" % error

        payload = {
            "ok": True,
            "python": python,
            "test_runner": test_runner,
            "test_files": test_files,
            "total": total,
            "skipped": skipped,
            "executed": executed,
            "report": report_output,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("[通过] 覆盖率采集完成")
            print("解释器：%s" % python)
            print("用例：总数 %d，跳过 %d，执行 %d" % (total, skipped, executed))
            print()
            print(report_output)
        return 0

    except (CoverageError, ValidityError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        else:
            print("[FAIL] %s" % error, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
