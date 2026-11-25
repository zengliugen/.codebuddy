# -*- coding: utf-8 -*-
"""代码规范检查报告生成器：解析 dotnet format 日志，生成模块化 Markdown 报告。

职责：
1. 解析一份或多份 dotnet format 日志（支持整仓 + 独立解决方案分别检查后合并）。
2. 按路径划分模块（`Assets/<域>`、`Packages/<包>`；`<包>/<X>~/` 按 Unity 约定视为独立模块）。
3. 按问题类型分类（命名 / 空白与布局 / using 指令 / 其他风格）并生成三类报告：
   - 00-总览.md（模块汇总、行尾统计、结论、目录结构、检查范围、建议）
   - 01-模块结论/<模块>.md（摘要、诊断分布、按类别汇总 + 文件表 + 明细含代码列）
   - 02-按问题类型汇总/<类别>.md（横向汇总）
4. 忽略目录经索引读取项目侧 format_checker.config，与检查范围口径一致；不内置任何项目专有值。

用法：
    python scripts/format_report.py --log <日志路径> [--log <日志路径>…] --out <输出目录>
"""

import argparse
import collections
import datetime
import json
import os
import re
import sys

SEP = "\\"

NAMING = "命名问题"
LAYOUT = "空白与布局"
USING = "using 指令"
OTHER = "其他代码风格"
CATEGORIES = (NAMING, LAYOUT, USING, OTHER)

DIAG_MEANING = {
    "ENDOFLINE": "行尾符与配置不一致",
    "IDE1006": "命名规则不符合 .editorconfig",
    "WHITESPACE": "空白字符不符合配置",
    "IDE0049": "使用框架类型名（int/String 等）",
    "IDE0047": "移除不必要的括号",
    "IDE0048": "按清晰性要求添加括号",
    "IDE2000": "存在多个连续空行",
    "IDE0025": "见说明列",
    "IDE0009": "见说明列",
    "IDE2002": "括号后存在不必要的空行",
    "IDE0018": "内联变量声明",
    "IDE0053": "lambda 改用代码块主体",
    "IDE0042": "见说明列",
    "IDE0017": "使用对象初始化器",
    "IDE0007": "见说明列",
    "IDE0019": "见说明列",
    "IMPORTS": "using 指令未排序/未分组",
}

_file_line_cache = {}


class ReportError(RuntimeError):
    """日志无法解析、配置缺失等无法继续生成报告的情况。"""


def read_exclude_dirs(project_root):
    """经索引读取 format_checker.config 的 exclude_dirs；缺失时返回空列表。"""
    if not project_root:
        return []
    index_path = os.path.join(project_root, ".codebuddy", "project.index.json")
    if not os.path.isfile(index_path):
        return []
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
        relative = index.get("files", {}).get("format_checker.config", {}).get("path", "")
        if not relative:
            return []
        config_path = os.path.join(project_root, relative)
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        return [item for item in config.get("exclude_dirs", []) if isinstance(item, str) and item]
    except (OSError, ValueError):
        return []


