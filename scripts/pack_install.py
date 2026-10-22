#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎包安装器：按 lib/packs.json 声明的可选包，在项目侧物化组件链接并登记安装状态。

引擎扫描根的形态（本脚本不创建默认包，只桥接可选包）：
  .codebuddy/rules/<pack>           默认包真实目录 / 可选包链接 → 项目侧
  .codebuddy/skills/<pack>          同上
  .codebuddy/agents/<pack>          同上（仅可选包）
  .codebuddy.project/rules/<pack>/<名>   → lib/<pack>/rules/<名>
  .codebuddy.project/skills/<pack>/<名>  → lib/<pack>/skills/<名>
  .codebuddy.project/agents/<pack>/<名>.md  同上（与 rules/skills 一致的目录链接）

用法：
  python .codebuddy/scripts/pack_install.py list
  python .codebuddy/scripts/pack_install.py install csharp unity-pipeline
  python .codebuddy/scripts/pack_install.py remove csharp
  python .codebuddy/scripts/pack_install.py status
  python .codebuddy/scripts/pack_install.py verify --repair

退出码：
  0 成功 / 一致
  1 存在漂移（status、verify 未修复时）
  2 参数错误、pack 不存在、依赖冲突
  3 物化失败（链接创建失败等）
"""

import argparse
import json
import os
import subprocess
import sys

TYPES = ("rules", "skills", "agents")
CONFIG_REL = os.path.join(".codebuddy.project", "configs", "packs.json")


class PackError(RuntimeError):
    """可预期的业务错误，由 main 统一转为退出码。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def find_engine_dir(start):
    """从起始路径向上查找名为 .codebuddy 的目录，返回其绝对路径。"""
    current = os.path.abspath(start)
    while True:
        if os.path.basename(current) == ".codebuddy":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise PackError("未能定位 .codebuddy 目录（脚本应位于 <项目>/.codebuddy/scripts/ 下）")
        current = parent


def engine_paths(engine_dir):
    """返回引擎侧与项目侧的关键路径。"""
    project_root = os.path.dirname(engine_dir)
    return {
        "project_root": project_root,
        "engine": engine_dir,
        "packs": os.path.join(engine_dir, "lib", "packs.json"),
        "lib": os.path.join(engine_dir, "lib"),
        "config": os.path.join(project_root, CONFIG_REL),
    }


