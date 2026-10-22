#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-lsp 技能环境检查脚本。

功能：
1. 安装检查 —— 确认 csharp-ls 语言服务器二进制是否可用。
2. 插件开启检查 —— 确认 csharp-lsp@codebuddy-plugins-official 插件已安装且已启用。
3. 本地缓存 —— 检查全部通过后，将结果连同环境指纹写入本地缓存
   （默认项目侧 .codebuddy.project/caches/skills/csharp/csharp-lsp/.cache/ 下，按项目隔离）。当缓存未超过 24 小时有效期且
   环境指纹（csharp-ls 路径、插件版本、settings.json 修改时间/大小）未变化时，
   直接复用上次通过结论，跳过重复检查。失败结果不缓存。

用法：
    python check_env.py [--project <项目绝对路径>] [--no-cache] [--cache-dir <目录>]

参数：
    --project    项目绝对路径（默认取当前工作目录）
    --no-cache   跳过缓存，强制重新检查
    --cache-dir  缓存目录（默认经索引 artifacts 定位到项目侧）

退出码：
    0 —— 全部通过；1 —— 存在未满足项（可修复）；2 —— 运行异常。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 插件标识与版本（与 codebuddy-plugins-official 市场一致）
PLUGIN_ID = "csharp-lsp@codebuddy-plugins-official"
CSHARP_LS = "csharp-ls"

# 缓存配置：缓存格式版本 + 默认有效期（24 小时）
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 24 * 60 * 60


def _find_codebuddy_dir(start):
    """自 start 向上查找名为 `.codebuddy` 的目录；找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        if os.path.basename(current) == ".codebuddy":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _resolve_artifact_dir(logical_name):
    """经索引 `artifacts.dirs` 解析运行时产物目录（相对路径基准为项目根），并确保目录存在。

    产物目录位于项目侧 `.codebuddy.project/`（不入库、不随引擎共享）；脚本不再写入技能目录。
    """
    codebuddy_dir = _find_codebuddy_dir(os.path.dirname(os.path.abspath(__file__)))
    if not codebuddy_dir:
        raise RuntimeError("未能定位 .codebuddy 目录（应位于项目根下）")
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise RuntimeError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise RuntimeError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    rel = (index.get("artifacts") or {}).get("dirs", {}).get(logical_name)
    if not isinstance(rel, str) or not rel:
        raise RuntimeError("索引缺少产物目录项 `artifacts.dirs.%s`：%s" % (logical_name, index_path))
    if os.path.isabs(rel):
        raise RuntimeError("索引 `artifacts.dirs.%s` 必须为相对路径（当前为绝对路径）：%s" % (logical_name, rel))
    path = Path(os.path.normpath(os.path.join(os.path.dirname(codebuddy_dir), rel)))
    path.mkdir(parents=True, exist_ok=True)
    return path


DEFAULT_CACHE_DIR = _resolve_artifact_dir("csharp_lsp.cache")


def print_result(status, message):
    """以统一格式输出检查结果。"""
    symbol = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
    print(f"{symbol.get(status, '[INFO]')} {message}")


def find_project_path(arg_path):
    """解析项目路径：优先命令行参数，回退到当前工作目录。"""
    if arg_path:
        return Path(arg_path).resolve()
    return Path.cwd()


def check_csharp_ls():
    """安装检查：csharp-ls 是否可用。"""
    exe = shutil.which(CSHARP_LS)
    if exe:
        print_result("PASS", f"csharp-ls 已安装，可执行文件：{exe}")
        return True

    # dotnet 全局工具兜底检查（可能已安装但不在当前 PATH）
    try:
        result = subprocess.run(
            ["dotnet", "tool", "list", "--global"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        if "csharp-ls" in result.stdout:
            tools_dir = Path.home() / ".dotnet" / "tools"
            print_result(
                "WARN",
                f"csharp-ls 已安装为 dotnet 全局工具（{tools_dir}），但当前进程 PATH 未包含该目录，需重启 CodeBuddy Code 后生效。",
            )
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print_result(
        "FAIL",
        "csharp-ls 未安装。修复：执行 `dotnet tool install --global csharp-ls`（需要 .NET SDK 6.0+，安装后重启 CodeBuddy Code）。",
    )
    return False


def load_json(path):
    """读取 JSON 文件，失败返回 None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_plugin_installed():
    """插件开启检查（第 1 步）：installed_plugins.json 中是否存在安装记录。"""
    installed_file = Path.home() / ".codebuddy" / "plugins" / "installed_plugins.json"
    if not installed_file.exists():
        print_result("FAIL", f"插件安装清单不存在：{installed_file}")
        return False

    data = load_json(installed_file)
    if not data:
        print_result("FAIL", f"插件安装清单解析失败：{installed_file}")
        return False

    records = data.get("plugins", {}).get(PLUGIN_ID, [])
    if not records:
        print_result("FAIL", f"插件 {PLUGIN_ID} 未安装。修复：执行 `/plugin` 或 `/plugin install {PLUGIN_ID}`。")
        return False

    for record in records:
        version = record.get("version", "?")
        scope = record.get("scope", "?")
        print_result("PASS", f"插件 {PLUGIN_ID} 已安装（version={version}，scope={scope}）")
    return True


