#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-code-review 门禁审查目标收集脚本（SVN 版）：汇总本次待审查的变更文件清单。

背景：
    `collect_review_targets.py`（Git 版）依赖 `git status`，在 SVN 工作副本中不可用；
    而手工执行 `svn status | grep -E '^[ADMR]'` 只拿到「已版本化改动」，未版本化新文件
    （`?` 状态）需另一条命令，且在未版本化目录上只报目录、不报其中的文件，
    新文件因此永远进不了审查清单。本脚本把这些坑一次性收口。

与 Git 版的差异（其余过滤语义完全一致，共用同一批函数）：
    1. **状态来源**：`svn status --xml` 而非 `git status --porcelain`。XML 输出是结构化
       且带 `encoding` 声明，中文路径无需猜测控制台代码页。
    2. **未版本化目录必须自行展开**：`svn status` 对未版本化目录只输出目录本身
       （不论 `--depth` 取值），脚本用 `os.walk` 展开为具体文件后再走过滤。
       未版本化目录内部不可能存在已版本化子项（SVN 要求祖先先入库），故无需回查状态。
    3. **忽略项直接不作为候选**：不传 `--no-ignore`，`svn:ignore` 覆盖的文件根本不出现在
       状态输出中，比 Git 版再按黑名单兜一层更省事。
    4. **路径基准要换算**：`svn status` 输出相对命令执行目录，而 `--dir` 可以是项目内任意
       子目录（`svn status` 只覆盖该子树，不像 `git status` 覆盖整个仓库）。脚本统一换算为
       绝对路径，再输出**项目根相对路径**——清单要交给审查方读文件，`--dir` 相对路径离开
       该目录就解析不到。

配置（**项目相关内容独立配置、经索引定位**）：
    与 Git 版共用同一份配置，经 `.codebuddy/project.index.json` 的 `code_review.config`
    定位到 `<项目根>/.codebuddy.project/configs/skills/csharp/csharp-code-review/config.json`。
    因此切换 VCS 只需把 `collect_cmd` 换成指向本脚本，白/黑名单参数不用重写。

    两种模式由「是否配了白名单」自动选择（`include_patterns` 为**可选**键）：
      - 白名单模式：`include_patterns` 非空 → 默认拒绝，只有匹配的文件进入审查目标；
      - 黑名单模式：`include_patterns` 缺失或为空 → 默认放行，仅按 `exclude_patterns` 排除。

    过滤顺序：**扩展名（技能固有边界）→ 白名单（可选）→ 黑名单 → 文件头 auto-generated**。

用法：
    python collect_review_targets_svn.py [--dir <工作副本目录>]
                                         [--config <配置路径>]
                                         [--include-patterns "*.cs"]
                                         [--exclude-patterns "<逗号分隔模式>"]
                                         [--no-header-check] [--json]

参数：
    --dir               svn 命令执行目录（默认当前目录）。必须是**工作副本内的目录**；
                       指向子目录时只收集该子树的变更（`svn status` 的语义）
    --config            项目配置路径（默认经索引 code_review.config 定位到项目侧）
    --include-patterns  纳入审查的文件模式（白名单，逗号分隔；缺省取项目配置）
    --exclude-patterns  排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）
    --no-header-check   关闭「读取文件头识别 auto-generated」检查
    --json              以 JSON 输出（tracked / untracked / targets / excluded）

输出：
    文本模式：逐行输出审查目标路径（**项目根相对**，可直接作为审查文件清单传递）。
    JSON 模式：结构化清单，区分已版本化变更与未版本化新文件。

退出码：
    0 —— 收集完成（列表可能为空）
    2 —— svn 不可用、非工作副本、--dir 不存在或参数错误
    3 —— 配置缺失、损坏或缺少必需键
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

# 与 Git 版共用配置定位、模式匹配、文件头判定等实现：过滤语义必须单一来源，
# 否则两个脚本的审查范围会随改动漂移，且不会有任何报错。
from collect_review_targets import (
    ConfigError,
    TARGET_EXTENSION,
    find_project_root,
    glob_to_regex,
    init_stdout,
    is_auto_generated_header,
    load_config,
    matches_any,
    normalize,
    resolve_exclude_patterns,
    resolve_include_patterns,
    to_project_rel,
)

# 需要纳入审查的 svn 状态（modified=修改、added=新增、replaced=替换、conflicted=冲突）。
# 与 Git 版的 M/A/R/C/U 对齐；deleted/missing 无审查目标，ignored/external/incomplete 不属本次范围。
REVIEW_ITEMS = {"modified", "added", "replaced", "conflicted"}

# 未版本化（`?` 状态）：文件直接入候选，目录需展开为其中的文件
UNVERSIONED_ITEM = "unversioned"


