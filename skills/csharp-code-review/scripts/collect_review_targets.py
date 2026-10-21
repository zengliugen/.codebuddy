#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-code-review 门禁审查目标收集脚本：汇总本次待审查的变更文件清单。

背景：
    提交前审查门禁需要「本次未提交变更」的文件清单。`git diff` 看不到**未跟踪的新文件**，
    需显式读取 `git status`；同时要按 exclude_patterns 排除生成代码与三方库。手工拼清单既繁琐
    又易漏，且在派发提示词里重复书写。

配置（**项目相关内容独立配置、经索引定位，便于引擎跨项目共享**）：
    经 `.codebuddy/project.index.json` 的 `code_review.config` 定位到
    `<项目根>/.codebuddy.project/configs/skills/csharp-code-review/config.json`

        {
          "file_patterns": ["*.cs"],
          "exclude_patterns": [
            "**/Generated/**", "**/Gen/**", "**/HybridCLRData/**", "*auto-generated*",
            "**/Assets/Plugins/**", "**/Library/PackageCache/**",
            "**/Packages/TouchSocket.*/**", "**/ThreadLib/**", "**/.codebuddy/**"
          ]
        }

    排除清单**完全由项目配置声明**（脚本不内置任何排除项）。迁移到目标项目时
    只需改写该配置的 `exclude_patterns`，无需改动脚本。

    该清单与 `csharp-format-checker/config.json` 的 `exclude_dirs`、`rules/csharp-code/RULE.mdc`
    的范围声明应保持同一口径，新增排除项时一并同步。

用法：
    python collect_review_targets.py [--dir <仓库目录>]
                                     [--config <配置路径>]
                                     [--patterns "*.cs"]
                                     [--exclude-patterns "<逗号分隔模式>"]
                                     [--no-header-check] [--json]

参数：
    --dir               git 命令执行目录（默认当前目录）
    --config            项目配置路径（默认经索引 code_review.config 定位到项目侧）
    --patterns          纳入审查的文件模式（逗号分隔；缺省取项目配置，再缺省为 *.cs）
    --exclude-patterns  排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）
    --no-header-check   关闭「读取文件头识别 auto-generated」检查
    --json              以 JSON 输出（tracked / untracked / targets / excluded）

输出：
    文本模式：逐行输出审查目标路径（可直接作为审查文件清单传递）。
    JSON 模式：结构化清单，区分已跟踪变更与未跟踪新文件。

退出码：
    0 —— 收集完成（列表可能为空）
    2 —— git 命令执行失败或参数错误
"""

import argparse
import json
import os
import re
import subprocess
import sys

# 需要纳入审查的 git 状态码（M=修改、A=新增、R=重命名、C=复制、U=冲突未解决）
REVIEW_STATUS_CODES = {"M", "A", "R", "C", "U"}

# 配置文件在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "code_review.config"

# 配置文件中必需的键（缺失即报错，避免静默使用内置默认值导致「配置写了但没生效」）
REQUIRED_CONFIG_KEYS = ("file_patterns", "exclude_patterns")


class ConfigError(RuntimeError):
    """配置缺失、损坏或缺少必需键时抛出；由 CLI 入口转为明确的错误退出。"""


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
    """经索引注册表解析审查配置路径（相对路径基准为项目根）。

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


def glob_to_regex(pattern):
    """把 glob 模式（支持 ** 与 *）转换为正则，用于路径匹配。

    匹配大小写不敏感，与注释检查工具（csharp-comment-checker）的排除规则保持一致，
    避免 Windows 路径大小写差异导致排除失效。
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
    """路径命中任一正则即视为匹配（同时尝试全路径与文件名，兼容 *.cs 这类模式）。"""
    name = path.rsplit("/", 1)[-1]
    return any(regex.match(path) or regex.match(name) for regex in regexes)


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


def is_auto_generated_header(file_path):
    """读取文件头若干行，判断是否含 auto-generated 标记（大小写不敏感）。"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            for _ in range(5):
                line = file.readline()
                if not line:
                    break
                lowered = line.lower()
                if "<auto-generated" in lowered or "<auto generated" in lowered:
                    return True
    except OSError:
        return False
    return False


def split_patterns(value):
    """拆分逗号分隔的模式串（也接受列表）并去除空项。"""
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value if str(item).strip()]
    return [normalize(item) for item in str(value).split(",") if item.strip()]


