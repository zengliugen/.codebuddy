#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVN 工作副本变更收集脚本（vcs-svn-commit 技能阶段一辅助）。

功能：
    - 解析 `svn status --xml`，把七列状态归一化为结构化 JSON；
    - 按「可提交 / 未版本化 / 已忽略 / 阻塞」四类分组，标出冲突、缺失、树冲突、锁、
      服务端新版本等需要人工确认的项；
    - 递归收集 `svn:ignore` 属性（忽略规则是版本化属性，不在工作区文件里，
      必须用命令读取，不能凭记忆或按 .gitignore 的经验推断）。

为什么需要脚本：
    `svn status` 的七列表头为空，靠目视逐列判断「哪些能提交、哪些在阻塞」
    容易漏看第二列（属性）与第四列（树冲突）；且未版本化项（`?`）不会进入提交也
    不报错，是 SVN 最容易静默漏提交的地方。把判定固化进脚本，避免靠肉眼比对。

用法：
    python collect_svn_changes.py [--dir 工作副本目录] [--no-ignore] [--show-updates] [--json]

参数：
    --dir        工作副本目录（默认当前工作目录），status 路径相对该目录输出
    --no-ignore  同时列出已忽略项（等价 svn status --no-ignore），用于核对误 add
    --show-updates  同时与服务器比对（-u），用于发现服务端已有新版本的路径
    --json       强制以 JSON 输出（默认行为，保留该参数以便与既有脚本习惯一致）

输出：
    stdout 输出 JSON；含 `blocking` 非空时退出码 1（存在阻断项，须先处理）。

退出码：
    0 —— 收集完成且无阻断项
    1 —— 收集完成但存在阻断项（冲突 / 缺失 / 树冲突 / 阻塞状态）
    2 —— 参数错误或 svn 命令执行失败（非工作副本、svn 未安装等）
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET


