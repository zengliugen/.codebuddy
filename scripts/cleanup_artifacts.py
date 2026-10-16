#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行时产物清理脚本（引擎侧通用工具）。

读取引擎索引 `.codebuddy/project.index.json` 的 `artifacts.dirs`，删除各产物目录中的
运行结果文件并重建空目录（便于后续结果继续落盘）。目录清单完全由索引驱动，脚本不硬编码
任何技能名或路径。

产物目录位于项目侧 `.codebuddy.project/`（不入库、不随引擎共享）。

用法：
  python cleanup_artifacts.py            # 交互确认后清理
  python cleanup_artifacts.py all        # 跳过确认直接清理
  python cleanup_artifacts.py --json     # 以 JSON 输出清理清单（不执行删除）

退出码：
  0 —— 成功（含无待清理文件）
  1 —— 执行错误（删除失败等）
  3 —— 索引缺失、损坏或缺少 artifacts 节
"""

import argparse
import json
import os
import shutil
import sys


class CleanupError(RuntimeError):
    """索引不可用或清理失败时抛出；由入口转为明确的错误退出。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if sys.platform == "win32":
        import ctypes as _ctypes
        try:
            _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            _ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
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


def resolve_artifact_dirs():
    """经索引解析全部产物目录，返回 [(逻辑名, 绝对路径)]。"""
    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        raise CleanupError("未找到 .codebuddy 目录。请在含 .codebuddy 的项目内运行。")
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise CleanupError(
            "未找到项目配置索引：%s\n"
            "       该索引由 .codebuddy 引擎提供；若缺失，请确认引擎包完整。" % index_path
        )
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise CleanupError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    dirs = (index.get("artifacts") or {}).get("dirs")
    if not isinstance(dirs, dict) or not dirs:
        raise CleanupError("索引缺少非空键 `artifacts.dirs`：%s" % index_path)
    project_root = os.path.dirname(codebuddy_dir)
    result = []
    for logical_name, rel in dirs.items():
        if not isinstance(rel, str) or not rel:
            continue
        if os.path.isabs(rel):
            raise CleanupError("索引 `artifacts.dirs.%s` 必须为相对路径：%s" % (logical_name, rel))
        result.append((logical_name, os.path.normpath(os.path.join(project_root, rel))))
    return result


def count_files(path):
    """统计目录下的文件总数（递归）。目录不存在返回 0。"""
    if not os.path.isdir(path):
        return 0
    total = 0
    for _root, _dirs, files in os.walk(path):
        total += len(files)
    return total


def main():
    init_stdout()
    parser = argparse.ArgumentParser(
        description="清理项目侧运行时产物目录（清单由索引 artifacts.dirs 驱动）"
    )
    parser.add_argument("mode", nargs="?", default="",
                        help="传 `all` 跳过交互确认直接清理")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出清理清单（不删除）")
    args = parser.parse_args()

    try:
        targets = resolve_artifact_dirs()
    except CleanupError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    plan = []
    total = 0
    for logical_name, path in targets:
        count = count_files(path)
        total += count
        plan.append({"name": logical_name, "path": path, "files": count})

    if args.json:
        print(json.dumps({"total_files": total, "targets": plan}, ensure_ascii=False, indent=2))
        return 0

    if total == 0:
        print("未发现任何待清理的结果文件，无需清理。")
        return 0

    print("将删除以下产物目录中的全部结果文件（共 %d 个文件），并保留目录结构：" % total)
    print()
    for item in plan:
        if item["files"] > 0:
            print("  [%d 个文件] %s" % (item["files"], item["path"]))
    print()

    if args.mode != "all":
        try:
            confirm = input("确认删除以上全部结果文件？(Y/N)：").strip()
        except EOFError:
            confirm = ""
        if confirm.lower() != "y":
            print("操作已取消，未删除任何文件。")
            return 0

    removed = 0
    for item in plan:
        path = item["path"]
        if not os.path.isdir(path) or item["files"] == 0:
            continue
        try:
            shutil.rmtree(path)
            os.makedirs(path, exist_ok=True)
            removed += item["files"]
        except OSError as error:
            sys.stderr.write("[警告] 清理失败，目录仍有残留：%s（%s）\n" % (path, error))

    print()
    print("清理完成：已删除 %d 个结果文件。" % removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
