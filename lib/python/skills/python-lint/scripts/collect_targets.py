#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""python-lint 门禁清单收集脚本：汇总本次待检查的 Python 变更文件。

背景：
    提交前门禁需要「本次未提交变更」的文件清单。`git diff` 看不到**未跟踪的新文件**，
    需显式读取 `git status`；同时要按 include_patterns 圈定范围（白名单）、按
    exclude_patterns 排除虚拟环境与缓存（黑名单）。手工拼清单既繁琐又易漏。

配置（**项目相关内容独立配置、经索引定位，便于引擎跨项目共享**）：
    经 `.codebuddy/project.index.json` 的 `python_lint.config` 定位到
    `<项目根>/.codebuddy.project/configs/skills/python/python-lint/config.json`

    纳入与排除清单**均完全由项目配置声明**（脚本不内置任何默认项）。迁移到目标项目时
    只需改写该配置的两个清单，无需改动脚本。

    两种模式由「是否配了白名单」自动选择（`include_patterns` 为**可选**键）：

      - **白名单模式**：`include_patterns` 非空 → 默认拒绝，只有匹配的文件进入清单；
        `exclude_patterns` 继续生效，用于排除白名单内的虚拟环境与缓存。
      - **黑名单模式**：`include_patterns` 缺失或为空 → 默认放行，仅按 `exclude_patterns` 排除。
      - 两者均未配置 → 报错退出（范围无法确定，不静默全量或全空）。

    过滤顺序：**扩展名（技能固有边界，始终生效）→ 白名单（可选）→ 黑名单**。
    扩展名硬编码为 `.py`（本技能只审 Python 源码，属技能定义而非项目偏好），
    因此黑名单模式不会把 `.json` / `.md` / 子模块指针等非源码变更纳入。

    `include_patterns` / `exclude_patterns` 的语义是**目录/文件模式的匹配清单**，一律按
    **项目根相对路径**书写（如 `extensions/**/*.py`）。脚本内部会把 `git status` 给出的
    仓库相对路径换算为项目根相对路径后再匹配，因此**无需为了抵销仓库前缀而补 `**/`**：
    `extensions/**` 与 `**/extensions/**` 都能命中，按语义选更精确的那种即可——要锚定在
    项目根下就用不带前缀的写法，要匹配任意层级的同名目录才用 `**/` 开头。

    > 本项目采用**不带前缀**的写法：带前缀会误匹配 `src/extensions/`、
    > `src/tasks/extensions/` 这类任意层级的同名目录（引擎 `engine-constraints.md` §2.1 有实测）。

用法：
    python collect_targets.py [--dir <仓库目录>]
                              [--config <配置路径>]
                              [--include-patterns "<逗号分隔模式>"]
                              [--exclude-patterns "<逗号分隔模式>"]
                              [--json]

参数：
    --dir               git 命令执行目录（默认当前目录）
    --config            项目配置路径（默认经索引 python_lint.config 定位到项目侧）
    --include-patterns  纳入检查的文件模式（白名单，逗号分隔；缺省取项目配置）。
                        不传且配置未写该键 → 退回黑名单模式（仅按 exclude_patterns 排除）
    --exclude-patterns  排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）
    --json              以 JSON 输出（tracked / untracked / targets / excluded / mode）

输出：
    文本模式：逐行输出目标路径（可直接作为检查文件清单传递）。
    JSON 模式：结构化清单，区分已跟踪变更与未跟踪新文件。

退出码：
    0 —— 收集完成（列表可能为空）
    2 —— git 命令执行失败或参数错误
    3 —— 配置不可用（缺失、损坏、缺少必需键）
"""

import argparse
import json
import os
import re
import subprocess
import sys

# 配置在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "python_lint.config"

# 配置文件中必需的键（缺失即报错，避免静默使用内置默认值导致「配置写了但没生效」）
REQUIRED_CONFIG_KEYS = ("exclude_patterns",)

# 可选键：白名单（目录/文件模式的默认拒绝清单）
OPTIONAL_INCLUDE_KEY = "include_patterns"

# 本技能只检查 Python 源码，扩展名属技能固有边界而非项目偏好，故硬编码、不设配置项
TARGET_EXTENSION = ".py"


class ConfigError(RuntimeError):
    """配置缺失、损坏或缺少必需键时抛出；由 CLI 入口转为明确的错误退出。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
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


