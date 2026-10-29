#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVN 提交目标清单校验脚本（vcs-svn-commit 技能阶段七辅助）。

背景：
    SVN 没有暂存区，"svn commit" 提交的是目标路径上的全部已版本化改动。因此
    「本笔只提交计划内的文件」这件事**无法靠 git 式的暂存区校验兜住**，必须在提交前后
    各做一次集合比对：

      pre  提交前：目标清单 vs "svn status" 的变更集。用于发现「目标写错/路径不存在/
           该路径根本没有改动」，以及「有改动但没进清单」（会静默漏提交）。
      post 提交后：目标清单 vs "svn log -l 1 -v" 的实际修订路径。用于发现「清单里列了
           目录，实际带上了目录内的计划外文件」。

    两条都不可省：pre 只能证明清单合法，证明不了实际提交了什么；post 只能事后发现，
    发现问题须如实报告并说明差异，不可自行"修正"用户已确认的提交。

路径口径：
    全部按**相对 "svn commit" 执行目录**的路径比对（与目标清单的书写方式一致）。
    "svn log -v" 输出的是仓库绝对路径，脚本用 "svn info" 的工作副本 URL 换算回来。

用法：
    python verify_targets.py --mode pre  --targets <目标清单.txt> [--dir <执行目录>] [--json]
    python verify_targets.py --mode post --targets <目标清单.txt> [--dir <执行目录>] [--revision HEAD] [--json]

参数：
    --mode         pre / post，见上文
    --targets      目标清单文件（每行一个路径；空行与以 # 开头的行忽略）
    --dir          svn 命令执行目录（默认当前目录），须与提交时的执行目录一致
    --json         以 JSON 输出比对结果
    --allow-extras post 模式下允许多出路径（仅校验无缺失）
    --revision     post 模式核对的修订号（默认 HEAD，即刚提交的那笔）

退出码：
    0 —— 一致（或 --allow-extras 下无缺失）
    1 —— 存在不一致（pre：目标无改动或变更未入清单；post：多出或缺失）
    2 —— 参数错误 / 清单读取失败 / svn 命令执行失败
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def run_svn(args, workdir):
    """执行 svn 命令，返回（退出码, 字节标准输出, 标准错误文本）。

    输出按字节返回，由调用方按需解码：Windows 控制台代码页与仓库编码不一致时，
    以文本模式捕获会把中文路径解码成乱码。
    """
    try:
        result = subprocess.run(["svn"] + args, cwd=workdir, capture_output=True)
    except OSError as error:
        return 1, b"", "无法执行 svn 命令（%s）" % error
    return result.returncode, result.stdout, result.stderr.decode("utf-8", errors="replace")


def normalize(path):
    """路径归一化：反斜杠转正斜杠、去除 ./ 前缀与首尾空白。"""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return "" if value == "." else value


def decode_targets(raw):
    """解码目标清单内容：先 UTF-8（含 BOM），失败再退到系统 ANSI 编码。

    为什么需要回退：`svn commit --targets` 在 Windows 上按**控制台 ANSI 码页**解析路径
    （中文环境为 GBK），UTF-8 清单里的中文路径会被解成乱码并以
    "is not under version control / 不在版本控制之下" 失败。因此实际用于提交的清单
    通常写成 GBK，而本脚本若只按 UTF-8 读就会读不出内容——两种编码都必须能读。
    """
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_targets(path):
    """读取目标清单，返回归一化路径列表（忽略空行与 # 注释行）。"""
    with open(path, "rb") as file:
        text = decode_targets(file.read())
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        value = normalize(stripped)
        if value:
            entries.append(value)
    return entries


def changed_paths(workdir):
    """取工作副本的变更集（相对 workdir），返回 (路径集合, 未版本化集合)。

    只收集能进提交的状态：added / deleted / modified / replaced，以及仅有属性变更的项。
    未版本化（?）与已忽略（I）单独返回：它们不会进提交，是「静默漏提交」的常见来源。
    """
    code, stdout, stderr = run_svn(["status", "--xml"], workdir)
    if code != 0:
        raise RuntimeError("svn status 执行失败：%s" % stderr.strip())
    changed, unversioned = set(), set()
    root = ET.fromstring(stdout.decode("utf-8", errors="replace"))
    for target in root.findall("target"):
        for entry in target.findall("entry"):
            path = normalize(entry.get("path") or "")
            status = entry.find("wc-status")
            if status is None or not path:
                continue
            item = status.get("item") or "normal"
            if item == "unversioned":
                unversioned.add(path)
            elif item in ("added", "deleted", "modified", "replaced"):
                changed.add(path)
            elif status.get("props") == "modified":
                # 仅属性变更（如 svn:ignore）：同样属于版本化内容
                changed.add(path)
    return changed, unversioned


