# -*- coding: utf-8 -*-
"""C# 工作区行尾合规检测脚本（git ls-files --eol）。

背景：
    项目根 .editorconfig 声明 `end_of_line = crlf`，配合 core.autocrlf=true 与
    .gitattributes 的 `* text=auto`，仓库内始终存 LF、工作区检出为 CRLF。
    当工具（编码转换、批量重写等）直接以 LF 写回工作区文件时，绕过 git 检出流程，
    工作区便停留在 LF。此时 git status 因比对前会归一化行尾而**看不到差异**，
    该异常被静默掩盖（实测：仅 `git ls-files --eol` 可检出）。

职责：
    1. 定位项目根目录（自调用目录向上查找含 .editorconfig 的目录）。
    2. 复用 csharp-format-checker 项目配置（经索引注册表定位）的 exclude_dirs，保持口径一致。
    3. 通过 `git ls-files --eol` 取出工作区行尾状态，筛出工作区非 CRLF 的 .cs 文件。
    4. 输出异常清单，并可给出修复命令（删除 + 重新检出）。

退出码：
    0 —— 无异常（或异常全部落在忽略目录内）
    1 —— 存在忽略目录之外的行尾异常文件
    3 —— 配置或环境不可用（配置缺失、非 git 仓库等）

用法：
    python check_eol.py                      # 检测整仓
    python check_eol.py --path src/module  # 仅检测指定目录
    python check_eol.py --fix                # 打印修复命令（不自动执行）
"""

import argparse
import json
import os
import subprocess
import sys

# 配置文件在索引注册表中的逻辑名（路径基准为项目根，由索引声明，与 dotnet_format.py 同项）
CONFIG_CODENAME = "format_checker.config"

# 期望的工作区行尾（项目根 .editorconfig 的 end_of_line 语义）
EXPECTED_WORKTREE_EOL = "w/crlf"

# 仅检测 C# 源文件
TARGET_PATTERN = "*.cs"


class ConfigError(RuntimeError):
    """配置不可用（缺失、损坏或缺少必需键）。"""


