#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCS 写操作互斥锁工具。

背景：
    git 的暂存区（index）与 HEAD 是仓库级共享状态。多个 CodeBuddy 会话
    并发执行 git 提交、回滚等写操作时，会互相污染暂存区或回滚彼此的提交。
    本工具为 VCS 写操作提供项目级互斥锁，保证同一项目
    同一时刻只有一个会话持有写操作权。

锁设计：
    - 锁文件位于项目侧 .codebuddy.project/caches/.vcs-lock/codebuddy-vcs.lock（通用锁目录），
      不依赖 git 目录，非 git 项目同样可用。
    - 定位方式：优先从当前工作目录向上查找 .codebuddy 目录，未命中时
      回退到脚本自身位置推导（脚本位于 .codebuddy 内）。
    - 使用 O_CREAT|O_EXCL 原子创建获取锁，杜绝并发同时拿锁。
    - 锁内容记录会话标识、操作类型、开始时间、PID、主机名。
    - 锁超过 stale 阈值（默认 30 分钟）视为过期，可自动接管或 --force 覆盖。
    - 释放时校验 session_id，防止误删已被其他会话接管的锁。

用法：
    # 获取锁（被占用时输出占用摘要并自动轮询等待）
    python vcs_lock.py acquire --op "<操作描述>" [--wait <秒>] [--timeout <秒>] [--force]

    # 释放锁（需传 acquire 时输出的 LOCK_SESSION；session 支持容错匹配，
    # 可容忍终端输出伪影附加的尾部字符；仍不匹配时输出锁中真实 session 供核对）
    python vcs_lock.py release --session <session_id>

    # 查看锁状态
    python vcs_lock.py status [--timeout <秒>]

退出码：
    0 —— 成功（获取/释放/状态查询完成）
    1 —— 失败（等待超时仍被占用、释放会话不匹配、未找到 .codebuddy 目录等）
"""

import argparse
import json
import os
import random
import socket
import string
import sys
import time
from datetime import datetime
from pathlib import Path

# 锁文件名与默认参数
LOCK_FILE_NAME = "codebuddy-vcs.lock"
DEFAULT_TIMEOUT = 30 * 60       # stale 阈值：30 分钟
DEFAULT_WAIT = 120              # 默认轮询等待：120 秒
POLL_INTERVAL = 3               # 轮询间隔：3 秒
PROGRESS_INTERVAL = 15          # 进度提示间隔：15 秒


def init_stdout():
    """Windows 下统一以 UTF-8 输出（与项目编码规范一致），关闭换行翻译避免 git-bash 杂讯。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def print_result(status, message):
    """以统一格式输出。"""
    symbol = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
    print(f"{symbol.get(status, '[INFO]')} {message}", flush=True)


def find_codebuddy_dir():
    """定位项目 .codebuddy 目录：优先从当前工作目录向上查找，未命中时回退到脚本自身位置推导。

    锁只与项目（.codebuddy）绑定，不依赖 VCS 类型。
    脚本位于 <项目根>/.codebuddy/skills/vcs-router/scripts/vcs_lock.py，
    向上遍历总能找到名为 .codebuddy 的目录。
    """
    # 方式一：从当前工作目录向上查找含 .codebuddy 的目录（目录链接共享配置时落在当前项目）
    current = Path.cwd()
    for parent in (current, *current.parents):
        candidate = parent / ".codebuddy"
        if candidate.is_dir():
            return candidate

    # 方式二：从脚本自身位置向上查找名为 .codebuddy 的目录
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name == ".codebuddy" and parent.is_dir():
            return parent
    return None


def new_session_id():
    """生成会话标识：PID-毫秒时间戳-6位随机串。"""
    random_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{os.getpid()}-{int(time.time() * 1000)}-{random_part}"


def resolve_lock_dir(codebuddy_dir):
    """经索引 `artifacts.dirs.vcs_router.lock` 解析锁目录（相对路径基准为项目根）。

    锁目录位于项目侧 `.codebuddy.project/caches/.vcs-lock/`（运行时生成，不入库、不随引擎共享）。
    索引缺失或缺少该项时回退到引擎内 `.codebuddy/.vcs-lock/`（保持可用性）。
    """
    index_path = codebuddy_dir / "project.index.json"
    if index_path.is_file():
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                index = json.load(handle)
            rel = (index.get("artifacts") or {}).get("dirs", {}).get("vcs_router.lock")
            if isinstance(rel, str) and rel and not os.path.isabs(rel):
                return Path(os.path.normpath(os.path.join(str(codebuddy_dir.parent), rel)))
        except (OSError, ValueError):
            pass
    return codebuddy_dir / ".vcs-lock"



