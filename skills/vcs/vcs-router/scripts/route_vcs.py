# -*- coding: utf-8 -*-
"""
VCS 操作路由脚本（vcs-router 技能核心）。

功能：
- 检测指定目录（默认当前工作目录）是否为 Git 仓库：git / none。
- 接收操作类型（--op，默认 commit），组合出路由目标技能名 git-<op>。
- 检查路由目标技能是否存在（skills/<目标>/SKILL.md 存在则视为可路由）。
- 检测结果缓存到技能目录 .cache/vcs-route.json，缓存目录一致且未超时时直接命中，
  跳过检测命令（目录切换立即失效，默认 10 分钟超时）。缓存仅存 VCS 类型，与操作类型无关。
- 支持 --out 将完整路由 JSON 落文件、--quiet 让 stdout 仅输出一行（规避终端伪影污染 JSON 解析）。

用法：
    python route_vcs.py [--dir 目录] [--op 操作] [--refresh] [--timeout 秒]
                        [--out 文件] [--quiet]

输出：
    stdout 输出 JSON 路由结果（--quiet 时仅输出一行 vcs_type/route_target 摘要）；退出码 0 表示成功。
    --out 指定时，完整 JSON 额外写入该文件；--quiet 且未指定 --out 时，落到默认结果文件
    项目侧 <项目根>/.codebuddy.project/caches/skills/vcs/vcs-router/.cache/vcs-route.result.json
    （与检测缓存 vcs-route.json 分开，避免互相覆盖）。

退出码：
    0  成功
    1  参数错误
    2  内部错误
"""

import argparse
import json
import os
import subprocess
import sys
import time

# Windows 控制台下强制 UTF-8 输出，避免中文提示乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def resolve_directory(value):
    """解析目标目录为绝对路径，目录不存在时抛出异常。"""
    directory = os.path.abspath(value)
    if not os.path.isdir(directory):
        raise ValueError(f"目录不存在：{directory}")
    return os.path.normpath(directory)


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


def _resolve_artifact_dir(logical_name):
    """经索引 `artifacts.dirs` 解析运行时产物目录（相对路径基准为项目根），并确保目录存在。"""
    codebuddy_dir = _find_codebuddy_dir(os.path.dirname(os.path.abspath(__file__)))
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
    rel = (index.get("artifacts") or {}).get("dirs", {}).get(logical_name)
    if not isinstance(rel, str) or not rel:
        raise RuntimeError("索引缺少产物目录项 `artifacts.dirs.%s`：%s" % (logical_name, index_path))
    if os.path.isabs(rel):
        raise RuntimeError("索引 `artifacts.dirs.%s` 必须为相对路径（当前为绝对路径）：%s" % (logical_name, rel))
    path = os.path.normpath(os.path.join(os.path.dirname(codebuddy_dir), rel))
    os.makedirs(path, exist_ok=True)
    return path


# 技能目录：脚本位于 <技能目录>/scripts/route_vcs.py
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 技能根目录：skills/，用于检查路由目标技能是否存在
USER_SKILLS_DIR = os.path.dirname(SKILL_DIR)


def get_cache_path():
    """返回缓存文件路径：项目侧产物 .cache/vcs-route.json（仅本机使用，不入库）。"""
    return os.path.join(_resolve_artifact_dir("vcs_router.cache"), "vcs-route.json")


def get_default_result_path():
    """返回 --quiet 时默认的结果文件路径，与检测缓存分开避免互相覆盖。"""
    return os.path.join(_resolve_artifact_dir("vcs_router.cache"), "vcs-route.result.json")


def emit_result(result, out_path, quiet):
    """输出路由结果：--out 落文件；--quiet 时 stdout 仅输出一行摘要，否则输出紧凑 JSON。"""
    if out_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as file:
                file.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        except OSError as error:
            # 写文件失败不影响路由结论，仅告警到 stderr
            print(f"[警告] 写入结果文件失败：{error}", file=sys.stderr)

    if quiet:
        target = result.get("route_target") or "（空）"
        print(
            f"vcs_type={result.get('vcs_type')}; route_target={target}; "
            f"target_exists={str(result.get('target_exists')).lower()}; source={result.get('source')}"
        )
    else:
        print(json.dumps(result, ensure_ascii=False))


def read_cache(cache_path):
    """读取缓存文件，损坏或无法解析时返回 None。"""
    try:
        with open(cache_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, ValueError):
        return None


