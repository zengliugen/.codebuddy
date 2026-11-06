#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""忽略配置（.gitignore）分层归属检测与修复。

规范见技能 references/spec.md（本脚本只实现机械可判定的部分）。

检测三个维度：

  1. **纯冗余文件**：组件根 .gitignore 去掉树根已覆盖的通用项后，一条专属规则都不剩。
     这类文件没有任何作用，只会让树根规则与组件副本各自演化、逐渐分叉。
  2. **格式不合规**：组件根缺 `#  目录:` 头注释、头注释路径与实际扫描根不一致、
     存在悬空分组（标题下无规则）、同一文件内规则重复、缺少常见通用项。
  3. **树根兜底缺失**：引擎树根或项目侧树根缺少 `__pycache__/`、`*.pyc`、`.DS_Store`
     等通用项——此时任何不自带 .gitignore 的组件都会把缓存直接入库。

用法：

    # 只检测（默认），有问题退出码 1
    python tool_gitignore.py scan

    # 检测并输出 JSON（供其他脚本消费）
    python tool_gitignore.py scan --json

    # 修复：删除纯冗余文件、统一组件根格式
    python tool_gitignore.py fix

    # 只处理某一棵树
    python tool_gitignore.py scan --tree engine

退出码：
    0 —— 无问题（或 fix 后已全部修好）
    1 —— 存在问题（scan 模式）
    2 —— 参数错误 / 找不到 .codebuddy 目录
"""

import argparse
import json
import os
import re
import sys

# 树根必须含有的通用项：(判定用的规则片段, 人类可读说明)
GENERIC_ITEMS = (
    ("__pycache__", "Python 字节码目录"),
    ("*.pyc", "Python 字节码文件"),
    (".DS_Store", "macOS 目录元数据"),
)

# 组件根规范样式里「通用项分组」的标准写法（仅用于生成，不用于判定）
GENERIC_BLOCK = "__pycache__/\n*.pyc\n*.pyo"

# 头注释行：`#  目录: <路径>`
HEADER_PATTERN = re.compile(r"^#\s+目录:\s*(.+?)\s*$")

# 视为「分隔线 / 标题」的注释行，用于识别空分组
SECTION_PATTERN = re.compile(r"^#\s*-{3,}|^#\s*={3,}")


def init_stdout():
    """Windows 下统一 UTF-8 输出，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def find_codebuddy_dir(start):
    """自 start 向上查找名为 .codebuddy 的目录，返回其绝对路径；找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        if os.path.basename(current) == ".codebuddy" and os.path.isdir(current):
            return current
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def read_rules(path):
    """读取 .gitignore 的有效规则行（去注释、空行、行尾空白），保留顺序。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    rules = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rules.append(stripped)
    return rules