def check_plugin_enabled(project_path):
    """插件开启检查（第 2 步）：settings.json 的 enabledPlugins 是否启用插件。"""
    check_locations = [
        ("项目", project_path / ".codebuddy" / "settings.json"),
        ("项目(本地)", project_path / ".codebuddy" / "settings.local.json"),
        ("用户", Path.home() / ".codebuddy" / "settings.json"),
    ]

    enabled = False
    for label, settings_file in check_locations:
        if not settings_file.exists():
            continue
        data = load_json(settings_file)
        if not data:
            continue
        enabled_plugins = data.get("enabledPlugins", {})
        if enabled_plugins.get(PLUGIN_ID) is True:
            print_result("PASS", f"插件已在「{label}设置」中启用：{settings_file}")
            enabled = True

    if not enabled:
        print_result(
            "FAIL",
            f"插件 {PLUGIN_ID} 未启用。修复：编辑 {project_path / '.codebuddy' / 'settings.json'}，"
            f"在 enabledPlugins 中添加 \"{PLUGIN_ID}\": true，然后重启 CodeBuddy Code。",
        )
    return enabled


def check_plugin_loaded(project_path):
    """插件开启检查（第 3 步，动态验证）：当前会话是否已加载插件（.in_use 标记）。

    该状态随会话变化，不做缓存，缓存命中时仍执行作为提示。
    """
    plugin_root = Path.home() / ".codebuddy" / "plugins" / "cache" / "codebuddy-plugins-official" / "csharp-lsp"
    versions = list(plugin_root.glob("*/")) if plugin_root.exists() else []
    for version_dir in versions:
        in_use_dir = version_dir / ".in_use"
        if in_use_dir.exists() and any(in_use_dir.iterdir()):
            print_result("PASS", f"插件当前会话已加载：{version_dir}")
            return True
    print_result("WARN", "未检测到插件加载标记（.in_use）。若上述检查均通过，建议重启 CodeBuddy Code 后再动态验证。")
    return False


def file_fingerprint(path):
    """返回文件指纹（修改时间 + 大小），文件不存在返回 None。"""
    try:
        stat = path.stat()
        return {"mtime": stat.st_mtime, "size": stat.st_size}
    except OSError:
        return None


def collect_fingerprints(project_path):
    """轻量采集环境指纹，用于缓存命中比对。

    对应三项静态检查（csharp-ls 安装、插件安装、插件启用）的输入：
    - csharp-ls 可执行文件路径与修改时间
    - installed_plugins.json 修改时间、大小、插件版本列表
    - 三处 settings.json（项目/项目本地/用户）修改时间与大小
    """
    fingerprints = {}

    # ① csharp-ls 安装指纹
    exe = shutil.which(CSHARP_LS)
    if exe is None:
        fingerprints["csharp_ls"] = None
    else:
        exe_fp = file_fingerprint(Path(exe))
        fingerprints["csharp_ls"] = {"path": exe, "mtime": exe_fp["mtime"] if exe_fp else None}

    # ② 插件安装指纹
    installed_file = Path.home() / ".codebuddy" / "plugins" / "installed_plugins.json"
    versions = []
    data = load_json(installed_file)
    if data:
        records = data.get("plugins", {}).get(PLUGIN_ID, [])
        versions = sorted(record.get("version", "") for record in records)
    fingerprints["plugin_installed"] = {
        "file": file_fingerprint(installed_file),
        "versions": versions,
    }

    # ③ 插件启用指纹（三处 settings.json）
    settings_files = {
        "project": project_path / ".codebuddy" / "settings.json",
        "project_local": project_path / ".codebuddy" / "settings.local.json",
        "user": Path.home() / ".codebuddy" / "settings.json",
    }
    fingerprints["plugin_enabled"] = {
        label: file_fingerprint(path) for label, path in settings_files.items()
    }

    return fingerprints