def default_out_dir(project_root, stamp):
    """默认报告目录：项目侧产物根下 skills/csharp/csharp-format-checker/report_logs/<时间戳>。

    路径经索引 artifacts.dirs.format_checker.check_logs 的父目录推导，不内置固定相对路径。
    """
    index_path = os.path.join(project_root, ".codebuddy", "project.index.json")
    if not os.path.isfile(index_path):
        raise ReportError("未找到项目配置索引，无法确定默认报告目录：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
        logs_dir = index.get("artifacts", {}).get("dirs", {}).get("format_checker.check_logs", "")
    except (OSError, ValueError) as error:
        raise ReportError("项目配置索引读取失败：%s（%s）" % (index_path, error))
    if not logs_dir:
        raise ReportError("索引缺少 artifacts.dirs.format_checker.check_logs，无法确定默认报告目录")
    skill_dir = os.path.dirname(logs_dir.replace("/", os.sep))
    return os.path.join(project_root, skill_dir, "report_logs", stamp)


def find_project_root(start):
    """自 start 向上查找含 .editorconfig 的目录。"""
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, ".editorconfig")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def parse_log(log_path, project_root):
    """解析 dotnet format 日志（先去硬折行）。"""
    if not os.path.isfile(log_path):
        raise ReportError("日志文件不存在：%s" % log_path)
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    flat = text.replace("\n", "").replace("\r", "")
    pattern = re.compile(
        r"([A-Za-z]:[^\s()\[\]]*?\.cs)\((\d+),(\d+)\): (error|warning) ([A-Z0-9_]+): ([^\[]*)(?:\[([^\]]*?\.csproj)\])?"
    )
    rows = []
    root_posix = project_root.replace(SEP, "/").rstrip("/") if project_root else None
    for match in pattern.finditer(flat):
        abs_path, line, col, severity, diag, message, project = match.groups()
        posix = abs_path.replace(SEP, "/")
        if root_posix and posix.startswith(root_posix + "/"):
            relative = posix[len(root_posix) + 1:]
        else:
            relative = posix.lstrip("/")
        rows.append(
            {
                "file": relative,
                "abs": abs_path,
                "line": int(line),
                "col": int(col),
                "severity": severity,
                "diag": diag,
                "msg": message.strip(),
                "project": os.path.basename(project) if project else "",
            }
        )
    return rows