def read_text(path):
    """读取整个文件文本；失败返回空串。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def covered_by_root(rule, root_rules):
    """判断组件根的一条规则是否已被树根等价规则覆盖。

    不能只做字符串相等比对——树根惯用 `**/bin/` 这类「任意层级」通配，
    而组件根写的是 `bin/`（只匹配组件根下一层）。两者在**语义**上等价：
    `**/bin/` 覆盖所有名为 bin 的目录，`bin/` 只能是其真子集。

    实测依据：树根有 `**/bin/` 时，组件根的 `bin/` 删掉后产物仍被忽略
    （二者命中同一路径，只是规则来源不同）。反之 `bin/` 不能覆盖 `**/bin/`——
    方向是单向的，故只判「通配是否覆盖具体」。

    归一化规则：把候选规则按 `/` 拆段，逐段比对；树根规则的段若为 `**`，
    则匹配任意多层。这足以覆盖 gitignore 的常用写法，不追求完整语义实现
    （正则、字符类等复杂写法仍退回精确比对，宁可漏报也不误删）。
    """
    if rule in root_rules:
        return True

    rule_segs = [seg for seg in rule.split("/") if seg]
    for root_rule in root_rules:
        root_segs = [seg for seg in root_rule.split("/") if seg]
        if not root_segs or "**" not in root_segs:
            continue
        # 尾斜杠与否不影响目录匹配语义，比对前已因 split 去空段而统一
        if _wildcard_match(root_segs, rule_segs):
            return True
    return False


def _wildcard_match(pattern_segs, target_segs):
    """段级通配匹配：pattern 中的 `**` 匹配任意数量段（含零段）。

    递归实现，段数很少（通常 ≤4），不存在性能问题。
    """
    if not pattern_segs:
        return not target_segs
    head, rest = pattern_segs[0], pattern_segs[1:]
    if head == "**":
        # `**` 吃掉 0..n 段
        for index in range(len(target_segs) + 1):
            if _wildcard_match(rest, target_segs[index:]):
                return True
        return False
    if not target_segs:
        return False
    if head != target_segs[0]:
        return False
    return _wildcard_match(rest, target_segs[1:])


def parse_structure(text):
    """解析文件结构，返回 (头注释路径或 None, 悬空分组标题列表, 重复规则列表)。

    悬空分组：某个标题块之后、下一个规则之前没有任何规则行。

    **连续注释行算同一个标题块**——多行分组说明（如「Unity CLI 离线安装二进制……」
    后跟一行「该二进制不随 git/引擎包分发……」）是合法的紧凑写法，逐行判悬空会误报。
    """
    header = None
    lines = text.splitlines()
    dangling = []
    seen_rules = []
    duplicates = []

    current_title = None
    current_title_line = 0
    has_rule_under_title = False
    previous_was_comment = False

    def close_title():
        """结束当前分组：若标题下无规则则记为悬空。"""
        if current_title is not None and not has_rule_under_title:
            dangling.append((current_title_line, current_title))

    for index, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            previous_was_comment = False
            continue
        if stripped.startswith("#"):
            if header is None:
                matched = HEADER_PATTERN.match(stripped)
                if matched:
                    header = matched.group(1)
                    previous_was_comment = False
                    continue
            # 分隔线不单独构成分组标题，跳过
            if SECTION_PATTERN.match(stripped):
                close_title()
                current_title = None
                has_rule_under_title = False
                previous_was_comment = False
                continue
            body = stripped.lstrip("#").strip()
            if not body:
                previous_was_comment = False
                continue
            if previous_was_comment and current_title is not None:
                # 连续注释行：视为同一标题块的续行，不新起分组
                current_title += " " + body
                previous_was_comment = True
                continue
            close_title()
            current_title = body
            current_title_line = index
            has_rule_under_title = False
            previous_was_comment = True
            continue
        # 规则行
        previous_was_comment = False
        if stripped in seen_rules:
            duplicates.append((index, stripped))
        else:
            seen_rules.append(stripped)
        has_rule_under_title = True

    close_title()
    return header, dangling, duplicates


def expected_scan_root(rel_dir):
    """按物理相对路径推导「引擎扫描根视角」的路径。

    lib/<pack>/<类型>/<名>  → .codebuddy/<类型>/<pack>/<名>
    <类型>/<pack>/<名>      → .codebuddy/<类型>/<pack>/<名>
    """
    parts = rel_dir.replace(os.sep, "/").split("/")
    if parts and parts[0] == "lib" and len(parts) >= 4:
        return ".codebuddy/%s/%s/%s" % (parts[2], parts[1], parts[3])
    return ".codebuddy/" + rel_dir.replace(os.sep, "/")


def collect_vendor_prefixes(codebuddy_dir):
    """从 lib/packs.json 读取 vendor 包的物理路径前缀，返回 {前缀: 包名}。

    判据只用**显式元数据** `vendor: true`，不做文本猜测（README 里的「只读 vendor」
    是给人看的说明，不是机器可读契约；靠正则匹配维护档位表会在表格调整时静默失效）。
    读取失败时返回空字典——此时 vendor 包会被当作普通包检查，宁可多报也不误删上游文件。

    返回映射而非集合：扫描结果要按**包名**汇报（`vendor_skipped: ["yao-meta-skill"]`），
    而不是物理路径前缀——后者对读者无意义，且包内组件类型变化时会跟着变。
    """
    path = os.path.join(codebuddy_dir, "lib", "packs.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            packs = json.load(handle).get("packs") or {}
    except (OSError, ValueError):
        return {}
    prefixes = {}
    for name, meta in packs.items():
        if not isinstance(meta, dict) or not meta.get("vendor"):
            continue
        for comp_type in ("rules", "skills", "agents"):
            prefixes["lib/%s/%s" % (name, comp_type)] = name
    return prefixes


def collect_component_files(tree_root, vendor_prefixes=()):
    """枚举某棵树下全部组件级 .gitignore（排除树根自身与 vendor 包）。

    返回 [(物理相对目录, 绝对路径)]。
    """
    results = []
    for current, dirs, files in os.walk(tree_root):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel = os.path.relpath(current, tree_root)
        if rel == ".":
            continue
        if ".gitignore" not in files:
            continue
        rel_posix = rel.replace(os.sep, "/")
        # vendor 包内容由上游维护，本地不改其 .gitignore（spec §3.3）。
        # 传进来的可能是 set 或 dict，两者都支持 in；用 dict 时按键匹配前缀。
        if any(rel_posix == prefix or rel_posix.startswith(prefix + "/")
               for prefix in vendor_prefixes):
            continue
        results.append((rel, os.path.join(current, ".gitignore")))
    return sorted(results)


def classify(rel_dir, path, root_rules):
    """分析单个组件级 .gitignore，返回问题字典列表。"""
    problems = []
    rules = read_rules(path)
    text = read_text(path)
    rel_display = rel_dir.replace(os.sep, "/")

    if not rules:
        problems.append({
            "type": "empty_file",
            "file": rel_display,
            "detail": "文件不含任何规则（只剩注释或全空），应删除",
        })
        return problems

    # 1. 纯冗余：所有规则都被树根覆盖（精确相同，或树根通配已涵盖）。
    #    注意此处**不提前返回**——即使整体判为冗余，头注释漂移、悬空分组、重复规则
    #    仍是独立的缺陷，一次性全报出来才便于一次改完；否则修完冗余再跑又冒出新问题。
    own_rules = [r for r in rules if not covered_by_root(r, root_rules)]
    if not own_rules:
        problems.append({
            "type": "redundant",
            "file": rel_display,
            "detail": "全部 %d 条规则都被树根 .gitignore 覆盖（含 **/ 通配），属纯冗余，"
                      "应删除该文件" % len(rules),
        })

    # 2. 头注释
    header, dangling, duplicates = parse_structure(text)
    if header is None:
        problems.append({
            "type": "missing_header",
            "file": rel_display,
            "detail": "缺少 `#  目录: <扫描根路径>` 头注释",
        })
    else:
        expected = expected_scan_root(rel_dir)
        if header != expected:
            problems.append({
                "type": "header_mismatch",
                "file": rel_display,
                "detail": "头注释路径与实际扫描根不符：注释为 %s，应为 %s"
                          % (header, expected),
            })

    # 3. 悬空分组
    for line_no, title in dangling:
        problems.append({
            "type": "dangling_section",
            "file": rel_display,
            "line": line_no,
            "detail": "分组「%s」之下没有任何规则，属悬空注释" % title,
        })

    # 4. 重复规则
    for line_no, rule in duplicates:
        problems.append({
            "type": "duplicate_rule",
            "file": rel_display,
            "line": line_no,
            "detail": "规则重复出现：%s" % rule,
        })

    # 5. 组件根抄树根（有专属规则但仍混入被树根覆盖的项）。
    #    整体冗余时已在第 1 项说明「删整个文件」，此处不再重复列同一批规则。
    copies = [r for r in rules if covered_by_root(r, root_rules)]
    if copies and own_rules:
        problems.append({
            "type": "copied_generic",
            "file": rel_display,
            "detail": "含 %d 条已被树根覆盖的规则（%s），应删除这些行"
                      % (len(copies), "、".join(copies[:5])),
        })
    return problems


def check_tree_root(path, label):
    """校验树根 .gitignore 是否含通用项兜底。"""
    problems = []
    if not os.path.isfile(path):
        problems.append({
            "type": "missing_tree_root",
            "file": label,
            "detail": "树根 .gitignore 不存在。组件根只放专属产物，通用项必须由树根兜底",
        })
        return problems
    rules = read_rules(path)
    missing = [desc for token, desc in GENERIC_ITEMS
               if not any(token in rule for rule in rules)]
    if missing:
        problems.append({
            "type": "missing_generic",
            "file": label,
            "detail": "缺少通用项兜底：%s。补上 %s（组件专属项仍留组件根，不要上移）"
                      % ("、".join(missing),
                         "、".join(token for token, _ in GENERIC_ITEMS)),
        })
    return problems


def run_scan(codebuddy_dir, tree_filter=None):
    """执行扫描，返回 (问题列表, 统计信息)。

    `vendor_skipped` 按**包名**回报（去重排序），而非物理路径前缀——读者要知道的是
    「跳过了哪个 vendor 包」，不是「跳过了 lib/<包>/<类型> 这串路径」。
    """
    project_root = os.path.dirname(codebuddy_dir)
    vendor_prefixes = collect_vendor_prefixes(codebuddy_dir)
    trees = [
        ("engine", codebuddy_dir, ".codebuddy"),
        ("project", os.path.join(project_root, ".codebuddy.project"),
         ".codebuddy.project"),
    ]
    problems = []
    stats = {"trees": [], "component_files": 0, "redundant": 0,
             "vendor_skipped": sorted(set(vendor_prefixes.values()))}

    for tree_key, tree_root, label in trees:
        if tree_filter and tree_filter != tree_key:
            continue
        if not os.path.isdir(tree_root):
            continue
        root_gitignore = os.path.join(tree_root, ".gitignore")
        root_rules = set(read_rules(root_gitignore))
        problems.extend(check_tree_root(root_gitignore, label + "/.gitignore"))

        files = collect_component_files(tree_root, vendor_prefixes)
        stats["component_files"] += len(files)
        for rel_dir, path in files:
            found = classify(rel_dir, path, root_rules)
            if any(p["type"] == "redundant" for p in found):
                stats["redundant"] += 1
            problems.extend(found)
        stats["trees"].append({
            "tree": label,
            "component_files": len(files),
        })
    return problems, stats


def main():
    """解析参数并执行 scan / fix。"""
    init_stdout()
    parser = argparse.ArgumentParser(
        description="忽略配置分层归属检测与修复（规范见 references/spec.md）")
    parser.add_argument("action", choices=("scan", "fix"),
                        help="scan 只检测；fix 修复可机械修复的问题")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--tree", choices=("engine", "project"),
                        help="只处理指定的一棵树（默认两棵都处理）")
    args = parser.parse_args()

    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        sys.stderr.write("[失败] 未找到 .codebuddy 目录，请在含该目录的项目内运行\n")
        return 2

    problems, stats = run_scan(codebuddy_dir, args.tree)

    if args.json:
        print(json.dumps({"problems": problems, "stats": stats},
                         ensure_ascii=False, indent=2))
        return 0 if not problems else 1

    if args.action == "fix":
        # 修复由调用方（Agent / 人工）按 spec 执行；脚本只给出可机械处理的清单，
        # 避免脚本擅自重写注释、丢失人工补充的分组理由。
        removable = [p for p in problems if p["type"] in ("redundant", "empty_file")]
        if removable:
            print("[待删除] 以下文件按规范应删除：")
            for item in removable:
                print("  - %s：%s" % (item["file"], item["detail"]))
        if not problems:
            print("[通过] 忽略配置符合规范")
        return 0 if not problems else 1

    if not problems:
        print("[通过] 忽略配置符合规范（组件级文件 %d 个）" % stats["component_files"])
        return 0

    by_type = {}
    for item in problems:
        by_type.setdefault(item["type"], []).append(item)

    labels = {
        "redundant": "纯冗余文件（应删除）",
        "empty_file": "空文件（应删除）",
        "missing_header": "缺少头注释",
        "header_mismatch": "头注释路径不符",
        "dangling_section": "悬空分组",
        "duplicate_rule": "重复规则",
        "copied_generic": "抄了树根通用项",
        "missing_tree_root": "树根文件缺失",
        "missing_generic": "树根缺通用项兜底",
    }
    for key in ("missing_tree_root", "missing_generic", "redundant", "empty_file",
                "missing_header", "header_mismatch", "dangling_section",
                "duplicate_rule", "copied_generic"):
        items = by_type.get(key)
        if not items:
            continue
        print("\n== %s（%d）==" % (labels.get(key, key), len(items)))
        for item in items:
            location = item["file"]
            if item.get("line"):
                location += ":%d" % item["line"]
            print("  - %s" % location)
            print("      %s" % item["detail"])

    print("\n共 %d 项问题。规范见 skills/tool/tool-gitignore-layout/references/spec.md"
          % len(problems))
    return 1


if __name__ == "__main__":
    sys.exit(main())
