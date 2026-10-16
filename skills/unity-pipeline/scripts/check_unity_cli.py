#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unity-pipeline 技能环境检查脚本：Unity CLI 安装状态检查。

功能：
1. 安装检查 —— 确认 `unity` 命令是否在 PATH 且可执行（`unity --version` 验证）。
2. 本地缓存 —— 检查通过后，将结果连同环境指纹写入本地缓存
   （默认项目侧 .codebuddy.project/skills/unity-pipeline/.cache/ 下，Unity CLI 为机器级安装，不按项目隔离）。
   当缓存未超过 24 小时有效期且环境指纹（unity 命令路径、版本输出）未变化时，
   直接复用上次通过结论，跳过重复检查。失败结果不缓存。

用法：
    python check_unity_cli.py [--no-cache] [--cache-dir <目录>]

参数：
    --no-cache   跳过缓存，强制重新检查
    --cache-dir  缓存目录（默认经索引 artifacts 定位到项目侧）

退出码：
    0 —— CLI 就绪；1 —— 未安装/不可执行（需按指引安装）；2 —— 运行异常。
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

# Unity CLI 命令名与安装位置说明
UNITY_CMD = "unity"
UNITY_INSTALL_HINT = (
    f"Unity CLI 未安装。修复：执行技能内置离线安装脚本"
    f"`powershell -ExecutionPolicy Bypass -File <技能目录>\\tools\\unity-cli-offline\\install.ps1`"
    f"（离线优先 + 在线回退，安装后重启 CodeBuddy Code）。"
)

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


DEFAULT_CACHE_DIR = _resolve_artifact_dir("unity_pipeline.cache")
CACHE_FILE_NAME = "unity_cli_ok.json"


def print_result(status, message):
    """以统一格式输出检查结果。"""
    symbol = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
    print(f"{symbol.get(status, '[INFO]')} {message}")


def load_json(path):
    """读取 JSON 文件，失败返回 None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_unity_version():
    """执行 `unity --version` 获取版本输出，失败返回 None。"""
    try:
        result = subprocess.run(
            [UNITY_CMD, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def collect_fingerprints():
    """采集环境指纹：unity 命令路径 + 版本输出。"""
    exe = shutil.which(UNITY_CMD)
    if exe is None:
        return {"unity": None, "version": None}
    version = get_unity_version()
    return {"unity": exe, "version": version}


def cache_file_for(cache_dir):
    """生成缓存文件路径（CLI 为机器级安装，单一缓存文件）。"""
    return cache_dir / CACHE_FILE_NAME


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


def save_cache(cache_file, fingerprints):
    """写入通过结果的缓存标记。"""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CACHE_VERSION,
        "checked_at": time.time(),
        "checked_at_readable": datetime.now().isoformat(timespec="seconds"),
        "ttl_seconds": CACHE_TTL_SECONDS,
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

    parser = argparse.ArgumentParser(description="unity-pipeline 技能环境检查（Unity CLI 安装状态）")
    parser.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新检查")
    parser.add_argument("--cache-dir", default=None, help="缓存目录（默认经索引 artifacts 定位到项目侧）")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else DEFAULT_CACHE_DIR
    cache_file = cache_file_for(cache_dir)
    current_fingerprints = collect_fingerprints()

    # 缓存命中：24 小时内检查通过且环境指纹未变化，直接复用上次结论
    if not args.no_cache:
        cached = load_cache(cache_file)
        if cached and cache_is_fresh(cached, current_fingerprints):
            print("== Unity CLI 环境检查 ==")
            print(
                f"[INFO] 缓存命中：上次检查通过于 {cached.get('checked_at_readable')}，"
                f"环境指纹（unity 命令路径/版本）未变化，跳过重复检查。"
            )
            print(f"[INFO] 缓存文件：{cache_file}")
            print("[INFO] 如需强制重查，请运行：python check_unity_cli.py --no-cache")
            print()
            print("结论：Unity CLI 就绪（缓存），可以直接调用 unity 命令。")
            return 0
        if cached:
            print("[INFO] 缓存未命中（已超过有效期或环境指纹变化），重新检查。")

    print("== Unity CLI 环境检查 ==")
    print(f"[INFO] 检查目标：{UNITY_CMD} 命令安装状态与可执行性\n")

    exe = shutil.which(UNITY_CMD)
    if exe is None:
        print_result("FAIL", UNITY_INSTALL_HINT)
        clear_cache(cache_file)
        print()
        print("结论：Unity CLI 未安装，按上方指引执行安装后重试。")
        return 1

    version = get_unity_version()
    if version is None:
        print_result("FAIL", f"找到 {UNITY_CMD}（{exe}），但 `{UNITY_CMD} --version` 验证失败。建议重装或修复 PATH 后重试。")
        clear_cache(cache_file)
        print()
        print("结论：Unity CLI 不可执行，修复后重试。")
        return 1

    print_result("PASS", f"Unity CLI 已安装，可执行文件：{exe}")
    print_result("PASS", f"Unity CLI 版本：{version}")

    save_cache(cache_file, current_fingerprints)
    print()
    print(
        "结论：Unity CLI 就绪，可以调用 unity 命令。"
        f"（已写入本地缓存 {cache_file}，24 小时内环境未变化将跳过重复检查）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
