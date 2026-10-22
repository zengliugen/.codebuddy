#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unity 覆盖率结果解析脚本。

优先解析配置 `realCoverage.reportSummaryJson` 指向的 Summary.json（ReportGenerator 产出），
该文件结构稳定且信息完整；当 Summary.json 缺失时回退解析配置 `realCoverage.openCoverRoot`
目录下的 `**/TestCoverageResults_*.xml`（OpenCover 格式）。
两处路径均由 `coverage_config.json` 声明，脚本不硬编码项目专属目录名。

实测事实（见 references/real-coverage-guide.md）：
  - 分支覆盖率在本项目实测恒为 0（numBranchPoints="0"），报告中须标注不可用。
  - OpenCover 目录下 0000 为全集（visitedSequencePoints=0），
    0001 为仅有执行的方法（CoveredMethodsOnly），统计须用 0000 做分母。

用法：
  python parse_unity_coverage.py                       # 自动发现产物并输出摘要
  python parse_unity_coverage.py --json                # 输出结构化 JSON
  python parse_unity_coverage.py --report <路径>       # 指定 Report 目录或 Summary.json
  python parse_unity_coverage.py --out <文件>          # 落盘 JSON
"""

import argparse
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

if sys.platform == "win32":
    import ctypes as _ctypes
    try:
        _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        _ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
sys.path.insert(0, SCRIPT_DIR)
import skill_config  # noqa: E402  框架包前缀等统一从配置读取

def _resolve_path(configured):
    """把配置中的产物路径解析为绝对路径（相对项目根）。

    `realCoverage.*` 是覆盖率产物的**唯一来源**（如 OpenCover 输出目录含解决方案名），
    脚本不硬编码任何项目名、也不提供默认路径；配置缺失会在取值时抛出 ConfigError。
    """
    rel = configured.strip()
    return rel if os.path.isabs(rel) else os.path.join(PROJECT_ROOT, rel)


def coverage_artifact_dirs():
    """解析报告目录与 OpenCover 目录（均取自配置，缺失即报错）。"""
    report_dir = os.path.dirname(
        _resolve_path(skill_config.get("realCoverage.reportSummaryJson"))
    )
    opencov_dir = _resolve_path(skill_config.get("realCoverage.openCoverRoot"))
    return report_dir, opencov_dir


def log(message):
    """输出进度信息到 stderr，避免污染 stdout 的 JSON 结果。"""
    sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), message))


def parse_summary_json(path):
    """解析 ReportGenerator 的 Summary.json。

    返回统一结构 dict；失败返回 None。
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        log("解析 Summary.json 失败：%s" % exc)
        return None

    summary = raw.get("summary", {})
    coverage = raw.get("coverage", {})
    assemblies_raw = coverage.get("assemblies", [])

    assemblies = []
    for item in assemblies_raw:
        classes = []
        for cls in item.get("classesinassembly") or []:
            classes.append({
                "Name": cls.get("name", ""),
                "Coverage": cls.get("coverage", 0),
                "CoveredLines": cls.get("coveredlines", 0),
                "CoverableLines": cls.get("coverablelines", 0),
                "TotalLines": cls.get("totallines", 0),
                "MethodCoverage": cls.get("methodcoverage", 0),
                "CoveredMethods": cls.get("coveredmethods", 0),
                "TotalMethods": cls.get("totalmethods", 0),
            })
        assemblies.append({
            "Name": item.get("name", ""),
            "Classes": item.get("classes", 0),
            "Coverage": item.get("coverage", 0),
            "CoveredLines": item.get("coveredlines", 0),
            "CoverableLines": item.get("coverablelines", 0),
            "TotalLines": item.get("totallines", 0),
            "MethodCoverage": item.get("methodcoverage", 0),
            "CoveredMethods": item.get("coveredmethods", 0),
            "TotalMethods": item.get("totalmethods", 0),
            "ClassesInAssembly": classes,
        })

    result = {
        "Source": "Summary.json",
        "SourcePath": path,
        "GeneratedOn": summary.get("generatedon"),
        "Parser": summary.get("parser"),
        "AssemblyCount": summary.get("assemblies", len(assemblies)),
        "ClassCount": summary.get("classes", 0),
        "FileCount": summary.get("files", 0),
        "CoveredLines": summary.get("coveredlines", 0),
        "UncoveredLines": summary.get("uncoveredlines", 0),
        "CoverableLines": summary.get("coverablelines", 0),
        "TotalLines": summary.get("totallines", 0),
        "LineCoverage": summary.get("linecoverage", 0),
        "CoveredMethods": summary.get("coveredmethods", 0),
        "TotalMethods": summary.get("totalmethods", 0),
        "MethodCoverage": summary.get("methodcoverage", 0),
        "CoveredBranches": summary.get("coveredbranches", 0),
        "TotalBranches": summary.get("totalbranches", 0),
        "AssemblyFilterActive": True,
        "Assemblies": assemblies,
    }
    return result


