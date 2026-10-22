#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unity-pipeline 异步命令轮询脚本：按 JSON 字段判定终态。

背景：
    `unity command <分组> <名称>` 的异步命令（`script recompile_status`、`test status`、
    `diagnostics audit_status` 等）
    需要反复调用直至进入终态。手写 shell 轮询常用 `grep -qE 'completed|up_to_date|failed'`
    对整段 JSON 做关键字匹配，会被 `"failed":false` 这类子串误命中而提前退出，掩盖真实
    进行中的状态。本脚本严格**按 JSON 字段取值**判定终态，解析失败时重试而非误判成功。

用法：
    python unity_wait.py --command "script recompile_status"
                         [--field status] [--until completed,up_to_date]
                         [--fail-field failed] [--fail-value true]
                         [--timeout 300] [--interval 3] [--json]
                         [--unity unity] [--dir <工作目录>] [--extra ...]

参数：
    --command      轮询的 unity 命令名，含分组（如 "script recompile_status" / "test status"）；
                   按空白切分为多个参数传给 CLI，故带空格的命令名必须整体加引号
    --field        判终态所依据的 JSON 字段（默认 status）
    --until        终态取值集合，逗号分隔（默认 completed,up_to_date）
    --fail-field   失败态字段（默认 failed；传空字符串可关闭失败态判定）
    --fail-value   失败态取值（默认 true；可用逗号分隔多个，如 error,cancelled）
    --timeout      总超时秒数（默认 300）
    --interval     轮询间隔秒数（默认 3）
    --json         仅向 stdout 输出终态 JSON（便于管道）；提示信息走 stderr
    --unity        unity 命令名或路径（默认 unity）
    --dir          unity 命令执行的工作目录（默认当前目录）
    --extra        unity 命令的附加参数（置于 `--` 之后原样透传）

输出：
    达到终态时输出该次命令的完整 JSON；`--json` 时 stdout 仅含 JSON。
    解析始终失败时输出最后一次的原始输出（便于排查），并提示可能仍在运行。

退出码：
    0 —— 达到终态
    1 —— 达到失败态（如 failed=true）
    2 —— 超时、参数错误或始终无法解析出 JSON

注意：
    本脚本只负责「轮询至终态」，命令本身的触发（如 `unity command script recompile`）仍需另行执行。
"""

import argparse
import json
import subprocess
import sys
import time


def init_stdout():
    """Windows 下统一以 UTF-8 输出，并关闭换行翻译避免 git-bash 渲染杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def log(message):
    """向 stderr 输出提示信息（不污染 stdout 的 JSON 管道）。"""
    print(message, file=sys.stderr, flush=True)


def run_unity_command(unity, command, extra, workdir):
    """执行一次 `unity command <分组> <名称> [附加参数]`，返回（退出码, stdout, stderr）。

    0.9 起命令一律 "分组 名称"，CLI 要求它作为**单个参数**传入（拆成两个参数会被当成
    「执行名为分组的那条命令」而失败），因此这里整串直传、不做切分。
    命令不存在或执行异常时退出码记为 -1，由调用方按「解析失败」处理（重试而非误判）。
    """
    argv = [unity, "command", command] + list(extra or [])
    try:
        result = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as error:
        return -1, "", str(error)


def parse_json_object(text):
    """从命令输出中解析首个完整 JSON 对象。

    命令输出可能包含信息性日志前缀，或「结果 JSON + 参数回显」两段拼接，因此从首个
    `{` 起用 raw_decode 只解首个对象；解析失败返回 None（由调用方重试，禁止据此判定成功）。
    """
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


def unwrap_envelope(obj, fields):
    """剥掉 CLI 的结果外壳，返回真正承载命令结果的 JSON 对象。

    CLI 的 `--json` 输出形如 {success, command, data:{command, parameters, result:{...}}}，
    human 输出则是表格（result 列已是结果对象本身）。若当前对象不含待判定的字段，
    就按 data.result → result 逐层下钻；都没有则原样返回（由调用方按解析失败重试）。
    """
    wanted = [f for f in fields if f]
    if not wanted or any(get_field(obj, f) is not None for f in wanted):
        return obj
    for key in ("data", "result"):
        inner = get_field(obj, key)
        if isinstance(inner, dict):
            deep = unwrap_envelope(inner, fields)
            if any(get_field(deep, f) is not None for f in wanted):
                return deep
    return obj


