#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目内临时文件工具（引擎侧通用工具）。

在项目侧缓存根下的 `tmp/` 目录创建**唯一命名**的临时文件，输出**正斜杠绝对路径**，
供提交消息、暂存清单等短生命周期内容使用。目录取自引擎索引 `artifacts.dirs` 的
`caches.root` 条目，脚本不硬编码任何项目路径。

为什么需要本工具（两类实测故障）：

1. **同一字面量 `/tmp` 被不同工具解析为不同目录**：Windows + Git Bash 下，Git Bash 与
   `git` 解析为 `C:/Users/<用户>/AppData/Local/Temp`，而 Python 内联代码解析为当前盘符
   根下的 `G:\\tmp`。跨工具传递时会出现「写完却找不到文件」。
2. **系统临时目录被同机所有项目共用**：固定文件名（如 `cb_commit_msg.txt`）会被并发
   会话覆盖，实测出现过提交消息被另一项目的内容替换。

本工具用项目内目录解决跨项目共享，用 `tempfile.mkstemp` 唯一命名解决同项目多会话，
输出的绝对路径没有解析分歧。

用法：
  python project_tmp.py new --prefix commit-msg --suffix .txt
      在 <caches.root>/tmp/ 下创建唯一空文件，stdout 输出绝对路径（正斜杠）
  python project_tmp.py new --system --prefix svn-msg --suffix .txt
      显式改用系统临时目录（供「临时文件不得位于工作副本内」的场景），仍唯一命名
  python project_tmp.py clean --older-than 24
      删除 <caches.root>/tmp/ 下超过指定小时数的遗留文件

退出码：
  0 —— 成功
  1 —— 参数或文件操作失败
  3 —— 索引缺失、损坏或缺少 artifacts.dirs['caches.root']
"""

import argparse
import os
import re
import sys
import tempfile
import time

# 与 cleanup_artifacts.py 同目录：复用其项目定位与索引读取逻辑，
# 避免两套「向上找 .codebuddy」的实现产生漂移。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleanup_artifacts import CleanupError, load_index

# 前缀 / 后缀允许的字符：仅字母、数字、点、下划线、连字符，防止路径分隔符注入。
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]*$")


def resolve_tmp_root():
    """经索引解析项目侧临时目录（<caches.root>/tmp），返回绝对路径。

    目录不存在时由调用方创建。索引缺失 `caches.root` 时报错退出 3——该条目由引擎
    索引提供，缺失说明项目侧配置未随引擎更新，应先运行 core-init 检查。
    """
    try:
        index, project_root = load_index()
    except CleanupError as error:
        sys.stderr.write("[错误] %s\n" % error)
        sys.exit(3)
    dirs = (index.get("artifacts") or {}).get("dirs")
    if not isinstance(dirs, dict) or not dirs:
        sys.stderr.write(
            "[错误] 索引缺少非空键 `artifacts.dirs`，请运行 core-init --status 检查项目配置。\n")
        sys.exit(3)
    rel = dirs.get("caches.root")
    if not isinstance(rel, str) or not rel:
        sys.stderr.write(
            "[错误] 索引缺少 `artifacts.dirs['caches.root']`。\n"
            "       该条目由引擎索引提供；请运行 core-init --status 查看并补齐项目侧配置。\n")
        sys.exit(3)
    if os.path.isabs(rel):
        sys.stderr.write(
            "[错误] 索引 `caches.root` 必须是相对项目根的路径，实际为：%s\n" % rel)
        sys.exit(3)
    tmp_root = os.path.normpath(os.path.join(project_root, rel, "tmp"))
    # 安全护栏：临时目录必须严格位于项目根内，防止索引写错时把文件建到项目外。
    root_key = os.path.normcase(project_root)
    tmp_key = os.path.normcase(tmp_root)
    if not (tmp_key == root_key or tmp_key.startswith(root_key + os.sep)):
        sys.stderr.write("[错误] 解析出的临时目录不在项目根内：%s\n" % tmp_root)
        sys.exit(3)
    return tmp_root


def validate_token(value, label):
    """校验前缀 / 后缀只含安全字符，防止路径分隔符注入。"""
    if not _NAME_PATTERN.match(value or ""):
        sys.stderr.write(
            "[错误] %s 只允许字母、数字、点、下划线、连字符，实际为：%r\n" % (label, value))
        sys.exit(1)
    return value


def cmd_new(args):
    """创建唯一临时文件并输出其绝对路径（正斜杠）。"""
    prefix = validate_token(args.prefix, "--prefix")
    suffix = validate_token(args.suffix, "--suffix")
    base_dir = tempfile.gettempdir() if args.system else resolve_tmp_root()
    try:
        os.makedirs(base_dir, exist_ok=True)
    except OSError as error:
        sys.stderr.write("[错误] 无法创建临时目录：%s（%s）\n" % (base_dir, error))
        return 1
    try:
        handle_fd, path = tempfile.mkstemp(
            prefix=prefix + "-", suffix=suffix, dir=base_dir)
        os.close(handle_fd)
    except OSError as error:
        sys.stderr.write("[错误] 无法创建临时文件：%s（%s）\n" % (base_dir, error))
        return 1
    # 统一输出正斜杠绝对路径：跨 shell 传递时无反斜杠转义风险。
    print(os.path.abspath(path).replace(os.sep, "/"))
    return 0


def cmd_clean(args):
    """删除临时目录下超过指定小时数的遗留文件。"""
    if args.older_than < 0:
        sys.stderr.write("[错误] --older-than 不能为负数。\n")
        return 1
    tmp_root = resolve_tmp_root()
    if not os.path.isdir(tmp_root):
        print("无临时目录，无需清理：%s" % tmp_root.replace(os.sep, "/"))
        return 0
    cutoff = time.time() - args.older_than * 3600
    removed = 0
    failed = 0
    for name in os.listdir(tmp_root):
        path = os.path.join(tmp_root, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError as error:
            failed += 1
            sys.stderr.write("[警告] 删除失败：%s（%s）\n" % (path, error))
    print("清理完成：删除 %d 个遗留临时文件（目录：%s）。"
          % (removed, tmp_root.replace(os.sep, "/")))
    return 0 if failed == 0 else 1


def main():
    """命令行入口：new / clean 两个子命令。"""
    parser = argparse.ArgumentParser(
        description="项目内临时文件工具：在项目缓存根下创建唯一命名的临时文件。")
    sub_parsers = parser.add_subparsers(dest="command", required=True)

    new_parser = sub_parsers.add_parser("new", help="创建唯一临时文件并输出绝对路径")
    new_parser.add_argument("--prefix", default="tmp", help="文件名前缀（默认 tmp）")
    new_parser.add_argument("--suffix", default="", help="文件名后缀（如 .txt）")
    new_parser.add_argument(
        "--system", action="store_true",
        help="改用系统临时目录（供临时文件不得位于工作副本内的场景）")
    new_parser.set_defaults(handler=cmd_new)

    clean_parser = sub_parsers.add_parser("clean", help="删除临时目录下超过指定小时数的遗留文件")
    clean_parser.add_argument(
        "--older-than", type=float, default=24.0,
        help="保留小时数，超过即删除（默认 24）")
    clean_parser.set_defaults(handler=cmd_clean)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
