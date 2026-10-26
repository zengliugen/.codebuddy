#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎更新影响分析（engine-sync 技能）。

对比引擎仓库两个版本之间的「项目侧契约」变化，输出需要同步到项目侧的清单：
索引条目（files / rule_shells / artifacts.dirs / root_symlinks.entries）与包注册表
（lib/packs.json 的包与组件）的增删改，并交叉项目侧磁盘现状给出动作建议。

设计原则：
- **只读**：不修改任何文件，仅输出分析结果。
- **索引为唯一事实来源**：不硬编码包名、路径、组件名。
- **结构化输出**：默认人类可读，--json 输出机器可读。

用法：
  python analyze_impact.py --from HEAD~1 --to HEAD
  python analyze_impact.py --from 4621b75 --to 502eff8 --json
  python analyze_impact.py --from HEAD~1 --to HEAD --project-root <项目根>

退出码：
  0 —— 分析完成（无论有无影响）
  3 —— 前置条件不满足（非 git 仓库 / 版本不存在 / 索引不可读）
"""

import argparse
import json
import os
import subprocess
import sys

INDEX_REL = "project.index.json"
PACKS_REL = os.path.join("lib", "packs.json")


class AnalyzeError(RuntimeError):
    """前置条件不满足或读取失败时抛出，由入口转为明确错误退出。"""


def find_engine_dir(start):
    """自 start 向上查找含 project.index.json 的目录，返回引擎根（.codebuddy）。

    用标记文件定位而非固定层数：脚本可能位于 .codebuddy/skills/<pack>/<技能>/scripts/，
    层数随技能在扫描根下的深度变化，写死层数会在结构调整后失效。
    """
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, INDEX_REL)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise AnalyzeError("未能定位引擎根（未找到 %s）：自 %s 向上查找失败" % (INDEX_REL, start))
        current = parent


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if sys.platform == "win32":
        import ctypes as _ctypes
        try:
            _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            _ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def run_git(args, cwd):
    """执行 git 命令，返回 (退出码, stdout, stderr)（均去除首尾空白）。"""
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as error:
        raise AnalyzeError("无法执行 git 命令：%s" % error)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def load_json_at_ref(repo, ref, rel):
    """读取某版本中的 JSON 文件；不存在时返回空字典（不视为错误）。"""
    rc, out, err = run_git(["show", "%s:%s" % (ref, rel.replace(os.sep, "/"))], repo)
    if rc != 0:
        if "does not exist" in err or "exists on disk" in err or "Path" in err:
            return {}
        return {}
    if not out.strip():
        return {}
    try:
        return json.loads(out)
    except ValueError as error:
        raise AnalyzeError("%s 在版本 %s 处 JSON 解析失败：%s" % (rel, ref, error))


def resolve_ref(repo, ref):
    """把 ref 解析为完整哈希；不存在时报错。"""
    rc, out, _err = run_git(["rev-parse", "--verify", "--quiet", ref], repo)
    if rc != 0 or not out:
        raise AnalyzeError("版本不存在：%s（请确认已 fetch 到该提交）" % ref)
    return out


def pack_of_path(rel):
    """从项目侧路径中解析所属包名（路径含 pack 层，见索引规范 §3.3）。

    约定为 .codebuddy.project/<configs|caches>/<类别>/<pack>/<组件>/...；
    非该结构（如根级通用目录）返回空串，表示不按包过滤。
    """
    parts = str(rel).replace("\\", "/").split("/")
    for index, segment in enumerate(parts):
        if segment in ("skills", "rules", "agents") and index + 2 < len(parts):
            return parts[index + 1]
    return ""


def project_path(project_root, rel):
    """把索引中的相对路径转为绝对路径。"""
    return os.path.normpath(os.path.join(project_root, str(rel).replace("/", os.sep)))


def dict_diff(old, new):
    """比较两个字典的键集合，返回 (新增键, 删除键, 共同键)。"""
    old_keys = set(old or {})
    new_keys = set(new or {})
    return sorted(new_keys - old_keys), sorted(old_keys - new_keys), sorted(old_keys & new_keys)


def active_packs(project_root, packs):
    """读取项目侧已装包集合，合并默认包，得到「生效包集合」。"""
    defaults = set(name for name, meta in (packs or {}).items() if (meta or {}).get("default"))
    state_path = os.path.join(project_root, ".codebuddy.project", "configs", "packs.json")
    installed = []
    if os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                installed = json.load(handle).get("installed") or []
        except (OSError, ValueError):
            installed = []
    return defaults | set(str(n) for n in installed)


def add_item(items, kind, change, name, action, severity, pack="", old="", new="", note=""):
    """追加一条影响项（统一结构，便于 JSON 与文本两种输出）。"""
    items.append({
        "kind": kind,
        "change": change,
        "name": name,
        "pack": pack,
        "old": old,
        "new": new,
        "action": action,
        "severity": severity,
        "note": note,
    })


def analyze_index(old_index, new_index, project_root, active):
    """分析索引四个分区的增删改，交叉项目侧现状给出动作。"""
    items = []

    # files 与 rule_shells 结构一致：name -> {path, format, ...}
    for group, label in (("files", "配置项"), ("rule_shells", "规则正文")):
        old_group = old_index.get(group) or {}
        new_group = new_index.get(group) or {}
        added, removed, common = dict_diff(old_group, new_group)

        for name in added:
            entry = new_group.get(name) or {}
            rel = entry.get("path") or ""
            pack = pack_of_path(rel)
            exists = os.path.exists(project_path(project_root, rel)) if rel else False
            if pack and pack not in active:
                add_item(items, "index." + group, "added", name,
                         "包 %s 未安装，装包后由 core-init 生成" % pack,
                         "info", pack=pack, new=rel)
            elif exists:
                add_item(items, "index." + group, "added", name,
                         "项目侧文件已存在，无需处理", "info", pack=pack, new=rel)
            else:
                add_item(items, "index." + group, "added", name,
                         "需生成项目侧骨架（core-init）", "action_required",
                         pack=pack, new=rel)

        for name in removed:
            entry = old_group.get(name) or {}
            rel = entry.get("path") or ""
            pack = pack_of_path(rel)
            exists = os.path.exists(project_path(project_root, rel)) if rel else False
            if exists:
                add_item(items, "index." + group, "removed", name,
                         "索引已移除但项目侧文件仍在，确认后可清理或归档",
                         "suggest", pack=pack, old=rel)
            else:
                add_item(items, "index." + group, "removed", name,
                         "索引已移除，项目侧无残留", "info", pack=pack, old=rel)

        for name in common:
            old_rel = (old_group.get(name) or {}).get("path") or ""
            new_rel = (new_group.get(name) or {}).get("path") or ""
            if old_rel == new_rel:
                continue
            pack = pack_of_path(new_rel)
            old_exists = os.path.exists(project_path(project_root, old_rel)) if old_rel else False
            new_exists = os.path.exists(project_path(project_root, new_rel)) if new_rel else False
            if old_exists and not new_exists:
                add_item(items, "index." + group, "path_changed", name,
                         "需迁移项目侧文件（旧路径存在、新路径缺失）", "action_required",
                         pack=pack, old=old_rel, new=new_rel)
            elif old_exists and new_exists:
                add_item(items, "index." + group, "path_changed", name,
                         "新旧路径都存在，确认后删除旧路径", "suggest",
                         pack=pack, old=old_rel, new=new_rel)
            else:
                add_item(items, "index." + group, "path_changed", name,
                         "项目侧无旧文件，按新路径生成即可", "info",
                         pack=pack, old=old_rel, new=new_rel)

    # artifacts.dirs：name -> 相对路径（字符串）
    old_dirs = (old_index.get("artifacts") or {}).get("dirs") or {}
    new_dirs = (new_index.get("artifacts") or {}).get("dirs") or {}
    added, removed, common = dict_diff(old_dirs, new_dirs)
    for name in added:
        rel = new_dirs.get(name) or ""
        pack = pack_of_path(rel)
        exists = os.path.isdir(project_path(project_root, rel)) if rel else False
        if pack and pack not in active:
            add_item(items, "index.artifacts", "added", name,
                     "包 %s 未安装，装包后创建" % pack, "info", pack=pack, new=rel)
        elif exists:
            add_item(items, "index.artifacts", "added", name,
                     "目录已存在，无需处理", "info", pack=pack, new=rel)
        else:
            add_item(items, "index.artifacts", "added", name,
                     "需创建产物目录（不入库）", "action_required", pack=pack, new=rel)
    for name in removed:
        rel = old_dirs.get(name) or ""
        pack = pack_of_path(rel)
        exists = os.path.isdir(project_path(project_root, rel)) if rel else False
        add_item(items, "index.artifacts", "removed", name,
                 "残留目录可清理（内容为运行时产物）" if exists else "索引已移除，无残留",
                 "suggest" if exists else "info", pack=pack, old=rel)
    for name in common:
        old_rel = old_dirs.get(name) or ""
        new_rel = new_dirs.get(name) or ""
        if old_rel == new_rel:
            continue
        pack = pack_of_path(new_rel)
        add_item(items, "index.artifacts", "path_changed", name,
                 "产物目录路径变更：旧目录可清理，新目录首次运行自动重建",
                 "suggest", pack=pack, old=old_rel, new=new_rel)

    # root_symlinks.entries：name -> {link, path, ...}
    old_links = (old_index.get("root_symlinks") or {}).get("entries") or {}
    new_links = (new_index.get("root_symlinks") or {}).get("entries") or {}
    added, removed, common = dict_diff(old_links, new_links)
    for name in added:
        entry = new_links.get(name) or {}
        add_item(items, "index.root_symlinks", "added", name,
                 "需生成项目侧源文件并建立根级软链接（core-init）",
                 "action_required", old="", new=entry.get("link", ""))
    for name in removed:
        entry = old_links.get(name) or {}
        add_item(items, "index.root_symlinks", "removed", name,
                 "索引已移除，确认后删除引擎内链接与项目侧源文件",
                 "suggest", old=entry.get("link", ""), new="")
    for name in common:
        old_entry = old_links.get(name) or {}
        new_entry = new_links.get(name) or {}
        if old_entry.get("link") == new_entry.get("link") and old_entry.get("path") == new_entry.get("path"):
            continue
        add_item(items, "index.root_symlinks", "link_changed", name,
                 "链接或源文件路径变更，需重建链接（core-init --force 或手工）",
                 "action_required", old=old_entry.get("link", ""), new=new_entry.get("link", ""))

    return items


def analyze_packs(old_packs, new_packs, active):
    """分析包注册表：包的新增/移除、以及每个包内组件的增减。"""
    items = []
    added, removed, common = dict_diff(old_packs, new_packs)

    for pack in added:
        meta = new_packs.get(pack) or {}
        add_item(items, "packs.pack", "added", pack,
                 "新增包，可用 pack_install.py install %s 安装" % pack,
                 "info", pack=pack, new=meta.get("description", ""))
    for pack in removed:
        add_item(items, "packs.pack", "removed", pack,
                 "包已从注册表移除%s" % ("（本项目已安装，链接将失效，需卸载）" if pack in active else ""),
                 "action_required" if pack in active else "info", pack=pack)

    for pack in common:
        old_comps = (old_packs.get(pack) or {}).get("comps") or {}
        new_comps = (new_packs.get(pack) or {}).get("comps") or {}
        for comp_type in ("rules", "skills", "agents"):
            old_names = set(old_comps.get(comp_type) or [])
            new_names = set(new_comps.get(comp_type) or [])
            for name in sorted(new_names - old_names):
                add_item(items, "packs.comps", "added", "%s/%s" % (comp_type, name),
                         "新增组件%s" % ("（本项目已装该包，重开会话后可用）" if pack in active else "（装包后可用）"),
                         "info", pack=pack, new=name)
            for name in sorted(old_names - new_names):
                add_item(items, "packs.comps", "removed", "%s/%s" % (comp_type, name),
                         "组件已移除，相关技能/规则将不可用",
                         "suggest" if pack in active else "info", pack=pack, old=name)

    return items


def summarize(items):
    """按严重程度统计。"""
    counts = {"action_required": 0, "suggest": 0, "info": 0}
    for item in items:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return counts


def print_report(result):
    """人类可读输出：按严重程度分组，逐条给出动作建议。"""
    print("=" * 68)
    print("引擎更新影响分析")
    print("=" * 68)
    print("  对比范围：%s → %s" % (result["from"][:7], result["to"][:7]))
    print("  项目根  ：%s" % result["project_root"])
    print("  生效包  ：%s" % (", ".join(sorted(result["active_packs"])) or "（仅默认包）"))
    print()

    items = result["items"]
    if not items:
        print("结论：本次更新未改变项目侧契约，无需同步。")
        print("=" * 68)
        return

    groups = (
        ("action_required", "必须处理（项目侧契约已变，不处理会缺失或失效）"),
        ("suggest", "建议处理（残留或可选优化，需确认后执行）"),
        ("info", "仅告知（无需动作）"),
    )
    for severity, title in groups:
        subset = [i for i in items if i["severity"] == severity]
        if not subset:
            continue
        print("-" * 68)
        print("[%s] %s（%d 项）" % (severity, title, len(subset)))
        print("-" * 68)
        for item in subset:
            scope = ("包 %s · " % item["pack"]) if item["pack"] else ""
            print("  · %s%s  <%s / %s>" % (scope, item["name"], item["kind"], item["change"]))
            if item["old"] and item["new"]:
                print("      旧：%s" % item["old"])
                print("      新：%s" % item["new"])
            elif item["old"]:
                print("      旧：%s" % item["old"])
            elif item["new"]:
                print("      新：%s" % item["new"])
            print("      动作：%s" % item["action"])
        print()

    counts = result["summary"]
    print("=" * 68)
    print("汇总：必须处理 %d 项，建议处理 %d 项，仅告知 %d 项"
          % (counts["action_required"], counts["suggest"], counts["info"]))
    if counts["action_required"]:
        print()
        print("建议后续步骤：")
        print("  1. python .codebuddy/skills/core/core-init/scripts/init_project_config.py --setup")
        print("  2. python .codebuddy/scripts/pack_install.py verify --repair")
        print("  3. python .codebuddy/skills/core/core-init/scripts/init_project_config.py --status")
    print("=" * 68)


def main():
    init_stdout()
    parser = argparse.ArgumentParser(
        description="对比引擎两版本的项目侧契约变化，输出需同步到项目侧的清单"
    )
    parser.add_argument("--from", dest="from_ref", required=True,
                        help="起始版本（如 HEAD~1 或提交哈希）")
    parser.add_argument("--to", dest="to_ref", default="HEAD",
                        help="目标版本（默认 HEAD）")
    parser.add_argument("--dir", default=None,
                        help="引擎仓库目录（默认：脚本所在仓库，即 .codebuddy）")
    parser.add_argument("--project-root", default=None,
                        help="项目根目录（默认为引擎目录的父目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    try:
        engine_dir = os.path.abspath(args.dir or find_engine_dir(os.path.dirname(os.path.abspath(__file__))))
    except AnalyzeError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3
    project_root = args.project_root or os.path.dirname(engine_dir)

    rc = run_git(["rev-parse", "--show-toplevel"], engine_dir)[0]
    if rc != 0:
        sys.stderr.write("[错误] 目标目录不是 git 仓库：%s\n" % engine_dir)
        return 3

    try:
        from_hash = resolve_ref(engine_dir, args.from_ref)
        to_hash = resolve_ref(engine_dir, args.to_ref)
        old_index = load_json_at_ref(engine_dir, from_hash, INDEX_REL)
        new_index = load_json_at_ref(engine_dir, to_hash, INDEX_REL)
        old_packs_doc = load_json_at_ref(engine_dir, from_hash, PACKS_REL)
        new_packs_doc = load_json_at_ref(engine_dir, to_hash, PACKS_REL)
    except AnalyzeError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    if not new_index:
        sys.stderr.write("[错误] 目标版本缺少 %s，无法分析：%s\n" % (INDEX_REL, args.to_ref))
        return 3

    old_packs = old_packs_doc.get("packs") or {}
    new_packs = new_packs_doc.get("packs") or {}
    active = active_packs(project_root, new_packs)

    items = []
    items.extend(analyze_index(old_index, new_index, project_root, active))
    items.extend(analyze_packs(old_packs, new_packs, active))

    result = {
        "from": from_hash,
        "to": to_hash,
        "engine_dir": engine_dir,
        "project_root": project_root,
        "active_packs": sorted(active),
        "items": items,
        "summary": summarize(items),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
