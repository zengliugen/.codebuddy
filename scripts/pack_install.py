#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""包安装器：按包注册表在项目侧物化组件链接并登记安装状态。

支持两套包注册表，结构完全同构：

  --source engine（默认）
    注册表  .codebuddy/lib/packs.json
    状态    .codebuddy.project/configs/packs.json
  --source project
    注册表  .codebuddy.project/project-lib/packs.json
    状态    .codebuddy.project/configs/project-packs.json

扫描根的形态由 `location` 决定（与 `default` 无关；本脚本不物化默认包，只桥接可选包）：

  .codebuddy/<类型>/<pack>              location=engine 真实目录 / lib 与 project-lib 链接
  .codebuddy.project/<类型>/<pack>      → <内容根>/<pack>/<类型>（lib 与 project-lib 一致）
  <内容根>                              location=lib 为 .codebuddy/lib
                                        location=project-lib 为 .codebuddy.project/project-lib

依赖允许**跨表单向展开**：项目包的 `requires` 可指向引擎包，反向禁止（引擎注册表
不得出现项目包名，见规则 `core-engine` 第 1、2 条）。装项目包时其引擎依赖会被
一并装进引擎侧安装状态。

用法：
  python .codebuddy/scripts/pack_install.py list          # 含「可选搭配」提示
  python .codebuddy/scripts/pack_install.py install csharp unity-pipeline
  python .codebuddy/scripts/pack_install.py remove csharp
  python .codebuddy/scripts/pack_install.py status
  python .codebuddy/scripts/pack_install.py verify --repair

  python .codebuddy/scripts/pack_install.py --source project list
  python .codebuddy/scripts/pack_install.py --source project install ok-script
  python .codebuddy/scripts/pack_install.py --source project status

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
LOCATIONS = ("engine", "lib", "project-lib")

# 两套来源的路径约定；相对路径均相对项目根（.codebuddy 的父目录）。
SOURCES = {
    "engine": {
        "packs_rel": os.path.join(".codebuddy", "lib", "packs.json"),
        "state_rel": os.path.join(".codebuddy.project", "configs", "packs.json"),
        "label": "引擎可选包",
    },
    "project": {
        "packs_rel": os.path.join(".codebuddy.project", "project-lib", "packs.json"),
        "state_rel": os.path.join(".codebuddy.project", "configs", "project-packs.json"),
        "label": "项目侧包",
    },
}


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
    roots = {}
    for source, spec in SOURCES.items():
        roots[source] = {
            "packs": os.path.normpath(os.path.join(project_root, spec["packs_rel"])),
            "state": os.path.normpath(os.path.join(project_root, spec["state_rel"])),
        }
    return {
        "project_root": project_root,
        "engine": engine_dir,
        "lib": os.path.join(engine_dir, "lib"),
        "project_lib": os.path.join(project_root, ".codebuddy.project", "project-lib"),
        "sources": roots,
    }


def content_base(paths, location):
    """按 location 返回该包的内容根（下含 <pack>/<类型>）。"""
    if location == "lib":
        return paths["lib"]
    if location == "project-lib":
        return paths["project_lib"]
    raise PackError("location=%s 的包无内容根（engine 包为引擎内真实目录）" % location)


def load_packs(paths, source):
    """读取指定来源的包注册表；缺失或损坏即报错，不回退默认值。"""
    path = paths["sources"][source]["packs"]
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
        if meta["location"] not in LOCATIONS:
            raise PackError("包 %s 的 location 非法：%s（合法值：%s）"
                            % (name, meta["location"], "、".join(LOCATIONS)))
    return packs


def load_all_packs(paths):
    """读取两套注册表，返回 ({来源: packs}, [缺失提示])。

    项目侧注册表缺失属正常（尚未建立包仓库），此时只返回引擎表；
    引擎注册表缺失才是硬错误。
    """
    regs = {"engine": load_packs(paths, "engine")}
    project_registry = paths["sources"]["project"]["packs"]
    if os.path.isfile(project_registry):
        regs["project"] = load_packs(paths, "project")
    else:
        regs["project"] = {}
    return regs