def find_project_root(start):
    """自 start 向上查找含 .git 或 .codebuddy 的目录作为项目根，找不到则返回 start。"""
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, ".git")) or os.path.isdir(os.path.join(current, ".codebuddy")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def load_config(root):
    """加载项目配置；缺失、损坏或缺少必需键时抛出 ConfigError。

    配置是审查范围的**唯一事实来源**：脚本不内置 `file_patterns` / `exclude_patterns`
    默认值，也不生成模板，避免「配置未生效」被静默掩盖。
    """
    config_abs = resolve_config_path(root)
    if not os.path.isfile(config_abs):
        raise ConfigError(
            "未找到审查配置：%s\n"
            "       请先按项目实际情况创建该配置（字段说明见该技能 references/）。" % config_abs
        )

    try:
        with open(config_abs, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, OSError) as error:
        raise ConfigError("审查配置读取失败（%s）：%s" % (error, config_abs))

    if not isinstance(config, dict):
        raise ConfigError("审查配置顶层必须是 JSON 对象：%s" % config_abs)

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigError(
            "审查配置缺少必需键：%s（%s）\n"
            "       配置为审查范围的唯一来源，请补齐后再运行。"
            % ("、".join(missing), config_abs)
        )
    return config


def resolve_exclude_patterns(args_value, config):
    """确定排除模式：命令行 > 项目配置。"""
    if args_value:
        return split_patterns(args_value)
    return split_patterns(config["exclude_patterns"])


def resolve_file_patterns(args_value, config):
    """确定纳入审查的文件模式：命令行 > 项目配置。"""
    if args_value:
        return split_patterns(args_value)
    return split_patterns(config["file_patterns"])


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="csharp-code-review 门禁审查目标收集")
    parser.add_argument("--dir", default=None, help="git 命令执行目录（默认当前目录）")
    parser.add_argument("--config", default=None, help="项目配置路径（默认经索引 code_review.config 定位到项目侧）")
    parser.add_argument("--patterns", default=None,
                        help="纳入审查的文件模式（逗号分隔；缺省取项目配置，再缺省为 *.cs）")
    parser.add_argument("--exclude-patterns", default=None,
                        help="排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）")
    parser.add_argument("--no-header-check", action="store_true", help="关闭文件头 auto-generated 识别")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    workdir = args.dir or os.getcwd()
    root = find_project_root(workdir)
    if args.config:
        config_abs = args.config if os.path.isabs(args.config) else os.path.join(root, args.config)
        if not os.path.isfile(config_abs):
            raise ConfigError("指定的审查配置不存在：%s" % config_abs)
        try:
            with open(config_abs, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (json.JSONDecodeError, OSError) as error:
            raise ConfigError("指定的审查配置读取失败（%s）：%s" % (error, config_abs))
        if not isinstance(config, dict):
            raise ConfigError("指定的审查配置顶层必须是 JSON 对象：%s" % config_abs)
        missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
        if missing:
            raise ConfigError(
                "指定的审查配置缺少必需键：%s（%s）" % ("、".join(missing), config_abs)
            )
    else:
        config = load_config(root)

    include_patterns = resolve_file_patterns(args.patterns, config)
    exclude_patterns = resolve_exclude_patterns(args.exclude_patterns, config)

    include_regexes = [glob_to_regex(p) for p in include_patterns]
    exclude_regexes = [glob_to_regex(p) for p in exclude_patterns]
    if not include_regexes:
        print("[FAIL] --patterns 至少需要一个模式", file=sys.stderr)
        return 2

    try:
        entries = get_git_status(workdir)
    except RuntimeError as error:
        print(f"[FAIL] 获取 git 状态失败：{error}", file=sys.stderr)
        return 2

    tracked = []
    untracked = []
    excluded = []

    for xy, path in entries:
        code = xy[0] if xy[0] != " " else xy[1]
        is_untracked = xy == "??"

        # 仅收集匹配审查模式的路径
        if not matches_any(path, include_regexes):
            continue

        # 已跟踪变更只纳入 M/A/R/C/U，删除项（D）无审查目标
        if not is_untracked and code not in REVIEW_STATUS_CODES:
            continue

        # 路径级排除（生成代码目录/命名）
        if matches_any(path, exclude_regexes):
            excluded.append({"path": path, "reason": "exclude_pattern"})
            continue

        # 文件头级排除（未跟踪/新增文件无法用 git 判断内容）
        if not args.no_header_check:
            absolute = path if os.path.isabs(path) else os.path.join(workdir, path)
            if is_auto_generated_header(absolute):
                excluded.append({"path": path, "reason": "auto_generated_header"})
                continue

        item = {"status": xy, "path": path}
        if is_untracked:
            untracked.append(item)
        else:
            tracked.append(item)

    targets = sorted({item["path"] for item in tracked} | {item["path"] for item in untracked})

    if args.json:
        print(
            json.dumps(
                {
                    "tracked": tracked,
                    "untracked": untracked,
                    "targets": targets,
                    "excluded": excluded,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not targets:
            print("[INFO] 本次无匹配的审查目标。")
        else:
            print(f"# 本次审查目标（{len(targets)} 个）：已跟踪 {len(tracked)} / 未跟踪 {len(untracked)}")
            for path in targets:
                print(path)
            if excluded:
                print(f"# 已排除 {len(excluded)} 个（生成代码/规则命中）", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as error:
        # 配置是审查范围的唯一来源：配置不可用即明确报错，不静默回退默认值
        print("[FAIL] %s" % error, file=sys.stderr)
        sys.exit(3)
