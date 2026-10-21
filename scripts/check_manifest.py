#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎清单一致性校验（codebuddy-init / 引擎维护辅助）。

原「迁移文档同步门禁」（`rules/codebuddy-migration-sync/` 规则）随迁移机制废除而删除。
本脚本承担其留下的**轻量登记守护**职责：核对引擎实际目录与登记清单是否一致，避免
「新增技能/规则却漏登记」。

校验项：
  1. `skills/*`（排除 third-party）与 `rules/*` 目录，均在本文件下方的清单中登记；
  2. 反向：清单中的条目在实际目录中存在（无残留）；
  3. `project.index.json` 的 `files` / `rule_shells` 中 `path` 均为相对路径（入库共享前提）；
  4. `root_symlinks.entries` 的 `link` / `path` 均为相对路径，且引擎内链接存在且为符号链接。

退出码：
  0 —— 一致
  1 —— 存在不一致（打印差异清单）

用法：
  python .codebuddy/scripts/check_manifest.py
"""

import json
import os
import sys

# 引擎技能清单（新增/删除技能时同步本清单；与 README.md 目录结构节对应）
KNOWN_SKILLS = [
    "cmd-script-writing",
    "codebuddy-init",
    "csharp-code-review",
    "csharp-comment-checker",
    "csharp-comment-generator",
    "csharp-format-checker",
    "csharp-lsp",
    "csharp-test-coverage",
    "export-zipped-dir",
    "git-commit",
    "git-merge",
    "rule-consolidation",
    "session-lesson-distill",
    "unity-pipeline",
    "vcs-router",
]

# 引擎规则清单（新增/删除规则时同步本清单）
KNOWN_RULES = [
    "codebuddy-engine-vcs",
    "codebuddy-project-config",
    "csharp-code",
    "csharp-comment",
    "csharp-lsp",
    "csharp-test",
    "language",
    "project-guide",
    "unity-pipeline",
    "vcs-router",
]


def find_codebuddy_dir(start):
    """自 start 向上查找含 `.codebuddy` 子目录的目录，返回该 .codebuddy 的绝对路径。"""
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def list_dirs(path, skip_symlinks=False):
    """列出目录下的一级子目录名（排序）。

    skip_symlinks：跳过符号链接目录（如 .codebuddy/skills/ 下的项目专有技能链接
    `project-skills`，它指向项目侧 .codebuddy.project/skills，不属引擎技能清单）。
    """
    if not os.path.isdir(path):
        return []
    result = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if not os.path.isdir(full):
            continue
        if skip_symlinks and os.path.islink(full):
            continue
        result.append(name)
    return sorted(result)


def main():
    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        sys.stderr.write("[错误] 未找到 .codebuddy 目录。请在含 .codebuddy 的项目内运行。\n")
        return 1

    problems = []

    # 1/2. 技能与规则清单双向核对（跳过 skills/ 下的软链接：项目专有技能链接不在引擎清单内）
    actual_skills = [d for d in list_dirs(os.path.join(codebuddy_dir, "skills"), skip_symlinks=True)
                     if d != "third-party"]
    actual_rules = list_dirs(os.path.join(codebuddy_dir, "rules"))

    for name in actual_skills:
        if name not in KNOWN_SKILLS:
            problems.append("技能未登记：skills/%s（请加入 check_manifest.py 的 KNOWN_SKILLS 与 README.md）" % name)
    for name in KNOWN_SKILLS:
        if name not in actual_skills:
            problems.append("清单残留：KNOWN_SKILLS 含 `%s`，但 skills/%s 不存在" % (name, name))
    for name in actual_rules:
        if name not in KNOWN_RULES:
            problems.append("规则未登记：rules/%s（请加入 check_manifest.py 的 KNOWN_RULES 与 pattern-spec 规则全景表）" % name)
    for name in KNOWN_RULES:
        if name not in actual_rules:
            problems.append("清单残留：KNOWN_RULES 含 `%s`，但 rules/%s 不存在" % (name, name))

    # 3. 索引路径相对性
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        problems.append("缺少配置注册表：%s" % index_path)
    else:
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                index = json.load(handle)
        except (OSError, ValueError) as error:
            problems.append("配置注册表读取失败：%s" % error)
            index = {}
        for group_key in ("files", "rule_shells"):
            for code_name, entry in (index.get(group_key) or {}).items():
                path = (entry or {}).get("path")
                if not path:
                    problems.append("索引 %s.%s 缺少 path" % (group_key, code_name))
                elif os.path.isabs(path):
                    problems.append("索引 %s.%s.path 为绝对路径（须为相对路径）：%s"
                                    % (group_key, code_name, path))

        # artifacts.dirs：产物目录路径相对性
        for logical_name, rel in (index.get("artifacts") or {}).get("dirs", {}).items():
            if not isinstance(rel, str) or not rel:
                problems.append("索引 artifacts.dirs.%s 值非法" % logical_name)
            elif os.path.isabs(rel):
                problems.append("索引 artifacts.dirs.%s 为绝对路径（须为相对路径）：%s"
                                % (logical_name, rel))

        # root_symlinks.entries：链接路径 / 源文件路径的相对性，且引擎内链接须存在（软链接）
        project_root = os.path.dirname(codebuddy_dir)
        for logical_name, entry in (index.get("root_symlinks") or {}).get("entries", {}).items():
            if not isinstance(entry, dict):
                problems.append("索引 root_symlinks.entries.%s 必须是对象" % logical_name)
                continue
            link_rel = entry.get("link")
            src_rel = entry.get("path")
            for label, rel in (("link", link_rel), ("path", src_rel)):
                if not isinstance(rel, str) or not rel:
                    problems.append("索引 root_symlinks.entries.%s.%s 缺失" % (logical_name, label))
                elif os.path.isabs(rel):
                    problems.append("索引 root_symlinks.entries.%s.%s 为绝对路径（须为相对路径）：%s"
                                    % (logical_name, label, rel))
            if isinstance(link_rel, str) and link_rel and not os.path.isabs(link_rel):
                link_abs = os.path.normpath(os.path.join(project_root, link_rel))
                if not os.path.lexists(link_abs):
                    problems.append("索引 root_symlinks.entries.%s 的链接不存在（请运行 codebuddy-init）：%s"
                                    % (logical_name, link_rel))
                elif not os.path.islink(link_abs):
                    problems.append("索引 root_symlinks.entries.%s 的链接路径不是符号链接：%s"
                                    % (logical_name, link_rel))

    if problems:
        print("[不一致] 发现 %d 项：" % len(problems))
        for item in problems:
            print("  - %s" % item)
        return 1

    print("[一致] 技能 %d 个、规则 %d 个、索引路径均合规。"
          % (len(actual_skills), len(actual_rules)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