def merged_registry(regs):
    """合并两表为 {包名: {"source": 来源, "meta": 定义}}；包名跨表冲突立即报错。

    跨表重名无法判断「装的是哪一个」，且会让单向依赖的方向语义失去意义，
    故视为硬错误而不做优先级取舍。
    """
    merged = {}
    for source, packs in regs.items():
        for name, meta in packs.items():
            if name in merged:
                raise PackError(
                    "包名跨表重复：%s（同时出现在 %s 与 %s 注册表）。"
                    "两表包名必须全局唯一" % (name, merged[name]["source"], source))
            merged[name] = {"source": source, "meta": meta}
    return merged


def load_state(paths, source):
    """读取指定来源的安装状态；缺失时返回空状态（不写盘）。"""
    path = paths["sources"][source]["state"]
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


def save_state(paths, source, installed):
    """写入指定来源的安装状态（排序后落盘，保证 diff 稳定）。"""
    path = paths["sources"][source]["state"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": 1, "installed": sorted(set(installed))}
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return payload


def default_packs(packs):
    """返回默认包名集合（随来源分发，不需物化）。"""
    return {name for name, meta in packs.items() if meta.get("default")}


def active_packs(regs, states):
    """返回已生效包名集合：两表默认包 + 两表已装包。"""
    active = set()
    for source, packs in regs.items():
        active |= default_packs(packs)
        active |= set(states[source]["installed"])
    return active


def resolve_closure(merged, active, add):
    """解析跨表依赖闭包。

    从 `add` 出发沿 `requires` 展开，可跨到另一张表（单向：项目包 → 引擎包，
    反向由注册表校验拦截）。`active` 内的包视为已生效，不再重复装。

    参数：
        merged：`merged_registry` 的返回值。
        active：已生效包名集合。
        add：本次要安装的包名列表。

    返回：
        (目标生效集合, [(来源, 包名), ...] 本次需物化的包)

    异常：
        PackError：包不存在。
    """
    result = set(active)
    queue = list(add)
    to_install = []
    while queue:
        name = queue.pop()
        if name not in merged:
            raise PackError("包不存在：%s" % name)
        if name in result:
            continue
        result.add(name)
        entry = merged[name]
        if not entry["meta"].get("default"):
            to_install.append((entry["source"], name))
        queue.extend(entry["meta"].get("requires") or [])
    # 按来源与包名排序，保证同一份输入每次输出完全一致
    to_install.sort()
    return result, to_install


def dependents(regs, target):
    """返回依赖 target 的 (来源, 包名) 列表（反向依赖检查用，跨两表）。"""
    found = []
    for source, packs in regs.items():
        for name, meta in packs.items():
            if target in (meta.get("requires") or []):
                found.append((source, name))
    return sorted(found)


def pack_dir_link(paths, pack, comp_type):
    """项目侧 pack 目录落点：.codebuddy.project/<类型>/<pack>。

    该目录整体是链接（→ <内容根>/<pack>/<类型>），不再逐个组件建链接。
    """
    return os.path.join(paths["project_root"], ".codebuddy.project", comp_type, pack)


def bridge_link(paths, pack, comp_type):
    """引擎扫描根的 pack 桥接链接落点。"""
    return os.path.join(paths["engine"], comp_type, pack)


def is_link(path):
    """判断路径是否为符号链接（只承认符号链接，不把 junction 视为链接）。"""
    return os.path.islink(path)


def safe_realpath(path):
    """返回真实路径；无法解析时返回 None 而不抛异常。

    Windows 上 `os.path.realpath()` 对「目录链接指向普通文件」会抛
    NotADirectoryError（WinError 267）。该状态正是克隆后链接链断裂的中间态：
    桥接链接仍指向 pack 目录，而 pack 目录被 git 落成了普通文本文件。
    若不吞掉异常，`verify --repair` 会在判定阶段就崩溃，无法进入修复。
    """
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None


def same_real_path(left, right):
    """两个路径是否指向同一实体；任一无法解析时返回 False。"""
    left_real = safe_realpath(left)
    right_real = safe_realpath(right)
    if left_real is None or right_real is None:
        return False
    return os.path.normcase(left_real) == os.path.normcase(right_real)


def remove_link_placeholder(path):
    """移除「本该是链接、实际却是普通文件/目录」的占位物。

    触发场景：Windows 默认 `core.symlinks=false`，克隆后 git 把符号链接落成
    内容为链接目标路径的普通文本文件。此时 `os.path.islink` 为假、
    `os.path.lexists` 为真，若直接用 `shutil.rmtree` 清理，会因「不是目录」
    抛 NotADirectoryError，导致 setup --force / verify --repair 无法修复。

    本函数按实际类型分派：目录用 rmtree、其余用 os.remove，返回是否已移除。
    """
    if os.path.islink(path):
        os.unlink(path)
        return True
    if os.path.isdir(path):
        import shutil
        shutil.rmtree(path)
        return True
    if os.path.lexists(path):
        os.remove(path)
        return True
    return False


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
    """物化项目侧 pack 目录链接（.codebuddy.project/<类型>/<pack> → <内容根>/<pack>/<类型>）。

    整目录链接意味着包内组件增删无需任何项目侧操作；返回 (状态, 说明)，
    状态：ok / created / fixed / drift / failed。
    """
    meta = packs[pack]
    location = meta["location"]
    if location == "engine":
        return "ok", "无需物化（location=engine，内容在引擎真实目录）"
    source_dir = os.path.join(content_base(paths, location), pack, comp_type)
    link = pack_dir_link(paths, pack, comp_type)
    if not os.path.isdir(source_dir):
        # 该包没有此类组件（如纯技能包无 rules），跳过
        return "ok", "包内无 %s 目录，跳过" % comp_type

    if is_link(link):
        if same_real_path(link, source_dir):
            return "ok", link
        current = safe_realpath(link) or "（无法解析）"
        if not (repair or force):
            return "drift", "链接指向错误：%s → %s" % (link, current)
        os.unlink(link)
    elif os.path.lexists(link):
        # 已存在非链接占位物，两种来源均需 force/repair 才允许替换：
        #   1) 旧版逐组件真实目录；
        #   2) core.symlinks=false 克隆后落成的普通文本文件（内容为链接目标）。
        if not (repair or force):
            return "drift", "已存在占位物（旧版目录或 symlinks=false 的链接落盘）：%s" % link
        remove_link_placeholder(link)
    target = os.path.relpath(source_dir, os.path.dirname(link))
    make_dir_link(link, target)
    return "created", "%s → %s" % (link, target)


def ensure_bridge(paths, pack, comp_type, repair=False, force=False):
    """物化引擎扫描根的 pack 桥接链接；返回 (状态, 说明)。"""
    link = bridge_link(paths, pack, comp_type)
    target_abs = os.path.join(paths["project_root"], ".codebuddy.project", comp_type, pack)
    if is_link(link):
        if same_real_path(link, target_abs):
            return "ok", link
        current = safe_realpath(link) or "（无法解析）"
        if not (repair or force):
            return "drift", "桥接指向错误：%s → %s" % (link, current)
        os.unlink(link)
    elif os.path.lexists(link):
        # 占位物有两种来源：location=engine 包的同名真实目录、或 core.symlinks=false 克隆后
        # 链接落成的普通文本文件。前者不可覆盖（引擎内容），后者可重建。
        if os.path.isdir(link):
            # location=engine 的包为引擎内真实目录，不重建也不覆盖（避免误删引擎内容）
            return "drift", "扫描根已存在同名真实目录（engine 包？）：%s" % link
        if not (repair or force):
            return "drift", "已存在占位文件（symlinks=false 的链接落盘）：%s" % link
        remove_link_placeholder(link)
    target = os.path.relpath(target_abs, os.path.dirname(link))
    make_dir_link(link, target)
    return "created", "%s → %s" % (link, target)


def materialize(paths, packs, pack, repair=False, force=False):
    """物化一个包的全部桥接与组件，返回明细列表 [(包, 类型, 组件, 状态, 说明)]。

    engine 包内容在引擎真实目录内，随引擎分发，无需物化；lib 与 project-lib
    两种来源形态完全一致（两层链接：扫描根桥接 + 项目侧 pack 目录），差别只在
    内容根不同，由 `content_base` 统一处理。
    """
    meta = packs[pack]
    if meta["location"] == "engine":
        return []
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


def drop_pack(paths, packs, pack):
    """移除一个包的桥接与组件链接（只删链接，不触碰内容根与项目侧配置）。"""
    meta = packs[pack]
    if meta["location"] == "engine":
        return []
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


def scan_drift(paths, regs, states, primary):
    """对照指定来源的安装状态与实际链接，返回漂移清单 [(类型, 位置, 说明)]。

    只扫描 `primary` 来源声明的包；跨表依赖由 `active_packs` 在闭包层处理，
    漂移检查各表独立，避免一次 status 同时报出两表的问题而分不清修哪个。
    """
    issues = []
    packs = regs[primary]
    installed = set(states[primary]["installed"])
    for name in sorted(installed):
        if name not in packs:
            issues.append(("state", name, "安装状态中存在未知包"))
            continue
        if packs[name].get("default"):
            issues.append(("state", name, "默认包不应出现在安装状态中"))
            continue
        location = packs[name]["location"]
        if location == "engine":
            issues.append(("state", name, "引擎内置包不应出现在安装状态中"))
            continue
        for comp_type in TYPES:
            names = packs[name]["comps"].get(comp_type) or []
            if not names:
                continue
            bridge = bridge_link(paths, name, comp_type)
            if not is_link(bridge):
                issues.append(("bridge", bridge, "缺少或非链接"))
            source_dir = os.path.join(content_base(paths, location), name, comp_type)
            if not os.path.isdir(source_dir):
                issues.append(("source", source_dir, "组件源目录缺失"))
                continue
            pack_link = pack_dir_link(paths, name, comp_type)
            if not is_link(pack_link):
                issues.append(("packdir", pack_link, "缺少或非链接（应为 pack 目录链接）"))
            elif not same_real_path(pack_link, source_dir):
                issues.append(("packdir", pack_link, "指向错误"))
            else:
                # 链接正确时，逐个核对声明的组件在链接内可见
                for comp in names:
                    suffix = ".md" if comp_type == "agents" else ""
                    target = os.path.join(pack_link, comp + suffix)
                    # 规则组件可能是入口独立目录（<名>.entry），两种形态都算存在
                    if comp_type == "rules":
                        entry = os.path.join(pack_link, comp + ".entry")
                        if os.path.isdir(entry):
                            continue
                    if not os.path.exists(target):
                        issues.append(("component", target, "包内组件缺失"))
    # 多余的项目侧 pack 目录：.codebuddy.project/<类型>/ 下除本表已声明包外不应有目录。
    # 必须跨表取「已知」——两个来源共用同一层 .codebuddy.project/<类型>/，
    # 只看本表会把另一张表的链接成片误报为多余。
    known = set()
    for source, packs_of_source in regs.items():
        known |= set(states[source]["installed"]) & set(packs_of_source)
        known |= default_packs(packs_of_source)
    for comp_type in TYPES:
        root = os.path.join(paths["project_root"], ".codebuddy.project", comp_type)
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            if os.path.isdir(full) and entry not in known:
                issues.append(("extra", full, "未在任一安装状态中的 pack 目录"))
    return issues


def cmd_list(paths, regs, states, primary, merged):
    """列出指定来源的包：默认标记、依赖、已装标记、组件计数。"""
    packs = regs[primary]
    installed = set(states[primary]["installed"])
    groups = {}
    for name, meta in packs.items():
        groups.setdefault(meta.get("category", "未分类"), []).append(name)
    print("包注册表：%s（%s）" % (paths["sources"][primary]["packs"], SOURCES[primary]["label"]))
    print("已装：%s" % (", ".join(sorted(installed)) or "（无）"))
    other = "project" if primary == "engine" else "engine"
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
            print("  %-24s 组件 %-2d 依赖 %-16s %s%s"
                  % (name, count, req, meta.get("description", ""), flag))
            # 可选搭配单独一行缩进展示：它是「装了本包后可考虑再装」的提示，
            # 与依赖在语义上完全不同，混进「依赖」列会让读者以为必须装。
            optional = meta.get("optional_requires") or []
            if optional:
                print("  %-24s %s" % ("", "可选搭配 %s（未装不影响本包功能）"
                                      % ", ".join(optional)))
            # 跨表依赖单独提示：它不在本表中，需另一条命令查看其状态
            cross = [dep for dep in (meta.get("requires") or [])
                     if dep in merged and merged[dep]["source"] == other]
            if cross:
                print("  %-24s %s" % ("", "跨表依赖 %s（属 %s 表，安装时自动带上）"
                                      % (", ".join(cross), SOURCES[other]["label"])))
    return 0


def cmd_install(paths, regs, states, primary, names, force, merged):
    """安装指定包及其跨表依赖闭包。默认包无需安装，跳过。"""
    packs = regs[primary]
    for name in names:
        if name not in packs:
            raise PackError("包不存在（%s 表）：%s" % (SOURCES[primary]["label"], name))
    active = active_packs(regs, states)
    _, to_install = resolve_closure(merged, active, names)
    if not to_install:
        print("无需安装：指定的包均属默认集或已安装")
        return 0
    rows = []
    touched = {}
    for source, name in to_install:
        touched.setdefault(source, []).append(name)
        rows.extend(materialize(paths, regs[source], name, repair=True, force=force))
        states[source]["installed"] = sorted(set(states[source]["installed"]) | {name})
    for source in sorted(touched):
        save_state(paths, source, states[source]["installed"])
    for pack, comp_type, comp, status, detail in rows:
        if status != "ok":
            print("[%s] %s/%s %s" % (status, comp_type, comp, detail))
    failed = [r for r in rows if r[3] == "failed"]
    print("")
    for source in sorted(touched):
        print("已安装（%s 表）：%s"
              % (SOURCES[source]["label"], ", ".join(touched[source])))
    # 可选搭配只提示不安装：装 A 不代表用户想要 B，替用户装会改变项目侧链接与安装状态。
    installed_now = active_packs(regs, states)
    hints = []
    for source, name in to_install:
        for dep in regs[source][name].get("optional_requires") or []:
            if dep not in merged or dep in installed_now:
                continue
            hints.append((name, dep, merged[dep]["source"]))
    if hints:
        print("")
        print("可选搭配（未安装，不影响已装包的功能）：")
        for name, dep, dep_source in hints:
            print("  %s 可搭配 %s：python .codebuddy/scripts/pack_install.py%s install %s"
                  % (name, dep, "" if dep_source == "engine" else " --source " + dep_source, dep))
    if failed:
        print("存在失败项 %d 个，请检查上方 [failed] 行" % len(failed))
        return 3
    return 0


def cmd_remove(paths, regs, states, primary, names, force):
    """卸载指定包；默认包拒绝，被依赖的包拒绝（force 时连带移除）。

    被依赖检查跨两表：项目包依赖的引擎包不能单独卸掉，否则项目技能运行时会
    在「引擎依赖缺失」处失败。
    """
    packs = regs[primary]
    installed = set(states[primary]["installed"])
    for name in names:
        if name not in packs:
            raise PackError("包不存在（%s 表）：%s" % (SOURCES[primary]["label"], name))
        if packs[name].get("default"):
            raise PackError("默认包不可卸载：%s（由来源自带）" % name)
        if name not in installed:
            raise PackError("未安装：%s" % name)
    closing = set(names)
    blocked = []
    for name in names:
        for dep_source, dep_name in dependents(regs, name):
            dep_installed = (dep_name in states[dep_source]["installed"]
                             or regs[dep_source][dep_name].get("default"))
            if dep_installed and dep_name not in closing:
                blocked.append((name, dep_name))
    if blocked and not force:
        lines = ["被依赖，拒绝卸载："]
        for name, dep in blocked:
            lines.append("  - %s 被 %s 依赖（使用 --force 连带移除）" % (name, dep))
        raise PackError("\n".join(lines))
    if blocked:
        queue = [dep for _, dep in blocked]
        while queue:
            dep = queue.pop()
            if dep in closing:
                continue
            closing.add(dep)
            for dep_source, dep_name in dependents(regs, dep):
                queue.append(dep_name)
    removed = []
    for name in sorted(closing):
        if name in packs and packs[name].get("default"):
            continue
        if name in packs:
            removed.extend(drop_pack(paths, packs, name))
    save_state(paths, primary, installed - closing)
    for path in removed:
        print("已移除：%s" % path)
    final = sorted(n for n in closing if n in packs and not packs[n].get("default"))
    print("")
    print("已卸载（%s 表）：%s"
          % (SOURCES[primary]["label"], ", ".join(final) or "（无）"))
    return 0


def cmd_status(paths, regs, states, primary):
    """报告指定来源安装状态与实际链接的差异。"""
    issues = scan_drift(paths, regs, states, primary)
    if not issues:
        print("一致：安装状态与实际链接完全匹配（%s 已装 %d 个）"
              % (SOURCES[primary]["label"], len(states[primary]["installed"])))
        return 0
    print("发现 %d 处漂移（%s）：" % (len(issues), SOURCES[primary]["label"]))
    for kind, where, detail in issues:
        print("  [%s] %s：%s" % (kind, where, detail))
    print("")
    print("运行 `verify --repair` 修复")
    return 1


def cmd_verify(paths, regs, states, primary, repair):
    """校验并（可选）修复指定来源的漂移。"""
    issues = scan_drift(paths, regs, states, primary)
    if not issues:
        print("一致：无需修复")
        return 0
    if not repair:
        print("发现 %d 处漂移（未修复）：" % len(issues))
        for kind, where, detail in issues:
            print("  [%s] %s：%s" % (kind, where, detail))
        return 1
    fixed, failed = 0, 0
    for name in sorted(states[primary]["installed"]):
        if name not in regs[primary] or regs[primary][name].get("default"):
            continue
        for _pack, comp_type, comp, status, detail in materialize(
                paths, regs[primary], name, repair=True, force=True):
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
        description="按包注册表安装、卸载、校验可选包（引擎可选包与项目侧包）",
    )
    parser.add_argument("--project-root", help="项目根目录（默认从脚本位置上溯推断）")
    parser.add_argument("--dry-run", action="store_true", help="只报告不落盘")
    parser.add_argument(
        "--source", choices=sorted(SOURCES), default="engine",
        help="包来源：engine=引擎可选包（.codebuddy/lib/packs.json）；"
             "project=项目侧包（.codebuddy.project/project-lib/packs.json）。默认 engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出全部包与安装状态")
    p_install = sub.add_parser("install", help="安装包（自动带出依赖，可跨表）")
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
        regs = load_all_packs(paths)
        merged = merged_registry(regs)
        states = {source: load_state(paths, source) for source in regs}
    except PackError as error:
        print("[错误] %s" % error, file=sys.stderr)
        return 2

    try:
        if args.command == "list":
            return cmd_list(paths, regs, states, args.source, merged)
        if args.command == "install":
            if args.dry_run:
                _, to_install = resolve_closure(
                    merged, active_packs(regs, states), args.packs)
                print("将安装：%s"
                      % (", ".join("%s（%s）" % (name, SOURCES[source]["label"])
                                   for source, name in to_install) or "（无）"))
                return 0
            return cmd_install(paths, regs, states, args.source, args.packs,
                               args.force, merged)
        if args.command == "remove":
            if args.dry_run:
                print("将卸载：%s" % ", ".join(args.packs))
                return 0
            return cmd_remove(paths, regs, states, args.source, args.packs, args.force)
        if args.command == "status":
            return cmd_status(paths, regs, states, args.source)
        if args.command == "verify":
            return cmd_verify(paths, regs, states, args.source, args.repair)
    except PackError as error:
        print("[错误] %s" % error, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