def parse_opencov_xml(path):
    """解析单个 OpenCover XML，返回模块级统计列表。"""
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        log("解析 OpenCover XML 失败 %s：%s" % (os.path.basename(path), exc))
        return None

    root = tree.getroot()
    modules = []
    for module in root.findall("./Modules/Module"):
        name_node = module.find("ModuleName")
        summary_node = module.find("Summary")
        if summary_node is None:
            continue
        num_points = int(summary_node.get("numSequencePoints", "0"))
        visited = int(summary_node.get("visitedSequencePoints", "0"))
        modules.append({
            "Name": name_node.text if name_node is not None else "",
            "NumSequencePoints": num_points,
            "VisitedSequencePoints": visited,
            "SequenceCoverage": float(summary_node.get("sequenceCoverage", "0") or 0),
            "NumMethods": int(summary_node.get("numMethods", "0")),
            "VisitedMethods": int(summary_node.get("visitedMethods", "0")),
            "NumClasses": int(summary_node.get("numClasses", "0")),
            "VisitedClasses": int(summary_node.get("visitedClasses", "0")),
        })
    return modules


def parse_opencov_dir(base_dir):
    """汇总 OpenCover 目录下的覆盖率数据。

    0000 文件为全集（分母），0001 为 CoveredMethodsOnly（分子），
    两者按模块名合并；以 0000 的序列点数为分母。
    """
    pattern = os.path.join(base_dir, "**", "TestCoverageResults_*.xml")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        return None

    # 区分全集与已覆盖集合：文件名尾号 0000 视作全集
    full_sets = [f for f in files if re.search(r"_0000\.xml$", f)]
    covered_sets = [f for f in files if not re.search(r"_0000\.xml$", f)]

    if not full_sets:
        log("未找到全集文件（*_0000.xml），以全部文件作为数据源")
        full_sets = files
        covered_sets = []

    full_modules = {}
    for path in full_sets:
        for module in parse_opencov_xml(path) or []:
            full_modules[module["Name"]] = module

    covered_modules = {}
    for path in covered_sets:
        for module in parse_opencov_xml(path) or []:
            covered_modules[module["Name"]] = module

    assemblies = []
    total_points = 0
    total_visited = 0
    for name, full in sorted(full_modules.items()):
        covered = covered_modules.get(name, {})
        num_points = full["NumSequencePoints"]
        visited = covered.get("VisitedSequencePoints", 0)
        total_points += num_points
        total_visited += visited
        coverage = round(100.0 * visited / num_points, 2) if num_points else 0.0
        assemblies.append({
            "Name": name,
            "Classes": full["NumClasses"],
            "Coverage": coverage,
            "CoveredLines": visited,
            "CoverableLines": num_points,
            "TotalLines": 0,
            "MethodCoverage": 0,
            "CoveredMethods": covered.get("VisitedMethods", 0),
            "TotalMethods": full["NumMethods"],
            "ClassesInAssembly": [],
        })

    line_coverage = round(100.0 * total_visited / total_points, 2) if total_points else 0.0
    return {
        "Source": "OpenCover XML",
        "SourcePath": base_dir,
        "GeneratedOn": None,
        "Parser": "OpenCoverParser",
        "AssemblyCount": len(assemblies),
        "ClassCount": sum(a["Classes"] for a in assemblies),
        "FileCount": 0,
        "CoveredLines": total_visited,
        "UncoveredLines": total_points - total_visited,
        "CoverableLines": total_points,
        "TotalLines": 0,
        "LineCoverage": line_coverage,
        "CoveredMethods": sum(a["CoveredMethods"] for a in assemblies),
        "TotalMethods": sum(a["TotalMethods"] for a in assemblies),
        "MethodCoverage": 0,
        "CoveredBranches": 0,
        "TotalBranches": 0,
        "AssemblyFilterActive": True,
        "Assemblies": assemblies,
    }


