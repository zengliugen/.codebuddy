#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-test-coverage 触发评估脚本。

验证技能的 description 是否准确匹配预期的触发场景，检测边界误触发与漏触发。

用法：
  python trigger_eval.py            # 人类可读报告
  python trigger_eval.py --json     # 结构化 JSON
退出码：0 无 FP/FN；2 存在 FP/FN。
"""

import argparse
import json
import os
import re
import sys


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

# 触发用例数据为项目专有资产，经索引注册表定位到项目侧（.codebuddy.project/）。
# 默认路径在 main 中延迟解析（显式 --cases 时不触碰索引）；索引缺失或未登记时报错退出。
sys.path.insert(0, SCRIPT_DIR)
import skill_config  # noqa: E402  （同目录共享模块，脚本自包含）


def default_cases_path():
    """经索引 `coverage.trigger_cases` 解析项目侧触发用例文件路径。"""
    return skill_config._resolve_project_config("coverage.trigger_cases", skill_config.PROJECT_ROOT)


def normalize(text):
    """标准化文本：小写、合并空白。"""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def load_cases(cases_path):
    """加载触发测试用例文件。"""
    if not os.path.isfile(cases_path):
        sys.stderr.write("错误：测试用例文件不存在：%s\n" % cases_path)
        sys.exit(1)
    with open(cases_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_description(skill_md_path):
    """从 SKILL.md frontmatter 提取 description。"""
    if not os.path.isfile(skill_md_path):
        sys.stderr.write("错误：SKILL.md 不存在：%s\n" % skill_md_path)
        sys.exit(1)

    with open(skill_md_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                line = line.strip()
                if line.startswith("description:"):
                    return line.split(":", 1)[1].strip().strip("'\"")
    return ""


# 语义关键词分组（任一命中即计分）
COVERAGE_KEYWORDS = [
    "覆盖率", "覆盖", "coverage", "未覆盖", "零测试", "没测试", "没有测试",
    "缺少测试", "无测试", "测试充分", "测试缺口", "未测试", "一条测试",
    "测试引用", "测试骨架", "骨架", "缺失测试",
]
ACTION_KEYWORDS = [
    "检查", "扫描", "找出", "看看", "评估", "统计", "列出", "生成", "跑一次",
    "check", "scan", "find", "review", "分析", "哪些", "哪些代码", "报告",
    "哪些文件", "哪些方法", "哪些成员", "都有哪些",
]
LANGUAGE_KEYWORDS = ["c#", "csharp", ".cs", "cs 文件", "c sharp", "c# 代码"]

# 排除性关键词：命中则说明属于邻近技能领域，不应由本技能触发
EXCLUDE_KEYWORDS = [
    "注释",          # → csharp-comment-checker
    "comment",
    "格式",          # → csharp-format-checker
    "dotnet format",
    "缩进",
    "审查",          # → csharp-code-review
    "代码质量",
    "提交",          # → vcs-router
    "git",
    "svn",
]


def score_match(prompt):
    """计算 prompt 与本技能的匹配度。"""
    prompt_norm = normalize(prompt)

    # 排除性判定优先：命中邻近领域关键词则直接判不触发
    if any(kw in prompt_norm for kw in EXCLUDE_KEYWORDS):
        return 0.0

    has_coverage = any(kw in prompt_norm for kw in COVERAGE_KEYWORDS)
    has_action = any(kw in prompt_norm for kw in ACTION_KEYWORDS)
    has_language = any(kw in prompt_norm for kw in LANGUAGE_KEYWORDS)

    if has_coverage and has_action:
        return 0.6
    if has_coverage:
        return 0.4
    if has_action and has_language:
        return 0.2
    return 0.0


def evaluate(cases, threshold):
    """评估触发质量，返回统计报告。"""
    buckets = ("should_trigger", "should_not_trigger", "near_neighbor")
    results = {bucket: [] for bucket in buckets}
    false_positives = 0
    false_negatives = 0

    for bucket in buckets:
        expected = bucket == "should_trigger"
        for item in cases.get(bucket, []):
            prompt = item if isinstance(item, str) else item.get("text", "")
            score = score_match(prompt)
            predicted = score >= threshold
            passed = predicted == expected

            if not passed and expected:
                false_negatives += 1
            if not passed and not expected:
                false_positives += 1

            record = {
                "prompt": prompt,
                "score": round(score, 3),
                "predicted_trigger": predicted,
                "expected_trigger": expected,
                "passed": passed,
            }
            if 0.75 * threshold <= score <= 1.25 * threshold:
                record["boundary_case"] = True
            results[bucket].append(record)

    true_positives = sum(1 for r in results["should_trigger"] if r["predicted_trigger"])
    denominator_p = true_positives + false_positives
    denominator_r = true_positives + false_negatives

    return {
        "threshold": threshold,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(true_positives / denominator_p, 3) if denominator_p else None,
        "recall": round(true_positives / denominator_r, 3) if denominator_r else None,
        "should_trigger_total": len(results["should_trigger"]),
        "should_not_trigger_total": len(results["should_not_trigger"]),
        "near_neighbor_total": len(results["near_neighbor"]),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="csharp-test-coverage 触发评估")
    parser.add_argument("--description", default=None, help="直接指定 description 文本")
    parser.add_argument("--cases", default=None,
                        help="触发测试用例文件路径（默认经索引 coverage.trigger_cases 定位到项目侧）")
    parser.add_argument("--threshold", type=float, default=None,
                        help="触发匹配阈值（缺省取用例文件的 recommended_threshold）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    if args.description:
        description = args.description
    else:
        description = load_description(os.path.join(SKILL_DIR, "SKILL.md"))
        if not description:
            sys.stderr.write("错误：无法从 SKILL.md 提取 description\n")
            return 1

    cases_path = args.cases
    if not cases_path:
        try:
            cases_path = default_cases_path()
        except skill_config.ConfigError as error:
            sys.stderr.write("错误：%s\n" % error)
            return 3

    cases = load_cases(cases_path)
    threshold = args.threshold
    if threshold is None:
        threshold = cases.get("recommended_threshold", 0.3)

    report = evaluate(cases, threshold)
    report["description_length"] = len(description)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("触发评估报告（csharp-test-coverage）")
        print("=" * 60)
        print("  Description 长度: %d 字符" % len(description))
        print("  匹配阈值: %s" % threshold)
        print("  应触发用例: %d 个" % report["should_trigger_total"])
        print("  不应触发用例: %d 个" % report["should_not_trigger_total"])
        print("  邻近领域用例: %d 个" % report["near_neighbor_total"])
        print("  误报 (FP): %d" % report["false_positives"])
        print("  漏报 (FN): %d" % report["false_negatives"])
        if report["precision"] is not None:
            print("  精确率: %s" % report["precision"])
        if report["recall"] is not None:
            print("  召回率: %s" % report["recall"])

        if report["false_positives"] or report["false_negatives"]:
            print()
            print("  异常用例:")
            for bucket in ("should_trigger", "should_not_trigger", "near_neighbor"):
                for record in report["results"][bucket]:
                    if not record["passed"]:
                        status = "漏报" if record["expected_trigger"] else "误报"
                        print("    [%s] %s (score=%s)"
                              % (status, record["prompt"][:70], record["score"]))
        else:
            print()
            print("  全部用例通过（无 FP / FN）。")

    if report["false_positives"] or report["false_negatives"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
