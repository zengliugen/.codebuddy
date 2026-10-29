#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""python-env：工具环境与应用解释器的探测、创建与校验。

两层环境，职责不同，不可混用：

    应用环境：项目自身（.venv 等），用于运行被测/被检代码，需能 import ok、PySide6 可用；
              由项目负责人按上游流程创建，本技能不代劳。
    工具环境：.codebuddy.project/envs/python，只装 ruff 与 coverage，由本技能的 ensure 创建。

    被测代码必须在其运行环境里执行——用工具环境跑测试会因缺 ok 让用例全部跳过，
    而 unittest 对全跳过仍返回退出码 0（实测输出 OK (skipped=7)），看起来像通过。

依赖定义与锁定在包内 lib/python/envs/（pyproject.toml 与 uv.lock），随引擎入库；
本脚本只负责把它物化成项目侧环境实例。

一致性判定用 uv sync --locked 而不是 --frozen：
    实测当 pyproject.toml 与 uv.lock 不一致时，--frozen 静默退出 0（等于改了依赖声明
    却不生效），--locked 退出 1 并明确报错。依据「配置缺失即报错」底线，必须用 --locked。

解释器探测顺序（每级都校验 import ok 成功，避免「能跑但全跳过」）：
    1. 配置 app_python（非空时）
    2. 环境变量 VIRTUAL_ENV
    3. 项目根候选目录 {.venv, venv, env} 的解释器
    4. py -3.12（Windows）或 PATH 上的 python
    全失败则退出码 3，输出每级失败原因（供 LLM 分析后向用户询问）。

用法：
    python env.py check [--json]      只读检测应用解释器与工具环境一致性
    python env.py ensure [--force]    创建/更新工具环境（--force 删除重建）
    python env.py python              打印应用解释器绝对路径
    python env.py tool                打印工具环境解释器与 ruff 路径

退出码：
    0 —— 就绪/成功
    3 —— 环境或配置不可用（缺失、过期、锁不一致）
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

# 配置在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "python_lint.config"

# 工具环境实例在项目侧的固定相对路径（引擎约定，全部项目一致，故不进索引）
TOOL_ENV_REL = os.path.join(".codebuddy.project", "envs", "python")

# 依赖定义与锁定所在位置（相对引擎根；不进入索引——该值跨项目一致，非项目专有）
DEPLOYMENT_REL = os.path.join("lib", "python", "envs")

# 应用解释器探测的候选目录（按序尝试）
APP_ENV_DIRS = (".venv", "venv", "env")


class EnvError(RuntimeError):
    """环境或配置不可用时抛出；由 CLI 入口转为退出码 3。"""


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