def run_svn_status(workdir):
    """执行 `svn status --xml` 并返回原始字节；失败时抛出 RuntimeError。

    不传 `--no-ignore`：被 `svn:ignore` 覆盖的文件不应进入审查清单，
    让 svn 直接不输出它们，比事后按黑名单兜一层更可靠。

    **必须显式识别「不是工作副本」**：该情形下 `svn status` 的退出码仍是 0，
    只在 stderr 打一条 `W155007 ... is not a working copy`，XML 里是空的 `<target>`。
    若只看退出码，门禁会得到「本次无审查目标」并顺利放行——静默漏审比报错危险得多。
    """
    try:
        result = subprocess.run(
            ["svn", "status", "--xml"],
            cwd=workdir,
            capture_output=True,
        )
    except FileNotFoundError:
        raise RuntimeError("未找到 svn 可执行文件，请确认已安装 Subversion 命令行客户端并在 PATH 中")
    except OSError as error:
        raise RuntimeError("执行 svn status 失败：%s" % error)

    stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
    if "is not a working copy" in stderr or "E155007" in stderr or "W155007" in stderr:
        raise RuntimeError(
            "目录不是 SVN 工作副本：%s\n       %s" % (workdir, stderr))
    if result.returncode != 0:
        raise RuntimeError(stderr or "svn status 执行失败（退出码 %d）" % result.returncode)
    return result.stdout or b""


def parse_status_xml(raw):
    """解析 `svn status --xml`，返回 [(item, tree_conflicted, path)]。

    `path` 为**命令执行目录相对路径**，Windows 下分隔符为反斜杠，此处统一归一化为正斜杠。
    `path="."` 表示目标目录自身，由调用方按状态区分处理。
    """
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise RuntimeError("svn status 的 XML 输出解析失败：%s" % error)

    entries = []
    for target in root.findall("target"):
        for entry in target.findall("entry"):
            status = entry.find("wc-status")
            if status is None:
                continue
            entries.append((
                status.get("item") or "",
                (status.get("tree-conflicted") or "").lower() == "true",
                normalize(entry.get("path") or ""),
            ))
    return entries


def expand_unversioned(workdir, relative):
    """把未版本化路径展开为候选文件清单（相对 workdir 的正斜杠路径）。

    `svn status` 对未版本化目录只报目录本身、不递归（`--depth infinity` 也一样），
    不展开就会漏掉所有新建目录里的 `.cs`——这正是「新文件永远不被审查」的根因。
    未版本化目录内部不存在已版本化的子项（SVN 要求祖先先入库），因此直接遍历即可。

    `relative` 为 `.` 时表示「工作目录自身是未版本化目录」（在未入库目录内运行脚本），
    此时按目录展开，返回其中的文件。
    """
    if relative in ("", "."):
        absolute = workdir
    else:
        absolute = os.path.join(workdir, relative.replace("/", os.sep))
    if os.path.isdir(absolute):
        found = []
        for current, dirs, files in os.walk(absolute):
            # 未版本化目录内理论上没有 .svn，仍显式跳过，避免误收管理目录
            dirs[:] = [name for name in dirs if name != ".svn"]
            for name in files:
                if name.lower().endswith(TARGET_EXTENSION):
                    full = os.path.join(current, name)
                    found.append(normalize(os.path.relpath(full, workdir)))
        return found
    if relative.lower().endswith(TARGET_EXTENSION):
        return [relative]
    return []


