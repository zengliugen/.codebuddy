#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git-commit 暂存区校验脚本：比对 `git diff --cached` 与本笔提交计划清单。

背景：
    提交规范要求「暂存区多出/缺失本笔计划文件即中止」，但手工用
    `git diff --cached --name-only | wc -l` 加肉眼比对容易漏判。本脚本做确定性集合比对，
    防止把后续组的文件或他会话的文件误提交。

用法：
    python verify_staged.py --expect-file <本笔计划清单.txt> [--json] [--allow-extras]
                            [--ignore-meta] [--dir <仓库目录>]

参数：
    --expect-file  本笔提交计划清单文件（每行一个路径；空行与以 # 开头的行忽略）
    --json         以 JSON 输出比对结果（extras/missing/staged/expected）
    --allow-extras 允许多出文件（仅校验无缺失），用于「多出但确认可接受」场景
    --ignore-meta  比对时忽略 .meta 文件（Unity 目录元数据）
    --dir          git 命令执行目录（默认当前目录）

输出：
    完全一致：打印通过提示，退出码 0。
    不一致：分别打印「多出（暂存区有、计划没有）」与「缺失（计划有、暂存区没有）」，退出码 1。
            并提示先释放 VCS 锁再调整暂存区。

退出码：
    0 —— 暂存区与本笔计划完全一致（或 --allow-extras 下无缺失）
    1 —— 存在多出或缺失文件
    2 —— 参数错误 / 清单文件读取失败 / git 命令执行失败
"""

import argparse
import json
import os
import subprocess
import sys


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def normalize(path):
    """路径归一化：反斜杠转正斜杠、去除 ./ 前缀、去除首尾空白。"""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def read_expect_file(path):
    """读取本笔计划清单，返回归一化路径列表（忽略空行与 # 注释行）。"""
    entries = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            entries.append(normalize(stripped))
    return entries


def get_staged_files(workdir):
    """取暂存区文件名列表（-z 以 NUL 分隔，避免路径含空格/引号时的转义干扰）。

    使用 `--relative` 使输出相对「git 命令执行目录」（即当前目录 / --dir），
    与 `git status --short` 及提交计划清单的书写方式一致——否则当执行目录是仓库根的
    子目录（monorepo）时，git 默认输出仓库根相对路径，会与本笔计划清单比对不上。
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--relative", "-z"],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff --cached 执行失败")
    return [normalize(item) for item in result.stdout.split("\0") if item.strip()]


def drop_meta(paths):
    """按需剔除 .meta 文件。"""
    return [p for p in paths if not p.lower().endswith(".meta")]


def print_list(title, items):
    """打印一组路径（带序号），空列表打印提示。"""
    if not items:
        print(f"{title}：无")
        return
    print(f"{title}（{len(items)}）：")
    for index, item in enumerate(items, start=1):
        print(f"  {index}. {item}")


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="git-commit 暂存区与本笔提交计划比对")
    parser.add_argument("--expect-file", required=True, help="本笔提交计划清单文件（每行一个路径）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出比对结果")
    parser.add_argument("--allow-extras", action="store_true", help="允许多出文件（仅校验无缺失）")
    parser.add_argument("--ignore-meta", action="store_true", help="比对时忽略 .meta 文件")
    parser.add_argument("--dir", default=None, help="git 命令执行目录（默认当前目录）")
    args = parser.parse_args()

    if not os.path.isfile(args.expect_file):
        print(f"[FAIL] 计划清单文件不存在：{args.expect_file}", file=sys.stderr)
        return 2

    try:
        expected = read_expect_file(args.expect_file)
    except OSError as error:
        print(f"[FAIL] 读取计划清单失败：{error}", file=sys.stderr)
        return 2

    if not expected:
        print("[FAIL] 计划清单为空：至少需要一行路径（忽略空行与 # 注释）", file=sys.stderr)
        return 2

    workdir = args.dir or os.getcwd()
    try:
        staged = get_staged_files(workdir)
    except RuntimeError as error:
        print(f"[FAIL] 获取暂存区失败：{error}", file=sys.stderr)
        return 2

    if args.ignore_meta:
        expected = drop_meta(expected)
        staged = drop_meta(staged)

    expected_set = set(expected)
    staged_set = set(staged)
    extras = sorted(staged_set - expected_set)
    missing = sorted(expected_set - staged_set)

    consistent = not missing and (not extras or args.allow_extras)

    if args.json:
        print(
            json.dumps(
                {
                    "staged": sorted(staged_set),
                    "expected": sorted(expected_set),
                    "extras": extras,
                    "missing": missing,
                    "consistent": consistent,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not extras and not missing:
            print("[PASS] 暂存区与本笔提交计划完全一致。")
        elif consistent:
            # --allow-extras 且无缺失：放行，但如实展示多出文件
            print(f"[PASS] 无缺失文件；多出 {len(extras)} 个已按 --allow-extras 放行。")
            print_list("多出（暂存区有、计划没有）", extras)
        else:
            print("[FAIL] 暂存区与本笔提交计划不一致。")
            print_list("多出（暂存区有、计划没有）", extras)
            print_list("缺失（计划有、暂存区没有）", missing)

    if not consistent and not args.json:
        print()
        print("[INFO] 处理建议：先调整暂存区（git add <本笔路径> / git reset <非本笔路径>），"
              "再重新校验；若已持有 VCS 锁，中止前请先释放：")
        print("       python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py release --session <LOCK_SESSION>")
    return 0 if consistent else 1


if __name__ == "__main__":
    sys.exit(main())
