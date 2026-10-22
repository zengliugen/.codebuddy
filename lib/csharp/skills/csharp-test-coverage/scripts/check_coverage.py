#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C# 测试覆盖率检查脚本（Python 入口层）。

调用基于 Roslyn 的 .NET 工具 CSharpTestCoverage 执行静态分析，
可选合并 Unity 真实覆盖率数据，产出 .md + .json 报告。

设计要点（详见 references/）：
  - 静态分析为主：解析运行时成员与 Tests/ 引用的映射，识别零引用成员
  - 真实采集为辅：合并 CodeCoverage/Report/Summary.json，标出分歧项
  - 骨架默认不生成：扫描完成后打印提示，需用户确认后另走 generate_skeletons.py
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime

# 在 Windows 上设置控制台代码页为 UTF-8，解决中文输出乱码问题
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
TOOL_DIR = os.path.join(SKILL_DIR, "tools", "CSharpTestCoverage")
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))

sys.path.insert(0, SCRIPT_DIR)
import skill_config  # noqa: E402  项目相关内容统一从覆盖率配置读取，脚本不硬编码

CONFIG_PATH = skill_config.config_path()


def log(message):
    """输出进度信息。

    注意：`--json` 模式下 stdout 必须只有 JSON，故进度信息一律写 stderr，
    保证 `check_coverage.py --json > out.json` 可直接管道消费。
    """
    sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), message))
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# .NET 工具构建
# ---------------------------------------------------------------------------

def compute_source_hash():
    """计算工具源码哈希，用于判断是否需要重新构建。

    只对 .cs / .csproj / .json 计算，跳过 bin/obj/publish 目录。
    """
    sha = hashlib.sha256()
    skip_dirs = {"bin", "obj", "publish", "__pycache__"}
    for root, dirs, files in os.walk(TOOL_DIR):
        dirs[:] = [d for d in sorted(dirs) if d not in skip_dirs]
        for name in sorted(files):
            if not name.endswith((".cs", ".csproj", ".json")):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as handle:
                    sha.update(os.path.relpath(path, TOOL_DIR).encode("utf-8"))
                    sha.update(handle.read())
            except OSError:
                continue
    return sha.hexdigest()


def is_build_current():
    """判断已发布的工具是否与当前源码一致。"""
    publish_dir = os.path.join(TOOL_DIR, "publish")
    hash_file = os.path.join(publish_dir, ".build_hash")
    if not os.path.isdir(publish_dir) or not os.path.isfile(hash_file):
        return False
    if not find_tool_executable():
        return False
    try:
        with open(hash_file, "r", encoding="utf-8") as handle:
            return handle.read().strip() == compute_source_hash()
    except OSError:
        return False


