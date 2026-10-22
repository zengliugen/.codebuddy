#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-comment-checker 报告切片脚本：把 checker 的 JSON 报告按文件切成若干组，供并行修复。

背景：
    大目录注释修复时，报告可能有数百项、分布在十余个文件。人工统计后再分派容易出错，
    且若同一文件被分到两个并行修复组，两个 Agent 会并发改写同一 `.cs` 互相覆盖。
    本脚本按**文件**切片，保证每个文件只出现在一个组中。

用法：
    python split_report.py --json <报告.json> --groups 5 --out-dir <目录>
                           [--max-per-group 200] [--group-by file]

参数：
    --json           checker 产出的 JSON 报告（Issue 数组）
    --groups         期望的组数（默认 5）；实际组数会按 --max-per-group 上调
    --out-dir        切片输出目录（生成 groupN.md 与 groups_summary.md）
    --max-per-group  每组问题数上限（默认 200），超出时自动增加组数
    --group-by       分组维度，当前仅支持 file（默认）

输出：
    <out-dir>/groupN.md        每组一份：文件清单 + error/warning/info 计数 + 问题行号表
    <out-dir>/groups_summary.md 全组概览（每组问题数、文件数、判重提示）

关键约束：
    **各组的文件集必须互斥**。本脚本按文件整体分配，天然满足；请勿在派发时手工把
    同一文件拆分到两组（会导致并行 generator 写同一文件互相覆盖）。

退出码：
    0 —— 切片成功
    1 —— 参数/数据错误（报告为空、JSON 非法、目录不可写等）
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def normalize(path):
    """路径归一化：反斜杠转正斜杠，便于跨来源比较。"""
    return str(path).strip().replace("\\", "/")


def display_path(path):
    """尽量以相对当前目录的路径展示，否则返回原路径。"""
    absolute = os.path.abspath(path)
    cwd = os.getcwd()
    if absolute.lower().startswith(cwd.lower()):
        relative = os.path.relpath(absolute, cwd)
        return normalize(relative)
    return normalize(path)


def severity_of(issue):
    """取问题严重程度（小写），缺失返回 unknown。"""
    return str(issue.get("Severity", "")).strip().lower() or "unknown"


def count_severities(issues):
    """统计一组问题的 error/warning/info 数量。"""
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        severity = severity_of(issue)
        if severity in counts:
            counts[severity] += 1
    return counts


