#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""python-lint 执行脚本：按项目配置驱动 ruff 的检查与格式化。

设计要点（为什么参数在这里拼、而不在门禁配置里重复一份）：
    ruff 的规则集、行宽、docstring 风格、目标版本全部来自项目侧配置
    `python_lint.config`。若门禁配置再写一份 CLI 参数，就会出现两套事实来源——
    改配置忘了改门禁，则技能结论与门禁结论不一致。因此门禁只调本脚本，范围与规则
    口径只有一处。

    项目根 `pyproject.toml` **不放** `[tool.ruff]`：该文件属上游 lineage，改动会与
    `git merge upstream/master` 冲突（项目侧 `project-upstream-compat` 规则）。

分级（`--blocking`，供 H1 使用）：
    1. `ruff check --fix --select I` —— import 排序是机械变换，自动修、不阻塞；
    2. `ruff format --check`        —— 格式漂移，阻塞；
    3. `ruff check`                 —— 配置的规则集（`E501` 已在 ignore 中，长行由
       formatter 兜住），阻塞。
    任一阻塞步骤非 0，本脚本退出 1。

工具环境：
    解释器与 ruff 位于 `<项目根>/.codebuddy.project/envs/python`，由 `python-env` 技能
    的 `env.py ensure` 生成。缺失时本脚本**不自动安装**（安装必须显式、可见），
    直接退出 3 并提示应先跑 ensure。

用法：
    python run_ruff.py [check|check --blocking|fix|format-check|format]
                       [--changed] [--json] [--target <路径> ...]

参数：
    --changed           只检查本次变更（调用同目录 collect_targets.py 取清单）
    --json              以 JSON 输出结果摘要
    --target <路径>     显式指定目标（可重复；不传则按配置的 include_patterns 展开）

退出码：
    0 —— 通过
    1 —— 有违规（含格式漂移）
    3 —— 配置或环境不可用（工具环境缺失、ruff 不存在、配置缺失）