def find_project_root(start):
    """自 start 向上查找含 .editorconfig 的目录作为项目根，找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, ".editorconfig")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


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


def resolve_config_path(root):
    """经索引注册表解析格式检查配置路径（相对路径基准为项目根）。

    索引 `.codebuddy/project.index.json` 为跨项目共享的入库文件，只读
    `files[逻辑名].path`；路径必须是相对路径（拒绝绝对路径，防索引污染）。
    """
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise ConfigError(
            "未能从项目根定位 .codebuddy 目录：%s\n"
            "       请确认在含 .codebuddy 的项目内运行。" % root
        )
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise ConfigError(
            "未找到项目配置索引：%s\n"
            "       该索引由 .codebuddy 引擎提供；若缺失，请确认引擎包完整。" % index_path
        )
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError("索引缺少配置项 `files.%s.path`：%s" % (CONFIG_CODENAME, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 `files.%s.path` 必须为相对路径（当前为绝对路径）：%s"
                          % (CONFIG_CODENAME, rel))
    return os.path.normpath(os.path.join(root, rel))


def load_config(root, config_abs):
    """加载格式检查配置，取 exclude_dirs 与检查范围保持同一口径。

    配置是检查范围的唯一事实来源：缺失或缺少必需键时明确报错，
    不静默回退内置默认值，避免「配置未生效」被掩盖。
    """
    if not os.path.isfile(config_abs):
        raise ConfigError(
            "未找到格式检查配置：%s\n"
            "       本脚本复用该配置的 exclude_dirs，需先按项目实际情况创建。"
            % config_abs
        )

    try:
        with open(config_abs, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("格式检查配置读取失败：%s（%s）" % (config_abs, error))

    if "exclude_dirs" not in config:
        raise ConfigError("格式检查配置缺少必需键 exclude_dirs：%s" % config_abs)

    return config


def get_git_root(workdir):
    """返回仓库根目录（git rev-parse --show-toplevel），非 git 环境返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workdir, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def list_eol_entries(git_root, path_arg):
    """执行 git ls-files --eol，返回 [(index_eol, worktree_eol, attr, repo_rel_path)]。"""
    cmd = ["git", "ls-files", "--eol"]
    if path_arg:
        cmd += ["--", path_arg]
    result = subprocess.run(cmd, cwd=git_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None, result.stderr.strip()

    entries = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # 输出格式固定为：i/<eol>  w/<eol>  attr/<attrs>  <path>（以空白分隔，路径在末列）
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        entries.append((parts[0], parts[1], parts[2], parts[3].strip()))
    return entries, None


def normalize(value):
    """归一化路径：统一正斜杠、去除首尾空白。"""
    return value.replace("\\", "/").strip()


def is_in_exclude_dirs(repo_rel_path, project_rel_path, exclude_dirs):
    """判断文件是否位于任一忽略目录内（大小写不敏感的前缀匹配）。

    同时按仓库相对路径与项目相对路径判断：exclude_dirs 以项目根为基准书写，
    而 git 返回的是仓库相对路径（本项目仓库根在项目根的上一级）。
    """
    candidates = [normalize(repo_rel_path).lower(), normalize(project_rel_path).lower()]
    for item in exclude_dirs:
        base = normalize(item).lower().rstrip("/")
        if not base:
            continue
        for cand in candidates:
            if cand == base or cand.startswith(base + "/") or ("/" + base + "/") in ("/" + cand):
                return True
            # 项目相对路径可能带仓库前缀（如 <子目录>/<路径>/...），检查后缀匹配
            if cand.endswith("/" + base) or ("/" + base + "/") in cand:
                return True
    return False


def to_project_rel(repo_rel_path, git_root, project_root):
    """把仓库相对路径转换为项目根相对路径（不在项目根下时返回原值）。"""
    abs_path = os.path.normpath(os.path.join(git_root, repo_rel_path))
    try:
        rel = os.path.relpath(abs_path, project_root)
    except ValueError:
        return normalize(repo_rel_path)
    if rel.startswith(".."):
        return normalize(repo_rel_path)
    return normalize(rel)


def to_repo_path(path_arg, git_root, project_root):
    """把用户给的路径（项目根相对或绝对）转换为仓库相对路径，供 git ls-files 过滤。

    git ls-files 的 pathspec 以**仓库根**为基准，而用户（与技能其余参数）习惯用
    项目根相对路径。两者在子目录型仓库下不同（本项目仓库根在项目根的上一级），
    故此处统一转换，避免 `--path src/module` 匹配不到任何文件。
    """
    normalized = normalize(path_arg)
    if os.path.isabs(normalized):
        abs_path = normalized
    else:
        abs_path = os.path.normpath(os.path.join(project_root, normalized))
    try:
        rel = os.path.relpath(abs_path, git_root)
    except ValueError:
        return normalized
    return normalize(rel)


def main():
    parser = argparse.ArgumentParser(
        description="C# 工作区行尾合规检测（git ls-files --eol，期望工作区为 CRLF）")
    parser.add_argument("--root", default=None,
                        help="项目根目录（含 .editorconfig），默认从当前目录向上查找")
    parser.add_argument("--path", default=None,
                        help="仅检测指定的项目根相对目录/文件范围")
    parser.add_argument("--fix", action="store_true",
                        help="额外打印异常文件的修复命令（删除 + 重新检出），不自动执行")
    parser.add_argument("--no-save", action="store_true",
                        help="兼容参数：本脚本只输出到终端，不产生报告文件")
    args = parser.parse_args()

    # 1. 定位项目根
    base_dir = args.root or os.getcwd()
    root = find_project_root(base_dir)
    if not root:
        print("[错误] 未找到项目根（当前目录及上级均无 .editorconfig）。")
        return 3
    root = os.path.abspath(root)
    print("[信息] 项目根：%s" % root)

    # 2. 读取配置（复用 exclude_dirs；经索引注册表定位项目侧配置）
    try:
        config_abs = resolve_config_path(root)
        config = load_config(root, config_abs)
    except ConfigError as error:
        print("[错误] %s" % error)
        return 3
    exclude_dirs = list(config["exclude_dirs"])
    print("[信息] 忽略目录：%d 项（复用 csharp-format-checker 项目配置）" % len(exclude_dirs))

    # 3. 定位仓库根
    git_root = get_git_root(root)
    if not git_root:
        print("[错误] 未找到 git 仓库根（请确认当前目录位于 git 仓库内）。")
        return 3
    print("[信息] 仓库根：%s" % git_root)

    # 4. 取出工作区行尾状态（仅 .cs）
    path_filter = None
    if args.path:
        path_filter = to_repo_path(args.path, git_root, root)
        print("[信息] 检查范围：%s（仓库相对：%s）" % (args.path, path_filter))
    entries, error = list_eol_entries(git_root, path_filter)
    if entries is None:
        print("[错误] git ls-files 执行失败：%s" % error)
        return 3

    cs_entries = [e for e in entries if e[3].lower().endswith(".cs")]
    print("[信息] 扫描 .cs 文件：%d 个" % len(cs_entries))

    # 5. 筛出异常：工作区行尾不是 CRLF（排除 w/-text 二进制项）
    abnormal_all = []
    abnormal_owned = []
    for index_eol, worktree_eol, attr, repo_rel in cs_entries:
        if worktree_eol == EXPECTED_WORKTREE_EOL or worktree_eol == "w/-text":
            continue
        project_rel = to_project_rel(repo_rel, git_root, root)
        item = (repo_rel, project_rel, index_eol, worktree_eol)
        abnormal_all.append(item)
        if not is_in_exclude_dirs(repo_rel, project_rel, exclude_dirs):
            abnormal_owned.append(item)

    print()
    if not abnormal_all:
        print("[结果] 行尾合规：所有 .cs 文件的工作区行尾均为 CRLF。")
        return 0

    print("[结果] 检出工作区行尾异常 %d 个（其中忽略目录外 %d 个）"
          % (len(abnormal_all), len(abnormal_owned)))
    print()

    if abnormal_owned:
        print("=== 需处理（忽略目录之外）===")
        for repo_rel, project_rel, index_eol, worktree_eol in abnormal_owned:
            print("  %s  [%s %s]" % (project_rel, index_eol, worktree_eol))
        print()
        if args.fix:
            print("=== 修复命令（删除工作区文件后由 git 按 autocrlf 重新检出为 CRLF）===")
            for repo_rel, project_rel, index_eol, worktree_eol in abnormal_owned:
                print('  rm -f "%s" && git checkout -- "%s"' % (project_rel, repo_rel))
            print()

    skipped = len(abnormal_all) - len(abnormal_owned)
    if skipped:
        print("=== 已跳过（位于忽略目录内）%d 个 ===" % skipped)
        for repo_rel, project_rel, index_eol, worktree_eol in abnormal_all:
            if (repo_rel, project_rel, index_eol, worktree_eol) not in abnormal_owned:
                print("  %s" % project_rel)
        print()

    print("说明：git status 对已提交内容的行尾差异不敏感（比对前会归一化行尾），"
          "文件被工具以 LF 静默改写后再提交时尤其容易漏检；git ls-files --eol 可稳定检出。")

    return 1 if abnormal_owned else 0


if __name__ == "__main__":
    sys.exit(main())