def group_files(issues_by_file, group_count):
    """按文件把问题尽量均匀地分配到 group_count 组（LPT 贪心：大文件优先，进最小负载组）。

    返回 groups：列表，每项为该组的文件路径列表。文件不可拆分，故各组文件集天然互斥。
    """
    groups = [[] for _ in range(group_count)]
    loads = [0] * group_count
    # 按问题数降序，先安排大文件，减少组间不均衡
    ordered = sorted(issues_by_file.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for file_path, issues in ordered:
        index = loads.index(min(loads))
        groups[index].append(file_path)
        loads[index] += len(issues)
    return groups


def render_group(group_index, files, issues_by_file):
    """生成单组 Markdown 内容。"""
    group_issues = [issue for file_path in files for issue in issues_by_file[file_path]]
    counts = count_severities(group_issues)
    lines = [
        f"# 注释修复分组 {group_index}",
        "",
        f"**生成时间:** {datetime.now().strftime('%Y年%m月%d日%H时%M分%S秒')}",
        f"**问题总数:** {len(group_issues)}（{counts['error']} 错误, {counts['warning']} 警告, {counts['info']} 提示）",
        f"**文件数:** {len(files)}",
        "",
        "> **派发约束**：本组仅修改下列文件；各组文件集互斥，禁止跨组修改同一文件。",
        "",
        "## 文件清单",
        "",
    ]
    for file_path in files:
        lines.append(f"- `{display_path(file_path)}`（{len(issues_by_file[file_path])} 项）")

    lines += ["", "## 问题行号表", ""]
    for file_path in files:
        lines.append(f"### {display_path(file_path)}")
        lines.append("")
        lines.append("| 行号 | 严重程度 | 类别 | 规则 | 消息 |")
        lines.append("|------|---------|------|------|------|")
        for issue in sorted(issues_by_file[file_path], key=lambda i: i.get("Line", 0) or 0):
            lines.append(
                "| {line} | {severity} | `{category}` | `{rule}` | {message} |".format(
                    line=issue.get("Line", "?"),
                    severity=severity_of(issue),
                    category=issue.get("Category", ""),
                    rule=issue.get("RuleName", ""),
                    message=str(issue.get("Message", "")).replace("|", "\\|"),
                )
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_summary(groups, issues_by_file):
    """生成全组概览 Markdown。"""
    lines = [
        "# 注释修复分组概览",
        "",
        f"**生成时间:** {datetime.now().strftime('%Y年%m月%d日%H时%M分%S秒')}",
        f"**组数:** {len(groups)}",
        "",
        "> 各组文件集互斥；全部组完成后须由主会话**复扫全目录**确认清零。",
        "",
        "| 组 | 文件数 | 问题数 | 错误 | 警告 | 提示 |",
        "|----|-------|-------|------|------|------|",
    ]
    for index, files in enumerate(groups, start=1):
        issues = [issue for file_path in files for issue in issues_by_file[file_path]]
        counts = count_severities(issues)
        lines.append(
            f"| {index} | {len(files)} | {len(issues)} | {counts['error']} | {counts['warning']} | {counts['info']} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="csharp-comment-checker 报告切片（按文件互斥分组）")
    parser.add_argument("--json", required=True, help="checker 产出的 JSON 报告路径")
    parser.add_argument("--groups", type=int, default=5, help="期望组数（默认 5）")
    parser.add_argument("--out-dir", required=True, help="切片输出目录")
    parser.add_argument("--max-per-group", type=int, default=200, help="每组问题数上限（默认 200）")
    parser.add_argument("--group-by", default="file", choices=["file"], help="分组维度（当前仅 file）")
    args = parser.parse_args()

    if args.groups <= 0 or args.max_per_group <= 0:
        print("[FAIL] --groups 与 --max-per-group 必须为正整数", file=sys.stderr)
        return 1

    if not os.path.isfile(args.json):
        print(f"[FAIL] 报告文件不存在：{args.json}", file=sys.stderr)
        return 1

    try:
        with open(args.json, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError) as error:
        print(f"[FAIL] 读取/解析报告失败：{error}", file=sys.stderr)
        return 1

    if not isinstance(data, list) or not data:
        print("[FAIL] 报告为空或格式非法（应为 Issue 数组）", file=sys.stderr)
        return 1

    issues_by_file = {}
    for issue in data:
        if not isinstance(issue, dict):
            continue
        file_path = normalize(issue.get("File", ""))
        if not file_path:
            continue
        issues_by_file.setdefault(file_path, []).append(issue)

    if not issues_by_file:
        print("[FAIL] 报告中未找到任何文件字段（File）", file=sys.stderr)
        return 1

    total = sum(len(v) for v in issues_by_file.values())
    # 组数取「期望组数」与「按上限所需组数」的较大者
    required_by_cap = max(1, math.ceil(total / args.max_per_group))
    group_count = max(args.groups, required_by_cap)

    groups = group_files(issues_by_file, group_count)

    try:
        os.makedirs(args.out_dir, exist_ok=True)
        for index, files in enumerate(groups, start=1):
            group_path = os.path.join(args.out_dir, f"group{index}.md")
            with open(group_path, "w", encoding="utf-8") as file:
                file.write(render_group(index, files, issues_by_file))
        summary_path = os.path.join(args.out_dir, "groups_summary.md")
        with open(summary_path, "w", encoding="utf-8") as file:
            file.write(render_summary(groups, issues_by_file))
    except OSError as error:
        print(f"[FAIL] 写入切片文件失败：{error}", file=sys.stderr)
        return 1

    print(
        f"[PASS] 已切片：{len(issues_by_file)} 个文件 / {total} 项问题 → {group_count} 组，"
        f"输出目录 {args.out_dir}"
    )
    for index, files in enumerate(groups, start=1):
        issues = sum(len(issues_by_file[f]) for f in files)
        print(f"  group{index}.md：{len(files)} 个文件 / {issues} 项")
    print(f"  概览：{normalize(summary_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