def find_project_root(start):
    """自 start 向上查找**含 .codebuddy 子目录**的目录作为项目根，找不到则返回 start。

    只认 .codebuddy 锚点，**不以 .git 为锚**：.codebuddy 自身是独立 git 仓库时
    （引擎以「独立 git 检出」形态挂载，.codebuddy/.git 是目录而非 submodule 的 gitfile），
    同时匹配 .git 会让向上查找先命中 .codebuddy 本身，项目根被误判，
    配置路径随之拼成 .codebuddy/.codebuddy.project/...，所有项目侧配置都读不到。
    """
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, ".codebuddy")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def resolve_config_path(root):
    """经索引注册表解析配置路径（相对路径基准为项目根）。

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


def load_config(root):
    """经索引加载并校验配置；缺失或损坏即抛 ConfigError（不静默回退默认值）。"""
    config_path = resolve_config_path(root)
    if not os.path.isfile(config_path):
        raise ConfigError(
            "配置未找到：%s\n"
            "       该文件应在项目侧由 core-init 生成并按项目填写。" % config_path
        )
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("配置读取失败（%s）：%s" % (error, config_path))
    if not isinstance(config, dict):
        raise ConfigError("配置顶层必须是 JSON 对象：%s" % config_path)
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigError(
            "配置缺少必需键：%s（%s）" % ("、".join(missing), config_path)
        )
    return config


def normalize(path):
    """路径归一化：反斜杠转正斜杠、去 ./ 前缀。"""
    value = str(path).strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def glob_to_regex(pattern):
    """把 glob 模式（支持 ** 与 *）转换为正则，用于路径匹配。

    匹配大小写不敏感，与引擎内既有收集脚本（csharp 包的 collect_review_targets.py）
    保持一致，避免 Windows 路径大小写差异导致排除失效。
    """
    pattern = normalize(pattern)
    index = 0
    out = ""
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out += "(?:.*/)?"
            index += 3
        elif pattern.startswith("**", index):
            out += ".*"
            index += 2
        elif pattern[index] == "*":
            out += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            out += "[^/]"
            index += 1
        else:
            out += re.escape(pattern[index])
            index += 1
    return re.compile("^" + out + "$", re.IGNORECASE)


def matches_any(path, regexes):
    """路径命中任一正则即视为匹配（同时尝试全路径与文件名，兼容 *.py 这类模式）。"""
    name = path.rsplit("/", 1)[-1]
    return any(regex.match(path) or regex.match(name) for regex in regexes)


def get_git_toplevel(workdir):
    """返回 git 仓库顶层目录（绝对路径）；非 git 环境返回 None。

    `git status` 输出的路径以**仓库顶层**为基准，而配置中的模式以**项目根**为基准；
    二者在有仓库前缀时并不相同，需显式换算。
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    toplevel = (result.stdout or "").strip()
    return os.path.abspath(toplevel) if toplevel else None


def to_project_rel(repo_rel, git_root, project_root):
    """把「仓库相对路径」换算为「项目根相对路径」；不在项目根内则返回 None。

    配置模式（include/exclude）一律按项目根相对路径书写，因此匹配前必须先换算——
    否则 `extensions/**` 这类不带上层前缀的模式会因仓库前缀失配，迫使用户为所有目录
    模式补 `**/` 前缀（把路径语义问题转嫁给配置书写者）。
    """
    if os.path.isabs(repo_rel):
        absolute = os.path.normpath(repo_rel)
    else:
        absolute = os.path.normpath(os.path.join(git_root, repo_rel))
    try:
        rel = os.path.relpath(absolute, project_root)
    except ValueError:
        return None
    if rel.startswith(".." + os.sep) or rel == "..":
        return None
    return normalize(rel)


def get_git_status(workdir):
    """解析 `git status --porcelain -z --untracked-files=all`，返回 [(xy, path)]。"""
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status 执行失败")

    tokens = [t for t in result.stdout.split("\0") if t != ""]
    entries = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 3:
            continue
        xy = token[:2]
        path = token[3:]
        # 重命名/复制在 -z 模式下追加一个「源路径」token，需一并消费
        if xy[0] in ("R", "C"):
            index += 1
        entries.append((xy, normalize(path)))
    return entries


