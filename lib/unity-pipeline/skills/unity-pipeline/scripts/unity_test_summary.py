#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unity-pipeline 测试结果归一化脚本：从 `test status` / `test run` 输出中提取摘要与失败清单。

背景：
    `unity command test run` / `test status` 的输出是「结果 JSON + 参数回显」两段 JSON（0.9 起命令分组命名）
    拼接（如 `{"Summary":{...},"Results":[...]}   {"mode":"editor","filter":"..."}`），
    直接 `json.load` 会因尾随内容报错，需用 raw_decode 只解首个对象。本脚本完成该解析，
    并归一化为「总数/通过/失败/跳过」摘要与失败用例清单（含消息与堆栈首 3 行）。

用法：
    python unity_test_summary.py [--file Temp/pipeline_test_status.json | --stdin]
                                 [--filter 关键词] [--fail-only] [--json] [--raw]

参数：
    --file    结果文件路径（不指定且未用 --stdin 时，自动取 Temp 下最新的 pipeline_test*.json）
    --stdin   从标准输入读取结果文本
    --filter  按用例 FullName 做关键词过滤（大小写不敏感）；过滤后按剩余用例重算摘要
    --fail-only 仅输出失败清单，不输出汇总行
    --json    以 JSON 输出归一化结果（便于程序处理）
    --raw     解析失败时原样打印输入文本（便于排查）

输出：
    人类可读：总数/通过/失败/跳过/不确定 摘要；存在失败时逐条打印 FullName + 消息 + 堆栈首 3 行。
    `--json`：{"total":..,"passed":..,"failed":..,"skipped":..,"inconclusive":..,"failures":[...]}

退出码：
    0 —— 全部通过（无失败用例）
    1 —— 存在失败用例
    2 —— 解析失败（可能仍在运行，请先轮询 `test status`）或参数/文件错误