def build_tool(force=False):
    """执行 dotnet publish 构建工具；返回是否成功。"""
    if not force and is_build_current():
        return True

    log("正在构建静态分析工具（首次运行或源码变更）……")
    try:
        result = subprocess.run(
            ["dotnet", "publish", "-c", "Release", "-o", "publish",
             "--self-contained", "false"],
            cwd=TOOL_DIR, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
            env={**os.environ, "DOTNET_CLI_UI_LANGUAGE": "en"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write("构建失败：%s\n" % exc)
        return False

    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        return False

    publish_dir = os.path.join(TOOL_DIR, "publish")
    os.makedirs(publish_dir, exist_ok=True)
    try:
        with open(os.path.join(publish_dir, ".build_hash"), "w", encoding="utf-8") as handle:
            handle.write(compute_source_hash())
    except OSError:
        pass

    log("工具构建完成。")
    return True


def find_tool_executable():
    """定位已构建的工具可执行文件；返回路径或 None。"""
    candidates = [
        os.path.join(TOOL_DIR, "publish", "CSharpTestCoverage.exe"),
        os.path.join(TOOL_DIR, "publish", "CSharpTestCoverage.dll"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    bin_dir = os.path.join(TOOL_DIR, "bin", "Release")
    if os.path.isdir(bin_dir):
        for target in sorted(os.listdir(bin_dir)):
            for name in ("CSharpTestCoverage.exe", "CSharpTestCoverage.dll"):
                candidate = os.path.join(bin_dir, target, name)
                if os.path.isfile(candidate):
                    return candidate
    return None


# ---------------------------------------------------------------------------
# 执行静态分析
# ---------------------------------------------------------------------------

def run_analysis(targets):
    """调用 .NET 工具执行分析，返回解析后的 CoverageReport；失败返回 None。"""
    if not build_tool():
        sys.stderr.write("错误：静态分析工具构建失败。\n")
        return None

    tool_path = find_tool_executable()
    if not tool_path:
        sys.stderr.write("错误：未找到已构建的工具可执行文件。\n")
        return None

    abs_targets = [os.path.abspath(t) for t in targets]
    if tool_path.endswith(".exe"):
        args = [tool_path] + abs_targets
    else:
        args = ["dotnet", tool_path] + abs_targets

    # 先合并两层配置并落盘，再经 --config 传给工具（工具侧无需感知分层）
    skill_config.load_config()
    args += ["--project-root", PROJECT_ROOT, "--json"]
    if os.path.isfile(CONFIG_PATH):
        args += ["--config", CONFIG_PATH]

    try:
        result = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write("错误：静态分析超时。\n")
        return None
    except OSError as exc:
        sys.stderr.write("错误：无法执行工具 - %s\n" % exc)
        return None

    output = result.stdout or ""
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            sys.stderr.write("%s\n" % line)

    start = output.find("{")
    if start < 0:
        sys.stderr.write("错误：工具未返回有效 JSON。\n")
        return None

    try:
        decoder = json.JSONDecoder()
        report, _ = decoder.raw_decode(output[start:])
        return report
    except (ValueError, TypeError) as exc:
        sys.stderr.write("错误：JSON 解析失败 - %s\n" % exc)
        return None


# ---------------------------------------------------------------------------
# 真实覆盖率合并
# ---------------------------------------------------------------------------

def _summary_json_path():
    """解析真实覆盖率的 Summary.json 路径（取自配置，缺失即报错）。"""
    rel = skill_config.get("realCoverage.reportSummaryJson").strip()
    return rel if os.path.isabs(rel) else os.path.join(PROJECT_ROOT, rel)


def load_real_coverage():
    """加载 Unity 真实覆盖率数据（Summary.json 优先）。

    返回 dict：{ 'loaded': bool, 'summary': {...}, 'classMap': {类型全名: 覆盖率} }
    """
    summary_path = _summary_json_path()
    if not os.path.isfile(summary_path):
        return {"loaded": False}

    try:
        with open(summary_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {"loaded": False}

    class_map = {}
    for assembly in raw.get("coverage", {}).get("assemblies", []):
        for cls in assembly.get("classesinassembly") or []:
            name = cls.get("name")
            if name:
                class_map[name] = {
                    "coverage": cls.get("coverage", 0),
                    "coveredlines": cls.get("coveredlines", 0),
                    "coverablelines": cls.get("coverablelines", 0),
                    "methodcoverage": cls.get("methodcoverage", 0),
                }

    return {
        "loaded": True,
        "path": summary_path,
        "summary": raw.get("summary", {}),
        "assemblies": raw.get("coverage", {}).get("assemblies", []),
        "classMap": class_map,
    }


def merge_real_coverage(report, real):
    """把真实覆盖率数据合并进静态分析结果，并标出分歧。

    **口径说明（重要）**：`Summary.json` 只提供**类级**覆盖率，没有成员级数据。
    因此分歧判定只在**类级**做，且需避免用类级数值去否定单个成员：

      - 仅当类型级「静态判定为已覆盖的成员数 == 0」但真实类覆盖率 > 0 时，
        标为 static_uncovered_real_covered（整类静态判无引用、实际有执行）
      - 仅当类型级「全部成员静态判定为已覆盖」但真实类覆盖率为 0 时，
        标为 static_covered_real_uncovered（整类静态判有引用、实际没执行）

    单成员级别的分歧不做判定——类级数值不足以支撑成员级结论，
    强行比对会产生大量假分歧（实测曾达 1223 项）。
    """
    if not real.get("loaded"):
        return {"merged": False}

    class_map = real.get("classMap", {})

    # 按类型聚合静态判定
    type_groups = {}
    for record in report.get("Records", []):
        type_full = record.get("Namespace", "")
        type_name = record.get("TypeName", "")
        full_name = "%s.%s" % (type_full, type_name) if type_full else type_name
        type_groups.setdefault(full_name, []).append(record)

    divergence_count = 0
    real_rated = 0

    for full_name, records in type_groups.items():
        matched = class_map.get(full_name)
        if matched is None:
            for key, value in class_map.items():
                if key.split("[")[0] == full_name:
                    matched = value
                    break
        if matched is None:
            continue

        real_rate = matched.get("coverage", 0)
        real_rated += len(records)

        covered_count = sum(1 for r in records if r.get("CoverageState") == "covered")
        total = len(records)

        # 类级分歧：整类无静态覆盖但真实有覆盖
        if covered_count == 0 and real_rate > 0:
            for record in records:
                record["RealCoverageLineRate"] = real_rate
                record["Divergence"] = "type_static_uncovered_real_covered"
            divergence_count += 1 if records else 0
        # 类级分歧：整类全静态覆盖但真实零覆盖
        elif covered_count == total and total > 0 and real_rate == 0:
            for record in records:
                record["RealCoverageLineRate"] = real_rate
                record["Divergence"] = "type_static_covered_real_uncovered"
            divergence_count += 1
        else:
            for record in records:
                record["RealCoverageLineRate"] = real_rate

    return {
        "merged": True,
        "divergence": divergence_count,
        "real_rated_members": real_rated,
        "granularity": "type",
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def sanitize_summary(summary, max_length=80):
    """清理摘要字符串：去空白、限长、去特殊字符。"""
    sanitized = re.sub(r"\s+", "_", (summary or "").strip())
    sanitized = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9_]", "", sanitized)
    return sanitized[:max_length]


def make_base_name(targets, report, external_summary=None):
    """生成报告文件名主干：{时间戳}_{目标名}_{统计}_{GUID}。"""
    if external_summary:
        name = sanitize_summary(external_summary)
    else:
        first = targets[0] if targets else "coverage"
        name = os.path.basename(os.path.normpath(first)) or "coverage"
        if name.endswith(".cs"):
            name = name[:-3]
        name = sanitize_summary(name.replace(" ", "_"))

    uncovered = report.get("UncoveredCount", 0)
    weak = report.get("WeakOnlyCount", 0)
    stats = "u%dr%d" % (uncovered, weak)

    timestamp = datetime.now().strftime("%Y年%m月%d日_%H时%M分%S秒")
    return "%s_%s_%s_%s" % (timestamp, name, stats, uuid.uuid4().hex[:8])


def format_markdown(report, targets, real_result):
    """生成 Markdown 报告。"""
    lines = []
    lines.append("# C# 测试覆盖率检查报告")
    lines.append("")

    member_count = report.get("MemberCount", 0)
    covered = report.get("CoveredCount", 0)
    weak = report.get("WeakOnlyCount", 0)
    uncovered = report.get("UncoveredCount", 0)
    rate = (100.0 * covered / member_count) if member_count else 0.0

    # --- 检查概览 ---
    lines.append("## 检查概览")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|----|----|")
    lines.append("| 检查时间 | %s |" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("| 检查目标 | %s |" % ", ".join("`%s`" % t for t in targets))
    lines.append("| 数据来源 | 静态分析%s |" % (" + 真实采集（合并）" if real_result.get("merged") else ""))
    lines.append("| 运行时文件数 | %s |" % report.get("RuntimeFileCount", 0))
    lines.append("| 成员总数 | %s |" % member_count)
    lines.append("| 已覆盖（强引用） | %s |" % covered)
    lines.append("| 仅弱引用 | %s |" % weak)
    lines.append("| 未覆盖 | %s |" % uncovered)
    lines.append("| **成员覆盖率** | **%.2f%%** |" % rate)
    lines.append("| 零测试文件数 | %s |" % len(report.get("ZeroTestFiles") or []))
    if report.get("UsedDefaultConfig"):
        lines.append("| 配置 | 未找到配置文件，使用内置默认值 |")
    lines.append("")

    if real_result.get("merged"):
        summary = real_result.get("summary", {})
        lines.append("> **真实采集数据**：行覆盖率 %s%%、方法覆盖率 %s%%（%s 个类）"
                     % (summary.get("linecoverage"), summary.get("methodcoverage"),
                        summary.get("classes")))
        lines.append(">")
        lines.append("> **分支覆盖率不可用**：本项目实测 `numBranchPoints=0`，"
                     "Coverage 包未采集分支数据，报告中不做分支维度结论。")
        lines.append("")

    # --- 按模块分布 ---
    lines.append("## 按模块的覆盖率分布")
    lines.append("")
    lines.append("| 模块 | 成员数 | 已覆盖 | 覆盖率 | 零测试文件数 |")
    lines.append("|------|--------|--------|--------|-------------|")

    modules = {}
    for record in report.get("Records", []):
        rel = record.get("RelativeFile", "")
        parts = rel.split("/")
        if len(parts) >= 2 and parts[0] == "Packages":
            module = parts[1]
        elif len(parts) >= 2 and parts[0] == "Assets":
            module = "%s/%s" % (parts[0], parts[1])
        else:
            module = parts[0] if parts else "(unknown)"
        entry = modules.setdefault(module, {"total": 0, "covered": 0, "files": set(), "zero": set()})
        entry["total"] += 1
        entry["files"].add(rel)
        if record.get("CoverageState") == "covered":
            entry["covered"] += 1

    zero_set = set(report.get("ZeroTestFiles") or [])
    for module, entry in modules.items():
        for rel in entry["files"]:
            if rel in zero_set:
                entry["zero"].add(rel)

    for module in sorted(modules, key=lambda m: modules[m]["covered"] / max(modules[m]["total"], 1)):
        entry = modules[module]
        mrate = 100.0 * entry["covered"] / entry["total"] if entry["total"] else 0.0
        lines.append("| `%s` | %d | %d | %.2f%% | %d |"
                     % (module, entry["total"], entry["covered"], mrate, len(entry["zero"])))
    lines.append("")

    # --- 零测试文件清单 ---
    zero_files = report.get("ZeroTestFiles") or []
    lines.append("## 零测试文件清单（整文件无任何强引用）")
    lines.append("")
    if zero_files:
        lines.append("共 %d 个文件。这类文件优先级最高——整个文件没有任何测试引用。" % len(zero_files))
        lines.append("")
        lines.append("| 文件 |")
        lines.append("|------|")
        for path in zero_files[:200]:
            lines.append("| `%s` |" % path)
        if len(zero_files) > 200:
            lines.append("")
            lines.append("（仅显示前 200 个，完整清单见 JSON 报告的 `ZeroTestFiles` 字段。）")
    else:
        lines.append("无。")
    lines.append("")

    # --- 未覆盖成员清单 ---
    uncovered_records = [r for r in report.get("Records", [])
                         if r.get("CoverageState") == "uncovered"]
    lines.append("## 未覆盖成员清单")
    lines.append("")
    if uncovered_records:
        lines.append("共 %d 个成员无任何强引用。" % len(uncovered_records))
        lines.append("")
        lines.append("| 文件 | 类型 | 成员 | 签名 | 建议落地方式 |")
        lines.append("|------|------|------|------|-------------|")
        # 按文件分组，优先展示已有对应测试文件的（可直接追加 partial），最多 300 条
        ordered = sorted(uncovered_records,
                         key=lambda r: (0 if r.get("CounterpartTestFile") else 1, r.get("RelativeFile", "")))
        for record in ordered[:300]:
            action = record.get("SuggestedAction", "")
            action_label = {
                "append_partial": "追加 partial 专项",
                "new_test_file": "新建镜像测试文件",
                "none": "-",
            }.get(action, action)
            lines.append("| `%s` | %s | `%s` | %s | %s |"
                         % (record.get("RelativeFile"), record.get("MemberKind"),
                            record.get("Member"), record.get("MemberSignature"), action_label))
        if len(uncovered_records) > 300:
            lines.append("")
            lines.append("（仅显示前 300 个，完整清单见 JSON 报告的 `Records` 字段。）")
    else:
        lines.append("无。")
    lines.append("")

    # --- 弱引用清单 ---
    weak_records = [r for r in report.get("Records", [])
                    if r.get("CoverageState") == "weak_reference"]
    lines.append("## 弱引用清单（仅 XML cref / 反射字符串命中）")
    lines.append("")
    if weak_records:
        lines.append("共 %d 个成员仅被弱引用命中——**这类成员需人工确认是否真的被测试**。" % len(weak_records))
        lines.append("")
        lines.append("| 文件 | 类型 | 成员 | 弱引用次数 |")
        lines.append("|------|------|------|-----------|")
        for record in weak_records[:200]:
            lines.append("| `%s` | %s | `%s` | %d |"
                         % (record.get("RelativeFile"), record.get("MemberKind"),
                            record.get("Member"), len(record.get("WeakReferenceSites") or [])))
    else:
        lines.append("无。")
    lines.append("")

    # --- 与真实覆盖率的分歧 ---
    if real_result.get("merged"):
        divergences = [r for r in report.get("Records", []) if r.get("Divergence")]
        divergence_types = len({r.get("Divergence") for r in divergences})
        lines.append("## 与真实覆盖率的分歧")
        lines.append("")
        lines.append("> **口径**：`Summary.json` 仅提供**类级**覆盖率，无成员级数据。"
                     "因此分歧只在**类级**判定，单成员分歧不判定——"
                     "用类级数值比对成员状态会产生大量假分歧（实测曾达 1223 项）。")
        lines.append("")
        if divergences:
            lines.append("共 %d 个类型存在分歧（涉及 %d 个成员记录）。" % (divergence_types, len(divergences)))
            lines.append("")
            lines.append("| 文件 | 成员 | 静态判定 | 真实类覆盖率 | 说明 |")
            lines.append("|------|------|---------|-------------|------|")
            for record in divergences[:100]:
                if record.get("Divergence") == "type_static_uncovered_real_covered":
                    note = "整类静态判无引用，但真实有覆盖（静态漏识别引用）"
                else:
                    note = "整类静态判有引用，但真实零覆盖（引用未真正执行）"
                lines.append("| `%s` | `%s` | %s | %s%% | %s |"
                             % (record.get("RelativeFile"), record.get("Member"),
                                record.get("CoverageState"),
                                record.get("RealCoverageLineRate"), note))
            if len(divergences) > 100:
                lines.append("")
                lines.append("（仅显示前 100 条。）")
        else:
            lines.append("无分歧项。")
        lines.append("")

    # --- 骨架说明 ---
    lines.append("## 关于测试骨架")
    lines.append("")
    lines.append("本报告**未生成任何骨架文件**。如需为上述未覆盖成员生成测试骨架，"
                 "请在确认后另行执行（见 `SKILL.md` 的骨架生成规则）。")
    lines.append("")
    lines.append("> **重要**：骨架仅为待补完的脚手架（含 `Assert.Inconclusive`），"
                 "**不可当作已补测试提交**。依据 `csharp-test/authoring.mdc`，"
                 "空过的用例比没有用例更危险。")
    lines.append("")

    # --- 统计与说明 ---
    lines.append("## 统计与说明")
    lines.append("")
    lines.append("- 统计口径：`u{未覆盖数}r{弱引用数}`")
    lines.append("- 分母：`public` + `internal` 成员（可在配置中调整）")
    # 豁免清单从项目配置读取，避免报告与实际生效规则脱节
    exclude_desc = "、".join("`%s`" % p for p in skill_config.exclude_paths())
    lines.append("- 豁免：%s 与 auto-generated 文件不计入分母" % exclude_desc)
    lines.append("- 分母口径与扫描范围来自项目配置：`%s`" % os.path.basename(CONFIG_PATH))
    lines.append("- 弱引用（XML `cref`、反射字符串成员名）**不计入已覆盖**，单列供人工确认")
    lines.append("- 生成的测试代码计入分子；生成的运行时代码不计入分母")

    warnings = report.get("Warnings") or []
    if warnings:
        lines.append("")
        lines.append("### 告警")
        lines.append("")
        for warning in warnings[:20]:
            lines.append("- %s" % warning)

    return "\n".join(lines)


def save_results(base_name, markdown, report, output_dir):
    """保存 .md 与 .json 报告，返回路径元组；默认目录经索引 artifacts 定位。"""
    if output_dir is None:
        output_dir = skill_config.resolve_artifact_dir("test_coverage.check_logs")
    os.makedirs(output_dir, exist_ok=True)

    md_path = os.path.join(output_dir, base_name + ".md")
    json_path = os.path.join(output_dir, base_name + ".json")

    with open(md_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    return md_path, json_path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def resolve_targets(targets, scope):
    """解析扫描目标：显式路径优先，否则按 scope 取默认范围。"""
    if targets:
        resolved = []
        for target in targets:
            path = target if os.path.isabs(target) else os.path.join(PROJECT_ROOT, target)
            if not os.path.exists(path):
                sys.stderr.write("错误：路径不存在 - %s\n" % target)
                sys.exit(1)
            resolved.append(path)
        return resolved

    # 扫描范围从项目配置读取（scanScopes），脚本不硬编码项目目录结构
    selected = skill_config.scan_scope(scope)
    resolved = []
    for relative in selected:
        path = os.path.join(PROJECT_ROOT, relative)
        if os.path.exists(path):
            resolved.append(path)
        else:
            log("跳过不存在的默认路径：%s" % relative)

    if not resolved:
        sys.stderr.write("错误：默认扫描范围内无可用路径。\n")
        sys.exit(1)
    return resolved


def main():
    parser = argparse.ArgumentParser(
        description="C# 测试覆盖率检查（静态分析为主，可合并 Unity 真实采集数据）"
    )
    parser.add_argument("target", nargs="*", help="目标包/目录/文件路径")
    parser.add_argument("--scope", default="all", choices=["all", "packages", "assets"],
                        help="未指定 target 时的默认扫描范围（默认 all）")
    parser.add_argument("--json", action="store_true", help="控制台输出结构化 JSON")
    parser.add_argument("--no-save", action="store_true", help="不保存结果文件")
    parser.add_argument("--output-dir", help="自定义报告输出目录")
    parser.add_argument("--summary", help="自定义报告文件名摘要")
    parser.add_argument("--real-coverage", action="store_true",
                        help="合并 Unity 真实覆盖率数据（需先执行 collect_real_coverage.py）")
    args = parser.parse_args()

    targets = resolve_targets(args.target, args.scope)
    log("检查目标：%s" % ", ".join(os.path.relpath(t, PROJECT_ROOT) for t in targets))

    report = run_analysis(targets)
    if report is None:
        return 1

    real_result = {"merged": False}
    if args.real_coverage:
        real = load_real_coverage()
        if real.get("loaded"):
            real_result = merge_real_coverage(report, real)
            real_result["summary"] = real.get("summary", {})
            log("已合并真实覆盖率数据（分歧项 %s 个）" % real_result.get("divergence", 0))
        else:
            log("未找到真实覆盖率数据（CodeCoverage/Report/Summary.json），跳过合并")

    markdown = format_markdown(report, targets, real_result)

    if args.no_save:
        log("已指定 --no-save，未保存报告文件")
    else:
        base_name = make_base_name(targets, report, args.summary)
        md_path, json_path = save_results(base_name, markdown, report, args.output_dir)
        log("报告已保存：")
        log("  Markdown: %s" % md_path)
        log("  JSON:     %s" % json_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        member_count = report.get("MemberCount", 0)
        covered = report.get("CoveredCount", 0)
        rate = (100.0 * covered / member_count) if member_count else 0.0
        print()
        print("成员总数 %d | 已覆盖 %d | 仅弱引用 %d | 未覆盖 %d | 覆盖率 %.2f%%"
              % (member_count, covered, report.get("WeakOnlyCount", 0),
                 report.get("UncoveredCount", 0), rate))
        print("零测试文件 %d 个" % len(report.get("ZeroTestFiles") or []))
        print()
        print(">>> 是否生成 Test 骨架？默认不生成。")
        print(">>> 如需生成，请确认后执行：python scripts/generate_skeletons.py <报告JSON>")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except skill_config.ConfigError as error:
        # 配置是覆盖率数据的唯一来源：配置不可用即明确报错，不静默回退默认值
        sys.stderr.write("[错误] %s\n" % error)
        sys.exit(3)