def load_config(root):
    """经索引加载 python_lint.config；缺失即抛 EnvError。"""
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise EnvError("未能从项目根定位 .codebuddy 目录：%s" % root)
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise EnvError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise EnvError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise EnvError("索引缺少配置项 files.%s.path：%s" % (CONFIG_CODENAME, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise EnvError("索引 files.%s.path 必须为相对路径：%s" % (CONFIG_CODENAME, rel))
    config_path = os.path.normpath(os.path.join(root, rel))
    if not os.path.isfile(config_path):
        raise EnvError("配置未找到：%s" % config_path)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise EnvError("配置读取失败（%s）：%s" % (error, config_path))
    if not isinstance(config, dict):
        raise EnvError("配置顶层必须是 JSON 对象：%s" % config_path)
    return config


def deployment_dir(root):
    """返回包内依赖定义目录（lib/python/envs）绝对路径。"""
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise EnvError("未能定位 .codebuddy 目录，无法解析依赖定义位置")
    return os.path.normpath(os.path.join(codebuddy_dir, DEPLOYMENT_REL))


def tool_env_dir(root):
    """返回项目侧工具环境实例目录绝对路径。"""
    return os.path.normpath(os.path.join(root, TOOL_ENV_REL))


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
            [python_path, "-c", "import ok"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, "执行失败：%s" % error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "未知原因"
        return False, "import ok 失败（%s）" % tail
    return True, "import ok 通过"


def detect_app_python(root, config):
    """按四级顺序探测应用解释器，返回 (路径, 来源说明)；全失败抛 EnvError。

    每级都校验 import ok：没有 ok 的解释器跑测试会让用例全部跳过且退出码为 0，
    比「找不到解释器」更危险（看起来像通过）。
    """
    attempts = []

    configured = (config.get("app_python") or "").strip()
    if configured:
        candidate = configured if os.path.isabs(configured) else os.path.join(root, configured)
        ok, detail = verify_app_python(candidate)
        attempts.append({"source": "config.app_python", "path": candidate, "ok": ok, "detail": detail})
        if ok:
            return os.path.normpath(candidate), "配置 app_python"

    venv_env = (os.environ.get("VIRTUAL_ENV") or "").strip()
    if venv_env:
        candidate = venv_python(venv_env)
        ok, detail = verify_app_python(candidate)
        attempts.append({"source": "VIRTUAL_ENV", "path": candidate, "ok": ok, "detail": detail})
        if ok:
            return os.path.normpath(candidate), "环境变量 VIRTUAL_ENV"

    for name in APP_ENV_DIRS:
        candidate = venv_python(os.path.join(root, name))
        ok, detail = verify_app_python(candidate)
        attempts.append({"source": "candidate_dir:%s" % name, "path": candidate,
                         "ok": ok, "detail": detail})
        if ok:
            return os.path.normpath(candidate), "项目根 %s 目录" % name

    launchers = []
    if os.name == "nt":
        launchers.append(["py", "-3.12"])
    launchers.append(["python"])
    for launcher in launchers:
        try:
            resolved = subprocess.run(
                launcher + ["-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            attempts.append({"source": "launcher:%s" % " ".join(launcher), "path": "",
                             "ok": False, "detail": "启动器不可用"})
            continue
        if resolved.returncode != 0:
            attempts.append({"source": "launcher:%s" % " ".join(launcher), "path": "",
                             "ok": False, "detail": "启动器返回非 0"})
            continue
        output_lines = (resolved.stdout or "").strip().splitlines()
        candidate = output_lines[-1].strip() if output_lines else ""
        ok, detail = verify_app_python(candidate)
        attempts.append({"source": "launcher:%s" % " ".join(launcher), "path": candidate,
                         "ok": ok, "detail": detail})
        if ok:
            return os.path.normpath(candidate), "启动器 %s" % " ".join(launcher)

    lines = ["未找到可用的应用解释器（需能 import ok）。各级探测结果："]
    for item in attempts:
        lines.append("  - %-24s %s -> %s（%s）" % (
            item["source"], item["path"] or "（无）",
            "通过" if item["ok"] else "失败", item["detail"]))
    lines.append("请在上游流程中创建项目虚拟环境并安装依赖，或在 python_lint.config 的 "
                 "app_python 中填写解释器路径。")
    raise EnvError("\n".join(lines))


def find_uv():
    """定位 uv 可执行文件；缺失即抛 EnvError。"""
    found = shutil.which("uv")
    if not found:
        raise EnvError(
            "未找到 uv。本技能统一使用 uv 创建工具环境（python -m venv 后端已弃用：\n"
            "       实测 pip 源不可达时无法安装 ruff，且创建速度与体积均劣于 uv）。\n"
            "       请安装 uv：https://docs.astral.sh/uv/getting-started/installation/"
        )
    return found


def run_uv_sync(root, extra_args, dry_run=False):
    """在包内依赖定义目录执行 uv sync，环境指向项目侧实例。

    关键点：
      - UV_PROJECT_ENVIRONMENT 把实例重定向到项目侧，不污染引擎包目录；
      - --project 指向包内定义目录，与当前工作目录无关；
      - --locked 保证锁与声明不一致时报错（--frozen 会静默忽略，已弃用）。
    """
    uv = find_uv()
    dep_dir = deployment_dir(root)
    if not os.path.isdir(dep_dir):
        raise EnvError("依赖定义目录缺失：%s" % dep_dir)
    for name in ("pyproject.toml", "uv.lock"):
        path = os.path.join(dep_dir, name)
        if not os.path.isfile(path):
            raise EnvError("依赖定义文件缺失：%s" % path)

    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = tool_env_dir(root)

    command = [uv, "sync", "--locked", "--project", dep_dir]
    if dry_run:
        command.append("--check")
    else:
        command += extra_args

    try:
        result = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EnvError("uv sync 执行失败：%s" % error)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode, output


def find_tool_binary(tool_dir, name):
    """在工具环境内查找可执行文件，找不到返回 None。"""
    if os.name == "nt":
        candidate = os.path.join(tool_dir, "Scripts", name + ".exe")
    else:
        candidate = os.path.join(tool_dir, "bin", name)
    return candidate if os.path.isfile(candidate) else None


def cmd_check(root, config, as_json):
    """只读检测：应用解释器可见性 + 工具环境与锁一致性。"""
    payload = {"app_python": None, "app_source": None, "tool_env": None, "ok": False}

    app_python, app_source = detect_app_python(root, config)
    payload["app_python"] = app_python
    payload["app_source"] = app_source

    tool_dir = tool_env_dir(root)
    payload["tool_env"] = tool_dir
    tool_python = venv_python(tool_dir)
    if not os.path.isfile(tool_python):
        payload["tool_reason"] = "工具环境不存在（请运行 ensure）"
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("应用解释器：%s（来源：%s）" % (app_python, app_source))
            print("工具环境：%s（不存在，请运行 ensure）" % tool_dir)
        return 3

    code, output = run_uv_sync(root, [], dry_run=True)
    if code != 0:
        payload["tool_reason"] = "工具环境与 uv.lock 不一致或已过期"
        payload["tool_output"] = output
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("应用解释器：%s（来源：%s）" % (app_python, app_source))
            print("工具环境：%s（与 uv.lock 不一致，请运行 ensure）" % tool_dir)
            if output:
                print(output)
        return 3

    payload["ok"] = True
    payload["tool_python"] = tool_python
    payload["ruff"] = find_tool_binary(tool_dir, "ruff")
    payload["coverage"] = tool_python

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("应用解释器：%s（来源：%s）" % (app_python, app_source))
        print("工具环境：%s（与 uv.lock 一致）" % tool_dir)
        print("ruff：%s" % (payload["ruff"] or "（未找到）"))
    return 0


def cmd_ensure(root, config, force):
    """创建或更新工具环境。"""
    tool_dir = tool_env_dir(root)
    if force and os.path.isdir(tool_dir):
        try:
            shutil.rmtree(tool_dir)
        except OSError as error:
            raise EnvError("删除旧工具环境失败（%s）：%s" % (tool_dir, error))
    os.makedirs(os.path.dirname(tool_dir), exist_ok=True)

    code, output = run_uv_sync(root, [])
    if code != 0:
        raise EnvError("工具环境创建失败（退出码 %d）：\n%s" % (code, output))

    tool_python = venv_python(tool_dir)
    if not os.path.isfile(tool_python):
        raise EnvError("工具环境创建后未找到解释器：%s" % tool_python)
    ruff = find_tool_binary(tool_dir, "ruff")
    if not ruff:
        raise EnvError("工具环境创建后未找到 ruff：%s" % tool_dir)

    if output:
        print(output)
    print("工具环境就绪：%s" % tool_dir)
    print("ruff：%s" % ruff)
    return 0


def cmd_python(root, config):
    """打印应用解释器绝对路径。"""
    app_python, _source = detect_app_python(root, config)
    print(app_python)
    return 0


def cmd_tool(root):
    """打印工具环境解释器与 ruff 路径。"""
    tool_dir = tool_env_dir(root)
    tool_python = venv_python(tool_dir)
    if not os.path.isfile(tool_python):
        raise EnvError("工具环境未就绪：%s\n       请先运行 ensure。" % tool_dir)
    ruff = find_tool_binary(tool_dir, "ruff")
    if not ruff:
        raise EnvError("工具环境内未找到 ruff：%s\n       请重新运行 ensure。" % tool_dir)
    print(tool_python)
    print(ruff)
    return 0


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="python-env：工具环境与应用解释器管理")
    parser.add_argument("command", choices=["check", "ensure", "python", "tool"],
                        help="子命令")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（仅 check 支持）")
    parser.add_argument("--force", action="store_true", help="删除并重建工具环境（仅 ensure 支持）")
    args = parser.parse_args()

    root = find_project_root(os.getcwd())

    try:
        config = load_config(root)
        if args.command == "check":
            return cmd_check(root, config, args.json)
        if args.command == "ensure":
            return cmd_ensure(root, config, args.force)
        if args.command == "python":
            return cmd_python(root, config)
        return cmd_tool(root)
    except EnvError as error:
        print("[FAIL] %s" % error, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
