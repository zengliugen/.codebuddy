#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目配置初始化脚本（core-init 技能）。

pack-ref-ok: cmd-script-writing —— 注释中说明生成内容遵循的 cmd 脚本书写规范，属编码约定引用，不调用该技能。

目标：新项目拉取 `.codebuddy` 引擎（submodule 或复制）后，本脚本读取引擎侧的
配置注册表 `.codebuddy/project.index.json`，据此在项目根下创建项目侧配置目录
`.codebuddy.project/` 的**全部占位骨架**（结构完整、值留占位），使各技能首次运行
时能定位到配置文件并按「缺失即报错」提示用户填写。

设计原则：
- **技能零项目值**：脚本自身不含任何项目相关内容，全部路径与骨架均来自索引。
- **幂等保护**：目标文件已存在时**跳过不覆盖**，避免抹掉用户已填写的内容。
- **索引为唯一事实来源**：索引缺失、损坏或缺少必需键时报错退出（退出码 3）。

用法：
  python init_project_config.py                # 生成占位骨架（默认）
  python init_project_config.py --force        # 覆盖已存在文件（谨慎）
  python init_project_config.py --json         # 结构化输出创建清单

退出码：
  0 —— 成功（含全部已存在而跳过）
  1 —— 执行错误（如无写权限）
  3 —— 索引缺失、损坏或缺少必需键
"""

import argparse
import json
import os
import subprocess
import sys


class InitError(RuntimeError):
    """索引不可用或执行失败时抛出；由入口转为明确的错误退出。"""


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


def find_codebuddy_dir(start):
    """自 start 向上查找含 `.codebuddy` 子目录的目录，返回该 .codebuddy 的绝对路径；找不到返回 None。

    项目根即 `.codebuddy` 的父目录；脚本通常从项目根或其子目录运行。
    """
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_index(codebuddy_dir):
    """读取并校验索引注册表；缺失、损坏或缺少必需键时抛出 InitError。"""
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise InitError(
            "未找到配置索引：%s\n"
            "       该索引由 .codebuddy 引擎随包提供；若缺失，请确认引擎包完整或版本匹配。" % index_path
        )
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise InitError("配置索引读取失败（%s）：%s" % (error, index_path))
    if not isinstance(index, dict):
        raise InitError("配置索引顶层必须是 JSON 对象：%s" % index_path)
    # 必需键：项目配置根 + files（骨架来源）
    if not index.get("project_config_root"):
        raise InitError("配置索引缺少键 `project_config_root`：%s" % index_path)
    if not isinstance(index.get("files"), dict) or not index["files"]:
        raise InitError("配置索引缺少非空对象键 `files`：%s" % index_path)
    return index, index_path


def render_markdown_skeleton(entry):
    """按 `template_outline` 生成 Markdown 占位骨架。

    每个章节标题后追加占位说明，提示填写；文件头加统一的外置说明。
    """
    outline = entry.get("template_outline")
    if not isinstance(outline, list) or not outline:
        raise InitError("Markdown 配置项缺少非空 `template_outline`")
    lines = [
        "> **本文件为项目侧配置骨架**（由 core-init 生成）。",
        "> 请按目标项目实际情况填写各处 `<填写说明>` 占位；填写完成前相关技能可能报错（配置缺失即报错）。",
        "",
    ]
    for item in outline:
        text = str(item)
        lines.append(text)
        # 顶级标题不加占位（避免与正文混淆），其余章节追加占位
        if not text.startswith("# "):
            lines.append("")
            lines.append("<填写说明：按目标项目实际情况补充本节内容>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def pack_install_set(project_root, codebuddy_dir, pack_arg, minimal):
    """解析本次运行生效的包集合：已装可选包 + 默认包。

    优先级：
    - 已有项目侧 packs.json → 以记录为准（幂等：重复运行不改变已选装包）；
    - 首次运行 → 按 --pack / --minimal 决定，并写回 packs.json。

    返回 (可选包名集合, 全部生效包名集合, 是否首次创建状态)。
    未装任何可选包时可选集合为空，仅有默认包。
    """
    packs, _err = load_engine_packs(codebuddy_dir)
    defaults = set(name for name, meta in packs.items() if (meta or {}).get("default"))
    installed, created = setup_pack_state(project_root, pack_arg, minimal)
    return set(installed), defaults | set(installed), created


def pack_of_path(rel):
    """从索引路径中解析所属包名。

    路径约定为 `.codebuddy.project/<configs|caches>/<类别>/<pack>/<组件>/...`，
    其中 <类别> 为 skills / rules / agents。非该结构（如根级通用目录
    `.codebuddy.project/caches/.vcs-lock`）返回空串，表示不按包过滤。
    """
    parts = rel.replace("\\", "/").split("/")
    for index, segment in enumerate(parts):
        if segment in ("skills", "rules", "agents") and index + 2 < len(parts):
            return parts[index + 1]
    return ""


def filter_by_packs(entries, active_packs):
    """按生效包集合过滤 (名称, 相对路径, 其余...) 条目，返回 (保留, 跳过)。

    路径无法归属任何包的条目一律保留（通用配置，如根级锁目录）。
    """
    kept, skipped = [], []
    for item in entries:
        rel = item[1]
        pack = pack_of_path(rel)
        if pack and pack not in active_packs:
            skipped.append(item)
        else:
            kept.append(item)
    return kept, skipped


def build_targets(index, project_root, active_packs=None):
    """由索引构造待生成文件清单：[(逻辑名, 绝对路径, 格式, 索引项)]。

    同时登记 `files`（config / 数据文件）与 `rule_shells`（项目事实正文）。
    active_packs 非空时，仅保留属于该集合（或无法归属包）的条目——
    未安装的可选包不再生成项目侧配置骨架。
    """
    targets = []
    for group_key in ("files", "rule_shells"):
        group = index.get(group_key) or {}
        for code_name, entry in group.items():
            if not isinstance(entry, dict) or not entry.get("path"):
                raise InitError("索引 `%s.%s` 缺少 `path`" % (group_key, code_name))
            rel = entry["path"]
            if os.path.isabs(rel):
                raise InitError("索引 `%s.%s.path` 必须为相对路径：%s" % (group_key, code_name, rel))
            fmt = entry.get("format", "json")
            abs_path = os.path.normpath(os.path.join(project_root, rel))
            targets.append((code_name, abs_path, fmt, entry, rel))
    if active_packs is not None:
        kept, _skipped = filter_by_packs(targets, active_packs)
        targets = kept
    return [(name, abs_path, fmt, entry) for name, abs_path, fmt, entry, _rel in targets]


def write_payload(fmt, entry):
    """按格式渲染待写入内容文本。"""
    if fmt == "json":
        if not isinstance(entry.get("template"), (dict, list)):
            raise InitError("JSON 配置项缺少 `template`")
        return json.dumps(entry["template"], ensure_ascii=False, indent=2) + "\n"
    if fmt == "markdown":
        return render_markdown_skeleton(entry)
    raise InitError("不支持的格式 `%s`" % fmt)


def build_artifact_dirs(index, project_root, active_packs=None):
    """由索引 `artifacts.dirs` 构造产物目录清单：[(逻辑名, 绝对路径)]。

    产物目录仅创建空目录（供脚本落盘），不入库。
    active_packs 非空时，未安装包的产物目录不创建。
    """
    dirs = (index.get("artifacts") or {}).get("dirs") or {}
    entries = []
    for logical_name, rel in dirs.items():
        if not isinstance(rel, str) or not rel:
            raise InitError("索引 `artifacts.dirs.%s` 值非法" % logical_name)
        if os.path.isabs(rel):
            raise InitError("索引 `artifacts.dirs.%s` 必须为相对路径：%s" % (logical_name, rel))
        entries.append((logical_name, rel))
    if active_packs is not None:
        kept, _skipped = filter_by_packs(entries, active_packs)
        entries = kept
    return [(name, os.path.normpath(os.path.join(project_root, rel))) for name, rel in entries]


def build_gitignore_content():
    """生成 `.codebuddy.project/.gitignore` 内容。

    包含两部分：
    - 忽略 `caches/` 运行时产物根目录（不入库）；
    - **反选 `configs/`**：项目根 .gitignore 可能含泛化的 `configs/` 规则
      （如 Python 项目忽略运行时用户配置），会把项目侧的入库配置一并忽略，
      故在此显式反选恢复（详见下方注释）。
    """
    return """# ============================================================
