#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C# 注释合规性检查脚本（Python 入口层）。
调用基于 Roslyn 的 .NET 工具 CSharpCommentChecker 执行实际检查。
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
    # 重新初始化 stdout/stderr 以适配新的代码页
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# 技能根目录（相对于本脚本）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TOOL_DIR = os.path.join(SKILL_DIR, "tools", "CSharpCommentChecker")


class ConfigError(RuntimeError):
    """索引或产物目录不可用时抛出；由 CLI 入口转为明确的错误退出。"""


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


def find_project_root(start):
    """自 start 向上查找含 `.codebuddy` 子目录的目录作为项目根；找不到回退为技能目录上三级。"""
    codebuddy_dir = find_codebuddy_dir(start)
    if codebuddy_dir:
        return os.path.dirname(codebuddy_dir)
    return os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))


def resolve_artifact_dir(logical_name):
    """经索引 `artifacts.dirs` 解析运行时产物目录（相对路径基准为项目根），并确保目录存在。

    产物目录位于项目侧 `.codebuddy.project/`（不入库、不随引擎共享）；脚本不再写入技能目录。
    """
    codebuddy_dir = find_codebuddy_dir(SCRIPT_DIR)
    if not codebuddy_dir:
        raise ConfigError("未能定位 .codebuddy 目录（应位于项目根下）")
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
    rel = (index.get("artifacts") or {}).get("dirs", {}).get(logical_name)
    if not isinstance(rel, str) or not rel:
        raise ConfigError("索引缺少产物目录项 `artifacts.dirs.%s`：%s" % (logical_name, index_path))
    if os.path.isabs(rel):
        raise ConfigError("索引 `artifacts.dirs.%s` 必须为相对路径（当前为绝对路径）：%s"
                          % (logical_name, rel))
    path = os.path.normpath(os.path.join(os.path.dirname(codebuddy_dir), rel))
    os.makedirs(path, exist_ok=True)
    return path



def _sanitize_summary(summary, max_length=80):
    """清理 summary 字符串：去空格、限制长度、去除特殊字符。"""
    sanitized = re.sub(r'\s+', '_', summary.strip())
    sanitized = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9_]', '', sanitized)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def generate_summary(target_paths, results, external_summary=None):
    """根据目标路径和检查结果生成分析摘要。

    若提供了 external_summary，则清理后直接使用；
    否则使用第一个路径的 basename 自动生成。
    """
    if external_summary:
        external_name = _sanitize_summary(external_summary)
        errors = sum(1 for r in results if r.get("Severity") == "error")
        warnings = sum(1 for r in results if r.get("Severity") == "warning")
        infos = sum(1 for r in results if r.get("Severity") == "info")
        issue_summary = f"e{errors}w{warnings}"
        if infos > 0:
            issue_summary += f"i{infos}"
        return f"{external_name}_{issue_summary}"

    target_name = os.path.basename(os.path.abspath(target_paths[0])) or os.path.basename(
        os.path.dirname(os.path.abspath(target_paths[0]))
    )

    # 清理名称中的特殊字符
    safe_name = target_name.replace(".cs", "_cs").replace(" ", "_")

    errors = sum(1 for r in results if r.get("Severity") == "error")
    warnings = sum(1 for r in results if r.get("Severity") == "warning")
    infos = sum(1 for r in results if r.get("Severity") == "info")

    # 构建问题摘要：e{N}w{M} 格式（errors + warnings）
    issue_summary = f"e{errors}w{warnings}"
    if infos > 0:
        issue_summary += f"i{infos}"

    return f"{safe_name}_{issue_summary}"


