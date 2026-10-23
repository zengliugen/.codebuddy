#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试骨架生成脚本。

pack-ref-ok: unity-pipeline —— 生成的后续提示按该可选包是否安装分支（未安装提示 dotnet build），不构成硬依赖。

依据 check_coverage.py 产出的 JSON 报告，为未覆盖成员生成测试骨架。

**重要约束**（详见 SKILL.md 与 references/）：
  - 默认不生成、不改动任何文件；必须先经用户确认
  - 骨架仅含 `Assert.Inconclusive`，**不可当作已补测试提交**
  - 已有对应测试类时只能追加 `<测试类名>.<主题>.cs` partial 专项，
    禁止另起 fixture 名（依据 rules/csharp-test/naming-layout.mdc）
  - 写前做 partial 分部成员查重
  - 生成后须编译验证：已安装可选包 unity-pipeline 时经其 recompile，未安装时用 dotnet build（由调用方执行）

用法：
  python generate_skeletons.py <报告.json>                    # 仅打印计划（不写文件）
  python generate_skeletons.py <报告.json> --apply            # 实际写入
  python generate_skeletons.py <报告.json> --apply --limit 20 # 限制生成数量
"""

import argparse
import hashlib
import json
import os
import re
import sys
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
sys.path.insert(0, SCRIPT_DIR)
import skill_config  # noqa: E402  项目相关内容统一从覆盖率配置读取

# 项目根统一取自 skill_config：它用锚点（含 .codebuddy / .git 的目录）向上查找，
# 不依赖技能目录的固定层级。引擎改为 lib/<pack>/skills/ 分层后，固定上三级会定位到
# .codebuddy/lib 而非项目根，导致默认扫描范围与产物路径全部失配。
PROJECT_ROOT = skill_config.PROJECT_ROOT

CONFIG_PATH = skill_config.config_path()


def log(message):
    """输出进度信息。"""
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))


def load_config():
    """读取骨架相关设置；统一经 skill_config 取配置，缺失即报错（不再回退默认值）。"""
    return {
        "threshold": skill_config.skeleton_setting("fileCountThreshold"),
        "inconclusive": skill_config.skeleton_setting("inconclusiveMessage"),
        "todo": skill_config.skeleton_setting("todoMarker"),
    }


def to_pascal(name):
    """把成员名转换为 PascalCase 派生名（用于测试方法名）。"""
    if not name:
        return "Member"
    cleaned = name.lstrip("_")
    if cleaned.startswith(("get_", "set_")):
        cleaned = cleaned[4:]
    parts = re.split(r"[_\s]+", cleaned)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def build_test_method_name(record):
    """由成员信息推导测试方法名。

    重载方法（同名不同签名）必须消歧，否则同一 partial/类内会出现
    重复方法名导致 CS0111 编译错误（实测发生过）。
    消歧依据：签名中的参数个数。
    """
    member = record.get("Member", "")
    kind = record.get("MemberKind", "")
    base = to_pascal(member)
    suffix = build_overload_suffix(record)

    if kind == "constructor" or member == ".ctor":
        return "TestConstructor" + base.replace("Ctor", "") + "Behavior" + suffix
    if kind == "property":
        return "TestProperty" + base + suffix
    if kind == "field":
        return "TestField" + base + suffix
    if kind == "enumvalue":
        return "TestEnumValue" + base + suffix
    if kind == "event":
        return "TestEvent" + base + suffix
    if kind == "operator":
        return "TestOperator" + base + suffix
    return "Test" + base + suffix


def build_overload_suffix(record):
    """为可重载成员生成消歧后缀，避免方法名冲突。

    仅对方法/构造函数/运算符追加（这些才可能重载）。
    后缀由**成员签名的短哈希**构成，保证：
      - 同名同签名（同一成员被重复采集）→ 同名，去重即可
      - 同名不同签名（真重载）→ 不同名，不会 CS0111
    """
    kind = record.get("MemberKind", "")
    if kind not in ("method", "constructor", "operator"):
        return ""

    signature = record.get("MemberSignature", "") or ""
    if not signature:
        return ""

    # 去掉返回值与方法名前缀，只保留参数部分作为消歧依据
    match = re.search(r"\(([^)]*)\)", signature)
    params = match.group(1).strip() if match else ""
    if not params:
        return ""

    digest = hashlib.sha1(params.encode("utf-8")).hexdigest()[:6]
    return "P" + digest


def infer_namespace(test_file_relative, type_name):
    """推导骨架文件的命名空间。

    优先复用**同目录已有测试文件**的命名空间（本项目存在局部约定差异：
    Collections/Managed/** 用完整镜像命名空间，Collections/Memory/** 用短命名空间），
    因此从同目录现有文件学习比机械套规则更可靠。
    无同目录参考时，按包名 + 测试根 + 镜像路径推导。
    """
    directory = os.path.dirname(test_file_relative)
    absolute_dir = os.path.join(PROJECT_ROOT, directory.replace("/", os.sep))
    if os.path.isdir(absolute_dir):
        for name in sorted(os.listdir(absolute_dir)):
            if not name.endswith(".cs"):
                continue
            path = os.path.join(absolute_dir, name)
            try:
                with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                    content = handle.read(4000)
            except OSError:
                continue
            match = re.search(r"^\s*namespace\s+([A-Za-z0-9_.]+)", content, re.MULTILINE)
            if match:
                return match.group(1)

    # 回退：按包名 + 测试根 + 镜像路径推导
    return derive_namespace_from_path(test_file_relative)


def derive_namespace_from_path(test_file_relative):
    """由测试文件路径机械推导命名空间（镜像目录层级）。

    规则（依据 naming-layout.mdc）：
      Packages/<包>/Tests/Editor/<镜像路径>/XxxTests.cs
        → <包命名空间>.Tests.Editor.<镜像路径各段>
    """
    parts = test_file_relative.replace("\\", "/").split("/")

    if len(parts) >= 4 and parts[0] == "Packages":
        package = parts[1]
        # 包名 → 命名空间映射从项目配置读取（namespaceMapping.mappings），
        # 不硬编码项目包名；无匹配映射时回退包名本身。
        mapped_root = skill_config.package_to_namespace(package)
        root = mapped_root if mapped_root else package

        try:
            tests_index = parts.index("Tests")
        except ValueError:
            return root + ".Tests"

        # Tests/ 之后的所有层级（含 Editor|Runtime 与镜像路径）都计入命名空间
        remainder = parts[tests_index + 1:]
        if remainder:
            # 最后一段是文件名，去掉扩展名并去掉 Tests 后缀
            file_stem = os.path.splitext(remainder[-1])[0]
            dirs = remainder[:-1]
            segments = [root, "Tests"] + dirs
            return ".".join(segments) if dirs else ".".join([root, "Tests"])
        return root + ".Tests"

    return "Tests"


def collect_existing_members(directory_absolute):
    """扫描同目录已有测试文件，收集已声明的成员名（用于 partial 查重）。"""
    declared = set()
    if not os.path.isdir(directory_absolute):
        return declared

    for name in sorted(os.listdir(directory_absolute)):
        if not name.endswith(".cs"):
            continue
        path = os.path.join(directory_absolute, name)
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                content = handle.read()
        except OSError:
            continue
        for match in re.finditer(r"\b(?:private|internal|protected|public)?\s*(?:static\s+)?(?:const|readonly)?\s*[A-Za-z0-9_<>,\[\]\.\?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=;(]", content):
            declared.add(match.group(1))
        for match in re.finditer(r"\bvoid\s+(Test[A-Za-z0-9_]*)\s*\(", content):
            declared.add(match.group(1))
    return declared


def build_partial_skeleton(records, test_class, namespace, config):
    """构建 partial 专项骨架文件内容（聚合同一测试类的多个未覆盖成员）。

    按测试类聚合而非按成员拆分：同一专项文件内为每个成员生成一个用例骨架。
    """
    type_name = records[0].get("TypeName", "") if records else ""
    topic = ""
    if records:
        stem = os.path.splitext(os.path.basename(records[0].get("SuggestedSkeletonFile", "")))[0]
        if "." in stem:
            topic = stem.split(".", 1)[1]

    lines = []
    lines.append("/// <file>")
    lines.append("/// %s 的 %s 专项测试骨架（partial 分部）。" % (type_name, topic or "Coverage"))
    lines.append("/// 本文件为覆盖率检查生成的骨架，所有用例均以 Assert.Inconclusive 占位，尚未补完断言；")
    lines.append("/// 覆盖未覆盖成员 %d 个，补断言前不可视为有效测试。" % len(records))
    lines.append("/// </file>")
    lines.append("")
    lines.append("namespace %s" % namespace)
    lines.append("{")
    lines.append("    using NUnit.Framework;")
    lines.append("    using System;")
    lines.append("")
    lines.append("    /// <summary>")
    lines.append("    /// %s 测试套件的 %s 专项分部。" % (test_class, topic or "Coverage"))
    lines.append("    /// </summary>")
    lines.append("    public partial class %s" % test_class)
    lines.append("    {")

    for record in records:
        member = record.get("Member", "")
        signature = record.get("MemberSignature", "")
        method_name = build_test_method_name(record)

        lines.append("        /// <summary>")
        lines.append("        /// 用例：验证 %s 的行为。" % member)
        lines.append("        /// </summary>")
        lines.append("        /// <remarks>")
        lines.append("        /// %s（签名：%s）。" % (config["todo"], signature))
        lines.append("        /// </remarks>")
        lines.append("        [Test]")
        lines.append("        public void %s()" % method_name)
        lines.append("        {")
        lines.append("            // %s：构造被测对象并补断言（当前为骨架，未覆盖任何真实断言）" % config["todo"])
        lines.append("")
        lines.append("            Assert.Inconclusive(\"%s\");" % config["inconclusive"])
        lines.append("        }")
        lines.append("")

    lines.append("    }")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def build_new_file_skeleton(records, test_file_relative, test_class, namespace, config):
    """构建新建镜像测试文件的骨架内容（聚合该文件下所有未覆盖成员）。"""
    type_name = records[0].get("TypeName", "") if records else ""
    runtime_file = records[0].get("RelativeFile", "") if records else ""

    lines = []
    lines.append("/// <file>")
    lines.append("/// %s 的 NUnit 测试集合（覆盖率检查生成的骨架）。" % type_name)
    lines.append("/// 对应运行时文件：%s。" % runtime_file)
    lines.append("/// 本文件为骨架，所有用例均以 Assert.Inconclusive 占位，尚未补完断言，")
    lines.append("/// 补断言前不可视为有效测试。")
    lines.append("/// </file>")
    lines.append("")
    lines.append("namespace %s" % namespace)
    lines.append("{")
    lines.append("    using NUnit.Framework;")
    lines.append("    using System;")
    lines.append("")
    lines.append("    /// <summary>")
    lines.append("    /// %s 的测试套件。" % type_name)
    lines.append("    /// </summary>")
    lines.append("    public class %s" % test_class)
    lines.append("    {")

    for record in records:
        member = record.get("Member", "")
        signature = record.get("MemberSignature", "")
        method_name = build_test_method_name(record)

        lines.append("        /// <summary>")
        lines.append("        /// 用例：验证 %s 的行为。" % member)
        lines.append("        /// </summary>")
        lines.append("        /// <remarks>")
        lines.append("        /// %s（签名：%s）。" % (config["todo"], signature))
        lines.append("        /// </remarks>")
        lines.append("        [Test]")
        lines.append("        public void %s()" % method_name)
        lines.append("        {")
        lines.append("            // %s：构造被测对象并补断言（当前为骨架，未覆盖任何真实断言）" % config["todo"])
        lines.append("")
        lines.append("            Assert.Inconclusive(\"%s\");" % config["inconclusive"])
        lines.append("        }")
        lines.append("")

    lines.append("    }")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def plan_skeletons(report, limit=0):
    """规划骨架生成：返回计划条目列表。"""
    records = report.get("Records", [])

    # 只处理有建议动作的未覆盖成员
    targets = [r for r in records
               if r.get("CoverageState") == "uncovered"
               and r.get("SuggestedAction") in ("append_partial", "new_test_file")
               and r.get("SuggestedSkeletonFile")]

    # 按建议文件聚合
    grouped = {}
    for record in targets:
        grouped.setdefault(record["SuggestedSkeletonFile"], []).append(record)

    plan = []
    for skeleton_file in sorted(grouped):
        group = grouped[skeleton_file]
        action = group[0].get("SuggestedAction")
        plan.append({
            "skeleton_file": skeleton_file,
            "action": action,
            "records": group,
            "member_count": len(group),
        })

    if limit > 0:
        plan = plan[:limit]

    return plan


def derive_test_class(skeleton_file, fallback_type_name):
    """由骨架文件路径推导测试类名（类名 = 文件名主干，去掉专项段）。"""
    stem = os.path.splitext(os.path.basename(skeleton_file))[0]
    if "." in stem:
        stem = stem.split(".")[0]
    return stem or (fallback_type_name + "Tests")


def apply_plan(plan, config):
    """执行骨架写入；返回写入结果列表。"""
    results = []

    for item in plan:
        skeleton_file = item["skeleton_file"]
        absolute = os.path.join(PROJECT_ROOT, skeleton_file.replace("/", os.sep))
        directory = os.path.dirname(absolute)

        # 本次计划内的方法名重名自检（重载消歧失败时会在编译期报 CS0111）
        planned_names = {}
        intra_conflicts = []
        for record in item["records"]:
            method_name = build_test_method_name(record)
            if method_name in planned_names:
                intra_conflicts.append(method_name)
            planned_names[method_name] = record.get("MemberSignature", "")

        # partial 成员查重（与同目录既有文件比对）
        existing = collect_existing_members(directory)
        conflicts = list(intra_conflicts)
        for record in item["records"]:
            method_name = build_test_method_name(record)
            if method_name in existing:
                conflicts.append(method_name)

        if intra_conflicts:
            results.append((skeleton_file, "aborted_intra_conflict", 0, conflicts))
            continue

        os.makedirs(directory, exist_ok=True)

        type_name = item["records"][0].get("TypeName", "Target")
        test_class = derive_test_class(skeleton_file, type_name)
        namespace = infer_namespace(skeleton_file, type_name)

        if item["action"] == "append_partial":
            content = build_partial_skeleton(
                item["records"], test_class, namespace, config)
            # partial 专项文件若已存在则不覆盖（保守策略）
            if os.path.exists(absolute):
                results.append((skeleton_file, "skipped_exists", len(item["records"]), conflicts))
                continue
        else:
            content = build_new_file_skeleton(
                item["records"], skeleton_file, test_class, namespace, config)
            if os.path.exists(absolute):
                results.append((skeleton_file, "skipped_exists", len(item["records"]), conflicts))
                continue

        try:
            with open(absolute, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            results.append((skeleton_file, "written", len(item["records"]), conflicts))
        except OSError as exc:
            results.append((skeleton_file, "failed:%s" % exc, 0, conflicts))

    return results


def main():
    parser = argparse.ArgumentParser(description="为未覆盖成员生成测试骨架")
    parser.add_argument("report", help="check_coverage.py 产出的 JSON 报告路径")
    parser.add_argument("--apply", action="store_true",
                        help="实际写入骨架文件（缺省仅打印计划）")
    parser.add_argument("--limit", type=int, default=0,
                        help="限制生成的骨架文件数（0 表示不限）")
    parser.add_argument("--out-log", help="将计划/结果清单写入指定文件")
    args = parser.parse_args()

    if not os.path.isfile(args.report):
        sys.stderr.write("错误：报告文件不存在 - %s\n" % args.report)
        return 1

    try:
        with open(args.report, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError) as exc:
        sys.stderr.write("错误：报告解析失败 - %s\n" % exc)
        return 1

    config = load_config()
    plan = plan_skeletons(report, args.limit)

    if not plan:
        log("报告中无可生成骨架的未覆盖成员（或均无建议骨架路径）。")
        return 0

    total_members = sum(item["member_count"] for item in plan)
    log("骨架规划：%d 个文件，覆盖 %d 个未覆盖成员" % (len(plan), total_members))

    lines = []
    lines.append("骨架规划清单（%d 个文件 / %d 个成员）" % (len(plan), total_members))
    lines.append("")
    for item in plan:
        action_label = "追加 partial 专项" if item["action"] == "append_partial" else "新建镜像测试文件"
        lines.append("  [%s] %s（%d 个成员）"
                     % (action_label, item["skeleton_file"], item["member_count"]))
        for record in item["records"][:5]:
            lines.append("      - %s %s" % (record.get("MemberKind"), record.get("Member")))
        if item["member_count"] > 5:
            lines.append("      - ...（其余 %d 个）" % (item["member_count"] - 5))

    for line in lines:
        print(line)

    if args.out_log:
        try:
            with open(args.out_log, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + "\n")
            log("清单已写入：%s" % args.out_log)
        except OSError as exc:
            sys.stderr.write("清单写入失败：%s\n" % exc)

    print()
    print("> **重要**：骨架仅含 Assert.Inconclusive 占位，**不可当作已补测试提交**。")
    print("> 依据 csharp-test/authoring.mdc，空过的用例比没有用例更危险。")

    if len(plan) > config["threshold"]:
        print()
        print("!! 待生成文件数 %d 超过阈值 %d，需二次确认。"
              % (len(plan), config["threshold"]))
        print("!! 可用 --limit <N> 限制数量，或确认全部生成。")

    if not args.apply:
        print()
        log("当前为计划模式，未写入任何文件。确认后加 --apply 执行。")
        return 0

    if len(plan) > config["threshold"] and not args.limit:
        print()
        sys.stderr.write("已阻止写入：文件数超过阈值且未指定 --limit。"
                         "请显式加 --limit <N> 或调高阈值。\n")
        return 2

    print()
    log("开始写入骨架……")
    results = apply_plan(plan, config)

    written = [r for r in results if r[1] == "written"]
    skipped = [r for r in results if r[1] == "skipped_exists"]
    failed = [r for r in results if r[1].startswith("failed") or r[1] == "aborted_intra_conflict"]
    conflicts = [r for r in results if r[3]]

    log("写入完成：成功 %d / 跳过 %d / 失败 %d" % (len(written), len(skipped), len(failed)))

    for path, status, count, conflict_list in results:
        if status == "written":
            log("  已写入 %s（%d 个骨架用例）" % (path, count))
        elif status == "skipped_exists":
            log("  已跳过（文件已存在）%s" % path)
        elif status == "aborted_intra_conflict":
            log("  已中止（计划内方法名重复）%s" % path)
        else:
            log("  失败 %s：%s" % (path, status))

    if conflicts:
        print()
        print("!! 检测到 partial 分部成员重名（需人工改名后重生成）：")
        for path, status, count, conflict_list in conflicts:
            print("   %s: %s" % (path, ", ".join(conflict_list)))

    print()
    print(">>> 后续必做：编译验证（按 unity-pipeline 安装状态二选一）")
    # 项目根统一经 skill_config 定位（不依赖技能目录层级），与 collect_real_coverage.py 保持一致
    unity_wait_py = os.path.join(
        PROJECT_ROOT, ".codebuddy", "skills", "unity-pipeline", "unity-pipeline",
        "scripts", "unity_wait.py",
    )
    if os.path.isfile(unity_wait_py):
        print(">>> [已安装 unity-pipeline]")
        print(">>>   unity command script recompile")
        print(">>>   python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_wait.py "
              "--command \"script recompile_status\"")
        print(">>> 确认 failed=false、errors=[] 后方可进入补断言阶段。")
    else:
        print(">>> [未安装可选包 unity-pipeline] 降级为 dotnet build：")
        print(">>>   dotnet build <包含 Tests/ 的解决方案或工程>")
        print(">>> 编译通过后方可进入补断言阶段；报告中标注「未经 unity-pipeline 校验」。")

    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except skill_config.ConfigError as error:
        # 配置是骨架生成参数的唯一来源：配置不可用即明确报错，不静默回退默认值
        sys.stderr.write("[错误] %s\n" % error)
        sys.exit(3)