def read_lock(lock_file):
    """读取锁内容，失败返回 None。"""
    try:
        return json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def normalize_session(session_id):
    """归一化会话标识：去除首尾空白及尾部非常规字符。

    终端捕获输出时偶发在行尾附加伪影字符（如 'X'），归一化后即可与锁中真实 session 对齐。
    """
    s = session_id.strip()
    while s and not s[-1].isalnum():
        s = s[:-1]
    return s


def session_matches(actual, provided):
    """会话归属匹配：完全一致、归一化后一致，或一方为另一方前缀（容忍尾部伪影）。

    会话标识形如 '<pid>-<毫秒时间戳>-<6位随机串>'，前缀达到最小长度后跨会话碰撞概率可忽略，
    因此凭前缀即可安全放行，避免终端输出伪影导致释放误判。
    """
    MIN_PREFIX_LEN = 12
    if not actual or not provided:
        return False
    if actual == provided:
        return True
    norm_actual = normalize_session(actual)
    norm_provided = normalize_session(provided)
    if norm_actual == norm_provided:
        return True
    if len(norm_provided) >= MIN_PREFIX_LEN and norm_actual.startswith(norm_provided):
        return True
    if len(norm_actual) >= MIN_PREFIX_LEN and norm_provided.startswith(norm_actual):
        return True
    return False


def is_stale(holder, timeout):
    """锁是否过期：开始时间距今超过 stale 阈值。"""
    return holder is not None and (time.time() - holder.get("started_at", 0)) > timeout


def describe_lock(holder):
    """生成锁的会话信息摘要（供冲突时告知用户）。"""
    if holder is None:
        return "（无法解析锁内容）"
    parts = [
        f"会话标识：{holder.get('session_id', '?')}",
        f"操作：{holder.get('operation', '?')}",
        f"开始时间：{holder.get('started_at_readable', '?')}",
        f"主机：{holder.get('host', '?')}",
        f"PID：{holder.get('pid', '?')}",
    ]
    return "；".join(parts)


def try_acquire(lock_file, session_id, operation):
    """原子创建锁文件。成功返回 (True, 锁信息)，已存在返回 (False, 锁信息)。"""
    info = {
        "session_id": session_id,
        "operation": operation,
        "started_at": time.time(),
        "started_at_readable": datetime.now().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "host": socket.gethostname(),
    }
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        # newline="\n"：避免 Windows 文本模式把 \n 转成 \r\n（CRLF 在部分终端渲染下会显示为尾部伪影字符）
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        return True, info
    except FileExistsError:
        return False, info


def do_acquire(lock_file, operation, wait, timeout, force):
    """执行锁获取主逻辑。"""
    if force:
        # 用户显式强制：无论锁是否存在都覆盖
        lock_file.unlink(missing_ok=True)

    session_id = new_session_id()
    acquired, _ = try_acquire(lock_file, session_id, operation)
    if acquired:
        print_result("PASS", f"已获取 VCS 写操作锁（操作：{operation}）")
        print_result("INFO", f"锁文件：{lock_file}")
        print_result("INFO", f"LOCK_SESSION={session_id}")
        return 0

    # 锁被其他会话占用：输出占用摘要并自动轮询等待
    holder = read_lock(lock_file)
    print_result("WARN", "VCS 写操作锁被其他会话占用：")
    print_result("INFO", f"占用详情：{describe_lock(holder)}")
    if is_stale(holder, timeout):
        print_result("WARN", f"该锁已超过 {timeout} 秒有效期，视为残留锁，立即接管。")
        lock_file.unlink(missing_ok=True)
        acquired, _ = try_acquire(lock_file, session_id, operation)
        if acquired:
            print_result("PASS", f"已接管并获取 VCS 写操作锁（操作：{operation}）")
            print_result("INFO", f"LOCK_SESSION={session_id}")
            return 0
        print_result("FAIL", "接管失败，请稍后重试。")
        return 1

    print_result("INFO", f"自动轮询等待对方释放（最多 {wait} 秒，每 {POLL_INTERVAL} 秒重试）...")
    deadline = time.time() + wait
    last_progress = time.time()
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)

        # 等待期间锁可能换持有者，每次刷新占用信息
        holder = read_lock(lock_file)

        # 锁已过期：视为残留，自动接管
        if holder is None or is_stale(holder, timeout):
            lock_file.unlink(missing_ok=True)
            acquired, _ = try_acquire(lock_file, session_id, operation)
            if acquired:
                print_result("PASS", f"对方已释放，获取 VCS 写操作锁（操作：{operation}）")
                print_result("INFO", f"LOCK_SESSION={session_id}")
                return 0
            continue

        # 周期性进度提示
        now = time.time()
        if (now - last_progress) >= PROGRESS_INTERVAL:
            elapsed = int(now - (deadline - wait))
            print_result("INFO", f"仍在等待锁释放（已等待约 {elapsed} 秒），占用详情：{describe_lock(holder)}")
            last_progress = now

    print_result("FAIL", f"等待 {wait} 秒后锁仍被占用，本次操作中止。占用详情：{describe_lock(holder)}")
    print_result("INFO", "可稍后重试；如需立即继续，可重新执行并加 --force 强制接管（会打断对方操作）。")
    return 1


