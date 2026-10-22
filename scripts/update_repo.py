#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仓库更新脚本（引擎侧通用工具）。

将目标仓库的当前分支更新到最新，并自动区分两种仓库形态、采用不同更新方式：

- **普通仓库**（独立克隆）：`git fetch` 后对当前分支执行快进拉取。
- **子模块**（submodule）：同样拉取当前分支最新；但会额外提示——父仓需提交
  submodule 指针更新，否则父仓仍锁定旧提交、其他协作者看不到新版本。

安全约束：

- 工作区存在未提交改动时，**仅报告不自动拉取**（避免冲突或丢失改动），
  打印本地/远程差异供用户手动处理。
- 默认使用 `--ff-only`（仅快进），不产生意外的合并提交；无法快进时报错提示。
- 检测到进行中的合并 / 变基时直接中止，不做任何网络操作。

用法：
  python update_repo.py                 # 更新脚本所在仓库（.codebuddy 引擎）
  python update_repo.py --dir <目录>     # 更新指定目录所在的仓库
  python update_repo.py --branch main   # 显式指定目标分支（默认取当前分支）
  python update_repo.py --fetch-only    # 只 fetch 并报告差异，不拉取
  python update_repo.py --json          # 结构化输出

退出码：
  0 —— 成功（含已是最好新、报告模式）
  1 —— 执行错误（git 命令失败）
  3 —— 目标不是 git 仓库 / 无远程 / 无法确定分支