def write_cache(cache_path, directory, vcs_type):
    """将检测结果写入缓存，.cache 目录不存在时先创建。"""
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        payload = {
            "path": directory,
            "vcs_type": vcs_type,
            "detected_at": int(time.time()),
        }
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    except OSError as error:
        # 缓存写入失败不阻塞检测，仅输出告警到 stderr
        print(f"[警告] 缓存写入失败：{error}", file=sys.stderr)


def is_cache_valid(cached, directory, timeout_seconds):
    """校验缓存是否有效：目录一致、类型合法、未超时。"""
    if not cached:
        return False
    cached_path = cached.get("path")
    cached_type = cached.get("vcs_type")
    cached_at = cached.get("detected_at")
    if not isinstance(cached_path, str) or not isinstance(cached_type, str) or not isinstance(cached_at, (int, float)):
        return False
    if cached_type != "git":
        return False
    if os.path.normcase(cached_path) != os.path.normcase(directory):
        return False
    if int(time.time()) - int(cached_at) > timeout_seconds:
        return False
    return True


def run_command(command, directory):
    """在指定目录执行命令，返回（退出码, 标准输出）。"""
    try:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout.strip()
    except OSError:
        # 命令不存在（如 git 未安装）视为检测失败
        return 1, ""


def detect_git(directory):
    """检测是否为 Git 仓库：命令确认 + .git 目录兜底。"""
    returncode, stdout = run_command(["git", "rev-parse", "--is-inside-work-tree"], directory)
    command_ok = returncode == 0 and stdout.lower() == "true"
    return command_ok or os.path.isdir(os.path.join(directory, ".git"))


def route_target(vcs_type, operation):
    """VCS 类型 + 操作类型 → 路由目标技能名（<vcs>-<op>）。none 或无操作返回空字符串。"""
    if vcs_type == "git" and operation:
        return f"{vcs_type}-{operation}"
    return ""


def target_exists(target):
    """检查路由目标技能是否存在（skills/<目标>/SKILL.md 存在则视为可路由）。"""
    if not target:
        return False
    target_skill_md = os.path.join(USER_SKILLS_DIR, target, "SKILL.md")
    return os.path.isfile(target_skill_md)


def parse_args(argv):
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="VCS 操作路由 + 缓存读写脚本")
    parser.add_argument("--dir", default=None, help="目标目录（默认当前工作目录）")
    parser.add_argument("--op", default="commit", help="操作类型（默认 commit，如 commit/merge）")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新检测")
    parser.add_argument("--timeout", type=int, default=600, help="缓存超时秒数（默认 600）")
    parser.add_argument("--out", default=None, help="将完整路由 JSON 写入指定文件")
    parser.add_argument("--quiet", action="store_true", help="stdout 仅输出一行 vcs_type/route_target 摘要")
    return parser.parse_args(argv)


def build_result(vcs_type, operation, cache_path, cache_hit, source, detected_at):
    """组装统一的路由结果字典。"""
    target = route_target(vcs_type, operation)
    return {
        "vcs_type": vcs_type,
        "operation": operation,
        "route_target": target,
        "target_exists": target_exists(target),
        "cache_hit": cache_hit,
        "cache_file": cache_path,
        "detected_at": detected_at,
        "source": source,
    }


def main(argv):
    """脚本主入口。"""
    args = parse_args(argv)
    operation = args.op or "commit"

    # --quiet 且未显式指定 --out 时，把完整 JSON 落到独立结果文件（不覆盖检测缓存）
    out_path = args.out
    if args.quiet and not out_path:
        out_path = get_default_result_path()

    try:
        directory = resolve_directory(args.dir if args.dir else os.getcwd())
        cache_path = get_cache_path()

        if not args.refresh:
            cached = read_cache(cache_path)
            if is_cache_valid(cached, directory, args.timeout):
                vcs_type = cached["vcs_type"]
                result = build_result(vcs_type, operation, cache_path, True, "cache", cached["detected_at"])
                emit_result(result, out_path, args.quiet)
                return 0

        # 缓存无效或强制刷新：执行检测
        vcs_type = "git" if detect_git(directory) else "none"

        # none 结果不写入缓存，避免目录初始化后旧缓存误导路由
        if vcs_type != "none":
            write_cache(cache_path, directory, vcs_type)

        result = build_result(vcs_type, operation, cache_path, False, "detection", int(time.time()))
        emit_result(result, out_path, args.quiet)
        return 0
    except ValueError as error:
        print(f"[错误] {error}", file=sys.stderr)
        return 1
    except Exception as error:  # 防御：未知异常统一转为退出码 2
        print(f"[错误] 内部异常：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