def save_results(results, target_paths, output_dir=None, summary=None):
    """将检查结果保存到项目侧产物 check_logs 目录（经索引 artifacts 定位）。

    生成两个文件（格式: {时间戳}_{目标名称}_{问题统计}_{8位GUID}.{ext}）：
      - {timestamp}_{summary}_{short_guid}.md  人类可读格式
      - {timestamp}_{summary}_{short_guid}.json  JSON 格式

    summary 参数允许外部指定摘要名称，不指定时自动从路径生成。
    """
    if output_dir is None:
        output_dir = resolve_artifact_dir("comment_checker.check_logs")

    os.makedirs(output_dir, exist_ok=True)

    file_summary = generate_summary(target_paths, results, summary)
    short_guid = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y年%m月%d日%H时%M分%S秒")
    base_name = f"{timestamp}_{file_summary}_{short_guid}"

    # 保存人类可读格式
    md_path = os.path.join(output_dir, f"{base_name}.md")
    md_content = _format_markdown(results, target_paths, summary)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 保存 JSON 格式
    json_path = os.path.join(output_dir, f"{base_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return md_path, json_path


def _format_markdown(results, target_paths, external_summary=None):
    """生成 Markdown 格式的检查报告。"""
    # 构建目标路径显示字符串
    if external_summary:
        target_display = external_summary
    else:
        target_display = "、".join(target_paths)

    if not results:
        return f"# 注释检查报告\n\n**检查目标:** `{target_display}`\n\n**结果:** 所有文件注释检查通过。\n"

    errors = sum(1 for r in results if r.get("Severity") == "error")
    warnings = sum(1 for r in results if r.get("Severity") == "warning")
    infos = sum(1 for r in results if r.get("Severity") == "info")

    lines = [
        f"# 注释检查报告",
        "",
        f"**检查目标:** `{target_display}`",
        f"**检查时间:** {datetime.now().strftime('%Y年%m月%d日%H时%M分%S秒')}",
        f"**问题统计:** {len(results)} 个问题（{errors} 错误, {warnings} 警告, {infos} 提示）",
        "",
        "---",
        "",
    ]

    # 按文件分组
    grouped = {}
    for issue in results:
        file_path = issue.get("File", "")
        grouped.setdefault(file_path, []).append(issue)

    for file_path, issues in sorted(grouped.items()):
        cwd = os.getcwd()
        display_path = file_path
        if file_path.startswith(cwd):
            rel = os.path.relpath(file_path, cwd)
            if len(rel) < len(file_path):
                display_path = rel

        lines.append(f"## {display_path}")
        lines.append("")
        lines.append("| 行号 | 严重程度 | 类别 | 消息 | 成员 |")
        lines.append("|------|---------|------|------|------|")

        for issue in sorted(issues, key=lambda i: i.get("Line", 0)):
            severity = issue.get("Severity", "未知")
            severity_zh = {"error": "错误", "warning": "警告", "info": "提示"}.get(severity, severity)
            member = issue.get("Member", "") or ""
            member_type = issue.get("MemberType", "") or ""
            code_snippet = issue.get("CodeSnippet", "") or ""

            # 合并成员与代码摘要为合理的一列
            if member:
                member_str = f"**{member_type}** {member}"
                # 方法/构造函数：成员名 + 签名摘要
                if member_type in ("method", "constructor") and code_snippet:
                    member_str += f"<br>`{code_snippet}`"
                # 属性/字段：成员名，签名如有差异则补充
                elif member_type in ("property", "event") and code_snippet:
                    member_str += f"<br>`{code_snippet}`"
            else:
                # 无成员名（文件头等）：直接显示代码摘要
                member_str = f"`{code_snippet}`" if code_snippet else "-"

            lines.append(
                f"| {issue.get('Line', '?')} | **{severity_zh}** | "
                f"`{issue.get('Category', '')}` | {issue.get('Message', '')} | {member_str} |"
            )

        lines.append("")

    # 汇总
    lines.append("---")
    lines.append("")

    # 按类别统计
    cat_counts = {}
    for issue in results:
        cat = issue.get("Category", "未知")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    lines.append("## 问题类别分布")
    lines.append("")
    lines.append("| 类别 | 数量 |")
    lines.append("|------|------|")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| `{cat}` | {count} |")

    lines.append("")
    lines.append(f"**需要修复:** {errors} 个错误")
    if warnings > 0:
        lines.append(f"  \n**建议修复:** {warnings} 个警告")
    if infos > 0:
        lines.append(f"  \n**提示信息:** {infos} 个提示")

    return "\n".join(lines) + "\n"


def find_dotnet_tool():
    """查找 .NET 工具的可执行文件路径，优先使用 publish 目录。"""
    # 优先查找 publish 目录
    publish_dir = os.path.join(TOOL_DIR, "publish")
    if os.path.isdir(publish_dir):
        exe_path = os.path.join(publish_dir, "CSharpCommentChecker.exe")
        dll_path = os.path.join(publish_dir, "CSharpCommentChecker.dll")
        if os.path.isfile(exe_path):
            return exe_path
        if os.path.isfile(dll_path):
            return dll_path

    # 回退到 bin/Release 构建输出
    release_dir = os.path.join(TOOL_DIR, "bin", "Release")
    if os.path.isdir(release_dir):
        for tfm in os.listdir(release_dir):
            tfm_path = os.path.join(release_dir, tfm)
            exe_path = os.path.join(tfm_path, "CSharpCommentChecker.exe")
            dll_path = os.path.join(tfm_path, "CSharpCommentChecker.dll")
            if os.path.isfile(exe_path):
                return exe_path
            if os.path.isfile(dll_path):
                return dll_path
    return None


def _compute_source_hash():
    """计算 tools/CSharpCommentChecker 目录下所有源代码文件的 SHA256 哈希。

    仅对 .cs、.csproj、.json 源文件计算哈希，排除 obj、bin、publish 目录。
    返回十六进制字符串。
    """
    sha = hashlib.sha256()
    source_exts = {".cs", ".csproj", ".json"}
    for root, dirs, files in os.walk(TOOL_DIR):
        # 排除构建输出目录
        dirs[:] = [d for d in dirs if d not in ("obj", "bin", "publish")]
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext in source_exts:
                filepath = os.path.join(root, fname)
                with open(filepath, "rb") as f:
                    sha.update(f.read())
    return sha.hexdigest()


def _read_build_hash(publish_dir):
    """读取 publish 目录下记录的上次构建哈希。

    返回哈希字符串，若不存在则返回 None。
    """
    hash_file = os.path.join(publish_dir, ".build_hash")
    if os.path.isfile(hash_file):
        with open(hash_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def _write_build_hash(publish_dir, hash_value):
    """将构建哈希写入 publish 目录。"""
    hash_file = os.path.join(publish_dir, ".build_hash")
    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(hash_value)


def is_build_current():
    """检测 publish 目录中的构建产物是否与最新源代码一致。

    若 publish 目录不存在或哈希不匹配，返回 False（需要重新构建）。
    若哈希匹配，返回 True（构建是最新的）。
    """
    publish_dir = os.path.join(TOOL_DIR, "publish")
    if not os.path.isdir(publish_dir):
        return False

    # 检查输出文件是否存在
    exe_path = os.path.join(publish_dir, "CSharpCommentChecker.exe")
    dll_path = os.path.join(publish_dir, "CSharpCommentChecker.dll")
    if not os.path.isfile(exe_path) and not os.path.isfile(dll_path):
        return False

    # 对比哈希
    current_hash = _compute_source_hash()
    stored_hash = _read_build_hash(publish_dir)
    return current_hash == stored_hash


def build_tool(force=False):
    """构建 .NET 工具（发布到 publish/ 目录）。

    Args:
        force: 是否强制重新构建（即使哈希匹配也要重建）。
    """
    if force:
        print("强制重新构建 CSharpCommentChecker ...", file=sys.stderr)
    else:
        print("检测到代码变更，正在重新构建 CSharpCommentChecker ...", file=sys.stderr)

    env = os.environ.copy()
    env["DOTNET_CLI_UI_LANGUAGE"] = "en"
    result = subprocess.run(
        ["dotnet", "publish", "-c", "Release", "-o", "publish", "--self-contained", "false"],
        cwd=TOOL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )
    if result.returncode != 0:
        print(f"构建失败:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # 写入构建哈希
    current_hash = _compute_source_hash()
    _write_build_hash(os.path.join(TOOL_DIR, "publish"), current_hash)


def run_check(target_paths, exclude_generated):
    """运行 .NET 工具并返回 JSON 结果。"""
    # 检测 publish 目录是否是最新构建
    if not is_build_current():
        build_tool()
    elif not find_dotnet_tool():
        # 哈希匹配但文件丢失（异常情况），强制重建
        build_tool(force=True)

    tool_path = find_dotnet_tool()
    if tool_path is None:
        build_tool(force=True)
        tool_path = find_dotnet_tool()
        if tool_path is None:
            print("错误: 无法找到或构建 CSharpCommentChecker 工具。", file=sys.stderr)
            sys.exit(1)

    # 转换所有路径为绝对路径
    abs_paths = [os.path.abspath(p) for p in target_paths]

    # 优先使用已发布的独立程序，回退到 dotnet run
    if tool_path.endswith(".exe"):
        args = [tool_path] + abs_paths + ["--json"]
    elif tool_path.endswith(".dll"):
        args = ["dotnet", tool_path] + abs_paths + ["--json"]
    else:
        args = ["dotnet", "run", "--project", TOOL_DIR, "-c", "Release", "--",
                *abs_paths, "--json"]

    if exclude_generated:
        args.append("--exclude-generated")

    env = os.environ.copy()
    env["DOTNET_CLI_UI_LANGUAGE"] = "en"
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env)
    if result.returncode != 0:
        print(f"检查失败: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 透传 .NET 工具的信息性日志（如语义分析状态）
    if result.stderr and result.stderr.strip():
        for line in result.stderr.strip().split('\n'):
            print(line.strip(), file=sys.stderr)

    output = result.stdout
    json_start = output.find('[')
    if json_start == -1:
        print(f"无法解析工具输出:\n{output}", file=sys.stderr)
        sys.exit(1)

    # JSON 之前的 stdout 内容作为信息日志输出
    if json_start > 0:
        for line in output[:json_start].strip().split('\n'):
            print(line.strip())

    json_str = output[json_start:]
    return json.loads(json_str)


def format_results(results):
    """格式化输出检查结果。"""
    if not results:
        print("\n✓ 所有文件注释检查通过。")
        return

    errors = sum(1 for r in results if r.get("Severity") == "error")
    warnings = sum(1 for r in results if r.get("Severity") == "warning")
    infos = sum(1 for r in results if r.get("Severity") == "info")

    print(f"\n检查完成: {len(results)} 个问题 ({errors} 错误, {warnings} 警告, {infos} 提示)")
    print("=" * 80)

    grouped = {}
    for issue in results:
        file_path = issue.get("File", "")
        grouped.setdefault(file_path, []).append(issue)

    for file_path, issues in sorted(grouped.items()):
        # 使用相对路径显示（如果可能）
        display_path = file_path
        cwd = os.getcwd()
        if file_path.startswith(cwd):
            rel = os.path.relpath(file_path, cwd)
            if len(rel) < len(file_path):
                display_path = rel

        print(f"\n文件: {display_path}")
        for issue in sorted(issues, key=lambda i: i.get("Line", 0)):
            severity_tag = {"error": "[错误]", "warning": "[警告]", "info": "[提示]"}.get(
                issue.get("Severity"), "[未知]"
            )
            print(f"  行 {issue.get('Line', '?')}: {severity_tag} "
                  f"[{issue.get('Category', '')}] {issue.get('Message', '')}")
            member = issue.get("Member", "")
            member_type = issue.get("MemberType", "")
            if member and member_type:
                print(f"    成员: {member_type} {member}")

    print("\n" + "=" * 80)
    print(f"合计: {len(results)} 个问题 ({errors} 错误, {warnings} 警告, {infos} 提示)")

    # 按严重程度汇总
    if errors > 0:
        print(f"\n需要修复: {errors} 个错误")
    if warnings > 0:
        print(f"建议修复: {warnings} 个警告")
    if infos > 0:
        print(f"提示信息: {infos} 个提示")


def main():
    parser = argparse.ArgumentParser(
        description="C# 注释合规性检查工具。使用 Roslyn 解析 .cs 文件并检查注释。"
    )
    parser.add_argument(
        "target",
        nargs="+",
        help="目标文件路径或目录路径（.cs 文件或包含 .cs 文件的目录），可传入多个"
    )
    parser.add_argument(
        "--exclude-generated", action="store_true",
        help="排除 Generated/ 目录中的文件"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出结果"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="不保存检查结果到文件"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="自定义输出目录（默认: 经索引 artifacts 定位的项目侧 check_logs/）"
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="外部指定的摘要名称，用于生成保存文件的文件名（不指定时自动从路径生成）"
    )

    args = parser.parse_args()

    # 验证所有路径存在
    for target_path in args.target:
        if not os.path.exists(target_path):
            print(f"错误: 路径不存在: {target_path}", file=sys.stderr)
            sys.exit(1)

    results = run_check(args.target, args.exclude_generated)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        format_results(results)

    # 自动保存检查结果
    if not args.no_save:
        md_path, json_path = save_results(results, args.target, args.output_dir, args.summary)
        print(f"\n检查结果已保存:")
        print(f"  Markdown: {md_path}")
        print(f"  JSON:     {json_path}")


if __name__ == "__main__":
    main()
