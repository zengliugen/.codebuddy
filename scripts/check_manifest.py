#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎清单一致性校验（core-init / 引擎维护辅助）。

原「迁移文档同步门禁」（`rules/codebuddy-migration-sync/` 规则）随迁移机制废除而删除。
本脚本承担其留下的**轻量登记守护**职责：核对引擎实际目录与登记清单是否一致，避免
「新增技能/规则却漏登记」。

校验项：
  1. `lib/packs.json` 引用的组件在对应位置真实存在（location=engine 查扫描根，location=lib 查 lib/）；
  2. `lib/` 下无任何包都未引用的孤儿目录；
  3. 每个包的 `requires` 指向同一份注册表中存在的包，且不出现同名组件跨包重复声明；
     `optional_requires`（可选搭配）同样指向存在的包，但**不得**与 `requires` 重复、不得自指——
     它只是「装了 A 时提示可以再装 B」的元数据，不进入依赖闭包，也不放宽校验项 7；
  4. 扫描根形态按 `location` 判定（与 `default` 无关）：`engine` 为真实目录；`lib` 与 `project`
     为链接（`project` 虽 default=true，但内容在项目侧，链接必须存在）；
  5. `project.index.json` 的 `files` / `rule_shells` 中 `path` 均为相对路径（入库共享前提）；
     且 `rule_shells` 的键能落到真实文件——判定时按包 location 区分：
     engine 查扫描根；lib 查 `lib/<pack>/rules/`（未安装该可选包时扫描根无链接属正常）；
     project 视为在项目侧、引擎内不持有。
  6. `root_symlinks.entries` 的 `link` / `path` 均为相对路径，且引擎内链接存在且为符号链接；
  7. **跨包引用合规**：各包正文（`.md`/`.mdc`/`.py` 等）不得引用 `requires` 依赖闭包**之外**的包组件。
     默认包引用可选包组件属违规（该可选包未安装时提示与命令全部失效）；
     允许项：本包自身组件、依赖闭包内包组件、同行命中 `BENIGN_CONTEXT` 的叙述性引用
     （「走 X」「不替代 X」等分流/关系说明）、`evals/` 与 `reports/` 目录（不参与运行时）、
     显式标注 `pack-ref-ok` 的行。
  8. 组件命名必须为 `<包名>-` 开头，或等于包名。
  9. 规则分类与落位：入口规则独占 `<名>.entry/` 目录且有同名文件与对应技能；入口规则
     必须 `alwaysApply: true`；有同名技能的 `RULE.mdc` 不得 `alwaysApply: true`。
  10. 项目专有包（`.codebuddy.project/<类型>/project/`）同样适用 8 与 9 的命名与落位约定。
  11. 触发字段：全库 `*.mdc` 不得出现 `paths`；入口规则必须 `alwaysApply: true`（缺 frontmatter
      即违规）；子规则不得 `alwaysApply: true`。
  12. 技能激活：`agents/interface.yaml` 的 `activation.mode` 不得为 `path_scoped`，
      `activation.paths` 必须为空——技能的唤起靠 `description` 与 `activation.triggers`。
  13. 索引落盘存在性：`files` 的 `path` 与 `artifacts.dirs` 的目录在**已生效包**范围内必须真实
      存在；路径归属未安装的可选包时豁免（该包的骨架本就不该生成）。仅校验相对性与格式时，
      索引写错路径、包卸载后的残留目录都查不出来——表现是技能运行时才报「配置缺失」。

退出码：
  0 —— 一致
  1 —— 存在不一致（打印差异清单）

用法：
  python .codebuddy/scripts/check_manifest.py