"""

import argparse
import glob
import json
import os
import sys

# 结果状态归一化：不同来源可能使用 Result / Status / Outcome 字段，取值大小写不一
PASS_VALUES = {"passed", "pass", "success", "succeeded"}
FAIL_VALUES = {"failed", "fail", "error", "errored"}
SKIP_VALUES = {"skipped", "skip", "ignored"}


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def log(message):
    """向 stderr 输出提示信息。"""
    print(message, file=sys.stderr, flush=True)


def get_field(mapping, names, default=None):
    """在字典中按候选字段名（大小写不敏感）取首个存在的值。"""
    if not isinstance(mapping, dict):
        return default
    lowered = {str(k).lower(): v for k, v in mapping.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return default


def parse_first_json(text):
    """解析文本中首个完整 JSON 对象（兼容「结果 JSON + 参数回显」拼接），失败返回 None。"""
    if not text:
        return None
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        start = text.find("{", start + 1)
    return None


def normalize_status(result_item):
    """将单条用例的结果状态归一化为 passed / failed / skipped / inconclusive。"""
    raw = get_field(result_item, ["Result", "Status", "Outcome", "State"], "")
    value = str(raw).strip().lower()
    if value in PASS_VALUES:
        return "passed"
    if value in FAIL_VALUES:
        return "failed"
    if value in SKIP_VALUES:
        return "skipped"
    return "inconclusive"


def resolve_input_file(explicit_file):
    """未显式指定输入文件时，自动取 Temp 下最新的 pipeline_test*.json。"""
    if explicit_file:
        return explicit_file
    candidates = glob.glob(os.path.join("Temp", "pipeline_test*.json"))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def load_text(args):
    """读取结果文本：优先 --file，其次 --stdin，最后自动发现 Temp 产物。返回（文本, 来源）。"""
    if args.stdin:
        return sys.stdin.read(), "标准输入"
    target = resolve_input_file(args.file)
    if not target:
        return None, None
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as file:
            return file.read(), target
    except OSError as error:
        log(f"[FAIL] 读取结果文件失败：{error}")
        return None, target


def extract_results(payload):
    """从结果 JSON 中取出用例列表（兼容 Results / results / TestResults 等命名）。"""
    results = get_field(payload, ["Results", "TestResults", "Tests"], None)
    if isinstance(results, list):
        return results
    return []


def summarize(payload, results, use_summary):
    """汇总计数：优先使用 Summary 字段；缺失时由用例列表统计。"""
    if use_summary:
        summary = get_field(payload, ["Summary", "summary"], None)
        if isinstance(summary, dict):
            total = get_field(summary, ["Total", "TotalCount"], None)
            passed = get_field(summary, ["Passed", "PassedCount"], None)
            failed = get_field(summary, ["Failed", "FailedCount"], None)
            skipped = get_field(summary, ["Skipped", "SkippedCount"], None)
            inconclusive = get_field(summary, ["Inconclusive", "InconclusiveCount"], None)
            if total is not None or passed is not None:
                return {
                    "total": int(total if total is not None else len(results)),
                    "passed": int(passed or 0),
                    "failed": int(failed or 0),
                    "skipped": int(skipped or 0),
                    "inconclusive": int(inconclusive or 0),
                }

    counts = {"total": len(results), "passed": 0, "failed": 0, "skipped": 0, "inconclusive": 0}
    for item in results:
        counts[normalize_status(item)] += 1
    return counts


def build_failures(results):
    """提取失败用例清单：全名 + 消息 + 堆栈（保留原文，输出时截取首 3 行）。"""
    failures = []
    for item in results:
        if normalize_status(item) != "failed":
            continue
        full_name = get_field(item, ["FullName", "Name", "TestName"], "（未命名用例）")
        message = get_field(item, ["Message", "message"], "") or ""
        stack = get_field(item, ["StackTrace", "stackTrace"], "") or ""
        failures.append(
            {
                "full_name": str(full_name),
                "message": str(message).strip(),
                "stack_trace": str(stack).strip(),
            }
        )
    return failures


def first_lines(text, limit=3):
    """取文本前若干行（用于堆栈摘要）。"""
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[:limit]


def print_human(counts, failures, source, fail_only, filtered):
    """人类可读输出。"""
    if not fail_only:
        print("== Unity 测试结果摘要 ==")
        print(f"数据来源：{source}")
        if filtered:
            print("（已按 --filter 过滤，计数为过滤后结果）")
        print(
            f"总数：{counts['total']}  通过：{counts['passed']}  失败：{counts['failed']}"
            f"  跳过：{counts['skipped']}  不确定：{counts['inconclusive']}"
        )
        print()
    if not failures:
        if not fail_only:
            print("[PASS] 未发现失败用例。")
        return
    print(f"失败用例（{len(failures)}）：")
    for index, failure in enumerate(failures, start=1):
        print(f"{index}. {failure['full_name']}")
        if failure["message"]:
            print(f"   消息：{failure['message'].splitlines()[0]}")
        for line in first_lines(failure["stack_trace"], 3):
            print(f"   堆栈：{line}")


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="unity-pipeline 测试结果归一化（摘要 + 失败清单）")
    parser.add_argument("--file", default=None, help="结果文件路径（默认自动取 Temp 下最新 pipeline_test*.json）")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取结果文本")
    parser.add_argument("--filter", default=None, help="按用例 FullName 关键词过滤（大小写不敏感）")
    parser.add_argument("--fail-only", action="store_true", help="仅输出失败清单")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出归一化结果")
    parser.add_argument("--raw", action="store_true", help="解析失败时原样打印输入文本")
    args = parser.parse_args()

    if args.stdin and args.file:
        log("[FAIL] --stdin 与 --file 不能同时使用")
        return 2

    text, source = load_text(args)
    if text is None:
        log("[FAIL] 未找到结果文件：请用 --file 指定路径、--stdin 传入文本，"
            "或先执行测试（输出位于 Temp/pipeline_test*.json）")
        return 2

    payload = parse_first_json(text)
    if payload is None:
        log("[FAIL] 无法从输入中解析出测试结果 JSON（可能仍在运行，请先轮询 `test status`）")
        if args.raw:
            log("[INFO] 原始输入如下：")
            print(text)
        return 2

    results = extract_results(payload)
    if args.filter:
        keyword = args.filter.strip().lower()
        results = [r for r in results if keyword in str(get_field(r, ["FullName", "Name", "TestName"], "")).lower()]

    counts = summarize(payload, results, use_summary=not args.filter)
    failures = build_failures(results)

    if args.json:
        output = dict(counts)
        output["failures"] = failures
        output["source"] = source
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_human(counts, failures, source, args.fail_only, bool(args.filter))

    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