def repositories_path(workdir):
    """取工作副本在**仓库内**的绝对路径（如 /Test/trunk），用于换算 svn log 的路径。

    为什么用 `relative-url`（形如 ^/Test/trunk）：svn log -v 输出的路径是**仓库根相对**的
    绝对路径（如 /Test/trunk/a.txt），而 `url` 是完整 URL、`repos-root-url` 是仓库根 URL，
    两者都可能与它不同前缀（仓库根为 /svn/Test 时，URL 却含 /svn/Test/Test/trunk）。
    只有 relative-url 去掉 "^" 后得到的 /Test/trunk 与 svn log 的路径同源，才能正确削前缀。
    """
    code, stdout, stderr = run_svn(["info", "--show-item", "relative-url"], workdir)
    if code != 0:
        raise RuntimeError("svn info 执行失败：%s" % stderr.strip())
    value = stdout.decode("utf-8", errors="replace").strip()
    if value.startswith("^"):
        value = value[1:]
    return value.rstrip("/")


def last_revision_paths(workdir, revision):
    """取指定修订的路径列表（相对 workdir）。

    为什么用 `-r <rev>` 而不是 `-l 1`：`-l 1` 取的是**工作副本当前基线**的最后一次变更，
    刚提交完但尚未 update 时基线仍停在提交前，会拿到上一笔修订的路径，post 校验全部误判。
    默认取 HEAD（即刚提交的那笔），也允许显式传修订号以核对历史修订。
    """
    code, stdout, stderr = run_svn(["log", "-r", revision, "-v", "--xml"], workdir)
    if code != 0:
        raise RuntimeError("svn log 执行失败：%s" % stderr.strip())
    base = repositories_path(workdir)
    paths = set()
    revision_number = ""
    root = ET.fromstring(stdout.decode("utf-8", errors="replace"))
    for entry in root.findall("logentry"):
        revision_number = entry.get("revision") or revision_number
        for path_node in entry.findall("paths/path"):
            raw = (path_node.text or "").strip()
            if not raw:
                continue
            # 仓库绝对路径（以 / 开头）：去掉工作副本在仓库内的路径部分
            rel = raw
            if base and raw.startswith(base + "/"):
                rel = raw[len(base) + 1:]
            else:
                # 提交目标在仓库根之上或不属于本仓库时不换算，保留原样以便人工核对
                rel = raw.lstrip("/")
            paths.add(normalize(rel))
    return paths, revision_number


def covered_by(target, changed):
    """判断目标是否覆盖到实际改动：目标自身在变更集内，或是某变更路径的上级目录。"""
    if target in changed:
        return True
    prefix = target + "/"
    return any(item.startswith(prefix) for item in changed)


def print_list(title, items):
    """打印一组路径（带序号），空列表打印提示。"""
    if not items:
        print("%s：无" % title)
        return
    print("%s（%d）：" % (title, len(items)))
    for index, item in enumerate(items, start=1):
        print("  %d. %s" % (index, item))


def check_pre(targets, workdir, allow_extras):
    """提交前校验：目标必须真能覆盖到改动，且全部改动都在清单内。"""
    changed, unversioned = changed_paths(workdir)
    # 目标无效：路径不在变更集内，也不覆盖任何变更
    invalid = [t for t in targets if not covered_by(t, changed)]
    # 未入清单：有改动但没有任何目标覆盖它
    uncovered = [c for c in sorted(changed)
                 if not any(covered_by(t, {c}) for t in targets)]
    result = {
        "mode": "pre",
        "targets": targets,
        "changed": sorted(changed),
        "unversioned": sorted(unversioned),
        "invalid_targets": invalid,
        "uncovered_changes": uncovered,
    }
    consistent = not invalid and (not uncovered or allow_extras)
    result["consistent"] = consistent
    return result, consistent