"""

import json
import os
import re
import sys

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


def list_dirs(path, skip_symlinks=False, only_symlinks=False):
    """列出目录下的一级子目录名（排序）。

    skip_symlinks：跳过符号链接目录（lib / project 包在扫描根以链接形式出现）；
    only_symlinks：只保留符号链接目录（用于核对包桥接形态）。
    """
    if not os.path.isdir(path):
        return []
    result = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if not os.path.isdir(full):
            continue
        is_link = os.path.islink(full)
        if skip_symlinks and is_link:
            continue
        if only_symlinks and not is_link:
            continue
        result.append(name)
    return sorted(result)


def load_packs(codebuddy_dir):
    """读取 `lib/packs.json`；返回 packs 字典，失败时返回 None 并记录问题。"""
    path = os.path.join(codebuddy_dir, "lib", "packs.json")
    if not os.path.isfile(path):
        return None, ["缺少包注册表：lib/packs.json"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        return None, ["包注册表读取失败：%s" % error]
    packs = data.get("packs")
    if not isinstance(packs, dict) or not packs:
        return None, ["包注册表缺少 packs 对象：lib/packs.json"]
    return packs, []


def component_path(codebuddy_dir, packs, pack, comp_type, name):
    """按 location 推导组件真实路径（与 pack_install.py 保持同一条推导规则）。

    规则组件支持两种目录形态：
      `<类型>/<pack>/<name>/`          —— 规范规则（含 RULE.mdc 与子规则）
      `<类型>/<pack>/<name>.entry/`    —— 入口规则（独占目录）
    优先返回实际存在的那个；均不存在时返回规范形态（供报错展示期望路径）。
    """
    meta = packs[pack]
    suffix = ".md" if comp_type == "agents" else ""
    if meta["location"] == "engine":
        bases = [os.path.join(codebuddy_dir, comp_type, pack)]
    elif meta["location"] == "project":
        # 项目专有包与其他包同构：内容在 .codebuddy.project/<类型>/<pack>/ 下
        bases = [os.path.join(os.path.dirname(codebuddy_dir), ".codebuddy.project",
                              comp_type, pack)]
    else:
        bases = [os.path.join(codebuddy_dir, "lib", pack, comp_type)]

    primary = os.path.join(bases[0], name + suffix)
    if comp_type == "rules":
        entry = os.path.join(bases[0], name + ".entry" + suffix)
        if os.path.isdir(entry) and not os.path.isdir(primary):
            return entry
    return primary


def check_packs(codebuddy_dir, packs):
    """校验包注册表与磁盘结构的一致性，返回问题清单。"""
    problems = []
    seen = {}
    for pack, meta in packs.items():
        for key in ("location", "requires", "comps", "default"):
            if key not in meta:
                problems.append("包 %s 缺少 %s 字段" % (pack, key))
        location = meta.get("location")
        if location not in ("engine", "lib", "project"):
            problems.append("包 %s 的 location 非法：%s" % (pack, location))
            continue
        for dep in meta.get("requires") or []:
            if dep not in packs:
                problems.append("包 %s 依赖了不存在的包：%s" % (pack, dep))
        # 可选搭配：只做提示用，不进入依赖闭包。因此与 requires 重复即冗余声明
        # （那说明它其实是硬依赖），自指则无意义。这两类错误都不会影响运行，
        # 只会让「可选」与「必需」的边界在注册表里变得不可读。
        optional = meta.get("optional_requires")
        if optional is not None:
            if not isinstance(optional, list) or not all(
                    isinstance(item, str) for item in optional):
                problems.append("包 %s 的 optional_requires 必须是字符串数组：%r"
                                % (pack, optional))
            else:
                required = set(meta.get("requires") or [])
                for dep in optional:
                    if dep not in packs:
                        problems.append("包 %s 的可选搭配指向不存在的包：%s" % (pack, dep))
                    elif dep in required:
                        problems.append(
                            "包 %s 的可选搭配与必需依赖重复：%s（既是必需就不该标为可选）"
                            % (pack, dep))
                    elif dep == pack:
                        problems.append("包 %s 的可选搭配不能指向自身" % pack)
        comps = meta.get("comps") or {}
        for comp_type in ("rules", "skills", "agents"):
            for name in comps.get(comp_type) or []:
                owner = seen.get((comp_type, name))
                if owner:
                    problems.append("组件 %s/%s 被两个包同时声明：%s 与 %s"
                                    % (comp_type, name, owner, pack))
                else:
                    seen[(comp_type, name)] = pack
                target = component_path(codebuddy_dir, packs, pack, comp_type, name)
                if not os.path.exists(target):
                    problems.append("组件缺失：bundle=%s %s/%s（期望 %s）"
                                    % (pack, comp_type, name, target))
        # 扫描根形态按 location 判定（与 default 无关）：engine 必须是真实目录；
        # lib 与 project 必须是链接（lib 未安装时允许缺席，project 必须存在）
        for comp_type in ("rules", "skills", "agents"):
            is_project_pack = location == "project"
            # 项目专有包固定三个桥接（内容可暂空）；其余包仅在声明了该类型时才校验
            if not comps.get(comp_type) and not is_project_pack:
                continue
            scan_root = os.path.join(codebuddy_dir, comp_type, pack)
            if is_project_pack:
                # 项目专有包：内容在项目侧，扫描根必须是指向它的链接
                if not os.path.islink(scan_root):
                    problems.append("项目专有包桥接缺失或非链接：%s/%s" % (comp_type, pack))
            elif location == "engine":
                if not os.path.isdir(scan_root):
                    problems.append("engine 包目录缺失：%s/%s" % (comp_type, pack))
                elif os.path.islink(scan_root):
                    problems.append("engine 包目录不应为链接：%s/%s" % (comp_type, pack))
            else:
                if os.path.lexists(scan_root) and not os.path.islink(scan_root):
                    problems.append("lib 包在扫描根应为链接（实际为真实目录）：%s/%s"
                                    % (comp_type, pack))
                # 项目侧 pack 目录同样必须是链接（整目录指向 lib，不逐组件建链）
                proj_pack = os.path.join(os.path.dirname(codebuddy_dir), ".codebuddy.project",
                                         comp_type, pack)
                if os.path.lexists(proj_pack) and not os.path.islink(proj_pack):
                    problems.append("项目侧 pack 目录应为链接（实际为真实目录）：.codebuddy.project/%s/%s"
                                    % (comp_type, pack))

    # lib/ 下的孤儿目录检测
    lib_dir = os.path.join(codebuddy_dir, "lib")
    if os.path.isdir(lib_dir):
        for entry in sorted(os.listdir(lib_dir)):
            full = os.path.join(lib_dir, entry)
            if not os.path.isdir(full) or entry == "packs.json":
                continue
            if entry not in packs:
                problems.append("lib/%s 未被任何包声明（孤儿目录）" % entry)
            elif packs[entry].get("location") != "lib":
                problems.append("lib/%s 存在但该包 location 非 lib" % entry)
    return problems


# 跨包引用校验：同行出现以下语境的引用属「叙述性」（分流 / 排除 / 关系说明），不构成功能耦合。
BENIGN_CONTEXT = (
    "走 ", "走\u0060", "排除", "路由", "不替代", "不检查", "不负责", "转本", "各自", "须让路",
    "详见", "交给", "由 ", "禁止", "改由", "参考", "登记", "vendor", "第三方", "上游",
    "同一布局", "同一份", "口径", "例：", "实例", "合计", "见 ", "按 ", "如 ", "当前为",
    "未安装", "已安装", "可选包", "安装状态", "降级",
)
# 参与跨包引用的正文文件类型（可执行脚本也纳入：脚本内硬编码他包路径危害最大）
PACK_REF_SCAN_EXT = (".md", ".mdc", ".yaml", ".yml", ".json", ".py", ".cmd", ".ps1", ".sh")
# 不参与运行时、可自由提及他包组件的目录（触发用例的反例语义需要点名其他技能）
PACK_REF_SKIP_DIRS = ("evals", "reports", "caches", "__pycache__", ".previews")
# 显式豁免标记（行级）：该行属有意引用，须同行注明理由
PACK_REF_OK_MARK = "pack-ref-ok"
# 显式豁免声明（文件级）：`pack-ref-ok: <包名>[,<包名>...]`，声明本文件有意引用这些包，
# 且已按安装状态做了条件化处理（如「已安装 X 时…；未安装降级为…」）。
# 声明可跨多行书写，逐行声明会累积生效；须随文件入库，供评审时复核是否仍成立。
PACK_REF_OK_DECL = re.compile(r"pack-ref-ok\s*[:：]\s*([A-Za-z0-9_.\-]+(?:\s*,\s*[A-Za-z0-9_.\-]+)*)")
# 组件名最小长度：低于此长度（如 language）易在自然语言中误命中
PACK_REF_MIN_NAME_LEN = 8
# 不参与跨包引用判定的组件名（通用词，在自然语言与其他语境中大量出现，无辨识度）
PACK_REF_IGNORED_NAMES = ("language",)


def component_owner_map(packs):
    """构建 组件名 -> 声明它的包集合 的映射。"""
    owners = {}
    for pack, meta in packs.items():
        for comp_type in ("rules", "skills", "agents"):
            for name in (meta.get("comps") or {}).get(comp_type) or []:
                owners.setdefault(name, set()).add(pack)
    return owners


def requires_closure(packs, pack):
    """计算包的依赖闭包（含自身）；遇到不存在的依赖时跳过（由 check_packs 另行报错）。"""
    seen = set()
    stack = [pack]
    while stack:
        current = stack.pop()
        if current in seen or current not in packs:
            continue
        seen.add(current)
        stack.extend(packs[current].get("requires") or [])
    return seen


def pack_of_file(codebuddy_dir, path):
    """按路径反推文件所属包；无法判定（不在任一包目录内）时返回 None。

    推导规则与 component_path 一致：
      lib/<pack>/<类型>/...     → location=lib 的包
      <类型>/<pack>/...         → location=engine 的包（引擎扫描根）
    """
    rel = os.path.relpath(path, codebuddy_dir).replace("\\", "/")
    segments = rel.split("/")
    if not segments:
        return None
    if segments[0] == "lib" and len(segments) > 2:
        return segments[1]
    if len(segments) > 2 and segments[0] in ("rules", "skills", "agents"):
        return segments[1]
    return None


def read_yaml_block(path, key):
    """按缩进提取 YAML 中某个顶层键的值块（不引入 PyYAML 依赖）。

    只服务「读 activation 段」这一种需求：先定位 `key:` 行，再收集其后
    缩进更深的所有行，遇到缩进不深于 `key` 的行即结束。

    参数：
        path：YAML 文件路径。
        key：目标顶层键名。

    返回：
        (块内行列表, key 行的缩进)；文件不存在或找不到该键时返回 (None, None)。
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None, None
    pattern = re.compile(r"^(\s*)%s\s*:\s*$" % re.escape(key))
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        block = []
        for follow in lines[index + 1:]:
            if not follow.strip():
                block.append(follow)
                continue
            if len(follow) - len(follow.lstrip()) <= indent:
                break
            block.append(follow)
        return block, indent
    return None, None


