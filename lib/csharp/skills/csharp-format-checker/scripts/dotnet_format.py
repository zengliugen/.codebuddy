# -*- coding: utf-8 -*-
"""C# 代码格式检查/修复入口脚本（dotnet format + 项目根 .editorconfig）。

职责：
1. 定位项目根目录（自调用目录向上查找含 .editorconfig 的目录）。
2. 经索引 .codebuddy/project.index.json 的 format_checker.config 定位并读取项目侧配置（缺失时报错退出）。
3. 解析工作区（.slnx/.sln/.csproj，支持 --project 覆盖）。
4. 按配置的分组（默认 whitespace + style）与忽略目录执行 dotnet format：
   - check 模式追加 --verify-no-changes（只读，不修改源码）；
   - fix 模式直接落盘应用格式修改。
5. 将原始输出保存至项目侧产物目录（经索引 artifacts 定位的 check_logs/），并生成 .md 摘要报告。
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import random
import re
import subprocess
import sys

# 配置文件在索引注册表中的逻辑名（路径基准为项目根，由索引声明）
CONFIG_CODENAME = "format_checker.config"

# 配置文件中必需的键（缺失即报错，避免静默使用内置默认值导致「配置写了但没生效」）
REQUIRED_CONFIG_KEYS = ("workspace", "groups", "severity", "no_restore", "exclude_dirs", "changed_scope")


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


def _load_index(root):
    """读取并校验索引注册表，返回 (index_dict, index_path)。"""
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
    return index, index_path


def resolve_config_path(root):
    """经索引注册表解析格式检查配置路径（相对路径基准为项目根）。

    索引 `.codebuddy/project.index.json` 为跨项目共享的入库文件，只读
    `files[逻辑名].path`；路径必须是相对路径（拒绝绝对路径，防索引污染）。
    """
    index, index_path = _load_index(root)
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError("索引缺少配置项 `files.%s.path`：%s" % (CONFIG_CODENAME, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 `files.%s.path` 必须为相对路径（当前为绝对路径）：%s"
                          % (CONFIG_CODENAME, rel))
    return os.path.normpath(os.path.join(root, rel))


def resolve_artifact_dir(root, logical_name):
    """经索引 `artifacts.dirs` 解析运行时产物目录（相对路径基准为项目根），并确保目录存在。

    产物目录位于项目侧 `.codebuddy.project/`（不入库、不随引擎共享）；脚本不再写入技能目录。
    """
    index, index_path = _load_index(root)
    rel = (index.get("artifacts") or {}).get("dirs", {}).get(logical_name)
    if not isinstance(rel, str) or not rel:
        raise ConfigError("索引缺少产物目录项 `artifacts.dirs.%s`：%s" % (logical_name, index_path))
    if os.path.isabs(rel):
        raise ConfigError("索引 `artifacts.dirs.%s` 必须为相对路径（当前为绝对路径）：%s"
                          % (logical_name, rel))
    path = os.path.normpath(os.path.join(root, rel))
    os.makedirs(path, exist_ok=True)
    return path


def load_config(root, config_abs):
    """加载项目配置；缺失、损坏或缺少必需键时抛出 ConfigError。

    配置是格式检查范围的**唯一事实来源**：脚本不内置 `groups`/`exclude_dirs` 等默认值，
    也不自动生成模板，避免「配置未生效」被静默掩盖。
    """
    if not os.path.isfile(config_abs):
        raise ConfigError(
            "未找到格式检查配置：%s\n"
            "       请先按项目实际情况创建该配置（字段说明见 references/config-guide.md）。"
            % config_abs
        )

    try:
        with open(config_abs, "r", encoding="utf-8") as fp:
            config = json.load(fp)
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError("格式检查配置读取失败（%s）：%s" % (exc, config_abs))

    if not isinstance(config, dict):
        raise ConfigError("格式检查配置顶层必须是 JSON 对象：%s" % config_abs)

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigError(
            "格式检查配置缺少必需键：%s（%s）\n"
            "       配置为检查范围的唯一来源，请补齐后再运行。"
            % ("、".join(missing), config_abs)
        )
    return config

# csproj 中的源码条目：<Compile Include="Assets\...\X.cs" />
COMPILE_INCLUDE_RE = re.compile(r"<Compile\s+Include=\"([^\"]+)\"", re.IGNORECASE)

# 报告复用时效（秒）：与 csharp-code-review Agent 侧的「5 分钟内报告直接复用」保持一致
REPORT_REUSE_SECONDS = 300

# 恢复模式判断：输出命中以下关键字时，去掉 --no-restore 重试一次
RESTORE_ERROR_KEYWORDS = ("project.assets.json", "MSB1009", "MSB", "NU1")

# 诊断行匹配：形如 D:\...\file.cs(1,1): error IMPORTS: 说明 [D:\...\proj.csproj]
DIAG_RE = re.compile(r"(?P<path>.+?\.cs)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s+(?P<diag>[A-Za-z0-9]+):")


def find_project_root(start):
    """自 start 向上查找含 .editorconfig 的目录作为项目根，找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, ".editorconfig")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent



def detect_workspace(root, preferred):
    """探测工作区：优先配置值（或 --project），其次按 .slnx/.sln/.csproj 顺序自动探测。"""
    candidate = preferred or ""
    if candidate:
        abs_path = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
        if os.path.isfile(abs_path):
            return candidate, abs_path
    # 自动探测：slnx（Unity 6 生成）→ sln → 根级 csproj
    for pattern in ("*.slnx", "*.sln", "*.csproj"):
        hits = [name for name in os.listdir(root) if name.lower().endswith(pattern[1:])]
        if hits:
            hits.sort()
            rel = hits[0]
            return rel, os.path.join(root, rel)
    return None, None


def to_dotnet_path(path):
    """将路径统一为 dotnet format 可识别的相对路径（正斜杠分隔）。"""
    return path.replace(os.sep, "/").replace("\\", "/")


def normalize_repo_path(value):
    """路径归一化：反斜杠转正斜杠、去除 `./` 前缀（与 csharp-code-review 的 normalize 保持语义一致）。"""
    text = str(value).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def to_project_rel_path(repo_rel_path, git_root, root):
    """仓库根相对路径 → 项目根相对路径；不在项目根下时返回 None。

    git 返回的是**仓库根**相对路径（如 `<子目录>/<路径>/...`），而本技能与 csproj
    都以**项目根**为基准（如 `Assets/...`）。若不做该转换，路径去匹配工程映射表会全部失配，
    进而静默回退整仓检查（提速失效且难以察觉），故必须在此剥掉仓库前缀。
    """
    if not git_root:
        candidate = os.path.normpath(os.path.join(root, normalize_repo_path(repo_rel_path)))
    else:
        candidate = os.path.normpath(os.path.join(git_root, repo_rel_path.replace("/", os.sep)))
    try:
        rel = os.path.relpath(candidate, root)
    except ValueError:
        return None
    rel = normalize_repo_path(rel)
    if rel == ".." or rel.startswith("../"):
        return None
    return rel


def get_git_root(workdir):
    """返回 git 仓库根绝对路径；非 git 仓库或 git 命令不可用时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    path = (result.stdout or "").strip()
    return os.path.normpath(path) if path else None


def get_git_status(workdir):
    """解析 `git status --porcelain -z --untracked-files=all`，返回 [(xy, 仓库相对路径)]。

    -z 模式下重命名/复制会追加一个「源路径」token，需一并消费以对齐下标；
    解析逻辑与 csharp-code-review/scripts/collect_review_targets.py 的同名函数保持一致
    （此处复制而非跨技能 import，以保证本技能可独立迁移运行）。
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stdout or "").strip() or "git status 执行失败")
    tokens = [token for token in (result.stdout or "").split("\0") if token != ""]
    entries = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 3:
            continue
        xy = token[:2]
        path = token[3:]
        if xy[0] in ("R", "C"):
            index += 1
        entries.append((xy, normalize_repo_path(path)))
    return entries


def is_in_exclude_dirs(project_rel_path, exclude_dirs):
    """判断项目根相对路径是否位于任一忽略目录内（大小写不敏感的前缀匹配）。"""
    lowered = normalize_repo_path(project_rel_path).lower()
    for item in exclude_dirs:
        base = normalize_repo_path(item).lower().rstrip("/")
        if not base:
            continue
        if lowered == base or lowered.startswith(base + "/"):
            return True
    return False


def build_project_map(root):
    """构建「源文件相对路径 → csproj 名称列表」映射（键统一小写以便 Windows 大小写无关匹配）。

    仅扫描项目根下的 *.csproj（Unity 生成，逐文件列出 <Compile Include>，无通配符），
    因此可精确反查文件所属工程。一个源文件可能被多个工程引用（如 Editor/Runtime 双引用），
    此时全部保留。csproj 通常含 BOM，故以 utf-8-sig 读取。
    """
    project_map = {}
    project_files = sorted(name for name in os.listdir(root) if name.lower().endswith(".csproj"))
    for csproj_name in project_files:
        csproj_abs = os.path.join(root, csproj_name)
        try:
            with open(csproj_abs, "r", encoding="utf-8-sig", errors="replace") as handle:
                content = handle.read()
        except OSError as exc:
            print("[警告] 工程文件读取失败，已跳过：%s（%s）" % (csproj_name, exc))
            continue
        for include in COMPILE_INCLUDE_RE.findall(content):
            source_rel = normalize_repo_path(include)
            # 防御性剥离可能存在的上溯前缀（本仓库实测无此写法）
            while source_rel.startswith("../"):
                source_rel = source_rel[3:]
            key = source_rel.lower()
            owners = project_map.setdefault(key, [])
            if csproj_name not in owners:
                owners.append(csproj_name)
    return project_map


