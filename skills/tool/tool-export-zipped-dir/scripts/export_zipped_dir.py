# -*- coding: utf-8 -*-
"""
导出任意目录为 zip 压缩包。

规则：
1. 目录位于 git 仓库内时，仅导出未被 gitignore 忽略的文件
   （已跟踪 + 未跟踪但未被忽略）。
2. 目录不在任何 git 仓库内时（如 .codebuddy 被单独复制到其他位置），
   自动退化为全量导出，仅跳过通用构建产物/缓存目录与文件
   （.git/、bin/、obj/、__pycache__/、node_modules/ 等），保证脚本可用。
3. 可通过 --force 额外强制包含某些文件（即使被 gitignore 忽略）。
4. zip 内条目以源目录名为顶级前缀（如 .codebuddy/xxx），与仓库外层结构无关。

用法：
    python export_zipped_dir.py --source .codebuddy --output out.zip
    python export_zipped_dir.py --source .codebuddy --output out.zip --force models.json
"""
import argparse
import os
import subprocess
import zipfile

# 非 git 模式下跳过的通用构建产物/缓存目录与文件
SKIP_DIRS = {".git", "__pycache__", "bin", "obj", "node_modules", ".idea", ".vs", ".venv", "venv"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def find_repo_root(start):
    """向上查找 git 仓库根目录；找不到时返回 None，由调用方决定退化为非 git 模式。

    ``.git`` 可能是**目录**（普通仓库），也可能是**文件**（submodule / worktree 的 gitfile，
    内容为 ``gitdir: <路径>``）。两种都要认——只判断目录会把 submodule 内的工作目录
    误判为「不在 git 仓库中」，导出时退化成全量模式，连带把被 gitignore 的产物打包进去。
    """
    current = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def git_ls(repo, *args):
    """调用 git ls-files 输出 null 分隔的文件列表，返回 UTF-8 解码后的列表。"""
    proc = subprocess.run(
        ["git", "ls-files", "-z", *args],
        cwd=repo,
        capture_output=True,
    )
    proc.check_returncode()
    return [name for name in proc.stdout.decode("utf-8").split("\0") if name]


def collect_entries_from_git(repo, rel_source, source_name, forced):
    """git 模式：已跟踪文件 + 未跟踪但未被忽略的文件 + --force 强制包含的文件。"""
    tracked = git_ls(repo, rel_source)
    untracked = git_ls(repo, "--others", "--exclude-standard", rel_source)

    # 合并并去重（按 zip 条目路径去重），保持顺序
    seen = set()
    entries = []
    for repo_rel in tracked + untracked + forced:
        repo_rel = repo_rel.replace("\\", "/")
        if rel_source == ".":
            zip_rel = repo_rel
        elif repo_rel == rel_source:
            zip_rel = source_name
        elif repo_rel.startswith(rel_source + "/"):
            zip_rel = source_name + "/" + repo_rel[len(rel_source) + 1:]
        else:
            # 非源目录内的路径（force 传入仓库相对路径时可能产生），保留原样
            zip_rel = repo_rel
        if zip_rel in seen:
            continue
        seen.add(zip_rel)
        entries.append((os.path.join(repo, repo_rel), zip_rel))
    return entries


def collect_entries_fallback(source, source_name):
    """非 git 模式：全量扫描源目录，仅跳过通用构建产物目录与文件。"""
    entries = []
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if name in SKIP_FILES:
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, source).replace("\\", "/")
            entries.append((abs_path, "{}/{}".format(source_name, rel)))
    return entries


def resolve_force(path, rel_source):
    """将 --force 输入转换为仓库相对路径。"""
    path = path.replace("\\", "/")
    if path == rel_source or path.startswith(rel_source + "/"):
        return path
    if rel_source == ".":
        return path
    return rel_source + "/" + path


def main():
    parser = argparse.ArgumentParser(description="导出目录为 zip（git 仓库内遵循 gitignore 过滤，非 git 环境自动全量导出）。")
    parser.add_argument("--source", required=True, help="要导出的目录路径（仓库内相对路径或绝对路径）。")
    parser.add_argument("--output", required=True, help="输出的 zip 文件路径。")
    parser.add_argument("--repo", help="git 仓库根目录，默认自动向上查找。")
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        help="强制包含的文件，可多次指定；即使被 gitignore 忽略也会打包。"
        "支持两种写法：源目录内相对路径（如 models.json）或仓库相对路径（如 .codebuddy/models.json）。",
    )
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    if not os.path.isdir(source):
        raise RuntimeError("源目录不存在：{}".format(source))

    source_name = os.path.basename(os.path.normpath(source)) or "."

    repo = os.path.abspath(args.repo) if args.repo else find_repo_root(source)
    if repo is None:
        # 目录不在任何 git 仓库内（例如 .codebuddy 被单独复制到其他位置）：
        # 无法使用 gitignore 过滤，退化为全量导出，保证脚本可用。
        print("未在 {} 及其上级目录中找到 .git，已切换为全量导出模式。".format(source))
        entries = collect_entries_fallback(source, source_name)
    else:
        rel_source = os.path.relpath(source, repo).replace("\\", "/")
        if rel_source == ".":
            source_name = "."
        forced = [resolve_force(f, rel_source) for f in args.force]
        entries = collect_entries_from_git(repo, rel_source, source_name, forced)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, zip_rel in entries:
            if os.path.isfile(abs_path):
                zf.write(abs_path, zip_rel)

    print("导出完成：{}".format(args.output))
    print("共导出 {} 个文件".format(len(entries)))
    if args.force:
        print("强制包含的文件：{}".format(", ".join(args.force)))


if __name__ == "__main__":
    main()