# 不参与技能触发校验的目录（示例、评测夹具、预览产物，均非真实生效的技能）
SKILL_SCAN_SKIP_DIRS = ("evals", "reports", "caches", "__pycache__", ".previews",
                        "examples", "fixtures")


def check_skill_activation(codebuddy_dir, project_root):
    """校验技能不得使用路径触发（校验项 12）。

    约定（见 rules/core/core-rule-governance/ 与技能工程规范）：
      1. `agents/interface.yaml` 的 `compatibility.activation.mode` 不得为 `path_scoped`；
      2. `activation.paths` 必须为空（`[]` 或缺省）——技能的唤起靠 `description` 与
         `activation.triggers`，路径条件会在「文件已改」之后才命中，赶不上决策点。

    为什么要覆盖这条：规则侧的 `paths` 已全库清除，但技能是**另一处触发面**——
    `interface.yaml` 里如果写了 `mode: path_scoped` + `paths`，同一个「事后触发」
    问题会从技能侧重新长出来，而规则校验完全看不到它。

    返回：
        缺口列表
    """
    problems = []
    roots = [codebuddy_dir, os.path.join(project_root, ".codebuddy.project")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKILL_SCAN_SKIP_DIRS]
            if "interface.yaml" not in filenames:
                continue
            if os.path.basename(dirpath) != "agents":
                continue
            full = os.path.join(dirpath, "interface.yaml")
            rel = os.path.relpath(full, project_root).replace("\\", "/")
            block, _indent = read_yaml_block(full, "activation")
            if block is None:
                continue
            text = "\n".join(block)
            mode = re.search(r"(?m)^\s*mode\s*:\s*[\"']?([A-Za-z_]+)[\"']?", text)
            if mode and mode.group(1) == "path_scoped":
                problems.append(
                    "技能不得使用 path_scoped 激活（改为 manual + triggers）：%s" % rel)
            if re.search(r"(?m)^\s*paths\s*:", text) and not re.search(
                    r"(?m)^\s*paths\s*:\s*\[\s*\]\s*$", text):
                problems.append(
                    "技能 activation.paths 必须为空（技能靠 description 与 triggers 唤起）：%s" % rel)
    return problems