def map_changed_to_projects(changed_files, project_map):
    """把变更文件映射到工程。

    返回 (project_names, matched, unmapped)：
    - project_names：涉及的工程名（已排序；因可能多工程引用，数量可多于文件数）
    - matched：成功映射的变更文件
    - unmapped：不在任何工程内的文件（如 .codebuddy/ 下代码、尚未被 Unity 导入的新文件）
    """
    project_names = set()
    matched = []
    unmapped = []
    for path in changed_files:
        owners = project_map.get(normalize_repo_path(path).lower())
        if owners:
            project_names.update(owners)
            matched.append(path)
        else:
            unmapped.append(path)
    return sorted(project_names), matched, unmapped


def build_command(root, workspace_abs, config, check_mode, group, extra):
    """构造单次 dotnet format 命令。"""
    argv = ["dotnet", "format", group, workspace_abs]
    if check_mode:
        argv.append("--verify-no-changes")
    if config["no_restore"]:
        argv.append("--no-restore")
    # whitespace 分组不支持 --severity（仅 style/analyzers 支持）
    severity = extra.get("severity") or config.get("severity")
    if severity and group != "whitespace":
        argv.extend(["--severity", severity])
    # 忽略目录：仅保留项目根下真实存在的目录
    exclude_dirs = extra.get("exclude_dirs") or config["exclude_dirs"] or []
    exists_excludes = []
    for item in exclude_dirs:
        abs_path = item if os.path.isabs(item) else os.path.join(root, item)
        if os.path.exists(abs_path):
            exists_excludes.append(to_dotnet_path(item))
        else:
            print("[提示] 忽略目录不存在，已跳过：%s" % item)
    for item in exists_excludes:
        argv.extend(["--exclude", item])
    # 指定目标范围（相对项目根目录）
    target = extra.get("path")
    if target:
        argv.extend(["--include", to_dotnet_path(target)])
    return argv


def run_groups_for_workspace(root, workspace_abs, config, check_mode, group_list, extra):
    """对单个工作区（解决方案或工程）逐分组执行，返回 (per_group_results, overall_code)。

    单工作区退出码聚合规则：
    - check 模式任一分组返回 2（存在待格式化文件）即视为整体 2；
    - 任一分组返回非 0 非 2（出错）则记录该值并中断后续分组。
    """
    per_group_results = []
    overall_code = 0
    for group in group_list:
        argv = build_command(root, workspace_abs, config, check_mode, group, extra)
        print("[信息] 执行分组 %s（%s 模式）……" % (group, "校验" if check_mode else "修复"))
        code, output = run_dotnet_format(argv, cwd=root)
        per_group_results.append((code, output))
        if code == 2:
            overall_code = 2
        elif code != 0:
            overall_code = code
            break
    return per_group_results, overall_code


def merge_overall_code(current, incoming):
    """跨工作区（多工程）退出码聚合：任一 2 则整体 2；非 0 非 2（出错）优先返回以便调用方中断。"""
    if incoming not in (0, 2):
        return incoming
    if incoming == 2 or current == 2:
        return 2
    return current


def _resolve_scope_entry(line, root, git_root):
    """把清单中的一行路径解析为「项目根相对路径」；无法定位到项目根下时返回 None。

    两种写法都要支持，且**必须优先按项目根解析**：
      - 项目根相对（`src/module/A.cs`）——H1 清单的常见形式；
      - 仓库根相对（`<子目录>/<路径>/A.cs`）——`git status` 的原始形式。

    若直接用 `to_project_rel_path`（其语义是「仓库根相对 → 项目根相对」），
    传入项目根相对路径会被当成仓库根相对拼接而落到项目根之外，返回 None
    （实测踩坑：清单里的 `.codebuddy/.../A.cs` 被误判为不存在）。
    """
    normalized = normalize_repo_path(line)
    # ① 先按项目根相对解析
    abs_path = os.path.normpath(os.path.join(root, normalized.replace("/", os.sep)))
    if os.path.exists(abs_path):
        try:
            rel = os.path.relpath(abs_path, root)
        except ValueError:
            rel = None
        if rel is not None:
            rel = normalize_repo_path(rel)
            if rel != ".." and not rel.startswith("../"):
                return rel
    # ② 再按仓库根相对解析（兼容 git status 形式）
    return to_project_rel_path(normalized, git_root, root)


def read_scope_file(list_path, root, git_root):
    """读取「本次提交计划清单」，返回项目根相对的 .cs 路径列表（排序去重）。

    清单文件每行一个路径，支持两种写法（自动判别，无需调用方转换）：
      - 项目根相对路径，如 `src/module/Core/A.cs`
      - 仓库根相对路径，如 `<子目录>/<路径>/A.cs`

    非 `.cs` 行、空行、以 `#` 开头的注释行一律忽略。
    与 `git status` 口径不同，本函数**只认清单里列出的文件**，因此不受工作区
    其他无关改动影响——这正是提交门禁 H1 需要的「本笔提交计划」语义。
    """
    abs_path = list_path if os.path.isabs(list_path) else os.path.join(os.getcwd(), list_path)
    if not os.path.isfile(abs_path):
        raise ConfigError("变更清单文件不存在：%s" % abs_path)

    paths = []
    try:
        with open(abs_path, "r", encoding="utf-8-sig") as handle:
            for raw in handle:
                line = raw.strip().strip('"')
                if not line or line.startswith("#"):
                    continue
                if not line.lower().endswith(".cs"):
                    continue
                rel = _resolve_scope_entry(line, root, git_root)
                if rel:
                    paths.append(rel)
    except OSError as exc:
        raise ConfigError("读取变更清单失败（%s）：%s" % (exc, abs_path))
    return sorted(set(paths))