#  项目侧配置目录（.codebuddy.project）忽略规则
#
#  caches/ 为运行时产物根目录（不持久化的临时结果：各技能 check_logs、
#  .cache、.vcs-lock 等），由脚本执行生成，不入库；
#  产物目录清单见 .codebuddy/project.index.json 的 artifacts.dirs。
#  configs/、store/、docs/ 为入库内容，不在此忽略。
# ============================================================

# 仓库根 .gitignore 的 configs/ 会匹配本项目侧 configs/ 目录（Python 运行时用户配置），
# 此处反选恢复：项目侧 configs 为入库配置，必须随项目共享。
# 两行缺一不可——目录级忽略（configs/）下，只写 !configs/ 无法恢复深层文件，
# 须用 !configs/** 才能让 configs/skills/<pack>/... 等嵌套内容正常入库。
!configs/
!configs/**

# docs/ 存放技能产出的项目文档（如 devflow 的能力设计/计划/测试文档），必须随项目入库。
# 与 configs/ 同理反选：不少仓库根有泛化的 docs/ 忽略规则（站点构建产物、临时笔记等），
# 会连带忽略此处，导致文档静默不入库。同样两行缺一不可。
!docs/
!docs/**

# 运行时产物根目录（整体忽略）
caches/

# 系统/编辑器临时文件
.DS_Store
Thumbs.db
"""


def build_cleanup_cmd_content():
    """生成 `.codebuddy.project/cleanup-caches.cmd` 薄入口内容（调用引擎侧清理工具）。

    遵循 cmd-script-writing 规范：含中文的行行尾补 ASCII 空格（规避 chcp 65001 下
    CMD 把后续内容误判为命令）；行尾为 CRLF（由写入方按 .cmd 特判，LF 会撕裂语句）。
    """
    lines = [
        "@echo off",
        "chcp 65001 > nul",
        "setlocal EnableDelayedExpansion",
        "",
        "rem ============================================================ ",
        "rem  清理项目侧运行时缓存目录（caches/ 下的 check_logs / .cache / .vcs-lock 等）。 ",
        "rem ",
        "rem  本脚本为薄入口：实际清理逻辑由引擎侧通用工具 ",
        "rem  （.codebuddy/scripts/cleanup_artifacts.py）承担，待清理目录清单 ",
        "rem  由 .codebuddy/project.index.json 的 artifacts.dirs 驱动， ",
        "rem  不硬编码任何技能名或路径。 ",
        "rem ",
        "rem  用法： ",
        "rem    cleanup-caches.cmd            交互确认后清理 ",
        "rem    cleanup-caches.cmd all        跳过确认直接清理 ",
        "rem ============================================================ ",
        "",
        "rem 定位引擎侧清理工具（相对本脚本：<项目根>/.codebuddy.project/ -> <项目根>/.codebuddy/scripts/） ",
        "set \"BASE=%~dp0\"",
        "rem 去除脚本路径末尾的反斜杠。 ",
        "if \"%BASE:~-1%\"==\"\\\" set \"BASE=%BASE:~0,-1%\"",
        "set \"CLEANUP_TOOL=%BASE%\\..\\.codebuddy\\scripts\\cleanup_artifacts.py\"",
        "",
        "if not exist \"%CLEANUP_TOOL%\" (",
        "    echo [错误] 未找到引擎侧清理工具：%CLEANUP_TOOL% ",
        "    echo        请确认 .codebuddy 引擎包完整。 ",
        "    pause",
        "    exit /b 1",
        ")",
        "",
        "rem 查找可用的 Python（python 优先，回退 py）。 ",
        "set \"PYEXE=\"",
        "where python >nul 2>&1",
        "if not errorlevel 1 set \"PYEXE=python\"",
        "if not defined PYEXE (",
        "    where py >nul 2>&1",
        "    if not errorlevel 1 set \"PYEXE=py\"",
        ")",
        "if not defined PYEXE (",
        "    echo [错误] 未找到 Python，请先安装 Python 3 并加入 PATH。 ",
        "    pause",
        "    exit /b 1",
        ")",
        "",
        "if /i \"%~1\"==\"all\" (",
        "    \"%PYEXE%\" \"%CLEANUP_TOOL%\" all",
        ") else (",
        "    \"%PYEXE%\" \"%CLEANUP_TOOL%\"",
        ")",
        "set \"RC=%ERRORLEVEL%\"",
        "",
        "echo.",
        "echo 提示：清理完成，按任意键关闭窗口。 ",
        "pause",
        "exit /b %RC%",
    ]
    return "\r\n".join(lines) + "\r\n"


def build_project_skills_readme_content():
    """生成 `.codebuddy.project/skills/README.md` 内容（组件落点与加载机制说明）。"""
    return """# 项目侧技能目录（.codebuddy.project/skills）

本目录存放**本项目独有的技能与 pack 链接**，随本项目仓库版本控制；`.codebuddy` 引擎（可 submodule 化、
多项目共享）不含本项目内容。

## 两类内容共存

```
.codebuddy.project/skills/
├── <pack>             # 引擎可选包的组件链接（由 pack_install.py 创建，勿手工增删）
└── project/           # ★项目专有技能（真实目录，随项目入库）
```

**`project` 与其他包同级并列**，区别仅在于它是真实目录（其他包是指向 `lib/` 的链接）。
规则与代理目录（`.codebuddy.project/rules/`、`.codebuddy.project/agents/`）结构完全一致。

## 如何被 CodeBuddy 加载

`.codebuddy/skills/` 是 CodeBuddy 的**内置技能扫描目录**。每个包经一个**目录软链接**挂载到该扫描目录下：

```
.codebuddy/skills/<pack>     ──软链接──▶  ../../.codebuddy.project/skills/<pack>
.codebuddy/skills/project    ──软链接──▶  ../../.codebuddy.project/skills/project
```

即本目录下的技能自动出现在 `.codebuddy/skills/<pack>/`，被 CodeBuddy 扫描并加载
（**实测：技能目录支持符号链接**）。新增/修改技能后新开会话生效。

## 创建项目专有技能

1. 建技能目录：`.codebuddy.project/skills/project/<技能名>/`
2. 写 `SKILL.md`（frontmatter 含 `name`、`description`）。
3. **无需其他操作**——`.codebuddy/skills/project` 链接已存在，CodeBuddy 自动扫描；新开会话即可见。

## 跨机器注意事项

- **git 配置**：克隆者需 `git config core.symlinks true`（Windows 默认 `false`）。若为 `false`，
  克隆出来是一个内容为路径字符串的普通文件；此时运行 `.codebuddy/setup.cmd --force` 重建链接
  （安装器会按实际文件类型移除该占位物后重建，不会因「不是目录」而失败）。
- **创建链接的权限**：Windows 需开启"开发者模式"或以管理员身份运行；`mklink /D` 失败时，
  初始化脚本会告警并给出手工命令。
- **平台**：macOS / Linux 原生支持符号链接，无额外要求。
- **链接目标用相对路径**（`../../.codebuddy.project/skills/<pack>`），保证跨机器有效。

## 与引擎的关系

本目录**不进入** `.codebuddy` 引擎库。可选包组件真实内容在引擎 `lib/<pack>/` 下，本目录只存
**指向它的链接**；`project/` 下是项目真实文件，与引擎完全解耦。
"""

def build_project_skills_targets(project_root):
    """构造项目专有技能目录骨架的待生成文件清单：[(绝对路径, 内容)]。

    - `.codebuddy.project/skills/README.md`：落点与加载机制说明；
    - `.codebuddy.project/skills/.gitkeep`：占位（保证空目录入库）。
    """
    base = os.path.normpath(os.path.join(project_root, ".codebuddy.project/skills"))
    return [
        (os.path.join(base, "README.md"), build_project_skills_readme_content()),
        (os.path.join(base, ".gitkeep"),
         "# 占位文件：保证空的本目录能入库。\n"
         "# 本目录下有两类内容：\n"
         "#   <pack>/     引擎可选包的组件链接（由 pack_install.py 创建，勿手工增删）\n"
         "#   project/    项目专有技能（真实目录，随项目入库）\n"
         "# 项目专有技能请放 .codebuddy.project/skills/project/<技能名>/SKILL.md，\n"
         "# 经 .codebuddy/skills/project 链接被加载。\n"),
    ]


def build_root_symlink_targets(index, project_root):
    """由索引 `root_symlinks` 构造根级软链接的待生成清单。

    返回 [(逻辑名, 链接绝对路径, 项目侧源文件绝对路径, 格式, 索引项)]。
    链接路径与源文件路径均须为相对路径（拒绝绝对路径，防索引污染）。
    """
    entries = (index.get("root_symlinks") or {}).get("entries") or {}
    result = []
    for code_name, entry in entries.items():
        if not isinstance(entry, dict):
            raise InitError("索引 `root_symlinks.entries.%s` 必须是对象" % code_name)
        link_rel = entry.get("link")
        src_rel = entry.get("path")
        for label, rel in (("link", link_rel), ("path", src_rel)):
            if not isinstance(rel, str) or not rel:
                raise InitError("索引 `root_symlinks.entries.%s.%s` 缺失" % (code_name, label))
            if os.path.isabs(rel):
                raise InitError("索引 `root_symlinks.entries.%s.%s` 必须为相对路径：%s"
                                % (code_name, label, rel))
        link_abs = os.path.normpath(os.path.join(project_root, link_rel))
        src_abs = os.path.normpath(os.path.join(project_root, src_rel))
        fmt = entry.get("format", "json")
        result.append((code_name, link_abs, src_abs, fmt, entry))
    return result


def ensure_file_symlink(link_abs, src_abs, force=False):
    """建立单个文件软链接 link_abs -> src_abs（相对路径目标）。

    返回 (状态, 说明)：状态为 `created` / `exists` / `failed`。
    Windows 用 `mklink`（不带 /D，文件链接）；类 Unix 用 `os.symlink`。
    链接目标优先取相对路径（相对于链接所在目录），保证跨机器有效。
    """
    if os.path.lexists(link_abs):
        if not force:
            return "exists", link_abs
        try:
            os.remove(link_abs)
        except OSError as error:
            return "failed", "移除已存在链接失败：%s（%s）" % (link_abs, error)

    os.makedirs(os.path.dirname(link_abs), exist_ok=True)
    target_rel = os.path.relpath(src_abs, os.path.dirname(link_abs))
    try:
        if os.name == "nt":
            import subprocess
            # mklink 是 cmd 内建命令，需经 cmd /c 调用；文件链接不带 /D：
            #   mklink <link> <target>（相对路径以 cwd 为基准，故 cwd 设在链接所在目录）
            result = subprocess.run(
                ["cmd", "/c", "mklink", os.path.basename(link_abs), target_rel],
                cwd=os.path.dirname(link_abs),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                return "failed", (result.stderr or result.stdout or "").strip()
        else:
            os.symlink(target_rel, link_abs)
    except OSError as error:
        return "failed", str(error)
    return "created", link_abs


def readme_content(project_config_root):
    """生成 `.codebuddy.project/README.md` 内容（技能零项目值，通用说明）。"""
    return """# 项目侧配置目录（{root}）

本目录存放**与具体项目绑定**的全部内容，与 `.codebuddy` 引擎目录分离：引擎可整体迁移
（如以 git submodule 在多项目共享），本目录则随当前项目独立维护。

## 目录结构

```
{root}/
├── configs/            # 配置（入库）：settings.json、skills/<技能>/、rules/<规则>/ 等
├── caches/             # 运行时产物（不入库）：各技能 check_logs/、.cache/、.vcs-lock/ 等
├── store/              # 持久化项目结果（入库）：需长期保留的运行结果
├── docs/               # 技能产出的项目文档（入库）：<pack>/ 如 devflow 的能力文档
├── skills/             # 技能目录（入库）：<pack>/ 可选包链接，project/ 项目专有技能
├── README.md
├── .gitignore          # 忽略 caches/ 与系统临时文件
└── cleanup-caches.cmd  # 缓存清理入口（薄入口，调用引擎侧清理工具）
```

四类内容的边界约定：

| 子目录 | 语义 | 是否入库 | 可否删除 |
|--------|------|---------|---------|
| `configs/` | 与项目绑定的配置 | 是 | 删除后技能按「配置缺失即报错」 |
| `caches/` | 运行时生成、**不持久化**的临时结果 | 否（整体忽略） | 随时可删，可重新生成 |
| `store/` | 运行时生成、需**持久化保留**的项目结果 | 是 | 删除即丢失，需谨慎 |
| `docs/` | 技能产出的**项目文档**（如 devflow 的能力设计/计划/测试文档） | 是 | 删除即丢失；卸载对应包后需手工清理 |

**约定**：后续所有运行时生成的、不持久化的临时结果一律放 `caches/`，不得散落到其他目录。

## 文件从何而来

- 本目录的全部配置由 `core-init` 技能依据 `.codebuddy/project.index.json`
  （引擎侧的配置注册表）生成占位骨架。
- **占位值（`<...>`）须按本项目实际情况填写**；填写完成前，对应技能会按
  「配置缺失即报错」的约定明确报错并提示缺失项（不静默使用默认值）。
- 已存在的文件不会被初始化脚本覆盖（幂等保护），可安全重复运行。

## 与引擎的对应关系

`.codebuddy/skills/<技能>/a.json` 的项目侧对应位置为
`{root}/configs/skills/<pack>/<技能>/a.json`（相对路径镜像，含包层）；规则项目事实正文同理位于
`{root}/configs/rules/...`。定位逻辑由各技能脚本经 `.codebuddy/project.index.json` 解析。

## 运行时产物目录（caches/）

脚本执行过程中生成的产物（各技能 `check_logs/`、`.cache/`、`.vcs-lock/` 等）统一落在
`caches/` 下（产物清单见索引 `artifacts.dirs`），由本目录 `.gitignore` 整体忽略、不入库。
清理用本目录的 `cleanup-caches.cmd`（薄入口，调用引擎侧 `.codebuddy/scripts/cleanup_artifacts.py`）。

## 项目专有技能

项目专有技能放在本目录的 `skills/project/<技能名>/SKILL.md`（随项目入库），
经软链接 `.codebuddy/skills/project` 被 CodeBuddy 自动加载（详见 `skills/README.md`）。
这样与 `.codebuddy` 引擎解耦：引擎可 submodule 化、多项目共享，项目专有内容只随本仓库版本控制、不进入引擎。

## 维护约定

- `configs/` 与 `store/` **入库**（随项目版本控制），`caches/` **不入库**；不含敏感信息
  （凭据等机器级配置保留在 `.codebuddy` 根的 `models.json` / `settings.local.json`，已被忽略）。
- 修改引擎侧索引（新增配置项或产物目录）后，可重新运行 `core-init` 补齐缺失内容。
""".format(root=project_config_root)


def build_store_targets(project_root, project_config_root):
    """构造持久化项目结果目录（store/）骨架的待生成文件清单：[(绝对路径, 内容)]。

    store/ 入库：存放运行时生成但需持久化保留的项目结果；临时产物一律放 caches/。
    """
    base = os.path.normpath(os.path.join(project_root, project_config_root, "store"))
    readme = """# 持久化项目结果目录（store/）

本目录存放**运行时生成但需要持久化保留**的项目结果内容，随项目仓库版本控制。

## 与 caches/ 的边界

| 目录 | 语义 | 是否入库 | 可否删除 |
|------|------|---------|---------|
| `../caches/` | 运行时临时产物（不持久化） | 否（整体忽略） | 随时可删，可重新生成 |
| `store/`（本目录） | 持久化项目结果 | 是 | 删除即丢失，需谨慎 |

## 约定

- 后续所有「运行时生成但不持久化」的结果一律放 `../caches/`，不要放本目录。
- 放入本目录的内容按子目录组织，并在子目录内说明用途与生成来源。
- 本目录由 `core-init` 技能初始化创建；初始化只建骨架，不写入任何项目值。
"""
    gitkeep = ("# 占位文件：保证空的 store/ 目录能入库。\n"
               "# 本目录存放需持久化保留的项目结果（入库）；运行时临时产物请放 caches/（不入库）。\n")
    return [
        (os.path.join(base, "README.md"), readme),
        (os.path.join(base, ".gitkeep"), gitkeep),
    ]


def setup_pack_state(project_root, pack_arg, minimal):
    """按 --pack / --minimal 决定可选包安装集合，并写入项目侧 packs.json（仅 --setup）。

    返回 (已装包名列表, 是否新建)。已存在 configs/packs.json 时保持原选择，不覆盖。
    """
    state_path = os.path.normpath(os.path.join(project_root, ".codebuddy.project", "configs", "packs.json"))
    if os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            installed = data.get("installed") or []
            if not isinstance(installed, list):
                raise InitError("packs.json 的 installed 必须是数组：%s" % state_path)
            return [str(x) for x in installed], False
        except (OSError, ValueError) as error:
            raise InitError("读取已有安装状态失败：%s（%s）" % (state_path, error))
    installed = []
    if pack_arg and not minimal:
        installed = [name.strip() for name in pack_arg.split(",") if name.strip()]
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"version": 1, "installed": sorted(set(installed))}, handle,
                  ensure_ascii=False, indent=2)
        handle.write("\n")
    return sorted(set(installed)), True


def build_project_pack_targets(project_root):
    """构造项目专有包（project）的内容目录骨架：[(绝对路径, 内容)]。

    项目专有包与其他包同构：内容位于 .codebuddy.project/<类型>/project/ 下，
    由引擎扫描根的 .codebuddy/<类型>/project 链接加载；此处只建空目录与占位文件。
    """
    base = os.path.normpath(os.path.join(project_root, ".codebuddy.project"))
    targets = []
    labels = {
        "rules": "规则（<规则名>/RULE.mdc）",
        "skills": "技能（<技能名>/SKILL.md）",
        "agents": "代理（<代理名>.md）",
    }
    for comp_type, label in labels.items():
        targets.append((
            os.path.join(base, comp_type, "project", ".gitkeep"),
            "# 占位文件：保证空的 %s/project/ 目录能入库。\n"
            "# 项目专有%s直接放在本目录下，经 .codebuddy/%s/project 链接被加载。\n"
            % (comp_type, label, comp_type),
        ))
    return targets


def run_pack_installer(codebuddy_dir, project_root, args):
    """调用引擎侧 pack_install.py 物化可选包；返回 (退出码, 输出文本)。"""
    installer = os.path.join(codebuddy_dir, "scripts", "pack_install.py")
    if not os.path.isfile(installer):
        return 3, "未找到引擎侧包安装器：%s" % installer
    command = [sys.executable, installer, "--project-root", project_root]
    if args.force:
        command.extend(["verify", "--repair"])
    else:
        command.extend(["verify", "--repair"])
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def configure_git_hooks(codebuddy_dir):
    """把引擎的 core.hooksPath 指向入库的 hooks/ 目录，使提交前校验生效。

    钩子文件随引擎仓库入库（hooks/pre-commit），但 git 的钩子目录默认在 .git/ 下、
    不随仓库分发；用 core.hooksPath 指向版本控制内的目录才能跨机器生效。

    submodule 场景下 .codebuddy/.git 是文件而非目录，git 仍能正常执行 config。

    返回 (状态, 说明)：状态取 created（已配置）/ exists（已是目标值）/ failed（失败）。
    """
    hooks_rel = "hooks"
    hooks_abs = os.path.join(codebuddy_dir, hooks_rel)
    if not os.path.isdir(hooks_abs):
        return "failed", "引擎内缺少 hooks 目录：%s" % hooks_abs

    hook_file = os.path.join(hooks_abs, "pre-commit")
    if not os.path.isfile(hook_file):
        return "failed", "引擎内缺少 hooks/pre-commit"

    # 类 Unix 需要执行位；Windows 下 git 通过 sh 执行，无执行位也可
    if os.name != "nt":
        try:
            os.chmod(hook_file, 0o755)
        except OSError:
            pass

    # 读取现有配置，已在目标值则跳过（幂等）
    current = subprocess.run(
        ["git", "-C", codebuddy_dir, "config", "--get", "core.hooksPath"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if current.returncode == 0 and (current.stdout or "").strip() == hooks_rel:
        return "exists", hooks_rel

    result = subprocess.run(
        ["git", "-C", codebuddy_dir, "config", "core.hooksPath", hooks_rel],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return "failed", (result.stderr or "").strip() or "git config 执行失败"
    return "created", hooks_rel


def load_engine_packs(codebuddy_dir):
    """读取引擎包注册表 lib/packs.json；缺失或损坏时返回空表与原因，不阻断状态查询。"""
    path = os.path.join(codebuddy_dir, "lib", "packs.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        return {}, "包注册表不可读：%s（%s）" % (path, error)
    packs = data.get("packs")
    if not isinstance(packs, dict):
        return {}, "包注册表缺少 packs 对象：%s" % path
    return packs, None


def read_installed_packs(project_root):
    """读取项目侧已记入安装状态的包名列表；文件缺失或损坏时返回空列表。"""
    path = os.path.normpath(os.path.join(project_root, ".codebuddy.project", "configs", "packs.json"))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    installed = data.get("installed")
    return [str(name) for name in installed] if isinstance(installed, list) else []


def probe_pack_drift(codebuddy_dir, project_root):
    """调用引擎侧 pack_install.py status 探测链接漂移；返回 (是否一致, 输出文本)。

    一致为 True；存在漂移为 False；无法探测为 None。
    """
    installer = os.path.join(codebuddy_dir, "scripts", "pack_install.py")
    if not os.path.isfile(installer):
        return None, "未找到包安装器：%s" % installer
    result = subprocess.run(
        [sys.executable, installer, "--project-root", project_root, "status"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, output


def collect_orphans(index, project_root, packs, installed):
    """检测不属于任何已装包的项目侧配置与产物目录（卸载包后的残留）。

    判定依据：索引路径中的 pack 段（见 pack_of_path）不在生效包集合内，
    且该路径在磁盘上真实存在。返回 [{kind, name, path, pack}]，按路径排序。

    只读取磁盘现状，不删除任何内容——清理须由用户确认后另行执行。
    """
    active = set(name for name, meta in packs.items() if (meta or {}).get("default"))
    active |= set(installed)
    found = []
    for group_key in ("files", "rule_shells"):
        for code_name, entry in (index.get(group_key) or {}).items():
            rel = (entry or {}).get("path")
            if not rel:
                continue
            pack = pack_of_path(rel)
            if not pack or pack in active:
                continue
            abs_path = os.path.normpath(os.path.join(project_root, rel))
            if os.path.exists(abs_path):
                found.append({"kind": group_key, "name": code_name, "path": rel, "pack": pack})
    for logical_name, rel in ((index.get("artifacts") or {}).get("dirs") or {}).items():
        if not isinstance(rel, str) or not rel:
            continue
        pack = pack_of_path(rel)
        if not pack or pack in active:
            continue
        abs_path = os.path.normpath(os.path.join(project_root, rel))
        if os.path.isdir(abs_path):
            found.append({"kind": "artifacts", "name": logical_name, "path": rel, "pack": pack})
    found.sort(key=lambda item: item["path"])
    return found


def prune_orphans(project_root, orphans):
    """删除指定孤儿条目（仅删文件与空目录，不递归删除非空目录）。

    返回 (已删除路径列表, 失败列表)。删除产物目录时仅在其为空时移除，
    避免误删用户手工放入的内容。
    """
    removed, failed = [], []
    for item in orphans:
        abs_path = os.path.normpath(os.path.join(project_root, item["path"]))
        try:
            if item["kind"] == "artifacts":
                if os.path.isdir(abs_path) and not os.listdir(abs_path):
                    os.rmdir(abs_path)
                    removed.append(item["path"])
                else:
                    failed.append((item["path"], "目录非空，未删除"))
                continue
            os.remove(abs_path)
            removed.append(item["path"])
            # 顺手清理因此变空的上级目录（最多上溯 3 层，止于 configs/caches 根）
            parent = os.path.dirname(abs_path)
            for _ in range(3):
                if not os.path.isdir(parent) or os.listdir(parent):
                    break
                if os.path.basename(parent) in ("configs", "caches"):
                    break
                os.rmdir(parent)
                parent = os.path.dirname(parent)
        except OSError as error:
            failed.append((item["path"], str(error)))
    return removed, failed


def collect_status(index, project_root, codebuddy_dir):
    """汇总初始化与包安装状态，作为技能询问用户「接下来要做什么」的依据。

    只读取磁盘现状，不创建也不修改任何文件，可安全重复调用。
    """
    config_root = index["project_config_root"]
    config_dir = os.path.normpath(os.path.join(project_root, config_root))
    initialized = os.path.isdir(config_dir)

    # 先取安装状态：缺失判定只在「已装包」范围内进行，
    # 未装包的索引条目既不算缺失（不该生成），也不算孤儿（磁盘上本来就没有）。
    packs, packs_error = load_engine_packs(codebuddy_dir)
    installed = read_installed_packs(project_root)
    active_packs = set(name for name, meta in packs.items() if (meta or {}).get("default")) | set(installed)

    missing_configs = []
    for group_key in ("files", "rule_shells"):
        for code_name, entry in (index.get(group_key) or {}).items():
            rel = (entry or {}).get("path")
            if not rel:
                continue
            pack = pack_of_path(rel)
            if pack and pack not in active_packs:
                continue
            if not os.path.isfile(os.path.normpath(os.path.join(project_root, rel))):
                missing_configs.append({"group": group_key, "name": code_name, "path": rel})

    missing_dirs = []
    for logical_name, rel in ((index.get("artifacts") or {}).get("dirs") or {}).items():
        if not isinstance(rel, str) or not rel:
            continue
        pack = pack_of_path(rel)
        if pack and pack not in active_packs:
            continue
        if not os.path.isdir(os.path.normpath(os.path.join(project_root, rel))):
            missing_dirs.append({"name": logical_name, "path": rel})

    optional = sorted(name for name, meta in packs.items() if not (meta or {}).get("default"))
    available = [name for name in optional if name not in installed]
    unknown = [name for name in installed if name not in packs]
    drift_ok, drift_text = probe_pack_drift(codebuddy_dir, project_root)
    orphans = collect_orphans(index, project_root, packs, installed)

    # 依据现状给出候选动作，供技能用 AskUserQuestion 呈现（键名跨项目稳定）
    actions = []
    if not initialized:
        actions.append("init_skeleton")
    if missing_configs or missing_dirs or not initialized:
        actions.append("fill_configs")
    actions.append("list_packs")
    if available:
        actions.append("install_packs")
    if installed:
        actions.append("remove_packs")
    if drift_ok is False or unknown:
        actions.append("verify_packs")
    if orphans:
        actions.append("prune_orphans")

    return {
        "project_root": project_root,
        "project_config_root": config_root,
        "initialized": initialized,
        "missing_configs": missing_configs,
        "missing_dirs": missing_dirs,
        "packs": {
            "installed": sorted(installed),
            "available": available,
            "unknown": sorted(unknown),
            "registry_error": packs_error,
        },
        "links": {"consistent": drift_ok, "detail": drift_text},
        "orphans": orphans,
        "actions": actions,
    }


def report_status(status, as_json):
    """输出状态摘要；as_json 为真时输出结构化 JSON，否则输出人类可读文本。"""
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    print("[信息] 项目根：%s" % status["project_root"])
    print("[状态] 项目配置目录：%s" % ("已初始化" if status["initialized"] else "未初始化"))
    if status["missing_configs"]:
        print("[状态] 缺失配置 %d 项（需补生成或填写）：" % len(status["missing_configs"]))
        for item in status["missing_configs"][:10]:
            print("  - %s/%s" % (item["group"], item["path"]))
    else:
        print("[状态] 配置骨架：齐全")
    if status["missing_dirs"]:
        print("[状态] 缺失产物目录 %d 项" % len(status["missing_dirs"]))
        for item in status["missing_dirs"][:10]:
            print("  - %s" % item["path"])

    packs = status["packs"]
    if packs["registry_error"]:
        print("[警告] %s" % packs["registry_error"])
    print("[可选包] 已装：%s" % (", ".join(packs["installed"]) or "（无）"))
    print("[可选包] 未装：%s" % (", ".join(packs["available"]) or "（无）"))
    if packs["unknown"]:
        print("[警告] 安装状态含注册表未登记的包：%s" % ", ".join(packs["unknown"]))

    consistent = status["links"]["consistent"]
    if consistent is True:
        print("[链接] 一致：安装状态与实际链接匹配")
    else:
        print("[链接] %s" % (status["links"]["detail"] or "无法探测"))

    orphans = status.get("orphans") or []
    if orphans:
        by_pack = {}
        for item in orphans:
            by_pack.setdefault(item["pack"], []).append(item)
        print("[孤儿] 存在 %d 项不属于已装包的残留（卸载包后的遗留）：" % len(orphans))
        for pack in sorted(by_pack):
            print("  · 包 %s（%d 项）" % (pack, len(by_pack[pack])))
            for item in by_pack[pack][:10]:
                print("    - %s" % item["path"])
            if len(by_pack[pack]) > 10:
                print("    …另有 %d 项未显示" % (len(by_pack[pack]) - 10))
        print("  清理方式：确认后运行 setup.cmd --prune-orphans，或手工删除上述路径")

    print("[候选动作] %s" % ", ".join(status["actions"]))
    return 0


def main():
    init_stdout()
    parser = argparse.ArgumentParser(
        description="依据 .codebuddy 引擎的配置索引，创建项目侧配置目录的占位骨架"
    )
    parser.add_argument("--force", action="store_true",
                        help="覆盖已存在的文件（默认跳过不覆盖）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出创建清单")
    parser.add_argument("--setup", action="store_true",
                        help="一键配置模式：生成骨架后建立扫描根 pack 链接并物化可选包")
    parser.add_argument("--pack", default="",
                        help="可选包名，逗号分隔（仅 --setup 首次克隆时使用）")
    parser.add_argument("--minimal", action="store_true",
                        help="只保留默认包，不安装任何可选包（仅 --setup）")
    parser.add_argument("--status", action="store_true",
                        help="只检测现状（初始化状态、缺失配置、可选包安装与链接漂移），不写盘")
    parser.add_argument("--prune-orphans", action="store_true",
                        help="删除不属于已装包的残留配置与空产物目录（卸载包后的清理，仅删空目录）")
    args = parser.parse_args()

    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        sys.stderr.write(
            "[错误] 未找到 .codebuddy 目录。请在含 .codebuddy 的项目根目录或其子目录下运行。\n")
        return 3

    try:
        index, index_path = load_index(codebuddy_dir)
    except InitError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    project_root = os.path.dirname(codebuddy_dir)

    # 只读状态探测：供技能据现状询问用户意图，不创建也不修改任何文件
    if args.status:
        return report_status(collect_status(index, project_root, codebuddy_dir), args.json)

    # 孤儿清理：仅删除不属于已装包的残留（由 --status 报告后经用户确认触发）
    if args.prune_orphans:
        packs, _err = load_engine_packs(codebuddy_dir)
        orphans = collect_orphans(index, project_root, packs, read_installed_packs(project_root))
        if not orphans:
            print("[孤儿] 未发现不属于已装包的残留，无需清理。")
            return 0
        removed, failed = prune_orphans(project_root, orphans)
        print("[孤儿] 已删除 %d 项：" % len(removed))
        for path in removed:
            print("  - %s" % path)
        if failed:
            print("[警告] %d 项未能删除：" % len(failed))
            for path, reason in failed:
                print("  ! %s（%s）" % (path, reason))
        return 0

    # 先确定生效的包集合（默认包 + 已装可选包），再据此过滤索引条目：
    # 未安装的包不生成项目侧配置骨架与产物目录。
    try:
        optional_installed, active_packs, state_created = pack_install_set(
            project_root, codebuddy_dir, args.pack, args.minimal)
    except InitError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    try:
        targets = build_targets(index, project_root, active_packs)
    except InitError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    created = []
    skipped = []
    created_dirs = []

    # 生成本目录 README（首个文件）
    readme_rel = index["project_config_root"]
    readme_path = os.path.normpath(os.path.join(project_root, readme_rel, "README.md"))
    readme_text = readme_content(readme_rel)

    all_files = [
        (None, readme_path, "markdown_text", readme_text),
        (None, os.path.normpath(os.path.join(project_root, readme_rel, ".gitignore")),
         "markdown_text", build_gitignore_content()),
        (None, os.path.normpath(os.path.join(project_root, readme_rel, "cleanup-caches.cmd")),
         "markdown_text", build_cleanup_cmd_content()),
    ]
    for code_name, abs_path, fmt, entry in targets:
        try:
            payload = write_payload(fmt, entry)
        except InitError as error:
            sys.stderr.write("[错误] %s（配置项 %s）\n" % (error, code_name))
            return 3
        all_files.append((code_name, abs_path, fmt, payload))

    # 项目专有技能目录骨架（.codebuddy.project/skills/）
    for abs_path, payload in build_project_skills_targets(project_root):
        all_files.append((None, abs_path, "markdown_text", payload))

    # 项目专有包内容骨架（.codebuddy.project/project/{rules,skills,agents}/）
    for abs_path, payload in build_project_pack_targets(project_root):
        all_files.append((None, abs_path, "markdown_text", payload))

    # 持久化项目结果目录骨架（store/，入库）
    for abs_path, payload in build_store_targets(project_root, readme_rel):
        all_files.append((None, abs_path, "markdown_text", payload))

    # 根级软链接的项目侧源文件骨架（如 .codebuddy.project/configs/settings.json）
    try:
        root_symlinks = build_root_symlink_targets(index, project_root)
    except InitError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3
    for code_name, link_abs, src_abs, fmt, entry in root_symlinks:
        try:
            payload = write_payload(fmt, entry)
        except InitError as error:
            sys.stderr.write("[错误] %s（配置项 %s）\n" % (error, code_name))
            return 3
        all_files.append((code_name, src_abs, fmt, payload))

    for code_name, abs_path, fmt, payload in all_files:
        if os.path.isfile(abs_path) and not args.force:
            skipped.append(abs_path)
            continue
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            # .cmd 需 CRLF 行尾（LF 会撕裂 CMD 语句）；其内容已内嵌 \r\n，关闭换行翻译
            newline = "" if abs_path.lower().endswith(".cmd") else "\n"
            with open(abs_path, "w", encoding="utf-8", newline=newline) as handle:
                handle.write(payload)
        except OSError as error:
            sys.stderr.write("[错误] 写入失败：%s（%s）\n" % (abs_path, error))
            return 1
        created.append(abs_path)

    # 创建运行时产物空目录（不入库，由项目侧 .gitignore 忽略）
    try:
        artifact_dirs = build_artifact_dirs(index, project_root, active_packs)
    except InitError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3
    for logical_name, abs_path in artifact_dirs:
        if os.path.isdir(abs_path):
            continue
        try:
            os.makedirs(abs_path, exist_ok=True)
        except OSError as error:
            sys.stderr.write("[错误] 创建产物目录失败：%s（%s）\n" % (abs_path, error))
            return 1
        created_dirs.append(abs_path)

    # 建立根级文件软链接（如 .codebuddy/settings.json -> ../.codebuddy.project/configs/settings.json）
    root_link_results = []
    for code_name, link_abs, src_abs, fmt, entry in root_symlinks:
        status, info = ensure_file_symlink(link_abs, src_abs, force=args.force)
        root_link_results.append((code_name, link_abs, src_abs, status, info))

    # 配置提交前校验钩子（core.hooksPath → 入库的 hooks/ 目录）。
    # 非 --setup 模式也执行：钩子是引擎自身的一致性保障，与是否首次安装无关。
    hook_status, hook_info = configure_git_hooks(codebuddy_dir)
    if hook_status == "failed":
        print("[警告] 提交前校验钩子未配置：%s" % hook_info)
        print("       引擎提交将不做一致性校验。可手工执行：")
        print("         git -C .codebuddy config core.hooksPath hooks")

    # --setup 模式：安装状态已在上文解析，此处只物化链接
    setup_report = None
    if args.setup:
        installed_packs = sorted(optional_installed)
        rc, output = run_pack_installer(codebuddy_dir, project_root, args)
        setup_report = {
            "state_created": state_created,
            "installed": installed_packs,
            "installer_exit_code": rc,
            "installer_output": output,
        }

    if args.json:
        print(json.dumps({
            "project_root": project_root,
            "project_config_root": readme_rel,
            "created": created,
            "created_dirs": created_dirs,
            "skipped": skipped,
            "root_symlinks": [
                {"name": n, "status": s, "link": os.path.relpath(l, project_root),
                 "source": os.path.relpath(src, project_root), "info": i}
                for n, l, src, s, i in root_link_results
            ],
            "setup": setup_report,
        }, ensure_ascii=False, indent=2))
        return 0

    print("[信息] 项目根：%s" % project_root)
    print("[信息] 项目配置目录：%s" % os.path.join(project_root, readme_rel))
    print()
    if created:
        print("[创建] %d 个文件：" % len(created))
        for path in created:
            print("  + %s" % os.path.relpath(path, project_root))
    if created_dirs:
        print("[创建] %d 个产物目录：" % len(created_dirs))
        for path in created_dirs:
            print("  + %s/" % os.path.relpath(path, project_root))
    if skipped:
        print("[跳过] %d 个已存在文件（未覆盖）：" % len(skipped))
        for path in skipped:
            print("  = %s" % os.path.relpath(path, project_root))
    print()

    # 根级文件软链接结果
    for code_name, link_abs, src_abs, status, info in root_link_results:
        rel_link = os.path.relpath(link_abs, project_root)
        rel_src = os.path.relpath(src_abs, project_root)
        if status == "created":
            print("[链接] 已创建：%s -> %s" % (rel_link, rel_src))
        elif status == "exists":
            print("[链接] 已存在（未改动）：%s" % rel_link)
        else:
            print("[警告] 软链接创建失败：%s（%s）" % (rel_link, info))
            print("       该文件将无法被 CodeBuddy 读取。请手工创建（Windows 需开发者模式/管理员）：")
            print("         cd .codebuddy && mklink %s %s"
                  % (os.path.basename(link_abs), os.path.relpath(src_abs, os.path.join(project_root, ".codebuddy"))))
            print("       （类 Unix： ln -s %s %s）"
                  % (os.path.relpath(src_abs, os.path.dirname(link_abs)), rel_link))

    print()
    if hook_status == "created":
        print("[钩子] 已配置提交前校验：core.hooksPath = %s" % hook_info)
    elif hook_status == "exists":
        print("[钩子] 提交前校验已配置：core.hooksPath = %s" % hook_info)

    print("下一步：按项目实际情况填写上述配置中的 `<...>` 占位值。")
    print("        未填写的配置在首次运行对应技能时会报错（配置缺失即报错）。")
    print("        项目专有内容放 .codebuddy.project/<类型>/project/ 下（经 .codebuddy/<类型>/project 链接自动加载）。")

    # --setup 结果摘要
    if setup_report is not None:
        print()
        if setup_report["state_created"]:
            print("[状态] 已创建 .codebuddy.project/configs/packs.json（首次配置）")
        installed = setup_report["installed"]
        print("[可选包] 安装状态：%s" % (", ".join(installed) or "（无，仅默认包）"))
        output = setup_report["installer_output"].strip()
        if output:
            for line in output.splitlines()[-10:]:
                print("  " + line)
        if setup_report["installer_exit_code"] != 0:
            print("[警告] 可选包物化未完全成功（退出码 %d），请检查上方输出"
                  % setup_report["installer_exit_code"])
            print("       可重试：python .codebuddy/scripts/pack_install.py verify --repair")

    return 0


if __name__ == "__main__":
    sys.exit(main())