def check_component_naming(packs):
    """校验组件命名是否符合「包前缀」约定（校验项 8）。

    约定：组件名必须以 `<包名>-` 开头；组件名等于包名时豁免
    （vendor 包自名组件，如 unity-pipeline / grilling / yao-meta-skill）。

    背景：组件名同时是目录名、packs.json 键与跨包引用锚点，命名无前缀时
    无法从名字判断归属，重构与排查都要反查注册表，因此把约定固化为校验。

    返回：
        缺口列表
    """
    problems = []
    for pack, meta in packs.items():
        if meta.get("location") == "project":
            continue  # 项目专有包由项目自行管理
        for comp_type in ("rules", "skills", "agents"):
            for name in (meta.get("comps") or {}).get(comp_type) or []:
                if name == pack or name.startswith(pack + "-"):
                    continue
                problems.append(
                    "组件命名不合规：%s/%s=%s（应以 %s- 开头，或与包名相同）"
                    % (pack, comp_type, name, pack))
    return problems


def check_rule_classification(codebuddy_dir, packs):
    """校验规则分类、目录落位与命名约定（校验项 9）。

    约定（见 rules/core/core-rule-governance/）：
      1. 入口规则独占目录：`<规则名>.entry/<规则名>.entry.mdc`；
      2. 入口规则必须有对应技能（精确同名，或为其共同前缀）；
      3. 规范规则在 `<规则名>/RULE.mdc`，有对应技能时不得 alwaysApply: true；
      4. 被其他技能拉起的技能不建入口规则（由人工判定，脚本只查落位）。

    返回：
        缺口列表
    """
    problems = []
    for pack, meta in packs.items():
        if meta.get("location") == "project":
            continue
        loc = meta.get("location")
        skills = set((meta.get("comps") or {}).get("skills") or [])
        base_dir = (os.path.join(codebuddy_dir, "rules", pack) if loc == "engine"
                    else os.path.join(codebuddy_dir, "lib", pack, "rules"))
        if not os.path.isdir(base_dir):
            continue
        for entry_dir in sorted(os.listdir(base_dir)):
            full = os.path.join(base_dir, entry_dir)
            if not os.path.isdir(full) or not entry_dir.endswith(".entry"):
                continue
            rule_name = entry_dir[: -len(".entry")]
            expect = os.path.join(full, rule_name + ".entry.mdc")
            rel_dir = os.path.relpath(full, codebuddy_dir).replace("\\", "/")
            if not os.path.isfile(expect):
                problems.append(
                    "入口规则目录缺少同名文件：%s（期望 %s.entry.mdc）" % (rel_dir, rule_name))
                continue
            if not (rule_name in skills or any(s.startswith(rule_name + "-") for s in skills)):
                problems.append(
                    "入口规则无对应技能：%s（期望技能 %s 或其前缀技能存在于包 %s）"
                    % (rel_dir, rule_name, pack))

        # 规范规则内不得重复定义强制入口：已有 .entry/ 目录时，RULE.mdc 里再写「强制入口」
        # 会造成两处定义，一旦不一致无法判断哪份为准（治理规则 §五第 5 条）。
        entry_names = {d[: -len(".entry")] for d in os.listdir(base_dir)
                       if d.endswith(".entry") and os.path.isdir(os.path.join(base_dir, d))}
        for rule in sorted(entry_names):
            rf = os.path.join(base_dir, rule, "RULE.mdc")
            if not os.path.isfile(rf):
                continue
            try:
                with open(rf, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                continue
            if re.search(r"(?m)^##+ .*强制入口", text):
                problems.append(
                    "规范规则内重复定义强制入口：%s（已有 %s.entry/，强制入口只写在入口规则里）"
                    % (os.path.relpath(rf, codebuddy_dir).replace("\\", "/"), rule))

        # 规范规则：有同名技能时不得 alwaysApply: true
        for rule in (meta.get("comps") or {}).get("rules") or []:
            d = os.path.join(base_dir, rule)
            rf = os.path.join(d, "RULE.mdc")
            if not os.path.isfile(rf):
                continue
            try:
                with open(rf, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                continue
            head = text
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    head = text[:end]
            if "alwaysApply: true" in head and rule in skills:
                problems.append(
                    "规范规则不应 alwaysApply: true：%s（该包存在同名技能 %s，规范应由其按需加载）"
                    % (os.path.relpath(rf, codebuddy_dir).replace("\\", "/"), rule))
    return problems


def read_frontmatter(path):
    """读取 *.mdc 的 frontmatter 头。

    返回：
        frontmatter 文本；文件不以 `---` 开头时返回 None（视为没有触发字段声明）。
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[:end] if end != -1 else text


def has_true_flag(head, key):
    """判断 frontmatter 中某个键是否为真值。

    兼容三类合法写法，避免把 `true  # 常驻` 误判为不合规：
      - `alwaysApply: true`
      - `alwaysApply: true  # 注释`（YAML 行尾注释）
      - `alwaysApply: "true"` / `'true'`

    参数：
        head：frontmatter 文本。
        key：字段名。

    返回：
        是否声明为真值。
    """
    pattern = r"(?m)^%s\s*:\s*[\"']?true[\"']?\s*(?:#.*)?$" % re.escape(key)
    return re.search(pattern, head) is not None


def check_trigger_fields(codebuddy_dir, project_root):
    """校验 alwaysApply 与 paths 的取值（校验项 11）。

    约定（见 rules/core/core-rule-governance/classification-spec.mdc §1 与 §1.1）：
      1. 任何规则都不得出现 `paths`——触发语义只保留「常驻」与「被显式读取」两种；
         常见崩溃形态是「文件已写坏规则才到场」与「路径模式与实际目录不符导致永不生效」；
      2. 入口规则必须 `alwaysApply: true`，且必须声明 frontmatter；
      3. 非入口规则（规范规则与子规则）不得 `alwaysApply: true`——它们只能被入口或技能
         显式读取，常驻会形成双份注入。例外是无对应技能的底线型 `RULE.mdc`：这类规则
         没有加载方，必须常驻，其判定与 `check_rule_classification` 项 9 保持一致。

    背景：判定条件全部只看 frontmatter。正文里出现 `paths:` 字样（如引述历史配置、
    说明为什么弃用）不构成触发配置，不应误报。

    返回：
        缺口列表
    """
    problems = []
    project_root = os.path.abspath(project_root)
    # 项目侧只校验「真正被加载的规则」（经软链接进引擎的 rules/project/）。
    # .codebuddy.project/configs/ 下是 rule_shells 的项目事实正文与配置，不被规则加载器扫描，
    # 也不承载触发语义，套用入口/子规则判定会误报（如正文沿用 .entry 目录名即被判为入口规则）。
    roots = [
        codebuddy_dir,
        os.path.join(project_root, ".codebuddy.project")
    ]
    skip_dirs = [os.path.join(project_root, ".codebuddy.project", "configs")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if any(dirpath == d or dirpath.startswith(d + os.sep) for d in skip_dirs):
                continue
            for name in sorted(filenames):
                if not name.endswith(".mdc"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, project_root).replace("\\", "/")
                is_entry = dirpath.endswith(".entry") and name.endswith(".entry.mdc")
                head = read_frontmatter(full)
                if head is None:
                    if is_entry:
                        problems.append(
                            "入口规则缺少 frontmatter（须 alwaysApply: true）：%s" % rel)
                    continue
                if re.search(r"(?m)^paths\s*:", head):
                    problems.append(
                        "规则不得使用 paths（改为常驻，或由入口/技能显式加载）：%s" % rel)
                    continue
                if is_entry:
                    if not has_true_flag(head, "alwaysApply"):
                        problems.append("入口规则必须 alwaysApply: true：%s" % rel)
                    continue
                # 非入口规则：只允许「无技能的底线型 RULE.mdc」常驻，其余必须为 false。
                # 是否属底线型由 check_rule_classification 依据 packs.json 的 comps.skills 判定，
                # 此处只拦「子规则」（非 RULE.mdc）误写常驻这类明确违规。
                if name != "RULE.mdc" and has_true_flag(head, "alwaysApply"):
                    problems.append(
                        "子规则不得 alwaysApply: true（由入口或技能按需加载）：%s" % rel)
    return problems


def iter_project_components(root):
    """递归列出项目侧组件目录，返回 [(种类, 绝对路径)]，种类为 entry / rule / skill。

    项目侧 `<类型>/project/` 下允许再按「族」分组，把入口规则、规范规则与技能收进同一族目录，
    组件因此可能不在第一层，不能用单层 listdir 判定。识别规则：
      - `<名>.entry/`   → 入口规则（不再深入）；
      - 含 `SKILL.md`   → 技能（不再深入，避免把 references/ 等子目录误判为技能）；
      - 含 `RULE.mdc`   → 规范规则（继续深入，其内可挂 `.entry/` 子目录）；
      - 其余目录视为分组层，继续深入。

    参数：
        root：组件根目录（如 `.codebuddy.project/rules/project`）。

    返回：
        [(种类, 绝对路径)]，按路径排序；根目录不存在时返回空列表。
    """
    if not os.path.isdir(root):
        return []
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        if os.path.basename(current).endswith(".entry"):
            found.append(("entry", current))
            continue
        if os.path.isfile(os.path.join(current, "SKILL.md")):
            found.append(("skill", current))
            continue
        if os.path.isfile(os.path.join(current, "RULE.mdc")):
            found.append(("rule", current))
        try:
            children = sorted(os.listdir(current))
        except OSError:
            continue
        for child in children:
            full = os.path.join(current, child)
            if os.path.isdir(full):
                stack.append(full)
    return sorted(found, key=lambda item: item[1])


def check_project_components(project_root):
    """校验项目专有包的组件命名与落位（校验项 10）。

    约定（见 rules/core/core-rule-governance/ §2.4）：
      1. `.codebuddy.project/<类型>/project/` 下的组件名必须以 `project-` 开头；
      2. 入口规则独占目录：`<名>.entry/<名>.entry.mdc`，且必须有同名（或前缀）技能；
      3. 规范规则有同名技能时不得 `alwaysApply: true`；
      4. 技能的 SKILL.md frontmatter `name` 必须等于技能目录名。

    背景：项目专有包在 packs.json 里 `comps` 为空（内容由项目自行管理），
    项 8 与项 9 都跳过它，导致项目侧改名后没有任何脚本兜底。此项按同一套约定补上。

    返回：
        缺口列表
    """
    problems = []
    rules_root = os.path.join(project_root, ".codebuddy.project", "rules", "project")
    skills_root = os.path.join(project_root, ".codebuddy.project", "skills", "project")

    skills = set()
    for kind, full in iter_project_components(skills_root):
        if kind != "skill":
            continue
        name = os.path.basename(full)
        rel = os.path.relpath(full, project_root).replace("\\", "/")
        if not name.startswith("project-"):
            problems.append("项目侧技能命名不合规：%s（应以 project- 开头）" % rel)
        skills.add(name)
        skill_md = os.path.join(full, "SKILL.md")
        try:
            with open(skill_md, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        declared = None
        if text.startswith("---"):
            end = text.find("\n---", 3)
            head = text[:end] if end != -1 else ""
            for line in head.splitlines():
                if line.startswith("name:"):
                    declared = line[len("name:"):].strip()
                    break
        if declared and declared != name:
            problems.append("项目侧技能 SKILL.md 的 name 与目录名不一致：%s（name=%s）"
                            % (os.path.relpath(full, project_root).replace("\\", "/"), declared))

    if not os.path.isdir(rules_root):
        return problems

    for kind, full in iter_project_components(rules_root):
        name = os.path.basename(full)
        rel = os.path.relpath(full, project_root).replace("\\", "/")
        if kind == "entry":
            rule_name = name[: -len(".entry")]
            if not rule_name.startswith("project-"):
                problems.append("项目侧入口规则命名不合规：%s（应以 project- 开头）" % rel)
            expect = os.path.join(full, rule_name + ".entry.mdc")
            if not os.path.isfile(expect):
                problems.append("项目侧入口规则目录缺少同名文件：%s（期望 %s.entry.mdc）"
                                % (rel, rule_name))
                continue
            if not (rule_name in skills
                    or any(s.startswith(rule_name + "-") for s in skills)):
                problems.append("项目侧入口规则无对应技能：%s（期望技能 %s 或其前缀技能）"
                                % (rel, rule_name))
            continue

        if kind != "rule":
            continue
        if not name.startswith("project-"):
            problems.append("项目侧规则命名不合规：%s（应以 project- 开头）" % rel)
        rule_file = os.path.join(full, "RULE.mdc")
        if not os.path.isfile(rule_file):
            continue
        try:
            with open(rule_file, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        head = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                head = text[:end]
        if "alwaysApply: true" in head and any(
                s == name or s.startswith(name + "-") for s in skills):
            problems.append("项目侧规范规则不应 alwaysApply: true：%s（存在对应技能，应由其按需加载）"
                            % rel)
    return problems


def check_cross_pack_refs(codebuddy_dir, packs):
    """校验各包正文是否引用了依赖闭包之外的包组件（校验项 7）。

    背景：目录引入 pack 层后，默认包（vcs/tool/core）曾大量硬编码可选包（csharp）的
    技能名、脚本路径与 CLI 参数。这类引用不是代码，不会编译报错，只会在「未安装该可选包
    的项目」上表现为提示路径不存在、命令跑不通，因此必须靠本校验兜住。
    """
    problems = []
    owners = component_owner_map(packs)
    names = [name for name in owners
             if len(name) >= PACK_REF_MIN_NAME_LEN and name not in PACK_REF_IGNORED_NAMES]
    if not names:
        return problems
    # 词边界匹配：避免 csharp-code 命中 csharp-code-review
    patterns = {}
    for name in names:
        patterns[name] = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
    closures = {pack: requires_closure(packs, pack) for pack in packs}

    for dirpath, dirnames, filenames in os.walk(codebuddy_dir):
        dirnames[:] = [d for d in dirnames
                       if d not in PACK_REF_SKIP_DIRS and d != ".git"]
        for filename in filenames:
            if not filename.endswith(PACK_REF_SCAN_EXT):
                continue
            full = os.path.join(dirpath, filename)
            owner = pack_of_file(codebuddy_dir, full)
            if owner not in packs:
                continue
            rel = os.path.relpath(full, codebuddy_dir).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as handle:
                    lines = handle.read().splitlines()
            except OSError as error:
                problems.append("跨包引用校验读取失败：%s（%s）" % (rel, error))
                continue
            # 解析文件级豁免声明：仅豁免被点名的包，其余引用照常校验。
            # 声明内可写包名，也可写组件名（组件名自动折算为其所属包），便于按实际写法标注。
            declared = set()
            for line in lines:
                match = PACK_REF_OK_DECL.search(line)
                if match:
                    declared.update(
                        item.strip() for item in match.group(1).split(",") if item.strip())
            allowed_packs = set()
            for item in declared:
                if item in packs:
                    allowed_packs.add(item)
                elif item in owners:
                    allowed_packs.update(owners[item])
            for lineno, line in enumerate(lines, 1):
                if PACK_REF_OK_MARK in line:
                    continue
                if any(token in line for token in BENIGN_CONTEXT):
                    continue
                for name, pattern in patterns.items():
                    if not pattern.search(line):
                        continue
                    targets = owners[name]
                    if owner in targets or targets & closures[owner]:
                        continue
                    if targets <= allowed_packs:
                        continue
                    problems.append(
                        "跨包引用违规：%s:%d 包 %s 引用了 %s（属包 %s，不在其 requires 闭包内）"
                        % (rel, lineno, owner, name, "、".join(sorted(targets))))
    return sorted(set(problems))


def pack_of_index_path(rel):
    """从索引路径中解析所属包名。

    路径约定为 `.codebuddy.project/<configs|caches>/<类别>/<pack>/<组件>/...`，
    其中 `<类别>` 为 skills / rules / agents。非该结构（如根级通用文件
    `.codebuddy.project/caches/.vcs-lock`）返回空串，表示不按包过滤。

    参数：
        rel：索引中登记的相对项目根路径。

    返回：
        包名；无法判定时返回空串。
    """
    parts = rel.replace("\\", "/").split("/")
    for index, segment in enumerate(parts):
        if segment in ("skills", "rules", "agents") and index + 2 < len(parts):
            return parts[index + 1]
    return ""


def read_installed_packs(project_root):
    """读取项目侧已装可选包清单；文件缺失或损坏时返回空集合。

    引擎仓库可能被单独检出（无项目侧目录），此时不做安装状态过滤——
    缺失属正常，不应阻断校验。

    参数：
        project_root：项目根（`.codebuddy` 的父目录）。

    返回：
        (已装包名集合, 问题列表)
    """
    path = os.path.join(project_root, ".codebuddy.project", "configs", "packs.json")
    if not os.path.isfile(path):
        return set(), []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        return set(), ["项目侧包清单读取失败：%s（%s）" % (path, error)]
    installed = data.get("installed")
    if not isinstance(installed, list):
        return set(), ["项目侧包清单的 installed 必须是数组：%s" % path]
    return set(str(name) for name in installed), []


def check_index_targets(index, packs, project_root):
    """校验索引登记的路径在磁盘真实存在（校验项 13）。

    背景：项 5 只校验 `files` / `rule_shells` 的 `path` 是否为相对路径，`artifacts.dirs`
    也只校验相对性——索引指向一个写错或已被删除的路径时，全部校验仍然通过，
    直到技能运行时才以「配置缺失」的形式暴露。包卸载后残留的条目同理无法识别。

    豁免规则：
      - 路径归属未安装的可选包 → 跳过（该包的骨架本就不该生成）；
      - 路径归属未在 `lib/packs.json` 声明的包 → 报错（索引与注册表脱节）；
      - 无法判定归属（通用配置/产物）→ 照常校验。

    参数：
        index：已解析的索引字典。
        packs：`lib/packs.json` 的 packs 字典。
        project_root：项目根（`.codebuddy` 的父目录）。

    返回：
        缺口列表。
    """
    problems = []
    installed, install_problems = read_installed_packs(project_root)
    problems.extend(install_problems)
    active = set(name for name, meta in (packs or {}).items() if meta.get("default")) | installed

    def skip_by_pack(code_name, rel, kind_label):
        """判断条目是否因归属未安装的可选包而豁免。

        参数：
            code_name：索引中的逻辑名。
            rel：索引登记的相对项目根路径。
            kind_label：报错时展示的条目全名（如 `files.code_review.config`）。

        返回：
            True 表示豁免（归属未安装的可选包），False 表示需继续校验存在性。
        """
        pack = pack_of_index_path(rel)
        if not pack:
            return False
        if pack not in (packs or {}):
            problems.append("索引 %s 的路径归属包 %s，但该包未在 lib/packs.json 声明：%s"
                            % (kind_label, pack, code_name))
            return False
        if pack not in active:
            return True
        return False

    for code_name, entry in (index.get("files") or {}).items():
        rel = (entry or {}).get("path")
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            continue
        if skip_by_pack(code_name, rel, "files." + code_name):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(project_root, rel))):
            problems.append(
                "索引 files.%s 指向的文件不存在：%s（包已安装，骨架须存在；"
                "写错路径请修索引，包已卸载请清条目）" % (code_name, rel))

    for code_name, entry in (index.get("rule_shells") or {}).items():
        rel = (entry or {}).get("path")
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            continue
        if skip_by_pack(code_name, rel, "rule_shells." + code_name):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(project_root, rel))):
            problems.append(
                "索引 rule_shells.%s 的项目事实正文不存在：%s（薄壳会指向空文件）"
                % (code_name, rel))

    for logical_name, rel in ((index.get("artifacts") or {}).get("dirs") or {}).items():
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            continue
        if skip_by_pack(logical_name, rel, "artifacts.dirs." + logical_name):
            continue
        if not os.path.isdir(os.path.normpath(os.path.join(project_root, rel))):
            problems.append(
                "索引 artifacts.dirs.%s 指向的目录不存在：%s（请运行 core-init 补齐产物目录）"
                % (logical_name, rel))

    return problems


def main():
    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        sys.stderr.write("[错误] 未找到 .codebuddy 目录。请在含 .codebuddy 的项目内运行。\n")
        return 1

    problems = []

    # 1/2. 包注册表与磁盘结构核对（唯一事实源为 lib/packs.json，不再维护硬编码清单）
    packs, pack_problems = load_packs(codebuddy_dir)
    problems.extend(pack_problems)
    if packs:
        problems.extend(check_packs(codebuddy_dir, packs))
        # 7. 跨包引用合规（防默认包硬编码可选包组件）
        problems.extend(check_cross_pack_refs(codebuddy_dir, packs))
        # 8. 组件命名合规（包前缀约定）
        problems.extend(check_component_naming(packs))
        # 9. 规则分类与命名（入口 vs 规范）
        problems.extend(check_rule_classification(codebuddy_dir, packs))
        # 10. 项目专有包组件的命名与落位（project- 前缀、入口目录、技能同名）
        problems.extend(check_project_components(os.path.dirname(codebuddy_dir)))
        # 11. alwaysApply 取值与 paths 禁用（入口常驻、规范不常驻、全库无 paths）
        problems.extend(check_trigger_fields(codebuddy_dir, os.path.dirname(codebuddy_dir)))
        # 12. 技能激活方式（不得 path_scoped，activation.paths 必须为空）
        problems.extend(check_skill_activation(codebuddy_dir, os.path.dirname(codebuddy_dir)))

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

        # rule_shells 的键为「薄壳相对 .codebuddy 的路径」，必须能落到真实文件（防路径随目录重构漂移）。
        # 候选位置随包 location 不同：
        #   location=engine → 扫描根 .codebuddy/rules/<pack>/<名>/...（真实目录）
        #   location=lib → 源在 .codebuddy/lib/<pack>/rules/<名>/...，扫描根仅是指向项目侧的链接；
        #                             未安装该包时扫描根无链接，此时 lib 源仍在，不应判为悬空。
        #   location=project         → 项目侧 .codebuddy.project/rules/project/...，引擎内不持有该文件
        for key in (index.get("rule_shells") or {}):
            if os.path.isabs(key):
                problems.append("索引 rule_shells 的键必须为相对路径：%s" % key)
                continue
            shell_abs = os.path.normpath(os.path.join(codebuddy_dir, key))
            if os.path.isfile(shell_abs):
                continue
            # 扫描根无文件：按包 location 判断是否为「可选包未安装」的正常情形
            segments = key.replace("\\", "/").split("/")
            pack = segments[1] if len(segments) > 1 else ""
            pack_meta = packs.get(pack) if packs else None
            if pack_meta and pack_meta.get("location") == "lib" and len(segments) > 3:
                lib_source = os.path.normpath(os.path.join(
                    codebuddy_dir, "lib", pack, "rules", segments[2], *segments[3:]))
                if os.path.isfile(lib_source):
                    # 可选包未安装属正常：源在 lib/，扫描根链接由 pack_install 在安装时创建
                    continue
                problems.append("索引 rule_shells 的键在包 %s 内不存在：%s（期望 %s）"
                                % (pack, key, lib_source))
                continue
            if pack_meta and pack_meta.get("location") == "project":
                # 项目专有包：文件在项目侧，引擎内本就不存在
                continue
            problems.append("索引 rule_shells 的键在磁盘不存在（目录重构后未同步）：%s" % key)

        # 项目专有包的内容不得登记索引（规则 core-engine 第 7 条）：
        # 索引随引擎共享且对所有消费项目一致，登入项目专有内容会让其他项目在
        # core-init 时生成用不上的骨架。
        project_root_for_index = os.path.dirname(codebuddy_dir)
        project_scan_roots = [
            os.path.join(project_root_for_index, ".codebuddy.project", kind, "project")
            for kind in ("rules", "skills", "agents")
        ]
        for group_key in ("files", "rule_shells"):
            for code_name, entry in (index.get(group_key) or {}).items():
                rel_path = (entry or {}).get("path")
                if not isinstance(rel_path, str) or not rel_path:
                    continue
                target = os.path.normpath(os.path.join(project_root_for_index, rel_path))
                for scan_root in project_scan_roots:
                    normalized_root = os.path.normpath(scan_root)
                    if target == normalized_root or target.startswith(normalized_root + os.sep):
                        problems.append(
                            "索引 %s.%s 指向项目专有包（%s）：%s。"
                            "项目专有包的配置/规则由项目侧脚本按相对路径定位，不得登记索引"
                            % (group_key, code_name,
                               os.path.relpath(normalized_root, project_root_for_index), rel_path))
                        break

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
                    problems.append("索引 root_symlinks.entries.%s 的链接不存在（请运行 core-init）：%s"
                                    % (logical_name, link_rel))
                elif not os.path.islink(link_abs):
                    problems.append("索引 root_symlinks.entries.%s 的链接路径不是符号链接：%s"
                                    % (logical_name, link_rel))

        # 13. 索引落盘存在性（已生效包范围内）
        problems.extend(check_index_targets(index, packs, os.path.dirname(codebuddy_dir)))

    if problems:
        print("[不一致] 发现 %d 项：" % len(problems))
        for item in problems:
            print("  - %s" % item)
        return 1

    # 按 location 分组展示：真正决定扫描根形态的是 location，default 只表示「随引擎分发」
    engine_packs = sorted(name for name, meta in (packs or {}).items()
                          if meta.get("location") == "engine")
    lib_packs = sorted(name for name, meta in (packs or {}).items()
                       if meta.get("location") == "lib")
    project_packs = sorted(name for name, meta in (packs or {}).items()
                           if meta.get("location") == "project")
    print("[一致] 包 %d 个（engine：%s；lib：%s；project：%s），组件与索引路径均合规。"
          % (len(packs or {}), "、".join(engine_packs) or "无",
             "、".join(lib_packs) or "无", "、".join(project_packs) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
