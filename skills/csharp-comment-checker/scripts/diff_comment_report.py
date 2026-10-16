#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-comment-checker 报告对比脚本：对比注释修复前后的 JSON 报告。

背景：
    注释修复链路（checker → generator → checker）需要确认修复效果：哪些已清零、哪些残留、
    以及是否有修复过程中**新引入**的问题。手工比对两份报告（数百项）易漏判。

用法：
    python diff_comment_report.py --before <修复前.json> --after <修复后.json> [--json] [--max-residual 200]

参数：
    --before        修复前的 checker JSON 报告
    --after         修复后的 checker JSON 报告
    --json          以 JSON 输出对比结果
    --max-residual  残留清单最多展示条数（默认 200，0 表示不限制）

判定口径：
    - 清零情况：按「文件 × 严重程度」对比修复前后计数；
    - 残留清单：修复后报告中仍存在的问题；
    - 意外新增：按 `(File, Category, RuleName, Member, Message)` 作为**忽略行号的匹配键**，
      在修复后出现、修复前不存在的问题项（用于发现「修复引入新问题」；行号因编辑漂移不入键）。

退出码：
    0 —— 修复后残留为 0
    1 —— 修复后仍有残留
    2 —— 参数/文件/解析错误
"""

import argparse
import json
import os
import sys

SEVERITY_ORDER = ["error", "warning", "info"]


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def normalize(path):
    """路径归一化：反斜杠转正斜杠、去 ./ 前缀。"""
    value = str(path).strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def display_path(path):
    """尽量以相对当前目录的路径展示。"""
    absolute = os.path.abspath(path)
    cwd = os.getcwd()
    if absolute.lower().startswith(cwd.lower()):
        return normalize(os.path.relpath(absolute, cwd))
    return normalize(path)


def severity_of(issue):
    """取问题严重程度（小写）。"""
    return str(issue.get("Severity", "")).strip().lower() or "unknown"


def match_key(issue):
    """构造忽略行号的匹配键（用于判断「同一问题」在修复前后是否仍存在）。"""
    return (
        normalize(issue.get("File", "")),
        str(issue.get("Category", "")),
        str(issue.get("RuleName", "")),
        str(issue.get("Member", "")),
        str(issue.get("Message", "")),
    )


def load_report(path, label):
    """读取报告 JSON（Issue 数组），失败抛出异常。"""
    if not os.path.isfile(path):
        raise ValueError(f"{label}报告文件不存在：{path}")
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{label}报告格式非法（应为 Issue 数组）：{path}")
    return data


def count_by_file_severity(issues):
    """按「文件 → 严重程度 → 计数」聚合。"""
    table = {}
    for issue in issues:
        file_path = normalize(issue.get("File", ""))
        severity = severity_of(issue)
        table.setdefault(file_path, {}).setdefault(severity, 0)
        table[file_path][severity] += 1
    return table


def summarize_counts(issues):
    """汇总总计数。"""
    counts = {"total": len(issues)}
    for severity in SEVERITY_ORDER:
        counts[severity] = sum(1 for issue in issues if severity_of(issue) == severity)
    return counts


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="csharp-comment-checker 修复前后报告对比")
    parser.add_argument("--before", required=True, help="修复前 JSON 报告")
    parser.add_argument("--after", required=True, help="修复后 JSON 报告")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出对比结果")
    parser.add_argument("--max-residual", type=int, default=200, help="残留清单最大条数（0 不限）")
    args = parser.parse_args()

    try:
        before = load_report(args.before, "修复前")
        after = load_report(args.after, "修复后")
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 2

    before_table = count_by_file_severity(before)
    after_table = count_by_file_severity(after)
    before_counts = summarize_counts(before)
    after_counts = summarize_counts(after)

    # 意外新增：修复后存在、修复前不存在（忽略行号匹配）
    before_keys = {match_key(issue) for issue in before}
    unexpected = [issue for issue in after if match_key(issue) not in before_keys]

    # 清零情况：按文件 × 严重程度列出修复前后计数
    all_files = sorted(set(before_table) | set(after_table))
    per_file = []
    for file_path in all_files:
        row = {"file": display_path(file_path), "before": {}, "after": {}}
        for severity in SEVERITY_ORDER:
            row["before"][severity] = before_table.get(file_path, {}).get(severity, 0)
            row["after"][severity] = after_table.get(file_path, {}).get(severity, 0)
        per_file.append(row)

    cleared_files = [row["file"] for row in per_file if sum(row["before"].values()) > 0 and sum(row["after"].values()) == 0]

    result = {
        "before": before_counts,
        "after": after_counts,
        "cleared_files": cleared_files,
        "per_file": per_file,
        "residual_count": len(after),
        "unexpected_count": len(unexpected),
        "unexpected": unexpected,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("== 注释修复前后对比 ==")
        print(
            f"修复前：{before_counts['total']} 项"
            f"（{before_counts['error']} 错误, {before_counts['warning']} 警告, {before_counts['info']} 提示）"
        )
        print(
            f"修复后：{after_counts['total']} 项"
            f"（{after_counts['error']} 错误, {after_counts['warning']} 警告, {after_counts['info']} 提示）"
        )
        print(f"已清零文件：{len(cleared_files)} 个")
        print()
        if after_counts["total"] == 0:
            print("[PASS] 修复后残留为 0，问题已清零。")
        else:
            print(f"[FAIL] 修复后仍有 {after_counts['total']} 项残留，逐文件分布如下：")
            for row in per_file:
                before_total = sum(row["before"].values())
                after_total = sum(row["after"].values())
                if after_total == 0:
                    continue
                print(f"  - {row['file']}：{before_total} → {after_total}")
        if unexpected:
            print()
            print(f"[WARN] 疑似修复引入的新问题 {len(unexpected)} 项：")
            for issue in unexpected[: args.max_residual or len(unexpected)]:
                print(
                    f"  - {display_path(issue.get('File', ''))}:{issue.get('Line', '?')} "
                    f"[{severity_of(issue)}] {issue.get('Message', '')}"
                )
            if args.max_residual and len(unexpected) > args.max_residual:
                print(f"  ...（其余 {len(unexpected) - args.max_residual} 项省略，可用 --max-residual 0 查看全部）")

    return 0 if after_counts["total"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