def load_packs(paths):
    """读取 lib/packs.json 的 packs 字典；缺失或损坏即报错，不回退默认值。"""
    path = paths["packs"]
    if not os.path.isfile(path):
        raise PackError("未找到包注册表：%s" % path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise PackError("包注册表读取失败：%s（%s）" % (path, error))
    packs = data.get("packs")
    if not isinstance(packs, dict) or not packs:
        raise PackError("包注册表缺少 packs 对象：%s" % path)
    for name, meta in packs.items():
        if not isinstance(meta, dict):
            raise PackError("包定义必须是对象：%s" % name)
        for key in ("location", "requires", "comps"):
            if key not in meta:
                raise PackError("包定义缺少 %s 字段：%s" % (key, name))
        if meta["location"] not in ("engine", "lib", "project"):
            raise PackError("包 %s 的 location 非法：%s" % (name, meta["location"]))
    return packs


def load_state(paths):
    """读取项目侧安装状态；缺失时返回空状态（不写盘）。"""
    path = paths["config"]
    if not os.path.isfile(path):
        return {"version": 1, "installed": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise PackError("安装状态读取失败：%s（%s）" % (path, error))
    installed = data.get("installed")
    if not isinstance(installed, list):
        raise PackError("安装状态缺少 installed 数组：%s" % path)
    return {"version": data.get("version", 1), "installed": list(installed)}


def save_state(paths, installed):
    """写入项目侧安装状态（排序后落盘，保证 diff 稳定）。"""
    path = paths["config"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": 1, "installed": sorted(set(installed))}
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return payload


def default_packs(packs):
    """返回默认包名集合（随引擎分发，不需物化）。"""
    return {name for name, meta in packs.items() if meta.get("default")}


def resolve_closure(installed, packs, add):
    """解析依赖闭包，返回 (新集合, 本次新增的包名列表)。pack 不存在立即失败。"""
    result = set(installed)
    queue = list(add)
    while queue:
        name = queue.pop()
        if name not in packs:
            raise PackError("包不存在：%s" % name)
        if name in result:
            continue
        result.add(name)
        queue.extend(packs[name].get("requires") or [])
    return result, sorted(result - set(installed))


def dependents(packs, target):
    """返回依赖 target 的包名列表（反向依赖检查用）。"""
    return sorted(name for name, meta in packs.items() if target in (meta.get("requires") or []))



def pack_dir_link(paths, pack, comp_type):
    """项目侧 pack 目录落点：.codebuddy.project/<类型>/<pack>。

    该目录整体是链接（→ lib/<pack>/<类型>），不再逐个组件建链接。
    """
    return os.path.join(paths["project_root"], ".codebuddy.project", comp_type, pack)


def bridge_link(paths, pack, comp_type):
    """引擎扫描根的 pack 桥接链接落点。"""
    return os.path.join(paths["engine"], comp_type, pack)


def is_link(path):
    """判断路径是否为符号链接（只承认符号链接，不把 junction 视为链接）。"""
    return os.path.islink(path)


def make_dir_link(link, target):
    """创建目录符号链接，target 为相对链接所在目录的相对路径。"""
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/D", os.path.basename(link), target],
            cwd=os.path.dirname(link),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            raise PackError("创建目录链接失败：%s（%s）"
                            % (link, (result.stderr or result.stdout or "").strip()))
    else:
        os.symlink(target, link, target_is_directory=True)


def ensure_pack_dir(paths, packs, pack, comp_type, repair=False, force=False):
    """物化项目侧 pack 目录链接（.codebuddy.project/<类型>/<pack> → lib/<pack>/<类型>）。

    整目录链接意味着包内组件增删无需任何项目侧操作；返回 (状态, 说明)，
    状态：ok / created / fixed / drift / failed。
    """
    meta = packs[pack]
    if meta["location"] != "lib":
        return "ok", "无需物化（location=%s）" % meta["location"]
    source = os.path.join(paths["lib"], pack, comp_type)
    link = pack_dir_link(paths, pack, comp_type)
    if not os.path.isdir(source):
        # 该包没有此类组件（如 grilling 无 rules），跳过
        return "ok", "包内无 %s 目录，跳过" % comp_type

    if is_link(link):
        current = os.path.realpath(link)
        if os.path.normcase(current) == os.path.normcase(os.path.realpath(source)):
            return "ok", link
        if not (repair or force):
            return "drift", "链接指向错误：%s → %s" % (link, current)
        os.unlink(link)
    elif os.path.lexists(link):
        # 旧版的逐组件目录：force/repair 时才允许迁移（先清空内部链接再替换）
        if not (repair or force):
            return "drift", "已存在真实目录（旧版逐组件布局？）：%s" % link
        import shutil
        shutil.rmtree(link)
    target = os.path.relpath(source, os.path.dirname(link))
    make_dir_link(link, target)
    return "created", "%s → %s" % (link, target)

def ensure_bridge(paths, pack, comp_type, repair=False, force=False):
    """物化引擎扫描根的 pack 桥接链接；返回 (状态, 说明)。"""
    link = bridge_link(paths, pack, comp_type)
    target_abs = os.path.join(paths["project_root"], ".codebuddy.project", comp_type, pack)
    if is_link(link):
        current = os.path.realpath(link)
        if os.path.normcase(current) == os.path.normcase(os.path.realpath(target_abs)):
            return "ok", link
        if not (repair or force):
            return "drift", "桥接指向错误：%s → %s" % (link, current)
        os.unlink(link)
    elif os.path.lexists(link):
        return "drift", "扫描根已存在同名真实目录（默认包？）：%s" % link
    target = os.path.relpath(target_abs, os.path.dirname(link))
    make_dir_link(link, target)
    return "created", "%s → %s" % (link, target)


def materialize(paths, packs, pack, repair=False, force=False):
    """物化一个包的全部桥接与组件，返回明细列表 [(包, 类型, 组件, 状态, 说明)]。

    engine 包随引擎分发、project 包内容直接位于项目侧，二者都无需物化。
    """
    meta = packs[pack]
    if meta["location"] == "engine":
        return []
    if meta["location"] == "project":
        # 项目专有包：内容直接位于项目侧，只需建立进入扫描根的桥接
        rows = []
        for comp_type in TYPES:
            status, detail = ensure_project_bridge(paths, comp_type, repair=repair, force=force)
            rows.append((pack, comp_type, "<桥接>", status, detail))
        return rows
    rows = []
    for comp_type in TYPES:
        names = meta["comps"].get(comp_type) or []
        if not names:
            continue
        status, detail = ensure_bridge(paths, pack, comp_type, repair=repair, force=force)
        rows.append((pack, comp_type, "<桥接>", status, detail))
        status, detail = ensure_pack_dir(paths, packs, pack, comp_type,
                                         repair=repair, force=force)
        rows.append((pack, comp_type, "<pack目录>", status, detail))
    return rows


def ensure_project_bridge(paths, comp_type, repair=False, force=False):
    """物化项目专有包的桥接链接：扫描根 project → .codebuddy.project/<类型>/project。

    项目专有包与其他包同构（位于 .codebuddy.project/<类型>/ 下），区别仅在于它是
    真实目录而非指向 lib 的链接；因此只需一层链接即可进入扫描根。返回 (状态, 说明)。
    """
    link = os.path.join(paths["engine"], comp_type, "project")
    target_abs = os.path.join(paths["project_root"], ".codebuddy.project", comp_type, "project")
    # 目标目录不存在时先建空目录，保证链接有效（项目可后续往里放内容）
    if not os.path.isdir(target_abs):
        os.makedirs(target_abs, exist_ok=True)
    if is_link(link):
        current = os.path.realpath(link)
        if os.path.normcase(current) == os.path.normcase(os.path.realpath(target_abs)):
            return "ok", link
        if not (repair or force):
            return "drift", "桥接指向错误：%s → %s" % (link, current)
        os.unlink(link)
    elif os.path.lexists(link):
        return "drift", "扫描根已存在同名真实目录：%s" % link
    target = os.path.relpath(target_abs, os.path.dirname(link))
    make_dir_link(link, target)
    return "created", "%s → %s" % (link, target)


def drop_pack(paths, packs, pack):
    """移除一个包的桥接与组件链接（只删链接，不触碰 lib 与项目侧配置）。"""
    meta = packs[pack]
    if meta["location"] == "engine":
        return []
    if meta["location"] == "project":
        # 项目专有包的内容是项目真实文件，只删扫描根桥接，不删内容
        removed = []
        for comp_type in TYPES:
            bridge = os.path.join(paths["engine"], comp_type, "project")
            if is_link(bridge):
                os.unlink(bridge)
                removed.append(bridge)
        return removed
    removed = []
    for comp_type in TYPES:
        if not (meta["comps"].get(comp_type) or []):
            continue
        pack_link = pack_dir_link(paths, pack, comp_type)
        if is_link(pack_link):
            os.unlink(pack_link)
            removed.append(pack_link)
        bridge = bridge_link(paths, pack, comp_type)
        if is_link(bridge):
            os.unlink(bridge)
            removed.append(bridge)
    return removed


def scan_drift(paths, packs, state):
    """对照安装状态与实际链接，返回漂移清单 [(类型, 位置, 说明)]。"""
    issues = []
    installed = set(state["installed"])
    for name in sorted(installed):
        if name not in packs:
            issues.append(("state", name, "安装状态中存在未知包"))
            continue
        if packs[name].get("default"):
            issues.append(("state", name, "默认包不应出现在安装状态中"))
            continue
        if packs[name]["location"] in ("engine", "project"):
            issues.append(("state", name, "engine/project 包不应出现在安装状态中"))
            continue
        for comp_type in TYPES:
            names = packs[name]["comps"].get(comp_type) or []
            if not names:
                continue
            bridge = bridge_link(paths, name, comp_type)
            if not is_link(bridge):
                issues.append(("bridge", bridge, "缺少或非链接"))
            source_dir = os.path.join(paths["lib"], name, comp_type)
            if not os.path.isdir(source_dir):
                issues.append(("source", source_dir, "组件源目录缺失"))
                continue
            pack_link = pack_dir_link(paths, name, comp_type)
            if not is_link(pack_link):
                issues.append(("packdir", pack_link, "缺少或非链接（应为 pack 目录链接）"))
            elif os.path.normcase(os.path.realpath(pack_link)) != os.path.normcase(os.path.realpath(source_dir)):
                issues.append(("packdir", pack_link, "指向错误"))
            else:
                # 链接正确时，逐个核对声明的组件在链接内可见
                for comp in names:
                    suffix = ".md" if comp_type == "agents" else ""
                    if not os.path.exists(os.path.join(pack_link, comp + suffix)):
                        issues.append(("component", os.path.join(pack_link, comp + suffix),
                                       "包内组件缺失"))
    # 默认的项目专有包：桥接必须存在（内容缺失不算漂移，项目可能尚未放内容）
    for name, meta in sorted(packs.items()):
        if meta.get("default") and meta.get("location") == "project":
            for comp_type in TYPES:
                bridge = os.path.join(paths["engine"], comp_type, "project")
                target = os.path.join(paths["project_root"], ".codebuddy.project", comp_type, "project")
                if not is_link(bridge):
                    issues.append(("bridge", bridge, "缺少项目专有包桥接"))
                elif os.path.normcase(os.path.realpath(bridge)) != os.path.normcase(os.path.realpath(target)):
                    issues.append(("bridge", bridge, "指向错误"))
    known = set()
    for name in installed:
        if name in packs and packs[name]["location"] == "lib":
            known.add(name)
    # 项目专有包在 .codebuddy.project/<类型>/ 下也是真实目录，不应被判为多余
    for name, meta in packs.items():
        if meta.get("location") == "project":
            known.add(name)
    for comp_type in TYPES:
        root = os.path.join(paths["project_root"], ".codebuddy.project", comp_type)
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            if os.path.isdir(full) and entry not in known:
                issues.append(("extra", full, "未在安装状态中的 pack 目录"))
    return issues


def cmd_list(paths, packs, state):
    """列出全部包：默认标记、依赖、已装标记、组件计数。"""
    installed = set(state["installed"])
    groups = {}
    for name, meta in packs.items():
        groups.setdefault(meta.get("category", "未分类"), []).append(name)
    print("包注册表：%s" % paths["packs"])
    print("已装：%s" % (", ".join(sorted(installed)) or "（无）"))
    for category in sorted(groups):
        print("")
        print("[%s]" % category)
        for name in sorted(groups[category]):
            meta = packs[name]
            marks = []
            if meta.get("default"):
                marks.append("默认")
            if name in installed:
                marks.append("已装")
            comps = meta["comps"]
            count = sum(len(comps.get(t) or []) for t in TYPES)
            req = ", ".join(meta.get("requires") or []) or "-"
            flag = "（%s）" % "，".join(marks) if marks else ""
            print("  %-18s 组件 %-2d 依赖 %-12s %s%s"
                  % (name, count, req, meta.get("description", ""), flag))
    return 0


def cmd_install(paths, packs, state, names, force):
    """安装指定包及其依赖闭包。默认包无需安装，跳过。"""
    for name in names:
        if name not in packs:
            raise PackError("包不存在：%s" % name)
    installed = set(state["installed"])
    new_set, added = resolve_closure(installed, packs, names)
    added = [n for n in added if not packs[n].get("default")]
    if not added:
        print("无需安装：指定的包均属默认集或已安装")
        return 0
    rows = []
    for name in added:
        rows.extend(materialize(paths, packs, name, repair=True, force=force))
    save_state(paths, new_set - default_packs(packs))
    for pack, comp_type, comp, status, detail in rows:
        if status != "ok":
            print("[%s] %s/%s %s" % (status, comp_type, comp, detail))
    failed = [r for r in rows if r[3] == "failed"]
    print("")
    print("已安装：%s" % ", ".join(added))
    if failed:
        print("存在失败项 %d 个，请检查上方 [failed] 行" % len(failed))
        return 3
    return 0


def cmd_remove(paths, packs, state, names, force):
    """卸载指定包；默认包拒绝，被依赖的包拒绝（force 时连带移除）。"""
    installed = set(state["installed"])
    for name in names:
        if name not in packs:
            raise PackError("包不存在：%s" % name)
        if packs[name].get("default"):
            raise PackError("默认包不可卸载：%s（由引擎自带）" % name)
        if name not in installed:
            raise PackError("未安装：%s" % name)
    closing = set(names)
    blocked = []
    for name in names:
        for dep in dependents(packs, name):
            if dep in installed and dep not in closing:
                blocked.append((name, dep))
    if blocked and not force:
        lines = ["被依赖，拒绝卸载："]
        for name, dep in blocked:
            lines.append("  - %s 被 %s 依赖（使用 --force 连带移除）" % (name, dep))
        raise PackError("\n".join(lines))
    if blocked:
        queue = [dep for _, dep in blocked]
        while queue:
            dep = queue.pop()
            if dep in closing or (dep in packs and packs[dep].get("default")):
                continue
            closing.add(dep)
            queue.extend(dependents(packs, dep))
    removed = []
    for name in sorted(closing):
        if packs[name].get("default"):
            continue
        removed.extend(drop_pack(paths, packs, name))
    save_state(paths, installed - closing)
    for path in removed:
        print("已移除：%s" % path)
    final = sorted(closing - default_packs(packs))
    print("")
    print("已卸载：%s" % (", ".join(final) or "（无）"))
    return 0


def cmd_status(paths, packs, state):
    """报告安装状态与实际物化的差异。"""
    issues = scan_drift(paths, packs, state)
    if not issues:
        print("一致：安装状态与实际链接完全匹配（已装 %d 个可选包）" % len(state["installed"]))
        return 0
    print("发现 %d 处漂移：" % len(issues))
    for kind, where, detail in issues:
        print("  [%s] %s：%s" % (kind, where, detail))
    print("")
    print("运行 `verify --repair` 修复")
    return 1


def cmd_verify(paths, packs, state, repair):
    """校验并（可选）修复漂移。"""
    issues = scan_drift(paths, packs, state)
    if not issues:
        print("一致：无需修复")
        return 0
    if not repair:
        print("发现 %d 处漂移（未修复）：" % len(issues))
        for kind, where, detail in issues:
            print("  [%s] %s：%s" % (kind, where, detail))
        return 1
    fixed, failed = 0, 0
    # 默认的项目专有包不记入安装状态，但其桥接需始终存在
    for name, meta in sorted(packs.items()):
        if meta.get("default") and meta.get("location") == "project":
            for pack, comp_type, comp, status, detail in materialize(
                    paths, packs, name, repair=True, force=True):
                if status in ("created", "fixed"):
                    fixed += 1
                    print("[修复] %s/%s %s" % (comp_type, comp, detail))
                elif status == "failed":
                    failed += 1
                    print("[失败] %s/%s %s" % (comp_type, comp, detail))
    for name in sorted(state["installed"]):
        if name not in packs or packs[name].get("default"):
            continue
        for pack, comp_type, comp, status, detail in materialize(paths, packs, name,
                                                                repair=True, force=True):
            if status in ("created", "fixed"):
                fixed += 1
                print("[修复] %s/%s %s" % (comp_type, comp, detail))
            elif status == "failed":
                failed += 1
                print("[失败] %s/%s %s" % (comp_type, comp, detail))
    print("")
    print("修复 %d 项，失败 %d 项" % (fixed, failed))
    return 0 if failed == 0 else 3


def build_parser():
    """构造命令行解析器。"""
    parser = argparse.ArgumentParser(
        prog="pack_install.py",
        description="按 lib/packs.json 安装、卸载、校验引擎可选包",
    )
    parser.add_argument("--project-root", help="项目根目录（默认从脚本位置上溯推断）")
    parser.add_argument("--dry-run", action="store_true", help="只报告不落盘")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出全部包与安装状态")
    p_install = sub.add_parser("install", help="安装包（自动带出依赖）")
    p_install.add_argument("packs", nargs="+", help="包名，多个以空格分隔")
    p_install.add_argument("--force", action="store_true", help="重建已存在的链接")
    p_remove = sub.add_parser("remove", help="卸载包")
    p_remove.add_argument("packs", nargs="+", help="包名，多个以空格分隔")
    p_remove.add_argument("--force", action="store_true", help="连带移除被依赖的包")
    sub.add_parser("status", help="报告漂移（不改动）")
    p_verify = sub.add_parser("verify", help="校验并修复漂移")
    p_verify.add_argument("--repair", action="store_true", help="实际修复")
    return parser


def main(argv=None):
    """入口：解析参数并分派子命令。"""
    init_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.project_root:
            engine_dir = os.path.join(os.path.abspath(args.project_root), ".codebuddy")
        else:
            engine_dir = find_engine_dir(os.path.dirname(os.path.abspath(__file__)))
        paths = engine_paths(engine_dir)
        packs = load_packs(paths)
        state = load_state(paths)
    except PackError as error:
        print("[错误] %s" % error, file=sys.stderr)
        return 2

    try:
        if args.command == "list":
            return cmd_list(paths, packs, state)
        if args.command == "install":
            if args.dry_run:
                _, added = resolve_closure(set(state["installed"]), packs, args.packs)
                added = [n for n in added if not packs[n].get("default")]
                print("将安装：%s" % (", ".join(added) or "（无）"))
                return 0
            return cmd_install(paths, packs, state, args.packs, args.force)
        if args.command == "remove":
            if args.dry_run:
                print("将卸载：%s" % ", ".join(args.packs))
                return 0
            return cmd_remove(paths, packs, state, args.packs, args.force)
        if args.command == "status":
            return cmd_status(paths, packs, state)
        if args.command == "verify":
            return cmd_verify(paths, packs, state, args.repair)
    except PackError as error:
        print("[错误] %s" % error, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