def check_post(targets, workdir, allow_extras, revision):
    """提交后校验：实际修订路径与目标清单比对。"""
    committed, revision_number = last_revision_paths(workdir, revision)
    target_set = set(targets)
    extras = sorted(p for p in committed
                    if not any(covered_by(t, {p}) for t in targets))
    missing = sorted(t for t in target_set if not covered_by(t, committed))
    consistent = not missing and (not extras or allow_extras)
    result = {
        "mode": "post",
        "revision": revision_number or revision,
        "targets": targets,
        "committed": sorted(committed),
        "extras": extras,
        "missing": missing,
        "consistent": consistent,
    }
    return result, consistent


def main(argv):
    """脚本主入口。"""
    init_stdout()
    parser = argparse.ArgumentParser(description="SVN 提交目标清单校验")
    parser.add_argument("--mode", required=True, choices=("pre", "post"),
                        help="pre=提交前（目标 vs 变更集）；post=提交后（目标 vs 实际修订路径）")
    parser.add_argument("--targets", required=True, help="目标清单文件（每行一个路径）")
    parser.add_argument("--dir", default=None, help="svn 命令执行目录（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出比对结果")
    parser.add_argument("--allow-extras", action="store_true", help="允许多出/未覆盖（仅校验无缺失）")
    parser.add_argument("--revision", default="HEAD",
                        help="post 模式核对的修订号（默认 HEAD，即刚提交的那笔）")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.targets):
        print("[FAIL] 目标清单文件不存在：%s" % args.targets, file=sys.stderr)
        return 2
    try:
        targets = read_targets(args.targets)
    except OSError as error:
        print("[FAIL] 读取目标清单失败：%s" % error, file=sys.stderr)
        return 2
    if not targets:
        print("[FAIL] 目标清单为空：至少需要一行路径（忽略空行与 # 注释）", file=sys.stderr)
        return 2

    workdir = os.path.abspath(args.dir or os.getcwd())
    try:
        if args.mode == "pre":
            result, consistent = check_pre(targets, workdir, args.allow_extras)
        else:
            result, consistent = check_post(targets, workdir, args.allow_extras, args.revision)
    except (RuntimeError, ET.ParseError) as error:
        print("[FAIL] %s" % error, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if consistent else 1

    if args.mode == "pre":
        if consistent and not result["uncovered_changes"] and not result["invalid_targets"]:
            print("[PASS] 目标清单覆盖全部变更，且每个目标都有对应改动。")
        elif consistent:
            print("[PASS] 无无效目标；%d 项变更未入清单，已按 --allow-extras 放行。"
                  % len(result["uncovered_changes"]))
            print_list("未入清单（有改动、无目标覆盖）", result["uncovered_changes"])
        else:
            print("[FAIL] 目标清单与工作副本变更不一致。")
            print_list("无效目标（该路径没有改动，提交会被拒绝或产生空提交）", result["invalid_targets"])
            print_list("未入清单（有改动、将被漏提交）", result["uncovered_changes"])
    else:
        if consistent and not result["extras"] and not result["missing"]:
            print("[PASS] 实际修订路径与目标清单完全一致（修订 r%s）。" % result["revision"])
        elif consistent:
            print("[PASS] 无缺失路径；%d 项多出已按 --allow-extras 放行。" % len(result["extras"]))
            print_list("多出（实际提交有、清单没有）", result["extras"])
        else:
            print("[FAIL] 实际修订路径与目标清单不一致。")
            print_list("多出（实际提交有、清单没有）", result["extras"])
            print_list("缺失（清单有、实际提交没有）", result["missing"])

    if not consistent and args.mode == "pre":
        print()
        print("[INFO] 处理建议：修正目标清单后重新校验；若已持有 VCS 锁，中止前请先释放：")
        print("       python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py release --session <LOCK_SESSION>")
    if not consistent and args.mode == "post":
        print()
        print("[INFO] 修订已提交，不可回退。请如实向用户报告差异（常见成因：清单里列了目录，")
        print("       目录内的计划外文件被一并带上），不要自行尝试撤销或改写历史。")
    return 0 if consistent else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
