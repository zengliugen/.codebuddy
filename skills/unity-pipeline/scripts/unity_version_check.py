#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unity-pipeline 版本一致性检查脚本：比对编辑器实际版本与项目声明版本。

背景：
    项目文档曾硬编码 Unity 版本（如 6000.3.18f1），但实际运行编辑器版本可能不同
    （如 6000.5.7f1），导致认知失配。权威来源应为 `ProjectSettings/ProjectVersion.txt`
    （项目声明）与正在运行的编辑器（`unity command editor_status`）。本脚本做两件事：
    1. 比对编辑器实际版本与项目声明版本，不一致时告警；
    2. 扫描规则文档中残留的硬编码版本号（约定「以 Hub 实际安装为准」，不应写死版本）。

用法：
    python unity_version_check.py [--project-version-file ProjectSettings/ProjectVersion.txt]
                                  [--rules-dir .codebuddy/rules] [--skip-editor]
                                  [--unity unity] [--json]

参数：
    --project-version-file 项目版本声明文件（默认 ProjectSettings/ProjectVersion.txt）
    --rules-dir            规则文档目录，用于扫描硬编码版本（默认 .codebuddy/rules）
    --skip-editor          跳过编辑器查询（编辑器未运行时使用）
    --unity                unity 命令名或路径（默认 unity）
    --json                 以 JSON 输出检查结果

退出码：
    0 —— 一致（编辑器版本与项目声明相符）
    1 —— 不一致（编辑器版本 ≠ 项目声明版本）
    2 —— 无法确定项目版本（文件缺失/解析失败）
"""

import argparse
import json
import os
import re
import subprocess
import sys

# Unity 版本号形如 6000.5.7f1 / 2022.3.10f1
VERSION_PATTERN = re.compile(r"\b(\d{4}\.\d+\.\d+[abfp]\d+)\b")


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def read_project_version(path):
    """从 ProjectVersion.txt 读取 m_EditorVersion。返回（版本, 错误信息）。"""
    if not os.path.isfile(path):
        return None, f"项目版本声明文件不存在：{path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            for line in file:
                if line.strip().lower().startswith("m_editorversion:"):
                    return line.split(":", 1)[1].strip(), None
    except OSError as error:
        return None, f"读取项目版本文件失败：{error}"
    return None, f"未在 {path} 中找到 m_EditorVersion"


def query_editor_version(unity):
    """查询正在运行编辑器的版本，返回（版本, 错误信息）。编辑器未运行时版本为 None。"""
    try:
        result = subprocess.run(
            [unity, "command", "editor_status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"调用 editor_status 失败：{error}"

    text = result.stdout or ""
    start = text.find("{")
    if start == -1:
        return None, "editor_status 未返回可解析 JSON（编辑器可能未运行）"
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None, "editor_status 返回的 JSON 解析失败"

    for key, value in payload.items():
        if str(key).lower() == "unityversion":
            return str(value).strip(), None
    return None, "editor_status 结果中缺少 unityVersion 字段"


def scan_hardcoded_versions(rules_dir):
    """扫描规则目录中硬编码的 Unity 版本号，返回 [(文件, 行号, 版本)]。"""
    found = []
    if not os.path.isdir(rules_dir):
        return found
    for root, _dirs, files in os.walk(rules_dir):
        for name in files:
            if not name.lower().endswith((".mdc", ".md")):
                continue
            file_path = os.path.join(root, name)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as file:
                    for index, line in enumerate(file, start=1):
                        for match in VERSION_PATTERN.findall(line):
                            found.append((file_path.replace("\\", "/"), index, match))
            except OSError:
                continue
    return found


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="unity-pipeline 版本一致性检查")
    parser.add_argument("--project-version-file", default=os.path.join("ProjectSettings", "ProjectVersion.txt"),
                        help="项目版本声明文件（默认 ProjectSettings/ProjectVersion.txt）")
    parser.add_argument("--rules-dir", default=os.path.join(".codebuddy", "rules"), help="规则文档目录（默认 .codebuddy/rules）")
    parser.add_argument("--skip-editor", action="store_true", help="跳过编辑器查询")
    parser.add_argument("--unity", default="unity", help="unity 命令名或路径（默认 unity）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    args = parser.parse_args()

    project_version, error = read_project_version(args.project_version_file)
    if project_version is None:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 2

    editor_version = None
    editor_error = "（已跳过编辑器查询）"
    if not args.skip_editor:
        editor_version, editor_error = query_editor_version(args.unity)

    hardcoded = scan_hardcoded_versions(args.rules_dir)
    hardcoded_mismatch = [item for item in hardcoded if item[2] != project_version]

    editor_mismatch = editor_version is not None and editor_version != project_version
    result = {
        "project_version": project_version,
        "editor_version": editor_version,
        "editor_query_error": editor_error if editor_version is None else None,
        "hardcoded_versions": [{"file": f, "line": n, "version": v} for f, n, v in hardcoded],
        "hardcoded_mismatch": [{"file": f, "line": n, "version": v} for f, n, v in hardcoded_mismatch],
        "consistent": not editor_mismatch,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("== Unity 版本一致性检查 ==")
        print(f"项目声明版本（{args.project_version_file}）：{project_version}")
        if editor_version is not None:
            print(f"编辑器实际版本（editor_status）：{editor_version}")
        else:
            print(f"编辑器实际版本：未取得（{editor_error}）")
        print()
        if editor_mismatch:
            print(f"[FAIL] 编辑器实际版本 {editor_version} 与项目声明版本 {project_version} 不一致。")
            print("       请用匹配项目版本的编辑器打开（`unity open .`），或确认项目已升级后更新 ProjectVersion.txt。")
        elif editor_version is not None:
            print("[PASS] 编辑器实际版本与项目声明版本一致。")
        else:
            print("[WARN] 未能取得编辑器版本，跳过编辑器一致性判定。")
        if hardcoded_mismatch:
            print()
            print(f"[WARN] 规则文档中发现 {len(hardcoded_mismatch)} 处疑似硬编码版本（约定『以 Hub 实际安装为准』，不应写死）：")
            for file_path, line_no, version in hardcoded_mismatch:
                print(f"       {file_path}:{line_no} → {version}")
        elif hardcoded:
            print()
            print(f"[INFO] 规则文档中有 {len(hardcoded)} 处版本号（均与项目声明一致）。")

    return 1 if editor_mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