"""

import argparse
import json
import os
import subprocess
import sys


class UpdateError(RuntimeError):
    """前置条件不满足或更新失败时抛出；由入口转为明确的错误退出。"""


def init_stdout():
    """Windows 下统一以 UTF-8 输出，关闭换行翻译避免渲染杂讯。"""
    if sys.platform == "win32":
        import ctypes as _ctypes
        try:
            _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            _ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def run_git(args, cwd):
    """执行 git 命令，返回 (退出码, stdout, stderr)（均去除首尾空白）。"""
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as error:
        raise UpdateError("无法执行 git 命令：%s" % error)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def git_ok(args, cwd):
    """执行 git 命令，成功时返回 stdout；失败返回 None（不抛错，用于探测）。"""
    rc, out, _err = run_git(args, cwd)
    return out if rc == 0 else None


# 进度总步数：1 检测形态、2 前置检查、3 获取远程、4 比较差异、5 拉取、6 重建包链接。
TOTAL_STEPS = 6


def log_step(index, message):
    """输出分步进度。

    一律写 stderr：stdout 需留给 --json 的结构化结果，混入进度会破坏可解析性。
    每次写入后立即 flush，保证双击运行时进度逐条出现，而非结束时一次性刷出。
    """
    sys.stderr.write("[%d/%d] %s\n" % (index, TOTAL_STEPS, message))
    sys.stderr.flush()


def log_detail(message):
    """输出步骤内的细节行（缩进对齐，便于扫读）。"""
    sys.stderr.write("        %s\n" % message)
    sys.stderr.flush()


def log_note(message):
    """输出提示/告警（带前缀，与普通细节区分）。"""
    sys.stderr.write("        [提示] %s\n" % message)
    sys.stderr.flush()


def rev_parse_head(repo_dir):
    """取当前 HEAD 的完整哈希；失败返回空串。"""
    return git_ok(["rev-parse", "HEAD"], repo_dir) or ""


def list_commits(repo_dir, rev_range, limit=20):
    """列出指定范围（如 HEAD..origin/main）的提交，返回 ["<短哈希> <标题>", ...]。"""
    rc, out, _err = run_git(["log", "--oneline", "--no-decorate", rev_range], repo_dir)
    if rc != 0 or not out:
        return []
    return [line for line in out.splitlines() if line.strip()][:limit]


def detect_repo(target_dir):
    """探测目标目录所在的仓库，返回信息字典。

    区分普通仓库与子模块：
    - 子模块：`.git` 为文件（gitdir 指针），或 `--show-superproject-working-tree` 非空。
    - 普通仓库：`.git` 为目录，且无 superproject。
    """
    if not os.path.isdir(target_dir):
        raise UpdateError("目标目录不存在：%s" % target_dir)

    toplevel = git_ok(["rev-parse", "--show-toplevel"], target_dir)
    if not toplevel:
        raise UpdateError(
            "目标目录不是 git 仓库（或不在仓库内）：%s\n"
            "       请确认该目录已初始化/克隆为 git 仓库。" % target_dir
        )

    # superproject 非空 → 位于子模块中；空 → 普通仓库（或非子模块）
    superproject = git_ok(["rev-parse", "--show-superproject-working-tree"], target_dir) or ""
    dot_git = os.path.join(toplevel, ".git")
    is_submodule = bool(superproject) or os.path.isfile(dot_git)

    branch = git_ok(["branch", "--show-current"], target_dir) or ""
    upstream = git_ok(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], target_dir) or ""
    remote_url = git_ok(["remote", "get-url", "origin"], target_dir) or ""

    return {
        "toplevel": os.path.normpath(toplevel),
        "is_submodule": is_submodule,
        "superproject": os.path.normpath(superproject) if superproject else "",
        "branch": branch,
        "upstream": upstream,
        "remote_url": remote_url,
    }


def check_in_progress(repo_dir):
    """检测进行中的合并 / 变基；返回描述字符串（无则返回空）。

    `git rev-parse --verify` 用 `-q` 静默；用 `.git` 下的标记文件判断更直观，
    但子模块的 `.git` 是文件（gitdir 指针），故统一走 `git rev-parse` 探测。
    """
    for ref, label in (("MERGE_HEAD", "合并（merge）"),
                       ("REBASE_HEAD", "变基（rebase）"),
                       ("CHERRY_PICK_HEAD", "拣选（cherry-pick）"),
                       ("REVERT_HEAD", "回退（revert）")):
        rc, _out, _err = run_git(["rev-parse", "--verify", "-q", ref], repo_dir)
        if rc == 0:
            return label
    return ""


def working_tree_dirty(repo_dir):
    """工作区是否有未提交改动（含未跟踪文件）。返回 (是否脏, 变更行列表)。"""
    rc, out, _err = run_git(["status", "--porcelain"], repo_dir)
    if rc != 0:
        raise UpdateError("读取工作区状态失败（git status 返回 %d）" % rc)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return bool(lines), lines


def divergence(repo_dir, ref_remote):
    """返回 (本地领先, 远程领先) 的提交数；无法比较时返回 None。"""
    rc, out, _err = run_git(["rev-list", "--left-right", "--count", "HEAD...%s" % ref_remote], repo_dir)
    if rc != 0:
        return None
    parts = out.split()
    if len(parts) != 2:
        return None
    return int(parts[0]), int(parts[1])


def do_update(target_dir, branch_override, fetch_only, dry_run):
    """执行更新主流程，返回结果字典。"""
    log_step(1, "检测仓库形态与分支…")
    info = detect_repo(target_dir)
    log_detail("仓库根目录：%s" % info["toplevel"])
    log_detail("仓库形态  ：%s" % ("子模块（submodule）" if info["is_submodule"] else "普通仓库"))
    if info["superproject"]:
        log_detail("所属父仓  ：%s" % info["superproject"])

    # 分支确定：显式参数 > 当前分支；子模块可能处于 detached（无当前分支）
    branch = branch_override or info["branch"]
    if not branch:
        raise UpdateError(
            "无法确定目标分支（仓库处于分离头指针 detached HEAD 状态）。\n"
            "       请用 `--branch <分支名>` 显式指定要更新的分支。"
        )
    info["branch"] = branch

    log_detail("目标分支  ：%s%s" % (branch, "" if info["branch"] else "（由 --branch 指定）"))
    log_detail("上游分支  ：%s" % (info["upstream"] or "（未配置，将回退 origin/%s）" % branch))

    if not info["remote_url"]:
        raise UpdateError(
            "仓库未配置远程 origin，无法拉取更新：%s\n"
            "       请先 `git remote add origin <远程地址>`。" % info["toplevel"]
        )
    log_detail("远程地址  ：%s" % info["remote_url"])

    log_step(2, "检查进行中的合并 / 变基…")
    # 进行中的合并 / 变基：不做任何网络操作
    in_progress = check_in_progress(info["toplevel"])
    if in_progress:
        raise UpdateError(
            "检测到进行中的%s操作，为安全起见中止。\n"
            "       请先完成或中止该操作（如 `git merge --abort` / `git rebase --abort`）。" % in_progress
        )
    log_detail("未发现进行中的合并 / 变基，可安全更新。")

    result = {
        "toplevel": info["toplevel"],
        "mode": "submodule" if info["is_submodule"] else "normal",
        "superproject": info["superproject"],
        "branch": branch,
        "remote_url": info["remote_url"],
        "upstream": info["upstream"],
        "action": "",
        "behind": None,
        "ahead": None,
        "dirty": False,
        "dirty_lines": [],
        "before_head": "",
        "after_head": "",
        "notice": "",
    }

    # 1. fetch（无论哪种模式都先取远程最新）
    log_step(3, "从远程获取最新提交（git fetch --prune）…")
    rc, _out, err = run_git(["fetch", "--prune", "origin"], info["toplevel"])
    if rc != 0:
        raise UpdateError("git fetch 失败：%s" % (err or "未知错误"))
    log_detail("远程获取完成。")

    # 远程分支引用（优先用上游；无上游则回退 origin/<branch>）
    remote_ref = "origin/%s" % branch

    # 2. 工作区脏：仅报告，不拉取
    log_step(4, "比较本地与远程差异…")
    dirty, dirty_lines = working_tree_dirty(info["toplevel"])
    if dirty:
        result["dirty"] = True
        result["dirty_lines"] = dirty_lines[:20]
        result["action"] = "report-only"
        div = divergence(info["toplevel"], remote_ref)
        if div:
            result["ahead"], result["behind"] = div
        log_note("工作区存在 %d 项未提交改动，已跳过拉取（避免冲突或丢失改动）。" % len(dirty_lines))
        log_detail("第 5 步「快进拉取」不会执行；仍会校验包链接以修复悬空。")
        result["notice"] = (
            "工作区存在未提交改动，已跳过拉取（避免冲突或丢失改动）。\n"
            "       请先提交或暂存改动后重试；如需查看差异可执行 git log HEAD..%s。" % remote_ref
        )
        return result

    # 3. 计算领先/落后
    div = divergence(info["toplevel"], remote_ref)
    if div:
        result["ahead"], result["behind"] = div

    if result["behind"] is None:
        log_note("无法与 %s 比较（远程分支可能不存在），将跳过差异统计。" % remote_ref)
    else:
        log_detail("本地领先 %d 个提交，落后 %d 个提交（对比 %s）。"
                   % (result["ahead"], result["behind"], remote_ref))

    if fetch_only or dry_run:
        result["action"] = "fetch-only"
        if result["behind"]:
            result["notice"] = "已获取远程最新；本地落后 %d 个提交（未拉取）。" % result["behind"]
            log_note("报告模式：不拉取。待拉取的提交：")
            for line in list_commits(info["toplevel"], "HEAD..%s" % remote_ref):
                log_detail("  " + line)
        else:
            result["notice"] = "已获取远程最新；本地已是最新。"
        return result

    # 4. 已是最好新 → 无需拉取
    if result["behind"] == 0:
        result["action"] = "up-to-date"
        log_detail("本地已是最新，无需拉取。")
        return result

    # 待拉取的提交先列出来，让用户看到「更新了什么」
    pending = list_commits(info["toplevel"], "HEAD..%s" % remote_ref)
    if pending:
        log_detail("待拉取 %d 个提交（最多显示 20 条）：" % result["behind"])
        for line in pending:
            log_detail("  " + line)
        if result["behind"] > len(pending):
            log_detail("  …另有 %d 个提交未显示" % (result["behind"] - len(pending)))

    # 5. 快进拉取（--ff-only：无法快进则报错，避免意外合并提交）
    before_head = rev_parse_head(info["toplevel"])
    log_step(5, "快进拉取（git pull --ff-only）…")
    if info["upstream"]:
        pull_args = ["pull", "--ff-only"]
    else:
        pull_args = ["pull", "--ff-only", "origin", branch]
    rc, out, err = run_git(pull_args, info["toplevel"])
    if rc != 0:
        raise UpdateError(
            "git pull 失败（可能本地与远程已分叉，无法快进）：\n       %s\n"
            "       请手动处理分叉（如 git rebase origin/%s）后重试。" % (err or out, branch)
        )
    result["action"] = "pulled"
    after_head = rev_parse_head(info["toplevel"])
    result["before_head"] = before_head[:7]
    result["after_head"] = after_head[:7]
    if before_head and after_head:
        log_detail("HEAD 变化：%s → %s" % (before_head[:7], after_head[:7]))
    else:
        log_detail("拉取完成。")

    # 6. 子模块额外提醒：父仓需提交指针更新
    if info["is_submodule"]:
        log_note("子模块已更新，父仓仍需提交指针更新才会对其他协作者生效。")
        result["notice"] = (
            "子模块已更新，但父仓仍锁定旧提交。\n"
            "       如需让更新生效，请在父仓执行：\n"
            "         git add %s\n"
            "         git commit -m \"chore: 更新 .codebuddy 引擎子模块\"\n"
            "       否则他人拉取到的仍是父仓锁定的旧版本，且父仓 `git submodule update`\n"
            "       会把子模块重置回旧提交。" % os.path.relpath(info["toplevel"], info["superproject"])
        )
    return result


def print_report(result):
    """人类可读输出。"""
    mode_label = "子模块（submodule）" if result["mode"] == "submodule" else "普通仓库"
    print("=" * 64)
    print("仓库更新报告")
    print("=" * 64)
    print("  目标仓库：%s" % result["toplevel"])
    print("  仓库形态：%s" % mode_label)
    if result["superproject"]:
        print("  所属父仓：%s" % result["superproject"])
    print("  分支    ：%s" % result["branch"])
    print("  远程    ：%s" % result["remote_url"])
    if result["upstream"]:
        print("  上游    ：%s" % result["upstream"])
    print()

    action = result["action"]
    if action == "up-to-date":
        print("结果：本地已是最新，无需更新。")
    elif action == "pulled":
        print("结果：已快进拉取到最新（落后 %s 个提交）。" % result["behind"])
        if result.get("before_head") and result.get("after_head"):
            print("        HEAD：%s → %s" % (result["before_head"], result["after_head"]))
    elif action == "fetch-only":
        print("结果：已获取远程最新（未拉取）。")
    elif action == "report-only":
        print("结果：仅报告，未拉取。")

    if result["behind"] is not None or result["ahead"] is not None:
        print()
        print("  本地领先：%s 个提交" % (result["ahead"] if result["ahead"] is not None else "?"))
        print("  本地落后：%s 个提交" % (result["behind"] if result["behind"] is not None else "?"))

    if result["dirty"]:
        print()
        print("  未提交改动（前 %d 项）：" % len(result["dirty_lines"]))
        for line in result["dirty_lines"]:
            print("    %s" % line)

    if result["notice"]:
        print()
        print("[提示] %s" % result["notice"])

    print("=" * 64)


def rebuild_pack_links(engine_dir):
    """引擎更新后重建项目侧包链接，消除改名/删除造成的悬空与哈希漂移。

    未初始化（无 .codebuddy.project/configs/packs.json）时跳过，避免给纯引擎仓带来副作用。
    返回 (退出码, 输出文本)；退出码 0 表示一致或修复成功。
    """
    project_root = os.path.dirname(engine_dir)
    state_path = os.path.join(project_root, ".codebuddy.project", "configs", "packs.json")
    installer = os.path.join(engine_dir, "scripts", "pack_install.py")
    log_step(TOTAL_STEPS, "重建项目侧包链接…")
    if not os.path.isfile(state_path):
        log_detail("未检测到项目侧安装状态（纯引擎仓），跳过。")
        return None, "未检测到项目侧安装状态，跳过包链接重建"
    if not os.path.isfile(installer):
        log_note("未找到引擎侧包安装器：%s" % installer)
        return 3, "未找到引擎侧包安装器：%s" % installer
    log_detail("调用 pack_install.py verify --repair …")
    result = subprocess.run(
        [sys.executable, installer, "--project-root", project_root, "verify", "--repair"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def main():
    init_stdout()
    parser = argparse.ArgumentParser(
        description="将目标仓库的当前分支更新到最新（自动识别普通仓库 / 子模块）"
    )
    parser.add_argument("--dir", default=None,
                        help="目标目录（默认：本脚本所在仓库，即 .codebuddy 引擎）")
    parser.add_argument("--branch", default=None, help="显式指定目标分支（默认取当前分支）")
    parser.add_argument("--fetch-only", action="store_true", help="只 fetch 并报告差异，不拉取")
    parser.add_argument("--dry-run", action="store_true", help="等同 --fetch-only（不修改工作区）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    # 默认目标：脚本所在目录（.codebuddy/scripts → .codebuddy）
    target_dir = args.dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not args.json:
        sys.stderr.write("=" * 64 + "\n")
        sys.stderr.write("CodeBuddy 引擎更新（共 %d 步）\n" % TOTAL_STEPS)
        sys.stderr.write("=" * 64 + "\n")
        sys.stderr.flush()

    try:
        result = do_update(target_dir, args.branch, args.fetch_only, args.dry_run)
    except UpdateError as error:
        sys.stderr.write("\n[错误] %s\n" % error)
        sys.stderr.flush()
        return 3

    # 更新后重建项目侧包链接：引擎内的组件可能改名/删除，链接需重新对齐
    pack_rc, pack_output = rebuild_pack_links(target_dir)

    if args.json:
        result["pack_links"] = {"exit_code": pack_rc, "output": pack_output}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)
        if pack_output:
            print()
            print("-" * 64)
            if pack_rc == 0:
                print("[包链接] 已对齐：%s" % pack_output)
            elif pack_rc is None:
                print("[包链接] %s" % pack_output)
            else:
                print("[包链接] 对齐失败（退出码 %s）：" % pack_rc)
                for line in pack_output.splitlines():
                    print("  " + line)
                print("  可手动重试：python .codebuddy/scripts/pack_install.py verify --repair")
    return 0


if __name__ == "__main__":
    sys.exit(main())