def do_release(lock_file, session_id):
    """执行锁释放。session 做容错匹配（归一化 + 安全前缀），避免终端输出伪影导致释放误判。"""
    if session_id:
        session_id = session_id.strip()
    if not lock_file.exists():
        print_result("INFO", "锁文件不存在，无需释放。")
        return 0

    holder = read_lock(lock_file)
    if holder and session_id:
        actual = holder.get("session_id") or ""
        if not session_matches(actual, session_id):
            print_result("FAIL", "释放失败：传入的会话标识与锁记录不一致。")
            print_result("INFO", f"传入 session：{session_id or '（空）'}")
            print_result("INFO", f"锁中 session：{actual}")
            print_result(
                "INFO",
                "可能原因：1) acquire 输出的 LOCK_SESSION 被终端输出伪影污染（如行尾附加字符）；"
                "2) 锁确实已被其他会话接管。",
            )
            print_result(
                "INFO",
                "建议：使用上方『锁中 session』重新执行 release；若确认锁归属无误且无并发会话，"
                "可确认后以 acquire --force 接管后释放。",
            )
            return 1

    try:
        lock_file.unlink(missing_ok=True)
        print_result("PASS", "VCS 写操作锁已释放。")
        return 0
    except OSError as exc:
        print_result("FAIL", f"释放锁失败：{exc}")
        return 1


def do_status(lock_file, timeout):
    """查看锁状态。"""
    if not lock_file.exists():
        print_result("INFO", "当前无 VCS 写操作锁。")
        return 0

    holder = read_lock(lock_file)
    print_result("WARN", "VCS 写操作锁当前被占用：")
    print_result("INFO", f"占用详情：{describe_lock(holder)}")
    if is_stale(holder, timeout):
        print_result("WARN", f"该锁已超过 {timeout} 秒有效期，视为残留锁，可在获取时自动接管或加 --force 覆盖。")
    else:
        print_result("INFO", f"锁在有效期内（stale 阈值 {timeout} 秒）。")
    return 0


def main():
    init_stdout()

    parser = argparse.ArgumentParser(description="VCS 写操作互斥锁工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # acquire
    p_acquire = subparsers.add_parser("acquire", help="获取 VCS 写操作锁")
    p_acquire.add_argument("--op", required=True, help="操作描述（如 'git commit'、'git reset'）")
    p_acquire.add_argument("--wait", type=int, default=DEFAULT_WAIT, help=f"被占用时轮询等待秒数（默认 {DEFAULT_WAIT}）")
    p_acquire.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"锁 stale 阈值秒数（默认 {DEFAULT_TIMEOUT}）")
    p_acquire.add_argument("--force", action="store_true", help="忽略现有锁强制接管（会打断对方操作，慎用）")

    # release
    p_release = subparsers.add_parser("release", help="释放 VCS 写操作锁")
    p_release.add_argument("--session", required=True, help="acquire 时输出的 LOCK_SESSION")

    # status
    p_status = subparsers.add_parser("status", help="查看锁状态")
    p_status.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"锁 stale 阈值秒数（默认 {DEFAULT_TIMEOUT}）")

    args = parser.parse_args()

    # 定位项目 .codebuddy 目录（锁目录的根），未找到时锁不可用
    codebuddy_dir = find_codebuddy_dir()
    if codebuddy_dir is None:
        print_result("FAIL", "未找到项目 .codebuddy 目录，VCS 写操作锁不可用。")
        return 1

    # 通用锁目录：经索引解析到项目侧 .codebuddy.project/caches/.vcs-lock/（回退引擎内 .vcs-lock/）
    lock_dir = resolve_lock_dir(codebuddy_dir)
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print_result("FAIL", f"创建锁目录失败：{exc}")
        return 1
    lock_file = lock_dir / LOCK_FILE_NAME

    if args.command == "acquire":
        return do_acquire(lock_file, args.op, args.wait, args.timeout, args.force)
    if args.command == "release":
        return do_release(lock_file, args.session)
    if args.command == "status":
        return do_status(lock_file, args.timeout)
    return 1


if __name__ == "__main__":
    sys.exit(main())
