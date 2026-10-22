#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csharp-comment-checker 触发评估脚本。
验证技能的 description 是否准确匹配预期的触发场景，检测边界误触发和漏触发。
"""

import argparse
import json
import os
import re
import sys


# 技能所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def _find_codebuddy_dir(start):
    """自 start 向上查找名为 `.codebuddy` 的目录；找不到返回 None。"""
    current = os.path.abspath(start)
    while True:
        if os.path.basename(current) == ".codebuddy":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def default_cases_path():
    """经索引 `comment_checker.trigger_cases` 解析项目侧触发用例文件路径。

    触发用例数据为项目专有资产，位于项目侧 `.codebuddy.project/`（不随引擎共享）；
    索引缺失或未登记时报错退出（退出码 3），不回退引擎内硬编码路径。
    """
    codebuddy_dir = _find_codebuddy_dir(SCRIPT_DIR)
    if not codebuddy_dir:
        raise RuntimeError("未能定位 .codebuddy 目录（应位于项目根下）")
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise RuntimeError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise RuntimeError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    entry = (index.get("files") or {}).get("comment_checker.trigger_cases") or {}
    rel = entry.get("path")
    if not rel:
        raise RuntimeError("索引缺少配置项 `files.comment_checker.trigger_cases.path`：%s" % index_path)
    if os.path.isabs(rel):
        raise RuntimeError("索引 `files.comment_checker.trigger_cases.path` 必须为相对路径：%s" % rel)
    project_root = os.path.dirname(codebuddy_dir)
    return os.path.normpath(os.path.join(project_root, rel))


def normalize(text: str) -> str:
    """标准化文本：小写、去除多余空格。"""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_cases(cases_path: str) -> dict:
    """加载触发测试用例文件。"""
    if not os.path.isfile(cases_path):
        print(f"错误: 测试用例文件不存在: {cases_path}", file=sys.stderr)
        sys.exit(1)
    with open(cases_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_description(skill_md_path: str) -> str:
    """从 SKILL.md frontmatter 中提取 description。"""
    if not os.path.isfile(skill_md_path):
        print(f"错误: SKILL.md 不存在: {skill_md_path}", file=sys.stderr)
        sys.exit(1)

    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 frontmatter 中的 description
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            for line in frontmatter.splitlines():
                line = line.strip()
                if line.startswith("description:"):
                    return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def score_match(description: str, prompt: str) -> float:
    """计算 prompt 与技能的语义匹配度。检查是否同时包含注释关键词和操作关键词。"""
    prompt_norm = normalize(prompt)
    
    # 注释相关关键词（任中一个即可）
    comment_keywords = ["注释", "comment", "xml", "文档注释", "行内注释"]
    # 操作相关关键词（任中一个即可）
    action_keywords = ["检查", "扫描", "验证", "合规", "check", "scan", "review", 
                       "规范", "质量", "是否", "缺少", "缺失"]
    # 语言相关关键词（C# 的常见中英文表达，任一命中即视为 C# 语境）
    language_keywords = ["c#", "csharp", ".cs", "cs 文件", "c sharp"]
    
    has_comment = any(kw in prompt_norm for kw in comment_keywords)
    has_action = any(kw in prompt_norm for kw in action_keywords)
    has_language = any(kw in prompt_norm for kw in language_keywords)
    
    if has_comment and has_action:
        return 0.6
    elif has_comment:
        return 0.3
    elif has_action and has_language:
        return 0.2
    else:
        return 0.0


def evaluate(description: str, cases: dict, threshold: float) -> dict:
    """评估触发质量，返回统计报告。"""
    results = {"should_trigger": [], "should_not_trigger": [], "near_neighbor": []}
    fp = 0
    fn = 0

    for bucket in ("should_trigger", "should_not_trigger", "near_neighbor"):
        expected = (bucket == "should_trigger")
        items = cases.get(bucket, [])
        for item in items:
            prompt = item if isinstance(item, str) else item.get("text", "")
            label = item.get("label", "") if isinstance(item, dict) else ""
            score = score_match(description, prompt)
            predicted = score >= threshold
            passed = predicted == expected

            if not passed and expected:
                fn += 1
            if not passed and not expected:
                fp += 1

            record = {
                "prompt": prompt,
                "label": label,
                "score": round(score, 3),
                "predicted_trigger": predicted,
                "expected_trigger": expected,
                "passed": passed,
            }
            if 0.75 * threshold <= score <= 1.25 * threshold:
                record["boundary_case"] = True
            results[bucket].append(record)

    tp = sum(1 for r in results["should_trigger"] if r["predicted_trigger"])
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None

    return {
        "threshold": threshold,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "should_trigger_total": len(results["should_trigger"]),
        "should_not_trigger_total": len(results["should_not_trigger"]),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="csharp-comment-checker 触发评估脚本"
    )
    parser.add_argument(
        "--description", default=None,
        help="直接指定 description 文本进行测试"
    )
    parser.add_argument(
        "--cases", default=None,
        help="触发测试用例文件路径（JSON 格式；默认经索引 comment_checker.trigger_cases 定位到项目侧）"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.3,
        help="触发匹配阈值，默认 0.3"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出结果"
    )
    args = parser.parse_args()

    # 加载 description
    if args.description:
        description = args.description
    else:
        skill_md = os.path.join(SKILL_DIR, "SKILL.md")
        description = load_description(skill_md)
        if not description:
            print("错误: 无法从 SKILL.md 提取 description", file=sys.stderr)
            sys.exit(1)

    # 加载测试用例（默认经索引定位到项目侧；显式 --cases 时不触碰索引）
    cases_path = args.cases
    if not cases_path:
        try:
            cases_path = default_cases_path()
        except (RuntimeError, OSError) as error:
            print(f"错误: {error}", file=sys.stderr)
            sys.exit(3)
    cases = load_cases(cases_path)

    # 评估
    report = evaluate(description, cases, args.threshold)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"触发评估报告")
        print("=" * 60)
        print(f"  Description 长度: {len(description)} 字符")
        print(f"  匹配阈值: {args.threshold}")
        print(f"  应触发用例: {report['should_trigger_total']} 个")
        print(f"  不应触发用例: {report['should_not_trigger_total']} 个")
        print(f"  误报 (FP): {report['false_positives']}")
        print(f"  漏报 (FN): {report['false_negatives']}")
        if report["precision"] is not None:
            print(f"  精确率: {report['precision']}")
        if report["recall"] is not None:
            print(f"  召回率: {report['recall']}")

        if report["false_positives"] > 0 or report["false_negatives"] > 0:
            print("\n  异常用例:")
            for bucket in ("should_trigger", "should_not_trigger"):
                for r in report["results"][bucket]:
                    if not r["passed"]:
                        status = "漏报" if r["expected_trigger"] else "误报"
                        print(f"    [{status}] {r['prompt'][:80]} (score={r['score']})")

    # 存在误报/漏报时以退出码 2 表示警告
    if report["false_positives"] > 0 or report["false_negatives"] > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