def resolve_check_scope(root, config, args, exclude_dirs):
    """解析本次检查范围，返回范围描述字典。

    mode = "projects"：变更文件成功定位到所属工程（串行检查这些工程）；
    mode = "repo"    ：默认整仓，或因任何原因回退整仓（fallback_reason 说明原因）。

    变更来源二选一（`--changed-from-file` 优先）：
      - `--changed`：取 `git status` 的整个工作区变更（**注意**：会带上工作区里
        与本次提交无关的改动，提交门禁应改用下面的清单方式）；
      - `--changed-from-file <清单>`：只取清单列出的文件（提交门禁 H1 用，
        语义为「本笔提交计划」，不受工作区其他改动干扰）。
    """
    scope = {
        "mode": "repo",
        "workspace_abs": None,
        "projects": [],
        "progress": [],
        "fallback_reason": None,
        "changed_total": 0,
        "changed_matched": [],
        "changed_excluded": [],
        "changed_unmapped": [],
        "changed_source": None,
    }
    if not args.changed and not args.changed_from_file:
        return scope

    git_root = get_git_root(root)
    if not git_root:
        scope["fallback_reason"] = "非 git 仓库或 git 命令不可用"
        return scope

    if args.changed_from_file:
        # 提交门禁路径：只认清单内文件，不受工作区其他改动影响
        scope["changed_source"] = "file"
        try:
            changed = read_scope_file(args.changed_from_file, root, git_root)
        except ConfigError as exc:
            scope["fallback_reason"] = str(exc)
            return scope
    else:
        scope["changed_source"] = "git_status"
        try:
            entries = get_git_status(root)
        except RuntimeError as exc:
            scope["fallback_reason"] = "获取 git 状态失败：%s" % exc
            return scope

        changed = []
        for xy, repo_rel in entries:
            if not repo_rel.lower().endswith(".cs"):
                continue
            # 删除项没有可检查的目标文件；未跟踪（??）与增删改改（M/A/R/C/U）都需纳入
            if xy != "??":
                status_code = xy[0] if xy[0] != " " else xy[1]
                if status_code not in ("M", "A", "R", "C", "U"):
                    continue
            project_rel = to_project_rel_path(repo_rel, git_root, root)
            if project_rel:
                changed.append(project_rel)
        changed = sorted(set(changed))

    if not changed:
        # 本次变更/清单中没有任何 .cs —— 这是**正常的「无需检查」**，不是异常回退。
        # 若此处回退整仓，会把全仓存量问题算到本次头上（与「全在忽略目录内」同类缺陷；
        # 实测踩坑：只改文档/配置类文件时回退整仓，扫出 Assets 的 2133 处 ENDOFLINE）。
        scope["mode"] = "none"
        scope["fallback_reason"] = ("变更中不含 .cs 文件，无需检查" if scope["changed_source"] == "file"
                                    else "未检测到变更的 .cs 文件")
        return scope

    in_scope = []
    excluded = []
    for path in changed:
        (excluded if is_in_exclude_dirs(path, exclude_dirs) else in_scope).append(path)
    scope["changed_total"] = len(changed)
    scope["changed_excluded"] = excluded

    if not in_scope:
        # 变更文件全部落在忽略目录内 —— 这是**正常的「无需检查」**，不是异常回退。
        # 若此处回退整仓，会把与本次提交无关的全仓存量问题算到本次头上（实测踩坑：
        # 只改 .codebuddy 下文件时，因回退整仓扫出 Assets 的 2133 处 ENDOFLINE）。
        scope["mode"] = "none"
        scope["fallback_reason"] = "变更文件全部位于忽略目录内，无需检查"
        return scope

    project_names, matched, unmapped = map_changed_to_projects(in_scope, build_project_map(root))
    scope["changed_matched"] = matched
    scope["changed_unmapped"] = unmapped
    if not project_names:
        scope["fallback_reason"] = ("%d 个变更文件均不在任何工程内（可能为尚未被 Unity 导入的新文件或范围外代码）"
                                    % len(in_scope))
        return scope

    changed_scope = config.get("changed_scope")
    if not isinstance(changed_scope, dict) or "max_projects" not in changed_scope:
        raise ConfigError(
            "配置缺少必需项 `changed_scope.max_projects`（索引逻辑名：%s）\n"
            "       该值为变更工程检查的工程数上限，请按项目规模填写（字段说明见 references/config-guide.md）。"
            % CONFIG_CODENAME
        )
    try:
        max_projects = int(changed_scope["max_projects"])
    except (TypeError, ValueError):
        raise ConfigError(
            "配置项 `changed_scope.max_projects` 必须是正整数，当前为：%r" % (changed_scope["max_projects"],)
        )
    if args.max_projects is not None:
        max_projects = args.max_projects
    if max_projects < 1:
        raise ConfigError(
            "配置项 `changed_scope.max_projects` 必须是正整数，当前为：%r" % (max_projects,)
        )

    if len(project_names) > max_projects:
        scope["fallback_reason"] = ("变更涉及 %d 个工程，超过上限 %d（每工程需独立重载工作区，"
                                    "串行耗时将不低于整仓）" % (len(project_names), max_projects))
        return scope

    scope["mode"] = "projects"
    scope["projects"] = [(name, os.path.join(root, name)) for name in project_names]
    scope["max_projects"] = max_projects
    return scope