def cache_file_for(project_path, cache_dir):
    """按项目路径生成缓存文件名（哈希隔离，避免跨项目串用）。"""
    key = str(project_path)
    # Windows 路径不区分大小写，统一小写避免同一项目生成不同缓存文件
    if os.name == "nt":
        key = key.lower()
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"env_check_{digest}.json"


def load_cache(cache_file):
    """读取缓存文件，格式不兼容或缺失返回 None。"""
    data = load_json(cache_file)
    if not data or data.get("version") != CACHE_VERSION:
        return None
    return data


def cache_is_fresh(cache_data, current_fingerprints):
    """缓存是否可用：未超过 TTL 且环境指纹完全一致。"""
    now = time.time()
    checked_at = cache_data.get("checked_at", 0)
    ttl = cache_data.get("ttl_seconds", CACHE_TTL_SECONDS)
    if (now - checked_at) > ttl:
        return False
    return cache_data.get("fingerprints") == current_fingerprints


def save_cache(cache_file, project_path, fingerprints):
    """写入通过结果的缓存标记。"""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CACHE_VERSION,
        "checked_at": time.time(),
        "checked_at_readable": datetime.now().isoformat(timespec="seconds"),
        "ttl_seconds": CACHE_TTL_SECONDS,
        "project_path": str(project_path),
        "fingerprints": fingerprints,
    }
    cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_cache(cache_file):
    """检查失败时清理过期缓存，避免残留的"通过"结论误导后续调用。"""
    try:
        cache_file.unlink(missing_ok=True)
    except OSError:
        pass


def main():
    # Windows 下统一以 UTF-8 输出（无论是否 TTY，均与项目编码规范一致），
    # 且显式关闭 \n 到 \r\n 的翻译，避免 git-bash 渲染产生杂讯。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")

    parser = argparse.ArgumentParser(description="csharp-lsp 技能环境检查")
    parser.add_argument("--project", default=None, help="项目绝对路径（默认取当前工作目录）")
    parser.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新检查")
    parser.add_argument("--cache-dir", default=None, help="缓存目录（默认经索引 artifacts 定位到项目侧）")
    args = parser.parse_args()

    project_path = find_project_path(args.project)
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else DEFAULT_CACHE_DIR
    cache_file = cache_file_for(project_path, cache_dir)

    current_fingerprints = collect_fingerprints(project_path)

    # 缓存命中：24 小时内检查通过且环境指纹未变化，直接复用上次结论
    if not args.no_cache:
        cached = load_cache(cache_file)
        if cached and cache_is_fresh(cached, current_fingerprints):
            print(f"== csharp-lsp 环境检查（项目：{project_path}）==")
            print(
                f"[INFO] 缓存命中：上次检查通过于 {cached.get('checked_at_readable')}，"
                f"环境指纹（csharp-ls 路径/插件版本/settings.json）未变化，跳过重复检查。"
            )
            print(f"[INFO] 缓存文件：{cache_file}")
            print("[INFO] 如需强制重查，请运行：python check_env.py --no-cache")
            # 动态验证（.in_use）随会话变化，不缓存，仅作提示
            check_plugin_loaded(project_path)
            print()
            print("结论：环境就绪（缓存），可以调用 LSP 工具获取 C# 代码智能。")
            return 0
        if cached:
            print("[INFO] 缓存未命中（已超过有效期或环境指纹变化），重新检查。")

    print(f"== csharp-lsp 环境检查（项目：{project_path}）==")
    print(f"[INFO] 检查目标：{CSHARP_LS} 安装状态 + {PLUGIN_ID} 插件开启状态\n")

    results = [
        check_csharp_ls(),
        check_plugin_installed(),
        check_plugin_enabled(project_path),
    ]
    # 动态验证（.in_use）仅作提示，不阻塞
    check_plugin_loaded(project_path)

    print()
    if all(results):
        save_cache(cache_file, project_path, current_fingerprints)
        print(
            "结论：环境就绪，可以调用 LSP 工具获取 C# 代码智能。"
            f"（已写入本地缓存 {cache_file}，24 小时内环境未变化将跳过重复检查）"
        )
        return 0

    # 检查失败不缓存，并清理可能残留的旧缓存
    clear_cache(cache_file)
    print("结论：存在未满足项，按上方 [FAIL]/[WARN] 指引修复后重试。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