def dedupe(rows):
    """同一 (文件, 行, 列, 诊断) 只保留一条，避免多份日志重复统计。"""
    seen = set()
    result = []
    for row in rows:
        key = (row["file"], row["line"], row["col"], row["diag"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def module_of(relative):
    """路径 → (模块全名, 类型, 显示目录)。类型：assets / package / ignored-dir / other。"""
    parts = relative.split("/")
    if len(parts) >= 2 and parts[0] == "Assets":
        name = "/".join(parts[:2])
        return (name, "assets", name)
    if len(parts) >= 3 and parts[0] == "Packages":
        package = parts[1]
        # Unity 忽略目录约定：<包>/<X>~/ 视作独立模块（如样例工程）
        if len(parts) >= 4 and parts[2].endswith("~"):
            name = "%s/%s" % (package, parts[2])
            return (name, "ignored-dir", "Packages/%s/%s" % (package, parts[2]))
        return (package, "package", "Packages/" + package)
    return (parts[0], "other", parts[0])


def common_package_prefix(names):
    """求包名的公共点分段前缀（用于展示与文件短名）。

    多包时取公共段；单包时去掉最后一段（否则短名会等于整包名，无法缩短）。
    """
    names = sorted(set(names))
    if not names:
        return ""
    segments = [name.split(".") for name in names]
    prefix = []
    for column in zip(*segments):
        if len(set(column)) == 1:
            prefix.append(column[0])
        else:
            break
    # 公共段等于某个包的全部段（单包或包含关系）时，再少取一段
    if len(prefix) == len(segments[0]):
        prefix = prefix[:-1]
    return ".".join(prefix) + "." if prefix else ""


def category_of(diag):
    if diag == "IDE1006":
        return NAMING
    if diag in ("ENDOFLINE", "WHITESPACE", "IDE0055"):
        return LAYOUT
    if diag in ("IMPORTS", "IDE0005"):
        return USING
    return OTHER


def naming_rule_of(message):
    match = re.search(r"缺少前缀[:：]\s*(\S+)", message)
    if match:
        return "缺少必需前缀（%s）" % match.group(1)
    if "必须以大写字符开头" in message:
        return "必须以大写开头"
    if "必须以小写字符开头" in message:
        return "必须以小写开头"
    match = re.search(r"前缀[“\"]([^”\"]+)[”\"]不是预期的", message)
    if match:
        return "使用了非预期前缀（%s）" % match.group(1)
    return "其他命名冲突"


def md_path(relative):
    return "`%s`" % relative


def cell(text):
    return text.replace("|", "\\|").replace("\n", " ").strip()


def get_code(abs_path, line):
    if abs_path not in _file_line_cache:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
                _file_line_cache[abs_path] = handle.read().splitlines()
        except OSError:
            _file_line_cache[abs_path] = []
    lines = _file_line_cache[abs_path]
    if 0 < line <= len(lines):
        return lines[line - 1].strip()
    return ""


def count_cs_files(project_root, display_dir, exclude_dirs):
    """统计模块目录内 .cs 文件数（排除配置目录）。"""
    if not project_root or not display_dir:
        return 0
    base = os.path.join(project_root, display_dir.replace("/", os.sep))
    if not os.path.isdir(base):
        return 0
    excluded = [item.replace("\\", "/").rstrip("/") for item in exclude_dirs]
    count = 0
    for current, dirs, files in os.walk(base):
        relative = os.path.relpath(current, project_root).replace(os.sep, "/")
        if any(relative == item or relative.startswith(item + "/") for item in excluded):
            continue
        count += sum(1 for name in files if name.endswith(".cs"))
    return count


def build_modules(rows, prefix):
    """按模块归并，并生成展示名 / 文件 stem。"""
    modules = collections.OrderedDict()
    for row in rows:
        name, kind, display = module_of(row["file"])
        if name not in modules:
            modules[name] = {"name": name, "kind": kind, "display": display, "rows": []}
        modules[name]["rows"].append(row)

    for name, info in modules.items():
        short = name[len(prefix):] if prefix and name.startswith(prefix) else name
        if info["kind"] == "assets":
            info["label"] = name
            info["stem"] = name.replace("/", "-")
        elif info["kind"] == "package":
            info["label"] = name
            info["stem"] = "pkg-" + short
        elif info["kind"] == "ignored-dir":
            package, directory = name.split("/", 1)
            package_short = package[len(prefix):] if prefix and package.startswith(prefix) else package
            info["label"] = name
            info["stem"] = "pkg-%s-%s" % (package_short, directory.rstrip("~"))
        else:
            info["label"] = name
            info["stem"] = name.replace("/", "-")

    # 稳定排序：领域模块在前，其余按名称
    ordered = sorted(
        modules.values(), key=lambda info: (0 if info["kind"] == "assets" else 1, info["name"])
    )
    return collections.OrderedDict((info["name"], info) for info in ordered)


def write_module_page(info, out_dir, title, timestamp, project_root, exclude_dirs):
    rows = info["rows"]
    by_category = collections.defaultdict(list)
    for row in rows:
        by_category[category_of(row["diag"])].append(row)
    files_by_category = {name: {row["file"] for row in by_category[name]} for name in CATEGORIES}
    total = len(rows)
    total_files = len({row["file"] for row in rows})
    projects = sorted({row["project"] for row in rows if row["project"]})
    cs_count = count_cs_files(project_root, info["display"], exclude_dirs)

    lines = []
    lines.append("# %s · %s" % (info["label"], title))
    lines.append("")
    lines.append("> 检查标准：项目根 `.editorconfig`（命名样式 + whitespace/style 规则）  ")
    lines.append("> 检查工具：`dotnet format`（whitespace + style 分组，只读校验）  ")
    lines.append("> 报告时间：%s  " % timestamp)
    lines.append("> 覆盖目录：`%s`  " % info["display"])
    lines.append(
        "> 覆盖工程：%d 个；目录内 `.cs` 文件：%d 个（已排除配置声明的生成代码与三方目录）"
        % (len(projects), cs_count)
    )
    lines.append("")

    lines.append("## 一、结论摘要")
    lines.append("")
    lines.append("| 结果类型 | 问题处数 | 涉及文件数 | 可否自动修复 |")
    lines.append("|----------|---------:|-----------:|--------------|")
    fixable = {
        NAMING: "否（需重命名或降低级别）",
        LAYOUT: "是（dotnet format）",
        USING: "是（dotnet format）",
        OTHER: "是（dotnet format）",
    }
    for name in CATEGORIES:
        lines.append(
            "| %s | %d | %d | %s |"
            % (name, len(by_category[name]), len(files_by_category[name]), fixable[name])
        )
    lines.append("| **合计** | **%d** | **%d** | — |" % (total, total_files))
    lines.append("")

    endofline_files = {row["file"] for row in by_category[LAYOUT] if row["diag"] == "ENDOFLINE"}
    if endofline_files:
        lines.append(
            "> 行尾类（`ENDOFLINE`）诊断**按行计数**（每个不合规行算一处），上表「处数」会显得很大；"
            "实际需处理的是 **%d 个文件**（整文件行尾需统一）。" % len(endofline_files)
        )
        lines.append("")

    summary = "；".join(
        "%s %d 个文件 / %d 处" % (name, len(files_by_category[name]), len(by_category[name]))
        for name in CATEGORIES
        if by_category[name]
    )
    if summary:
        lines.append("**结论：本模块存在 %d 处问题，涉及 %d 个文件——%s。**" % (total, total_files, summary))
    else:
        lines.append("**结论：本模块未发现不符合 `.editorconfig` 的问题。**")
    lines.append("")

    diag_counts = collections.Counter(row["diag"] for row in rows)
    if diag_counts:
        lines.append("### 诊断类型分布")
        lines.append("")
        lines.append("| 诊断 ID | 含义 | 处数 |")
        lines.append("|---------|------|-----:|")
        for diag, count in diag_counts.most_common():
            lines.append("| `%s` | %s | %d |" % (diag, DIAG_MEANING.get(diag, "见说明列"), count))
        lines.append("")

    section_index = ["二", "三", "四", "五"]
    for position, name in enumerate(CATEGORIES):
        category_rows = by_category[name]
        lines.append("## %s、%s" % (section_index[position], name))
        lines.append("")
        if not category_rows:
            lines.append("未发现该类问题。")
            lines.append("")
            continue

        if name == NAMING:
            lines.append("> dotnet format **不支持**自动重命名符号，可用 `scripts/rename_symbol.py` 批量处理，或在 `.editorconfig` 中降低该诊断级别。")
            lines.append("")
            rule_counts = collections.Counter(naming_rule_of(row["msg"]) for row in category_rows)
            rule_files = collections.defaultdict(set)
            for row in category_rows:
                rule_files[naming_rule_of(row["msg"])].add(row["file"])
            lines.append("**按违反的命名规则**")
            lines.append("")
            lines.append("| 违反规则 | 处数 | 涉及文件 |")
            lines.append("|----------|-----:|---------:|")
            for rule, count in rule_counts.most_common():
                lines.append("| %s | %d | %d |" % (rule, count, len(rule_files[rule])))
            lines.append("")

        per_file = collections.Counter(row["file"] for row in category_rows)
        lines.append("**涉及文件（%d 个）**" % len(per_file))
        lines.append("")
        lines.append("| 文件 | 处数 | 构成 |")
        lines.append("|------|-----:|------|")
        for file_path, count in per_file.most_common():
            diag_of_file = collections.Counter(
                row["diag"] for row in category_rows if row["file"] == file_path
            )
            parts = []
            for diag, diag_count in diag_of_file.most_common():
                if diag == "ENDOFLINE":
                    parts.append("ENDOFLINE（按行计）")
                else:
                    parts.append("%s×%d" % (diag, diag_count))
            lines.append("| %s | %d | %s |" % (md_path(file_path), count, "、".join(parts)))
        lines.append("")

        lines.append("### 明细")
        lines.append("")
        grouped = collections.defaultdict(list)
        for row in category_rows:
            grouped[row["file"]].append(row)
        for file_path in sorted(grouped, key=lambda item: (-len(grouped[item]), item)):
            file_rows = grouped[file_path]
            endofline_rows = [row for row in file_rows if row["diag"] == "ENDOFLINE"]
            other_rows = [row for row in file_rows if row["diag"] != "ENDOFLINE"]
            if endofline_rows and not other_rows:
                lines.append(
                    "#### %s（ENDOFLINE，共 %d 行，需整体转换）" % (md_path(file_path), len(endofline_rows))
                )
                lines.append("")
                continue
            if endofline_rows:
                lines.append(
                    "#### %s（ENDOFLINE 共 %d 行需整体转换；另 %d 处见下表）"
                    % (md_path(file_path), len(endofline_rows), len(other_rows))
                )
            else:
                lines.append("#### %s（%d 处）" % (md_path(file_path), len(file_rows)))
            lines.append("")
            lines.append("| 行:列 | 诊断 | 说明 | 代码 |")
            lines.append("|-------|------|------|------|")
            for row in sorted(other_rows, key=lambda item: (item["line"], item["col"])):
                lines.append(
                    "| %d:%d | `%s` | %s | `%s` |"
                    % (row["line"], row["col"], row["diag"], cell(row["msg"]), cell(get_code(row["abs"], row["line"])))
                )
            lines.append("")

    lines.append("## 六、处理方式")
    lines.append("")
    lines.append("### 6.1 自动修复（命名问题不受影响）")
    lines.append("")
    lines.append("```bash")
    lines.append(
        'python scripts/dotnet_format.py fix --path "%s"' % info["display"]
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "> `fix` 会直接改写源码，执行前请确认工作区干净或先提交；执行后用 `git diff` 审阅。"
        "命名问题需 `scripts/rename_symbol.py`（默认 dry-run）或人工处理。"
    )
    lines.append("")

    diag_ids = sorted(diag_counts) if diag_counts else []
    if diag_ids:
        lines.append("### 6.2 忽略模板")
        lines.append("")
        lines.append("若本模块暂不处理，可在项目根 `.editorconfig` 末尾追加：")
        lines.append("")
        lines.append("```ini")
        lines.append("[%s/**/*.cs]" % info["display"])
        for diag in diag_ids:
            if diag in ("ENDOFLINE", "WHITESPACE", "IMPORTS"):
                continue
            lines.append("dotnet_diagnostic.%s.severity = none" % diag)
        lines.append("```")
        lines.append("")
        lines.append(
            "> `ENDOFLINE`、`WHITESPACE`、`IMPORTS` 不是 Roslyn 分析器诊断，"
            "`dotnet_diagnostic.*.severity` 对其无效：行尾需整文件统一，"
            "空白与 using 只能修复或把目录加入 `exclude_dirs`。"
        )
        lines.append("")

    path = os.path.join(out_dir, "01-模块结论", "%s.md" % info["stem"])
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def write_category_page(name, stem, rows_by_module, modules, out_dir, timestamp):
    lines = []
    lines.append("# %s · 全模块汇总" % name)
    lines.append("")
    lines.append("> 本文件按**结果类型**横向汇总，便于一次性处理同类问题。  ")
    lines.append("> 报告时间：%s" % timestamp)
    lines.append("")
    lines.append("## 各模块分布")
    lines.append("")
    lines.append("| 模块 | 问题处数 | 涉及文件数 |")
    lines.append("|------|---------:|-----------:|")
    total = 0
    for info in modules.values():
        module_rows = rows_by_module.get(info["name"], [])
        total += len(module_rows)
        lines.append(
            "| %s | %d | %d |"
            % (info["label"], len(module_rows), len({row["file"] for row in module_rows}))
        )
    lines.append("| **合计** | **%d** | — |" % total)
    lines.append("")

    lines.append("## 明细（按模块 / 文件）")
    lines.append("")
    for info in modules.values():
        module_rows = rows_by_module.get(info["name"], [])
        if not module_rows:
            continue
        lines.append("### %s" % info["label"])
        lines.append("")
        grouped = collections.defaultdict(list)
        for row in module_rows:
            grouped[row["file"]].append(row)
        for file_path in sorted(grouped, key=lambda item: (-len(grouped[item]), item)):
            file_rows = grouped[file_path]
            endofline_rows = [row for row in file_rows if row["diag"] == "ENDOFLINE"]
            other_rows = [row for row in file_rows if row["diag"] != "ENDOFLINE"]
            if endofline_rows and not other_rows:
                lines.append(
                    "- %s（ENDOFLINE 共 %d 行，需整体转换）" % (md_path(file_path), len(endofline_rows))
                )
                continue
            desc = "%d 处" % len(file_rows)
            if endofline_rows:
                desc = "%d 处（含 ENDOFLINE 按行计 %d）" % (len(file_rows), len(endofline_rows))
            lines.append("- %s（%s）" % (md_path(file_path), desc))
            for row in sorted(other_rows, key=lambda item: (item["line"], item["col"]))[:200]:
                lines.append(
                    "  - %d:%d `%s` %s ｜ `%s`"
                    % (row["line"], row["col"], row["diag"], cell(row["msg"]), cell(get_code(row["abs"], row["line"])))
                )
            if len(other_rows) > 200:
                lines.append("  - ……（其余 %d 处见模块文件）" % (len(other_rows) - 200))
        lines.append("")

    path = os.path.join(out_dir, "02-按问题类型汇总", "%s.md" % stem)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def write_overview(out_dir, title, timestamp, modules, rows, project_root, exclude_dirs, log_count):
    total_by_category = collections.Counter()
    for row in rows:
        total_by_category[category_of(row["diag"])] += 1

    lines = []
    lines.append("# %s · 总览" % title)
    lines.append("")
    lines.append("> 检查标准：项目根 `.editorconfig`（命名样式 + whitespace/style 规则）  ")
    lines.append("> 检查工具：`dotnet format`（`whitespace` + `style` 分组，只读校验）  ")
    lines.append("> 报告时间：%s  " % timestamp)
    lines.append("> 数据来源：%d 份 dotnet format 日志（同一文件重复出现的诊断已去重）" % log_count)
    lines.append("")
    lines.append("## 一、模块汇总")
    lines.append("")
    lines.append("| 模块 | 工程数 | 目录内 .cs | 命名问题 | 空白与布局 | using 指令 | 其他风格 | 合计 | 涉及文件 |")
    lines.append("|------|-------:|-------:|--------:|-----------:|-----------:|--------:|-----:|---------:|")
    for info in modules.values():
        module_rows = info["rows"]
        counts = {name: 0 for name in CATEGORIES}
        for row in module_rows:
            counts[category_of(row["diag"])] += 1
        projects = {row["project"] for row in module_rows if row["project"]}
        cs_count = count_cs_files(project_root, info["display"], exclude_dirs)
        lines.append(
            "| [%s](01-模块结论/%s.md) | %d | %d | %d | %d | %d | %d | %d | %d |"
            % (
                info["label"],
                info["stem"],
                len(projects),
                cs_count,
                counts[NAMING],
                counts[LAYOUT],
                counts[USING],
                counts[OTHER],
                len(module_rows),
                len({row["file"] for row in module_rows}),
            )
        )
    lines.append(
        "| **合计** | — | — | **%d** | **%d** | **%d** | **%d** | **%d** | — |"
        % (
            total_by_category[NAMING],
            total_by_category[LAYOUT],
            total_by_category[USING],
            total_by_category[OTHER],
            len(rows),
        )
    )
    lines.append("")
    lines.append(
        "> 「命名 / 空白与布局 / using 指令 / 其他风格」四列对应四类结果；「合计」为四类之和；"
        "「涉及文件」为去重后的源文件数；「工程数」按日志中实际出现诊断的工程统计。"
    )
    lines.append("")

    endofline_by_module = collections.defaultdict(list)
    for row in rows:
        if row["diag"] == "ENDOFLINE":
            name, _, _ = module_of(row["file"])
            endofline_by_module[name].append(row)
    if endofline_by_module:
        lines.append("### 行尾（ENDOFLINE）不合规统计")
        lines.append("")
        lines.append(
            "`ENDOFLINE` 按行计数（每个不合规行算一处），「空白与布局」一列会被显著放大；"
            "实际影响的是整份文件的换行符，需按文件整体转换："
        )
        lines.append("")
        lines.append("| 模块 | 行尾不合规的文件数 | 涉及总行数 |")
        lines.append("|------|------------------:|-----------:|")
        for info in modules.values():
            module_rows = endofline_by_module.get(info["name"])
            if not module_rows:
                continue
            lines.append(
                "| %s | %d | %d |"
                % (info["label"], len({row["file"] for row in module_rows}), len(module_rows))
            )
        lines.append("")

    lines.append("## 二、结论")
    lines.append("")
    total_projects = len({row["project"] for row in rows if row["project"]})
    total_cs = sum(count_cs_files(project_root, info["display"], exclude_dirs) for info in modules.values())
    lines.append(
        "- 本次共汇总 %d 个模块、%d 个工程、约 %d 个源文件，发现 **%d 处**不符合 `.editorconfig` 的问题。"
        % (len(modules), total_projects, total_cs, len(rows))
    )
    clean = [info["label"] for info in modules.values() if not info["rows"]]
    if clean:
        lines.append("- 完全合规的模块：%s。" % "、".join(clean))
    worst = max(modules.values(), key=lambda item: len(item["rows"]))
    lines.append(
        "- 问题最集中的模块是 **%s**（%d 处，其中命名问题 %d 处）。"
        % (
            worst["label"],
            len(worst["rows"]),
            sum(1 for row in worst["rows"] if row["diag"] == "IDE1006"),
        )
    )
    lines.append(
        "- 命名问题（IDE1006）无法由 dotnet format 自动修复，可用 `scripts/rename_symbol.py` "
        "批量重命名（默认 dry-run，只采用 warning/error 级规则）；空白、using 与其他风格类可由 `dotnet format` 自动修复。"
    )
    lines.append("")

    lines.append("## 三、目录结构")
    lines.append("")
    lines.append("```")
    lines.append("%s/" % os.path.basename(os.path.abspath(out_dir)))
    lines.append("├── 00-总览.md                     本文件")
    lines.append("├── 01-模块结论/                   每个模块一个文件，内含按结果类型分类的小节")
    for info in modules.values():
        lines.append("│   ├── %s.md" % info["stem"])
    lines.append("└── 02-按问题类型汇总/             横向汇总，便于同类问题一次性处理")
    for _, stem in CATEGORY_STEMS:
        lines.append("    ├── %s.md" % stem)
    lines.append("```")
    lines.append("")

    lines.append("## 四、检查范围说明")
    lines.append("")
    lines.append("**纳入检查**：日志中出现的全部 C# 源文件，按路径归入 `Assets/<域>`、`Packages/<包>` 模块；" )
    lines.append("Unity 忽略目录（`<包>/<X>~/`，如样例工程）按独立模块统计。")
    lines.append("")
    if exclude_dirs:
        lines.append("**排除（既不检查也不修改，来自项目配置 `format_checker.config`）**：")
        lines.append("")
        lines.append("| 路径 |")
        lines.append("|------|")
        for item in exclude_dirs:
            lines.append("| `%s` |" % item)
        lines.append("")

    lines.append("## 五、建议处理顺序")
    lines.append("")
    lines.append(
        "1. **先做机械性修复（风险最低）**：`dotnet format` 可同时处理行尾、空格、换行与 using 排序；"
        "整文件行尾转换在提交时会被 git 归一化，不产生无关 diff。"
    )
    lines.append(
        "2. **再逐模块评估其他风格（IDE 系列）**：多为括号、类型名、对象初始化器等偏好，"
        "自动修复会大范围改写，建议单模块执行并逐笔审阅。"
    )
    lines.append(
        "3. **最后处理命名问题（IDE1006）**：可用 `scripts/rename_symbol.py --dry-run` 出清单后分批落盘，"
        "或按模块在 `.editorconfig` 中降低该诊断级别。"
    )
    lines.append("")
    lines.append("> 逐模块处理时，直接打开 `01-模块结论/<模块>.md`，文末附有该模块的忽略模板与修复命令。")

    with open(os.path.join(out_dir, "00-总览.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


CATEGORY_STEMS = [
    (NAMING, "命名问题-IDE1006"),
    (LAYOUT, "空白与布局"),
    (USING, "using指令"),
    (OTHER, "其他风格-IDE系列"),
]


def main():
    parser = argparse.ArgumentParser(
        description="解析 dotnet format 日志并生成模块化 Markdown 报告",
        epilog="示例：python scripts/format_report.py --log a.log --log b.log --out <目录>",
    )
    parser.add_argument("--log", action="append", required=True, help="dotnet format 日志路径（可多次指定）")
    parser.add_argument(
        "--out",
        default=None,
        help="报告输出目录（默认：项目侧产物目录 report_logs/<时间戳>，经索引定位）",
    )
    parser.add_argument("--project-root", default=None, help="项目根（默认自当前目录向上查找 .editorconfig）")
    parser.add_argument("--title", default="代码规范检查结论", help="报告标题")
    parser.add_argument("--config", default=None, help="format_checker 配置文件路径（默认经索引定位）")
    args = parser.parse_args()

    project_root = args.project_root or find_project_root(os.getcwd())
    if not project_root:
        print("[错误] 未找到项目根（含 .editorconfig 的目录），请用 --project-root 指定", file=sys.stderr)
        return 3

    exclude_dirs = []
    if args.config:
        try:
            with open(args.config, "r", encoding="utf-8") as handle:
                exclude_dirs = [
                    item for item in json.load(handle).get("exclude_dirs", []) if isinstance(item, str) and item
                ]
        except (OSError, ValueError) as error:
            print("[错误] 配置读取失败：%s（%s）" % (args.config, error), file=sys.stderr)
            return 3
    else:
        exclude_dirs = read_exclude_dirs(project_root)

    all_rows = []
    for log_path in args.log:
        all_rows.extend(parse_log(log_path, project_root))
    all_rows = dedupe(all_rows)
    if not all_rows:
        raise ReportError("日志中未解析到任何诊断")

    # 先按空前缀构建以取得包名（含忽略目录的父包），再求公共前缀生成短名
    preliminary = build_modules(all_rows, "")
    package_names = []
    for info in preliminary.values():
        if info["kind"] == "package":
            package_names.append(info["name"])
        elif info["kind"] == "ignored-dir":
            package_names.append(info["name"].split("/", 1)[0])
    modules = build_modules(all_rows, common_package_prefix(package_names))

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out_dir = args.out or default_out_dir(project_root, datetime.datetime.now().strftime("%Y%m%d%H%M%S"))

    os.makedirs(os.path.join(out_dir, "01-模块结论"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "02-按问题类型汇总"), exist_ok=True)

    for info in modules.values():
        write_module_page(info, out_dir, args.title, timestamp, project_root, exclude_dirs)

    for category, stem in CATEGORY_STEMS:
        rows_by_module = collections.defaultdict(list)
        for info in modules.values():
            rows_by_module[info["name"]] = [
                row for row in info["rows"] if category_of(row["diag"]) == category
            ]
        write_category_page(category, stem, rows_by_module, modules, out_dir, timestamp)

    write_overview(out_dir, args.title, timestamp, modules, all_rows, project_root, exclude_dirs, len(args.log))

    print("报告已生成：%s（模块 %d 个，诊断 %d 处）" % (out_dir, len(modules), len(all_rows)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReportError as error:
        print("[错误] %s" % error, file=sys.stderr)
        sys.exit(1)