def discover(report_arg):
    """发现覆盖率产物；返回解析结果 dict 或 None。"""
    if report_arg:
        if os.path.isfile(report_arg) and report_arg.endswith(".json"):
            return parse_summary_json(report_arg)
        if os.path.isfile(report_arg):
            return parse_opencov_dir(os.path.dirname(report_arg))
        if os.path.isdir(report_arg):
            summary = os.path.join(report_arg, "Summary.json")
            if os.path.isfile(summary):
                return parse_summary_json(summary)
            return parse_opencov_dir(report_arg)
        log("指定路径不存在：%s" % report_arg)
        return None

    report_dir, opencov_dir = coverage_artifact_dirs()
    summary_path = os.path.join(report_dir, "Summary.json")
    if os.path.isfile(summary_path):
        return parse_summary_json(summary_path)

    if os.path.isdir(opencov_dir):
        log("Summary.json 缺失，回退解析 OpenCover XML")
        return parse_opencov_dir(opencov_dir)

    log("未找到任何覆盖率产物，请先执行 collect_real_coverage.py")
    return None


def format_markdown(result):
    """生成 Markdown 摘要。"""
    lines = []
    lines.append("# Unity 真实覆盖率摘要")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|----|----|")
    lines.append("| 数据来源 | %s |" % result.get("Source"))
    lines.append("| 生成时间 | %s |" % (result.get("GeneratedOn") or "-"))
    lines.append("| 解析器 | %s |" % (result.get("Parser") or "-"))
    lines.append("| 程序集数 | %s |" % result.get("AssemblyCount"))
    lines.append("| 类数 | %s |" % result.get("ClassCount"))
    lines.append("| 可覆盖行 | %s |" % result.get("CoverableLines"))
    lines.append("| 已覆盖行 | %s |" % result.get("CoveredLines"))
    lines.append("| 行覆盖率 | %s%% |" % result.get("LineCoverage"))
    lines.append("| 方法覆盖率 | %s%% |" % result.get("MethodCoverage"))
    lines.append("")
    lines.append("> **分支覆盖率不可用**：本项目实测 `numBranchPoints=0`，"
                 "Coverage 包未采集分支数据，报告中不做分支维度结论。")
    lines.append("")
    lines.append("## 各程序集覆盖率")
    lines.append("")
    lines.append("| 程序集 | 类数 | 已覆盖行 | 可覆盖行 | 行覆盖率 | 方法覆盖率 |")
    lines.append("|--------|------|---------|---------|---------|-----------|")
    for item in sorted(result.get("Assemblies", []), key=lambda x: x.get("Coverage", 0)):
        lines.append(
            "| %s | %s | %s | %s | %s%% | %s%% |"
            % (
                item.get("Name"), item.get("Classes"), item.get("CoveredLines"),
                item.get("CoverableLines"), item.get("Coverage"),
                item.get("MethodCoverage"),
            )
        )
    # 框架包前缀取自项目配置，不硬编码项目名称
    framework_prefix = skill_config.framework_package_prefix()
    framework = [
        a for a in result.get("Assemblies", [])
        if framework_prefix and a.get("Name", "").startswith(framework_prefix)
    ]
    lines.append("")
    lines.append("## 框架包覆盖情况")
    lines.append("")
    if framework:
        lines.append("共 %d 个框架包程序集进入覆盖率统计：" % len(framework))
        lines.append("")
        for item in sorted(framework, key=lambda x: x.get("Coverage", 0)):
            lines.append(
                "- `%s`：%s%%（%s/%s 行）"
                % (item.get("Name"), item.get("Coverage"),
                   item.get("CoveredLines"), item.get("CoverableLines"))
            )
    elif not framework_prefix:
        lines.append("未配置框架包识别前缀（`realCoverage.frameworkPackagePrefix`），"
                     "跳过框架包分组。")
    else:
        lines.append("**未发现任何框架包数据**，说明程序集过滤未生效，"
                     "需检查 IncludeAssemblies 是否含 `%s*`。" % framework_prefix)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="解析 Unity 代码覆盖率产物")
    parser.add_argument("--report", help="Report 目录或 Summary.json 路径")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--out", help="将 JSON 落盘到指定文件")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown 摘要")
    args = parser.parse_args()

    result = discover(args.report)
    if result is None:
        return 1

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        log("JSON 已落盘：%s" % args.out)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(format_markdown(result))
    else:
        print(format_markdown(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except skill_config.ConfigError as error:
        # 配置是覆盖率数据的唯一来源：配置不可用即明确报错，不静默回退默认值
        sys.stderr.write("[错误] %s\n" % error)
        sys.exit(3)