"""

import argparse
import json
import os
import subprocess
import sys

# 配置在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "python_lint.config"

# 工具环境实例在项目侧的固定相对路径（引擎约定，全部项目一致，故不进索引）
TOOL_ENV_REL = os.path.join(".codebuddy.project", "envs", "python")

# 配置中必需的键（缺失即报错，不静默回退内置默认值）
REQUIRED_CONFIG_KEYS = ("line_length", "select", "target_version")


class ConfigError(RuntimeError):
    """配置缺失、损坏或缺少必需键时抛出；由 CLI 入口转为明确的错误退出。"""


class ToolEnvError(RuntimeError):
    """工具环境不可用时抛出（未 ensure、ruff 缺失等）。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def find_codebuddy_dir(start):
    """自 start 向上查找含 `.codebuddy` 子目录的目录，返回该 .codebuddy 的绝对路径；找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_project_root(start):
    """自 start 向上查找**含 .codebuddy 子目录**的目录作为项目根，找不到则返回 start。

    只认 .codebuddy 锚点，**不以 .git 为锚**：.codebuddy 自身是独立 git 仓库时
    （引擎以「独立 git 检出」形态挂载，.codebuddy/.git 是目录而非 submodule 的 gitfile），
    同时匹配 .git 会让向上查找先命中 .codebuddy 本身，项目根被误判，
    配置路径随之拼成 .codebuddy/.codebuddy.project/...，所有项目侧配置都读不到。
    """
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, ".codebuddy")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def resolve_config_path(root):
    """经索引注册表解析配置路径（相对路径基准为项目根，拒绝绝对路径）。"""
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise ConfigError("未能从项目根定位 .codebuddy 目录：%s" % root)
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise ConfigError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError("索引缺少配置项 `files.%s.path`：%s" % (CONFIG_CODENAME, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 `files.%s.path` 必须为相对路径：%s" % (CONFIG_CODENAME, rel))
    return os.path.normpath(os.path.join(root, rel))


def load_config(root):
    """经索引加载并校验配置；缺失或损坏即抛 ConfigError。"""
    config_path = resolve_config_path(root)
    if not os.path.isfile(config_path):
        raise ConfigError("配置未找到：%s" % config_path)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("配置读取失败（%s）：%s" % (error, config_path))
    if not isinstance(config, dict):
        raise ConfigError("配置顶层必须是 JSON 对象：%s" % config_path)
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigError("配置缺少必需键：%s（%s）" % ("、".join(missing), config_path))
    return config


def tool_env_dir(root):
    """返回工具环境实例目录（绝对路径）。"""
    return os.path.join(root, TOOL_ENV_REL)


def find_ruff(root):
    """定位工具环境内的 ruff 可执行文件；缺失即抛 ToolEnvError（不自动安装）。"""
    base = tool_env_dir(root)
    if not os.path.isdir(base):
        raise ToolEnvError(
            "工具环境未就绪：%s\n"
            "       请先运行 python-env 技能的 ensure 子命令：" % base
        )
    candidates = [
        os.path.join(base, "Scripts", "ruff.exe"),
        os.path.join(base, "bin", "ruff"),
        os.path.join(base, "Scripts", "ruff"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise ToolEnvError(
        "工具环境内未找到 ruff：%s\n"
        "       请重新运行 python-env 技能的 ensure 子命令。" % base
    )


def build_format_args(config):
    """拼出 ruff format 的参数。

    format 只接受 target-version / line-length / --config 三项，**不接受**
    --select 与 --ignore（规则集是 check 的概念）。传错会导致 ruff 直接报
    「unexpected argument」，让格式检查永远失败——必须与 check 参数分开构造。
    """
    return [
        "--target-version", str(config["target_version"]),
        "--line-length", str(config["line_length"]),
    ]


def build_check_args(config):
    """拼出 ruff check 的参数（配置是唯一事实来源）。"""
    args = [
        "--target-version", str(config["target_version"]),
        "--line-length", str(config["line_length"]),
    ]
    select = config.get("select") or []
    if select:
        args += ["--select", ",".join(select)]
    ignore = config.get("ignore") or []
    if ignore:
        args += ["--ignore", ",".join(ignore)]
    convention = config.get("pydocstyle_convention")
    if convention:
        # pydocstyle 风格只能经 --config 覆盖项传入（无独立 CLI 开关）
        args += ["--config", 'lint.pydocstyle.convention="%s"' % convention]
    return args


def expand_patterns(root, patterns):
    """按项目根相对路径的 glob 模式展开为实际文件列表。

    用 pathlib 的 glob：`**` 匹配零或多层目录，故 `extensions/**/*.py` 会命中
    `extensions/__init__.py` 与 `extensions/core/x.py` 两类。
    """
    from pathlib import Path

    found = []
    base = Path(root)
    for pattern in patterns:
        for path in base.glob(pattern):
            if path.is_file():
                rel = os.path.relpath(str(path), root).replace("\\", "/")
                if rel not in found:
                    found.append(rel)
    return sorted(found)


def collect_changed(root):
    """调用同目录 collect_targets.py 取本次变更清单；失败即抛 ConfigError。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collect_targets.py")
    if not os.path.isfile(script):
        raise ConfigError("同目录收集脚本缺失：%s" % script)
    result = subprocess.run(
        [sys.executable, script, "--dir", root],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ConfigError(
            "收集变更清单失败（退出码 %d）：%s"
            % (result.returncode, (result.stderr or "").strip())
        )
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def run_ruff(ruff, args):
    """执行一次 ruff，返回 (退出码, 合并输出)。"""
    result = subprocess.run(
        [ruff] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode, output


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="python-lint 执行（ruff 驱动）")
    parser.add_argument("mode", nargs="?", default="check",
                        choices=["check", "fix", "format-check", "format"],
                        help="执行模式（默认 check）")
    parser.add_argument("--blocking", action="store_true",
                        help="分级阻塞模式（供 H1 使用）：自动修 import → 格式检查 → 规则检查")
    parser.add_argument("--changed", action="store_true", help="只检查本次变更")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果摘要")
    parser.add_argument("--target", action="append", default=None,
                        help="显式目标路径（可重复；不传则按配置 include_patterns 展开）")
    args = parser.parse_args()

    root = find_project_root(os.getcwd())

    try:
        config = load_config(root)
    except ConfigError as error:
        print("[FAIL] %s" % error, file=sys.stderr)
        return 3

    try:
        ruff = find_ruff(root)
    except ToolEnvError as error:
        print("[FAIL] %s" % error, file=sys.stderr)
        return 3

    # 目标来源优先级：显式 --target > --changed > 配置 include_patterns
    if args.target:
        targets = [t.replace("\\", "/") for t in args.target]
    elif args.changed:
        try:
            targets = collect_changed(root)
        except ConfigError as error:
            print("[FAIL] %s" % error, file=sys.stderr)
            return 3
    else:
        patterns = config.get("include_patterns") or []
        if not patterns:
            print("[FAIL] 配置缺少 include_patterns，无法确定检查范围（或用 --target 指定）",
                  file=sys.stderr)
            return 3
        targets = expand_patterns(root, patterns)

    if not targets:
        if args.json:
            print(json.dumps({"passed": True, "steps": [], "targets": []}, ensure_ascii=False, indent=2))
        else:
            print("无待检查文件（清单为空）。")
        return 0

    check_args = build_check_args(config)
    fmt_args = build_format_args(config)
    steps = []

    if args.mode == "check" and args.blocking:
        # 第 1 步：import 排序自动修（机械变换，不阻塞）
        # 必须同时限定 --select 与 --fixable：只写 --select I 时，ruff 仍会修复其他规则的
        # 可自动修问题（实测 F401 未使用导入被直接删除），超出「只自动修 import 排序」的授权边界。
        code, output = run_ruff(
            ruff, ["check", "--fix", "--select", "I", "--fixable", "I"] + check_args + targets)
        steps.append({"step": "fix-imports", "returncode": code, "blocking": False, "output": output})
        # 第 2 步：格式检查（阻塞）
        code, output = run_ruff(ruff, ["format", "--check"] + fmt_args + targets)
        steps.append({"step": "format-check", "returncode": code, "blocking": True, "output": output})
        if code != 0:
            return report(args.json, steps, targets, 1)
        # 第 3 步：规则检查（阻塞）
        code, output = run_ruff(ruff, ["check"] + check_args + targets)
        steps.append({"step": "check", "returncode": code, "blocking": True, "output": output})
        return report(args.json, steps, targets, 0 if code == 0 else 1)

    if args.mode == "check":
        code, output = run_ruff(ruff, ["check"] + check_args + targets)
        steps.append({"step": "check", "returncode": code, "blocking": True, "output": output})
        return report(args.json, steps, targets, 0 if code == 0 else 1)

    if args.mode == "fix":
        code, output = run_ruff(ruff, ["check", "--fix"] + check_args + targets)
        steps.append({"step": "fix", "returncode": code, "blocking": True, "output": output})
        return report(args.json, steps, targets, 0 if code == 0 else 1)

    if args.mode == "format-check":
        code, output = run_ruff(ruff, ["format", "--check"] + fmt_args + targets)
        steps.append({"step": "format-check", "returncode": code, "blocking": True, "output": output})
        return report(args.json, steps, targets, 0 if code == 0 else 1)

    # format：落盘
    code, output = run_ruff(ruff, ["format"] + fmt_args + targets)
    steps.append({"step": "format", "returncode": code, "blocking": True, "output": output})
    return report(args.json, steps, targets, 0 if code == 0 else 1)


def report(as_json, steps, targets, exit_code):
    """输出结果摘要并返回退出码。"""
    if as_json:
        payload = {
            "passed": exit_code == 0,
            "targets": targets,
            "steps": steps,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in steps:
            label = "阻塞" if item["blocking"] else "仅记录"
            status = "通过" if item["returncode"] == 0 else "未通过"
            print("[%s] %s（%s）" % (status, item["step"], label))
            if item["output"]:
                print(item["output"])
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