def get_field(obj, field):
    """按字段名取值（大小写不敏感），缺失或字段名为空时返回 None。"""
    if not field:
        return None
    for key, value in obj.items():
        if str(key).lower() == field.lower():
            return value
    return None


def as_text(value):
    """将字段值归一化为小写字符串，便于与终态/失败态取值比较。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower()


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="unity-pipeline 异步命令轮询（按 JSON 字段判终态）")
    parser.add_argument("--command", required=True, help='轮询的 unity 命令名，含分组（如 "script recompile_status" / "test status"）')
    parser.add_argument("--field", default="status", help="判终态所依据的 JSON 字段（默认 status）")
    parser.add_argument("--until", default="completed,up_to_date", help="终态取值集合，逗号分隔（默认 completed,up_to_date）")
    parser.add_argument("--fail-field", default="failed", help="失败态字段（默认 failed；传空字符串关闭失败态判定）")
    parser.add_argument("--fail-value", default="true", help="失败态取值（默认 true；可逗号分隔多个，如 error,cancelled）")
    parser.add_argument("--timeout", type=int, default=300, help="总超时秒数（默认 300）")
    parser.add_argument("--interval", type=int, default=3, help="轮询间隔秒数（默认 3）")
    parser.add_argument("--json", action="store_true", help="仅向 stdout 输出终态 JSON（提示信息走 stderr）")
    parser.add_argument("--unity", default="unity", help="unity 命令名或路径（默认 unity）")
    parser.add_argument("--dir", default=None, help="unity 命令执行的工作目录（默认当前目录）")
    parser.add_argument("--extra", nargs=argparse.REMAINDER, default=None, help="附加参数（置于 -- 之后原样透传）")
    args = parser.parse_args()

    if args.timeout <= 0 or args.interval <= 0:
        log("[FAIL] --timeout 与 --interval 必须为正整数")
        return 2

    until_values = {v.strip().lower() for v in args.until.split(",") if v.strip()}
    if not until_values:
        log("[FAIL] --until 至少需要一个取值")
        return 2

    fail_values = {v.strip().lower() for v in args.fail_value.split(",") if v.strip()}

    deadline = time.time() + args.timeout
    attempt = 0
    last_object = None
    last_raw = ""

    while True:
        attempt += 1
        returncode, stdout, stderr = run_unity_command(args.unity, args.command, args.extra, args.dir)
        last_raw = stdout.strip()

        obj = parse_json_object(stdout)
        if obj is None:
            # 解析失败不判定成功：记录告警并重试（命令仍在运行或输出未成形）
            detail = (stderr or stdout).strip().splitlines()
            detail = detail[-1] if detail else "无输出"
            log(f"[WARN] 第 {attempt} 次轮询未取到可解析 JSON（退出码 {returncode}）：{detail}")
        else:
            # 剥掉 CLI 外壳：--json 时结果在 data.result 里，human 时已在最外层
            obj = unwrap_envelope(obj, [args.field, args.fail_field])
            last_object = obj

            # 失败态优先判定：如 script recompile_status 的 failed=true
            fail_value = get_field(obj, args.fail_field)
            if fail_value is not None and as_text(fail_value) in fail_values:
                if not args.json:
                    log(f"[FAIL] 命令 {args.command} 进入失败态（{args.fail_field}={fail_value}），完整结果如下：")
                print(json.dumps(obj, ensure_ascii=False, indent=2))
                return 1

            # 终态判定：严格取字段值，禁止对整段 JSON 做关键字匹配
            state = get_field(obj, args.field)
            if state is not None and as_text(state) in until_values:
                if not args.json:
                    log(f"[PASS] 命令 {args.command} 已达终态（{args.field}={state}，第 {attempt} 次轮询）")
                print(json.dumps(obj, ensure_ascii=False, indent=2))
                return 0

        if time.time() >= deadline:
            break
        time.sleep(args.interval)

    # 超时
    log(f"[FAIL] 命令 {args.command} 在 {args.timeout} 秒内未达到终态（已轮询 {attempt} 次）")
    if last_object is not None:
        log("[INFO] 最后一次可解析结果如下：")
        print(json.dumps(last_object, ensure_ascii=False, indent=2))
    elif last_raw:
        log("[INFO] 命令可能仍在运行；最后一次原始输出如下：")
        print(last_raw)
    log("[INFO] 可加大 --timeout 后重试，或用 `unity command test cancel` 等命令中止。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