def compute_scope_key(scope):
    """计算范围指纹，用于报告复用的严格匹配。

    - 工程模式：排序后工程名列表的哈希（顺序无关，内容相关）；
    - 整仓模式：固定常量 "repo"。
    """
    if scope.get("mode") == "projects":
        names = sorted(name for name, _ in scope.get("projects") or [])
        digest = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()
        return "projects:" + digest[:16]
    return "repo"


def find_reusable_report(log_dir, scope_key, now=None):
    """在产物 check_logs 目录中查找 REPORT_REUSE_SECONDS 内、scope_key 严格匹配的 .json 报告。

    命中则返回报告字典（含 report_path / exit_code / created），否则返回 None。
    严格匹配范围可避免「用整仓报告充当变更工程门禁结果」这类错配。
    """
    if not os.path.isdir(log_dir):
        return None
    current = now if now is not None else datetime.datetime.now()
    candidates = []
    for name in os.listdir(log_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(log_dir, name)
        try:
            if current.timestamp() - os.path.getmtime(path) > REPORT_REUSE_SECONDS:
                continue
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if data.get("scope_key") != scope_key:
            continue
        if data.get("mode") != "check":
            continue
        candidates.append((os.path.getmtime(path), path, data))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, path, data = candidates[0]
    data["report_path"] = path
    return data


def run_dotnet_format(argv, cwd):
    """执行命令并返回（返回码, 合并输出）。返回码失败且疑似还原问题时自动去 --no-restore 重试一次。"""
    def invoke(cmd):
        proc = subprocess.run(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", text=True,
        )
        return proc.returncode, (proc.stdout or "")

    code, output = invoke(argv)
    if code != 0 and "--no-restore" in argv:
        lowered = output.lower()
        if any(keyword.lower() in lowered for keyword in RESTORE_ERROR_KEYWORDS):
            retry = [item for item in argv if item != "--no-restore"]
            print("[提示] 首次执行疑似还原问题（--no-restore 失败），改为允许还原重试一次……")
            code, output = invoke(retry)
    return code, output


def parse_diagnostics(output):
    """从输出中统计诊断：返回（诊断 ID → 次数, 涉及文件集合）。"""
    diag_counter = {}
    files = set()
    for line in output.splitlines():
        match = DIAG_RE.search(line)
        if match:
            diag = match.group("diag")
            diag_counter[diag] = diag_counter.get(diag, 0) + 1
            files.add(match.group("path"))
    return diag_counter, files


def save_reports(log_dir, root, workspace_abs, check_mode, group_list, extra,
                 per_group_results, total_output, overall_code=None, scope_key=None):
    """在产物 check_logs 目录下生成 .log / .md / .json 报告。

    log_dir：产物目录（经索引 artifacts 解析，位于项目侧 .codebuddy.project/）。
    overall_code：本次检查的最终退出码（多工程串行时为聚合值）；为空时回退为末次分组退出码。
    scope_key：检查范围指纹，写入 .json 供 --reuse-report 严格匹配（避免复用错范围报告）。
    """
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    rand = "%08x" % random.getrandbits(32)
    base = os.path.join(log_dir, "%s_code-format_%s" % (ts, rand))
    log_path = base + ".log"
    md_path = base + ".md"
    json_path = base + ".json"

    # .log：完整原始输出（含多次分组/多工程输出分隔）
    with open(log_path, "w", encoding="utf-8") as fp:
        fp.write(total_output if total_output else "(无输出)")

    # .md：可读摘要
    scope = extra.get("scope") or {"mode": "repo"}
    mode_text = "check（只读校验）" if check_mode else "fix（应用格式修改）"
    final_code = overall_code if overall_code is not None else (
        per_group_results[-1][0] if per_group_results else 1)
    head_lines = ["# dotnet format 检查报告", ""]
    head_lines.append("- 时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    head_lines.append("- 项目根：%s" % root)
    # 检查范围：明确标注是整仓还是变更工程，避免把「只查了部分工程」误读为全量合规
    if scope.get("mode") == "projects":
        head_lines.append("- 检查范围：变更工程（%d 个）" % len(scope.get("projects") or []))
        progress = scope.get("progress") or []
        if progress:
            head_lines.append("- 变更工程：%s" % "、".join(
                "%s（%d/%d，退出码 %d）" % (item["project"], item["index"], item["total"], item["exit_code"])
                for item in progress))
        else:
            head_lines.append("- 变更工程：%s" % "、".join(name for name, _ in scope.get("projects") or []))
    else:
        if scope.get("fallback_reason"):
            head_lines.append("- 检查范围：整仓（回退：%s）" % scope["fallback_reason"])
        else:
            head_lines.append("- 检查范围：整仓")
    if scope.get("changed_total"):
        head_lines.append("- 变更文件：共 %d 个（映射 %d / 已排除 %d / 未纳入 %d）"
                          % (scope["changed_total"], len(scope.get("changed_matched") or []),
                             len(scope.get("changed_excluded") or []),
                             len(scope.get("changed_unmapped") or [])))
    head_lines.append("- 工作区：%s%s" % (workspace_abs,
                                          "（变更工程模式下以工程为单位执行）" if scope.get("mode") == "projects" else ""))
    head_lines.append("- 模式：%s" % mode_text)
    head_lines.append("- 分组：%s" % ", ".join(group_list))
    if extra.get("path"):
        head_lines.append("- 指定范围：%s" % extra["path"])
    if extra.get("exclude_dirs"):
        head_lines.append("- 忽略目录：%s" % ", ".join(extra["exclude_dirs"]))
    head_lines.append("- 最终退出码：%d（0 合规/完成，2 存在待格式化文件，1 出错）" % final_code)
    head_lines.append("")

    all_diags = {}
    all_files = set()
    for code, output in per_group_results:
        diags, files = parse_diagnostics(output)
        for diag, count in diags.items():
            all_diags[diag] = all_diags.get(diag, 0) + count
        all_files |= files
    head_lines.append("## 诊断统计")
    if all_diags:
        head_lines.append("")
        head_lines.append("| 诊断 ID | 次数 | 说明 |")
        head_lines.append("|---------|------|------|")
        diag_notes = {
            "IMPORTS": "using 指令排序/分组",
            "IDE0055": "格式规则（空格/换行/缩进）",
            "IDE0005": "多余的 using",
            "IDE1006": "命名规则（csharp_style / dotnet_naming）",
        }
        for diag, count in sorted(all_diags.items(), key=lambda kv: -kv[1]):
            head_lines.append("| %s | %d | %s |" % (diag, count, diag_notes.get(diag, "详见 .log")))
        head_lines.append("")
        head_lines.append("涉及文件数：%d" % len(all_files))
        head_lines.append("")
    else:
        head_lines.append("- 未检测到需格式化的诊断。")
        head_lines.append("")

    # 未纳入检查的变更文件：显式列出，避免「以为已检查」的误判
    excluded = scope.get("changed_excluded") or []
    unmapped = scope.get("changed_unmapped") or []
    if excluded or unmapped:
        head_lines.append("## 未纳入检查的变更文件")
        head_lines.append("")
        head_lines.append("| 文件 | 原因 |")
        head_lines.append("|------|------|")
        for item in excluded:
            head_lines.append("| `%s` | 命中忽略目录 |" % item)
        for item in unmapped:
            head_lines.append("| `%s` | 不在任何工程内（如尚未被 Unity 导入生成 csproj 条目，或属检查范围外目录） |"
                              % item)
        head_lines.append("")

    head_lines.append("## 完整输出")
    head_lines.append("")
    head_lines.append("完整原始输出见同目录文件：`%s`" % os.path.basename(log_path))
    head_lines.append("")

    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(head_lines))

    # .json：结构化报告，供 --reuse-report 严格匹配范围后复用（与 csharp-comment-checker 双报告模式对齐）
    json_data = {
        "version": 1,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project_root": root,
        "workspace": workspace_abs,
        "mode": "check" if check_mode else "fix",
        "scope": {
            "type": scope.get("mode") or "repo",
            "projects": [name for name, _ in scope.get("projects") or []],
            "progress": scope.get("progress") or [],
            "fallback_reason": scope.get("fallback_reason"),
            "changed_total": scope.get("changed_total", 0),
            "changed_matched": scope.get("changed_matched") or [],
            "changed_excluded": scope.get("changed_excluded") or [],
            "changed_unmapped": scope.get("changed_unmapped") or [],
        },
        "scope_key": scope_key,
        "groups": list(group_list),
        "exit_code": final_code,
        "diagnostics": all_diags,
        "affected_files": sorted(all_files),
        "log_file": os.path.basename(log_path),
        "md_file": os.path.basename(md_path),
    }
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(json_data, fp, ensure_ascii=False, indent=2)

    return log_path, md_path, json_path


def main():
    parser = argparse.ArgumentParser(description="C# 代码格式检查/修复（dotnet format + .editorconfig）")
    parser.add_argument("mode", nargs="?", default="check",
                        choices=["check", "fix"], help="执行模式：check 只检查不修改（默认），fix 落盘修复")
    parser.add_argument("--root", default=None, help="项目根目录（含 .editorconfig），默认从当前目录向上查找")
    parser.add_argument("--path", default=None, help="相对项目根的目标目录/文件范围（--include）")
    parser.add_argument("--project", default=None, help="指定工作区文件（.slnx/.sln/.csproj），覆盖配置 workspace")
    parser.add_argument("--changed", action="store_true",
                        help="按变更文件所属工程检查（与 --project/--path 互斥）；无法定位时回退整仓并告警")
    parser.add_argument("--changed-from-file", default=None, metavar="清单文件",
                        help="按「提交计划清单」内的 .cs 定位所属工程（提交门禁 H1 用）。"
                             "清单每行一个路径（项目根相对或仓库根相对），只检查清单内文件，"
                             "不受工作区其他无关改动影响")
    parser.add_argument("--max-projects", type=int, default=None,
                        help="变更工程数上限（--changed / --changed-from-file 生效），超过则回退整仓")
    parser.add_argument("--reuse-report", action="store_true",
                        help="若存在 5 分钟内且检查范围一致的报告则直接复用，不重复执行")
    parser.add_argument("--severity", default=None, help="dotnet format --severity（error/warn/info）")
    parser.add_argument("--no-save", action="store_true", help="不保存报告文件")
    parser.add_argument("--no-restore", dest="no_restore", action="store_true", default=None, help="强制免还原")
    parser.add_argument("--restore", dest="no_restore", action="store_false", help="允许还原")
    args = parser.parse_args()

    # 0. 参数互斥校验：自动定位范围与手动指定范围互斥
    if args.changed and args.changed_from_file:
        print("[错误] --changed 与 --changed-from-file 互斥：前者取工作区全部变更，"
              "后者只取清单内文件，请按用途二选一。")
        return 1
    if (args.changed or args.changed_from_file) and (args.project or args.path):
        print("[错误] --changed/--changed-from-file 与 --project/--path 互斥："
              "前者按变更工程自动定位，后者手动指定范围，请二选一。")
        return 1
    if args.max_projects is not None and not (args.changed or args.changed_from_file):
        print("[提示] --max-projects 仅在 --changed/--changed-from-file 下生效，本次已忽略。")
    if args.changed_from_file and args.mode == "fix":
        print("[提示] --changed-from-file 在 fix 模式下只会修复清单内文件所属工程；"
              "如需整体修复请显式指定 --project/--path。")

    # 1. 定位项目根（含 .editorconfig）
    base_dir = args.root or os.getcwd()
    root = find_project_root(base_dir)
    if not root:
        print("[错误] 未找到项目根（当前目录及上级均无 .editorconfig）。请在项目根目录或其子目录下运行。")
        return 1
    root = os.path.abspath(root)
    print("[信息] 项目根：%s" % root)

    # 2. 读取项目配置（经索引注册表定位到项目侧配置）
    config_abs = resolve_config_path(root)
    config = load_config(root, config_abs)
    if args.no_restore is not None:
        config["no_restore"] = args.no_restore

    # 3. 解析工作区
    workspace_rel, workspace_abs = detect_workspace(root, args.project or config.get("workspace"))
    if not workspace_abs:
        print("[错误] 未找到工作区（.slnx/.sln/.csproj）。请通过配置 workspace 或 --project 指定。")
        return 1
    print("[信息] 工作区：%s" % workspace_abs)

    # 4. 组装分组与忽略目录
    check_mode = args.mode == "check"
    group_list = config["groups"]
    if args.path:
        path_rel = args.path.replace("\\", "/")
        path_abs = path_rel if os.path.isabs(path_rel) else os.path.join(root, path_rel)
        if not os.path.exists(path_abs):
            print("[错误] --path 指定的目录/文件不存在：%s" % args.path)
            return 1
        # dotnet format 的目录 include 需带尾部分隔符才按目录递归匹配
        target = to_dotnet_path(os.path.relpath(path_abs, root))
        if os.path.isdir(path_abs):
            target = target.rstrip("/") + "/"
    else:
        target = None
    # fix 模式需要真实生效的忽略目录列表供命令构造与报告使用
    exclude_dirs = list(config["exclude_dirs"])

    # 4.5 解析检查范围（整仓 / 变更工程 / 无需检查）
    scope = resolve_check_scope(root, config, args, exclude_dirs)
    scope_key = compute_scope_key(scope)
    # extra 依赖 scope，提前定义：下方「无需检查」分支会提前 return 并用到它
    extra = {
        "severity": args.severity,
        "path": target,
        "exclude_dirs": exclude_dirs,
        "scope": scope,
    }
    if args.changed or args.changed_from_file:
        flag = "--changed-from-file" if args.changed_from_file else "--changed"
        source_desc = ("提交计划清单：%s" % args.changed_from_file) if args.changed_from_file else "工作区 git status"
        if scope["mode"] == "projects":
            print("[信息] 检查范围：变更工程（%d 个，来源 %s）—— %s"
                  % (len(scope["projects"]), source_desc,
                     "、".join(name for name, _ in scope["projects"])))
            if scope["changed_unmapped"]:
                print("[提示] 有 %d 个变更文件不在任何工程内，不会被 dotnet format 检查："
                      % len(scope["changed_unmapped"]))
                for item in scope["changed_unmapped"]:
                    print("       - %s" % item)
        elif scope["mode"] == "none":
            # 变更文件全在忽略目录内：正常通过，不检查也不回退整仓
            print("[信息] 无需检查：%s（来源 %s）" % (scope["fallback_reason"], source_desc))
            if scope["changed_excluded"]:
                for item in scope["changed_excluded"]:
                    print("       - %s" % item)
            if not args.no_save:
                log_dir = resolve_artifact_dir(root, "format_checker.check_logs")
                log_path, md_path, json_path = save_reports(
                    log_dir, root, workspace_abs, check_mode, [], extra,
                    [], "", overall_code=0, scope_key=scope_key)
                print("[信息] 摘要报告：%s" % md_path)
            return 0
        else:
            print("[警告] %s 已指定，但%s，回退整仓检查。" % (flag, scope["fallback_reason"]))

    # 4.6 报告复用（供提交门禁避免重复执行完整检查）
    if args.reuse_report and check_mode:
        reusable = find_reusable_report(
            resolve_artifact_dir(root, "format_checker.check_logs"), scope_key)
        if reusable:
            print("[信息] 复用 5 分钟内的检查报告（范围一致）：%s" % reusable["report_path"])
            return int(reusable.get("exit_code") or 0)
        print("[信息] 无可用复用报告，执行完整检查。")

    # 5. 按范围执行 dotnet format
    per_group_results = []
    total_output_parts = []
    overall_code = 0
    if scope["mode"] == "projects":
        # 变更工程模式：外层遍历工程、内层遍历分组（串行）
        projects = scope["projects"]
        total = len(projects)
        for index, (proj_name, proj_abs) in enumerate(projects, start=1):
            print("[信息] 检查变更工程 %d/%d：%s" % (index, total, proj_name))
            proj_results, proj_code = run_groups_for_workspace(
                root, proj_abs, config, check_mode, group_list, extra)
            scope["progress"].append({"project": proj_name, "index": index,
                                      "total": total, "exit_code": proj_code})
            per_group_results.extend(proj_results)
            total_output_parts.append("#" * 30 + " 工程: %s  退出码: %d " % (proj_name, proj_code) + "#" * 30)
            for _, output in proj_results:
                total_output_parts.append(output.rstrip())
            overall_code = merge_overall_code(overall_code, proj_code)
            if proj_code not in (0, 2):
                print("[错误] 工程 %s 执行出错（退出码 %d），已中止后续工程检查。详见 .log。" % (proj_name, proj_code))
                break
    else:
        # 整仓模式（无参默认行为，保持与改造前一致）
        per_group_results, overall_code = run_groups_for_workspace(
            root, workspace_abs, config, check_mode, group_list, extra)
        for group, (code, output) in zip(group_list, per_group_results):
            total_output_parts.append("=" * 30 + " 分组: %s  退出码: %d " % (group, code) + "=" * 30)
            total_output_parts.append(output.rstrip())
    total_output = "\n".join(total_output_parts)

    # 6. 生成报告
    if args.no_save:
        print("[信息] 已指定 --no-save，不生成报告文件。")
    else:
        log_dir = resolve_artifact_dir(root, "format_checker.check_logs")
        log_path, md_path, json_path = save_reports(
            log_dir, root, workspace_abs, check_mode, group_list, extra,
            per_group_results, total_output, overall_code=overall_code, scope_key=scope_key)
        print("[信息] 完整输出：%s" % log_path)
        print("[信息] 摘要报告：%s" % md_path)
        print("[信息] 结构化报告：%s" % json_path)

    # 7. 控制台汇总
    if overall_code not in (0, 2):
        print("[错误] 执行出错（退出码 %d）。请查看 .log 报告中的完整错误信息。" % overall_code)
    elif check_mode:
        all_diags, all_files = {}, set()
        for code, output in per_group_results:
            diags, files = parse_diagnostics(output)
            for diag, count in diags.items():
                all_diags[diag] = all_diags.get(diag, 0) + count
            all_files |= files
        if overall_code == 2:
            print("[结果] 存在 %d 个需格式化文件的诊断（%d 种）。详见报告文件。" %
                  (len(all_files), len(all_diags)))
            for diag, count in sorted(all_diags.items(), key=lambda kv: -kv[1]):
                print("       - %s：%d 处" % (diag, count))
        else:
            print("[结果] 格式合规，无待格式化文件。")
    else:
        print("[结果] fix 模式执行完成，请用 git status / git diff 核对变更。")

    return overall_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as error:
        # 配置是检查范围的唯一来源：配置不可用即明确报错，不静默回退默认值
        print("[错误] %s" % error)
        sys.exit(3)