def collect_candidates(workdir):
    """汇总候选清单，返回 (tracked, untracked)，元素为 (状态名, 执行目录相对路径)。

    树冲突**不能一概纳入**：删除式树冲突（本地 `svn rm`、远端有改动）的 `item` 是
    `deleted` 且 `tree-conflicted="true"`，磁盘上已无该文件；把它当作审查目标会让
    审查方读到「文件不存在」而卡住。因此「状态命中」之后还要过一道**磁盘存在性**校验——
    状态位只说工作副本怎么记的，审查方要读的是磁盘。该判据同时挡掉纯属性变更
    （`item="normal"`，本就不在 `REVIEW_ITEMS` 内）。
    """
    tracked = []
    untracked = []
    for item, tree_conflicted, path in parse_status_xml(run_svn_status(workdir)):
        if item == UNVERSIONED_ITEM:
            # `.` 说明执行目录自身未入库，同样按目录展开，否则在其中运行时永远收不到目标
            for expanded in expand_unversioned(workdir, path):
                untracked.append((item, expanded))
            continue
        if path in ("", "."):
            # 目标目录自身：目录不是审查对象（其属性变更也不涉及源码内容）
            continue
        if item not in REVIEW_ITEMS and not tree_conflicted:
            continue
        absolute = os.path.join(workdir, path.replace("/", os.sep))
        if os.path.isfile(absolute):
            tracked.append((item, path))
    return tracked, untracked


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="csharp-code-review 门禁审查目标收集（SVN 版）")
    parser.add_argument("--dir", default=None, help="svn 命令执行目录（默认当前目录）")
    parser.add_argument("--config", default=None, help="项目配置路径（默认经索引 code_review.config 定位到项目侧）")
    parser.add_argument("--include-patterns", default=None,
                        help="纳入审查的文件模式（白名单，逗号分隔；缺省取项目配置的 include_patterns）")
    parser.add_argument("--exclude-patterns", default=None,
                        help="排除模式（逗号分隔；缺省取项目配置的 exclude_patterns）")
    parser.add_argument("--no-header-check", action="store_true", help="关闭文件头 auto-generated 识别")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    workdir = args.dir or os.getcwd()
    root = find_project_root(workdir)
    if not root:
        raise ConfigError(
            "未找到项目根（含 .codebuddy 的目录）。脚本锚点与当前目录（%s）向上均未命中，"
            "请确认 .codebuddy 引擎完整。" % workdir)
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
        if "exclude_patterns" not in config:
            raise ConfigError("指定的审查配置缺少必需键：exclude_patterns（%s）" % config_abs)
    else:
        config = load_config(root)

    include_patterns = resolve_include_patterns(args.include_patterns, config)
    exclude_patterns = resolve_exclude_patterns(args.exclude_patterns, config)

    include_regexes = [glob_to_regex(p) for p in include_patterns]
    exclude_regexes = [glob_to_regex(p) for p in exclude_patterns]

    # 白名单模式由「是否配了白名单」决定：配了 → 默认拒绝；没配 → 默认放行，仅按黑名单排除
    whitelist_mode = bool(include_regexes)
    if not whitelist_mode and not exclude_regexes:
        print("[FAIL] 白名单与黑名单均未配置，审查范围无法确定（配置 include_patterns 或 exclude_patterns）",
              file=sys.stderr)
        return 2

    workdir_abs = os.path.abspath(workdir)
    if not os.path.isdir(workdir_abs):
        # 前置校验：`subprocess` 遇不存在的 cwd 抛 NotADirectoryError，落到下面的
        # OSError 分支会被说成「svn status 执行失败」，把「参数写错」误报成「svn 出问题」
        print("[FAIL] --dir 指定的目录不存在：%s" % workdir_abs, file=sys.stderr)
        return 2
    try:
        tracked_candidates, untracked_candidates = collect_candidates(workdir_abs)
    except RuntimeError as error:
        print(f"[FAIL] 获取 svn 状态失败：{error}", file=sys.stderr)
        return 2

    tracked = []
    untracked = []
    excluded = []

    for source, candidates in ((tracked, tracked_candidates), (untracked, untracked_candidates)):
        for item, path in candidates:
            # 技能固有边界：只审 C# 源码（与白名单无关、始终生效）
            if not path.lower().endswith(TARGET_EXTENSION):
                continue

            project_rel = to_project_rel(path, workdir_abs, root)
            if project_rel is None:
                # 变更不在项目根内（同一工作副本的其他子项目），不属于本次审查范围
                continue

            # 白名单模式：不匹配白名单的路径一律不进入审查（默认拒绝）
            if whitelist_mode and not matches_any(project_rel, include_regexes):
                continue

            # 路径级排除（生成代码目录/命名）
            if matches_any(project_rel, exclude_regexes):
                excluded.append({"path": project_rel, "reason": "exclude_pattern"})
                continue

            # 文件头级排除（新增/未版本化文件无法靠路径判断内容）
            if not args.no_header_check:
                absolute = os.path.join(workdir_abs, path.replace("/", os.sep))
                if is_auto_generated_header(absolute):
                    excluded.append({"path": project_rel, "reason": "auto_generated_header"})
                    continue

            # 输出**项目根相对路径**而非 `--dir` 相对路径：清单要交给审查方去读文件，
            # 而 `--dir` 可以是项目内任意子目录（`svn status` 只覆盖该子树），
            # 用它作基准输出的路径离开该目录就解析不到。项目根相对路径是可移植的唯一口径，
            # 与配置模式的书写口径也一致。
            source.append({"status": item, "path": project_rel})

    targets = sorted({item["path"] for item in tracked} | {item["path"] for item in untracked})

    if args.json:
        print(
            json.dumps(
                {
                    "vcs": "svn",
                    "mode": "whitelist" if whitelist_mode else "blacklist",
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
        mode_text = "白名单模式" if whitelist_mode else "黑名单模式（未配置白名单）"
        if not targets:
            print(f"[INFO] 本次无匹配的审查目标（{mode_text}）。")
        else:
            print(f"# 本次审查目标（{len(targets)} 个，{mode_text}）："
                  f"已版本化 {len(tracked)} / 未版本化 {len(untracked)}")
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