def split_patterns(value):
    """拆分逗号分隔的模式串（也接受列表）并去除空项。"""
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value if str(item).strip()]
    return [normalize(item) for item in str(value).split(",") if item.strip()]


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="python-lint 门禁检查目标收集")
    parser.add_argument("--dir", default=None, help="git 命令执行目录（默认当前目录）")
    parser.add_argument("--config", default=None, help="项目配置路径（默认经索引 python_lint.config 定位）")
    parser.add_argument("--include-patterns", default=None,
                        help="纳入检查的文件模式（白名单，逗号分隔；缺省取项目配置的 include_patterns）")
    parser.add_argument("--exclude-patterns", default=None,
                        help="排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    workdir = args.dir or os.getcwd()
    root = find_project_root(workdir)

    try:
        if args.config:
            config_abs = args.config if os.path.isabs(args.config) else os.path.join(root, args.config)
            if not os.path.isfile(config_abs):
                raise ConfigError("指定的配置不存在：%s" % config_abs)
            try:
                with open(config_abs, "r", encoding="utf-8") as handle:
                    config = json.load(handle)
            except (OSError, ValueError) as error:
                raise ConfigError("指定的配置读取失败（%s）：%s" % (error, config_abs))
            if not isinstance(config, dict):
                raise ConfigError("指定的配置顶层必须是 JSON 对象：%s" % config_abs)
            missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
            if missing:
                raise ConfigError("指定的配置缺少必需键：%s（%s）"
                                  % ("、".join(missing), config_abs))
        else:
            config = load_config(root)
    except ConfigError as error:
        print("[FAIL] %s" % error, file=sys.stderr)
        return 3

    include_patterns = split_patterns(args.include_patterns) if args.include_patterns \
        else split_patterns(config.get(OPTIONAL_INCLUDE_KEY) or [])
    exclude_patterns = split_patterns(args.exclude_patterns) if args.exclude_patterns \
        else split_patterns(config.get("exclude_patterns") or [])

    include_regexes = [glob_to_regex(p) for p in include_patterns]
    exclude_regexes = [glob_to_regex(p) for p in exclude_patterns]

    # 白名单模式由「是否配了白名单」决定：
    #   配了 → 默认拒绝，只收白名单内的文件（白名单模式）；
    #   没配 → 默认放行，仅按黑名单排除（黑名单模式）。
    # 两种模式下 exclude_patterns 都继续生效（白名单只管「看哪里」，黑名单管「其中什么不看」）。
    whitelist_mode = bool(include_regexes)
    if not whitelist_mode and not exclude_regexes:
        print("[FAIL] 白名单与黑名单均未配置，检查范围无法确定（配置 include_patterns 或 exclude_patterns）",
              file=sys.stderr)
        return 3

    try:
        entries = get_git_status(workdir)
    except RuntimeError as error:
        print("[FAIL] 获取 git 状态失败：%s" % error, file=sys.stderr)
        return 2

    # git status 给的是仓库相对路径，配置模式是项目根相对路径；统一换算后用项目相对路径匹配
    git_root = get_git_toplevel(workdir) or root

    tracked = []
    untracked = []
    excluded = []

    for xy, path in entries:
        is_untracked = xy == "??"
        project_rel = to_project_rel(path, git_root, root)
        # 不在项目根内的变更（同仓其他子项目）直接排除
        if project_rel is None:
            excluded.append({"path": path, "reason": "outside_project_root"})
            continue
        # 扩展名是技能固有边界，始终生效
        if not project_rel.lower().endswith(TARGET_EXTENSION):
            continue
        if whitelist_mode and not matches_any(project_rel, include_regexes):
            excluded.append({"path": project_rel, "reason": "not_in_include_patterns"})
            continue
        if exclude_regexes and matches_any(project_rel, exclude_regexes):
            excluded.append({"path": project_rel, "reason": "matched_exclude_patterns"})
            continue
        if is_untracked:
            untracked.append(project_rel)
        else:
            tracked.append(project_rel)

    targets = tracked + untracked

    if args.json:
        payload = {
            "mode": "whitelist" if whitelist_mode else "blacklist",
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "tracked": tracked,
            "untracked": untracked,
            "targets": targets,
            "excluded": excluded,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for path in targets:
            print(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