def init_stdout():
    """Windows 控制台下强制 UTF-8 输出，避免中文路径乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def run_svn(args, workdir):
    """在指定目录执行 svn 命令，返回（退出码, 标准输出文本, 标准错误文本）。

    输出按字节捕获后以 UTF-8 解码：Windows 控制台代码页与仓库编码不一致时，
    直接以文本模式捕获会把中文路径解码成乱码。
    """
    try:
        result = subprocess.run(
            ["svn"] + args,
            cwd=workdir,
            capture_output=True,
        )
    except OSError as error:
        return 1, "", "无法执行 svn 命令（%s）；请确认已安装 Subversion 命令行客户端并加入 PATH" % error
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    return result.returncode, stdout, stderr


def normalize(path):
    """路径归一化：反斜杠转正斜杠、去除 ./ 前缀与首尾空白。"""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


# svn status 的 item 取值 → 是否属于「可提交」
COMMITTABLE_ITEMS = ("added", "deleted", "modified", "replaced")
# 需要人工先处理、否则提交必然失败或语义错误的取值
BLOCKING_ITEMS = {"conflicted": "存在内容冲突，须先解决并 svn resolved",
                  "missing": "文件已丢失（非版本化删除），须 svn delete 或恢复",
                  "obstructed": "路径类型被占用，须先清理障碍物"}


def parse_status(xml_text):
    """解析 `svn status --xml`，返回条目列表。

    每项为字典：path / item / props / tree_conflicted / locked / remote_modified。
    """
    entries = []
    root = ET.fromstring(xml_text)
    for target in root.findall("target"):
        target_path = normalize(target.get("path") or "")
        for entry in target.findall("entry"):
            path = normalize(entry.get("path") or "")
            # status --xml 的 entry path 已相对 target，target 为 "." 时无需拼接
            if not path and target_path:
                path = target_path
            status = entry.find("wc-status")
            if status is None:
                continue
            # 树冲突在 wc-status 上以属性或子元素两种形态出现，两者都认
            tree = (status.get("tree-conflicted") == "true"
                    or entry.find("tree-conflicted") is not None)
            repos = entry.find("repos-status")
            remote = repos is not None and (repos.get("item") or "none") != "none"
            entries.append({
                "path": path,
                "item": status.get("item") or "normal",
                "props": status.get("props") or "none",
                "tree_conflicted": tree,
                "locked": status.get("wc-locked") == "true",
                "remote_modified": remote,
            })
    return entries


def collect_ignore_rules(workdir):
    """递归读取 `svn:ignore` 属性，返回（规则行列表, 错误信息）。

    忽略规则只存在于版本化属性里，工作区中没有对应文件，因此必须经命令读取。
    """
    code, stdout, stderr = run_svn(["propget", "-R", "svn:ignore", "."], workdir)
    if code != 0:
        # 未设置任何 svn:ignore 时部分版本返回非 0，属正常，不视为错误
        return [], stderr.strip() if stderr.strip() else ""
    return [line.rstrip() for line in stdout.splitlines() if line.strip()], ""


def classify(entries, ignore_rules):
    """把条目分入 可提交 / 未版本化 / 已忽略 / 阻塞 四类，并汇总需确认项。"""
    committable, unversioned, ignored, blocking, notices = [], [], [], [], []
    for entry in entries:
        path, item = entry["path"], entry["item"]
        if entry["tree_conflicted"]:
            blocking.append({"path": path, "reason": "树冲突（tree-conflicted），须先解决"})
            continue
        if item in BLOCKING_ITEMS:
            blocking.append({"path": path, "reason": BLOCKING_ITEMS[item]})
            continue
        if item == "unversioned":
            unversioned.append(path)
            continue
        if item == "ignored":
            ignored.append(path)
            continue
        if item in COMMITTABLE_ITEMS or entry["props"] == "modified":
            if path == "." and item == "normal":
                # 工作副本根仅属性变更：不能把 "." 当作提交目标（那等于提交整个工作副本）
                notices.append({"path": ".",
                                "note": "工作副本根有属性变更，须以 --depth empty 单独提交，"
                                        "不可把根目录作为目标路径"})
                continue
            committable.append(path)
            # 属性变更必须进提交计划：改 svn:ignore 本身就是一次内容变更
            if entry["props"] == "modified" and item == "normal":
                notices.append({"path": path, "note": "仅属性变更（如 svn:ignore），须纳入提交计划"})
            if entry["locked"]:
                notices.append({"path": path, "note": "该路径被锁定，提交会释放锁，须确认锁归属"})
            if entry["remote_modified"]:
                notices.append({"path": path, "note": "服务端已有新版本，未自动 update"})
    return committable, unversioned, ignored, blocking, notices


def parse_args(argv):
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="SVN 工作副本变更收集（结构化输出）")
    parser.add_argument("--dir", default=None, help="工作副本目录（默认当前工作目录）")
    parser.add_argument("--no-ignore", action="store_true", help="同时列出已忽略项")
    parser.add_argument("--show-updates", action="store_true",
                        help="同时与服务器比对（-u），可发现服务端已有新版本的路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（默认行为）")
    return parser.parse_args(argv)


def main(argv):
    """脚本主入口。"""
    init_stdout()
    args = parse_args(argv)
    workdir = os.path.abspath(args.dir or os.getcwd())
    if not os.path.isdir(workdir):
        print("[错误] 目录不存在：%s" % workdir, file=sys.stderr)
        return 2

    status_args = ["status", "--xml"]
    if args.no_ignore:
        status_args.append("--no-ignore")
    if args.show_updates:
        status_args.append("--show-updates")
    code, stdout, stderr = run_svn(status_args, workdir)
    if code != 0:
        print("[错误] svn status 执行失败（退出码 %d）：%s" % (code, stderr.strip()), file=sys.stderr)
        print("       请确认目标目录是 SVN 工作副本（含 .svn 目录）。", file=sys.stderr)
        return 2

    try:
        entries = parse_status(stdout)
    except ET.ParseError as error:
        print("[错误] svn status 输出解析失败：%s" % error, file=sys.stderr)
        return 2

    ignore_rules, ignore_error = collect_ignore_rules(workdir)
    committable, unversioned, ignored, blocking, notices = classify(entries, ignore_rules)

    result = {
        "root": workdir,
        "committable": committable,
        "unversioned": unversioned,
        "ignored": ignored,
        "blocking": blocking,
        "notices": notices,
        "ignore_rules": ignore_rules,
        "ignore_error": ignore_error,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if blocking:
        print("[FAIL] 存在 %d 个阻断项，须先处理后才能提交。" % len(blocking), file=sys.stderr)
        return 1
    if not committable:
        print("[INFO] 无已版本化改动需要提交；未版本化 %d 项（需 svn add 后才进提交）。"
              % len(unversioned), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
