#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行时产物清理脚本（引擎侧通用工具）。

读取引擎索引 `.codebuddy/project.index.json` 的 `artifacts.dirs`，清理项目侧运行时产物：

- **上级目录条目按整目录清空**：若某条目是其他条目的上级目录（如 `caches.root` →
  `.codebuddy.project/caches`），清空该目录后重建——其下**未登记**的残留（旧版本技能目录、
  手工留存的临时文件）一并清除，避免「清理时列不全」；
- **其余条目**删除自身内容并重建空目录（便于后续结果继续落盘）。

登记表仍用于脚本落盘、`core-init` 初始化与存在性校验；整目录清空只是让新增缓存目录
不必逐条登记也不会被漏清。目录清单完全由索引驱动，脚本不硬编码任何技能名或路径。

产物目录位于项目侧 `.codebuddy.project/`（不入库、不随引擎共享）。

用法：
  python cleanup_artifacts.py            # 交互确认后清理
  python cleanup_artifacts.py all        # 跳过确认直接清理
  python cleanup_artifacts.py --json     # 以 JSON 输出清理清单（不执行删除）

退出码：
  0 —— 成功（含无待清理文件）
  1 —— 执行错误（删除失败等）
  3 —— 索引缺失、损坏或缺少 artifacts 节
"""

import argparse
import json
import os
import shutil
import sys


class CleanupError(RuntimeError):
    """索引不可用或清理范围不安全时抛出；由入口转为明确的错误退出。"""


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


def _codebuddy_from_script():
    """自脚本位置向上查找名为 .codebuddy 的目录，返回其绝对路径；找不到返回 None。

    这是**唯一可靠的锚点**：脚本必然位于 <项目>/.codebuddy 之下，与当前工作目录无关。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(current) == ".codebuddy" and os.path.isdir(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _codebuddy_from_cwd(start=None):
    """自 start（缺省为当前工作目录）向上查找含 .codebuddy 子目录的目录。"""
    current = os.path.abspath(start if start else os.getcwd())
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_codebuddy_dir(start=None):
    """定位本项目的 .codebuddy 目录，返回绝对路径；找不到返回 None。

    判据：**以脚本自身位置为主，当前工作目录仅作一致性核对**。

    为什么不能 CWD 优先：向上查找会越过项目边界。实测在宿主仓库根运行脚本时，
    查找会命中上一层另一个项目的 .codebuddy（同级目录下还有别的引擎检出），
    于是包注册表、索引、配置全部读错，报出一批与本项目无关的错误，并在项目侧留下残留目录。

    为什么仍要看 CWD：「多项目经目录链接共享同一份 .codebuddy」是受支持的用法，
    此时 CWD 找到的 .codebuddy 与脚本锚点 realpath 相同，采用它不改变语义。
    CWD 结果与锚点 realpath 不同，说明命中的是另一份引擎，必须忽略。
    """
    anchor = _codebuddy_from_script()
    cwd_dir = _codebuddy_from_cwd(start)
    if anchor and cwd_dir and os.path.realpath(anchor) == os.path.realpath(cwd_dir):
        return cwd_dir
    if anchor:
        if cwd_dir:
            sys.stderr.write(
                "[提示] 当前目录向上命中的 .codebuddy 与脚本所属的不是同一份，已忽略：\n"
                "       忽略：%s\n       采用：%s\n" % (cwd_dir, anchor))
        return anchor
    return cwd_dir


def load_index():
    """读取项目配置索引，返回 (索引字典, 项目根绝对路径)。"""
    codebuddy_dir = find_codebuddy_dir(os.getcwd())
    if not codebuddy_dir:
        raise CleanupError("未找到 .codebuddy 目录。请在含 .codebuddy 的项目内运行。")
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise CleanupError(
            "未找到项目配置索引：%s\n"
            "       该索引由 .codebuddy 引擎提供；若缺失，请确认引擎包完整。" % index_path
        )
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise CleanupError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    return index, os.path.dirname(os.path.normpath(codebuddy_dir))


def resolve_artifact_dirs(index, project_root):
    """经索引解析全部产物目录，返回 [(逻辑名, 绝对路径)]。"""
    dirs = (index.get("artifacts") or {}).get("dirs")
    if not isinstance(dirs, dict) or not dirs:
        raise CleanupError("索引缺少非空键 `artifacts.dirs`：%s"
                           % os.path.join(project_root, ".codebuddy", "project.index.json"))
    result = []
    for logical_name, rel in dirs.items():
        if not isinstance(rel, str) or not rel:
            continue
        if os.path.isabs(rel):
            raise CleanupError("索引 `artifacts.dirs.%s` 必须为相对路径：%s" % (logical_name, rel))
        result.append((logical_name, os.path.normpath(os.path.join(project_root, rel))))
    return result


def collect_protected_paths(index, project_root):
    """收集索引中**入库内容**的绝对路径，作为整目录清理的保护清单。

    整目录清理只允许发生在纯运行时产物根上；若某个根包含任一入库文件（配置、规则正文、
    根级软链接源文件），说明索引把入库内容错登成了产物根，必须报错而不是照删。
    """
    protected = []
    for group_key in ("files", "rule_shells"):
        for code_name, entry in (index.get(group_key) or {}).items():
            rel = (entry or {}).get("path")
            if isinstance(rel, str) and rel and not os.path.isabs(rel):
                protected.append(("%s.%s" % (group_key, code_name),
                                  os.path.normpath(os.path.join(project_root, rel))))
    entries = (index.get("root_symlinks") or {}).get("entries") or {}
    for code_name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        for label in ("link", "path"):
            rel = entry.get(label)
            if isinstance(rel, str) and rel and not os.path.isabs(rel):
                protected.append(("root_symlinks.entries.%s.%s" % (code_name, label),
                                  os.path.normpath(os.path.join(project_root, rel))))
    return protected


def _normalized(path):
    """返回用于包含关系比较的规范化路径（Windows 下统一大小写）。"""
    return os.path.normcase(os.path.normpath(path))


def _is_within(path, parent):
    """判断 path 是否等于 parent 或位于其下（按路径分隔符比较，避免前缀误判）。"""
    path_key = _normalized(path)
    parent_key = _normalized(parent)
    return path_key == parent_key or path_key.startswith(parent_key + os.sep)


def _is_strict_parent(parent, child):
    """判断 parent 是否为 child 的严格上级目录。"""
    return _normalized(parent) != _normalized(child) and _is_within(child, parent)


def count_files(path):
    """统计目录下的文件总数（递归）。目录不存在返回 0。"""
    if not os.path.isdir(path):
        return 0
    total = 0
    for _root, _dirs, files in os.walk(path):
        total += len(files)
    return total


def list_unregistered_children(root, registered):
    """列出 root 下**未登记**的直接子项（相对名），用于在确认清单中显式展示。

    判定：某子项既不等于任何登记路径，也不是任何登记路径的上级目录 → 未登记。
    这些项只会被整目录清空带走，逐目录清理永远清不到。
    """
    if not os.path.isdir(root):
        return []
    names = []
    for child in sorted(os.listdir(root)):
        child_abs = os.path.normpath(os.path.join(root, child))
        if not any(_is_within(entry_path, child_abs) for entry_path in registered):
            names.append(child)
    return names


def build_plan(targets, protected, project_root):
    """把产物目录分为「整目录清理的根」与「单独清理的目录」。

    返回 (plan, covered)：
        plan —— 待清理项（根条目含 `unregistered` 字段，列出其下未登记残留）；
        covered —— 被根条目覆盖、需在清空后重建的登记目录。
    """
    # 第一步：找出「包含其他条目」的目录，即产物根；只保留最上层的一个。
    candidates = [(name, path) for name, path in targets
                  if any(_is_strict_parent(path, other) for other_name, other in targets
                         if other_name != name)]
    roots = [(name, path) for name, path in candidates
             if not any(_is_strict_parent(other_path, path)
                        for other_name, other_path in candidates if other_name != name)]

    # 第二步：安全护栏——产物根必须严格位于项目根内，且不得包含任何入库内容。
    registered = [path for _name, path in targets]
    for name, path in roots:
        if not _is_strict_parent(project_root, path):
            raise CleanupError(
                "索引 `artifacts.dirs.%s` 指向 %s，该路径不是项目根下的子目录，"
                "不能作为整目录清理的产物根。" % (name, path))
        for label, protected_path in protected:
            if _is_within(protected_path, path):
                raise CleanupError(
                    "索引 `artifacts.dirs.%s` 指向 %s，清理时会整目录清空；但该目录包含"
                    "入库内容 %s（%s）。请调整索引：产物根不得包含 files / rule_shells / "
                    "root_symlinks 登记的路径。" % (name, path, protected_path, label))

    # 第三步：生成清理项。根条目排在最前，未覆盖的目录各自清理。
    root_paths = [path for _name, path in roots]
    plan = [{"name": name, "path": path, "kind": "root",
             "files": count_files(path),
             "unregistered": list_unregistered_children(path, registered)}
            for name, path in roots]
    covered = []
    for name, path in targets:
        if any(_is_within(path, root_path) for root_path in root_paths):
            if not any(_normalized(path) == _normalized(root_path) for root_path in root_paths):
                covered.append((name, path))
            continue
        plan.append({"name": name, "path": path, "kind": "dir",
                     "files": count_files(path), "unregistered": []})
    return plan, covered


def main():
    """按索引清单清理产物目录，返回进程退出码。"""
    init_stdout()
    parser = argparse.ArgumentParser(
        description="清理项目侧运行时产物目录（清单由索引 artifacts.dirs 驱动）"
    )
    parser.add_argument("mode", nargs="?", default="",
                        help="传 `all` 跳过交互确认直接清理")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出清理清单（不删除）")
    args = parser.parse_args()

    try:
        index, project_root = load_index()
        targets = resolve_artifact_dirs(index, project_root)
        protected = collect_protected_paths(index, project_root)
        plan, covered = build_plan(targets, protected, project_root)
    except CleanupError as error:
        sys.stderr.write("[错误] %s\n" % error)
        return 3

    total = sum(item["files"] for item in plan)
    # 空目录也可能需要清理：整目录清空会带走未登记的残留项。
    has_residue = any(item["kind"] == "root" and item["unregistered"] for item in plan)

    if args.json:
        print(json.dumps({
            "total_files": total,
            "targets": plan,
            "covered": [{"name": name, "path": path} for name, path in covered],
        }, ensure_ascii=False, indent=2))
        return 0

    if total == 0 and not has_residue:
        print("未发现任何待清理的结果文件，无需清理。")
        return 0

    print("将清理以下产物目录（共 %d 个文件），并保留登记目录结构：" % total)
    print()
    for item in plan:
        if item["files"] == 0 and not item["unregistered"]:
            continue
        action = "整目录清空" if item["kind"] == "root" else "清空内容"
        print("  [%d 个文件] %s（%s）" % (item["files"], item["path"], action))
        if item["unregistered"]:
            print("      含未登记项：%s" % "、".join(item["unregistered"]))
    print()

    if args.mode != "all":
        try:
            confirm = input("确认删除以上全部结果文件？(Y/N)：").strip()
        except EOFError:
            confirm = ""
        if confirm.lower() != "y":
            print("操作已取消，未删除任何文件。")
            return 0

    removed = 0
    failed = []
    for item in plan:
        path = item["path"]
        if item["kind"] == "dir" and (not os.path.isdir(path) or item["files"] == 0):
            continue
        if item["kind"] == "root" and not os.path.isdir(path):
            continue
        try:
            shutil.rmtree(path)
            os.makedirs(path, exist_ok=True)
            removed += item["files"]
        except OSError as error:
            failed.append(path)
            sys.stderr.write("[警告] 清理失败，目录仍有残留：%s（%s）\n" % (path, error))

    # 重建被整目录清空覆盖的登记目录：即使其中原本没有文件，也要保留目录结构。
    for _name, path in covered:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as error:
            failed.append(path)
            sys.stderr.write("[警告] 重建产物目录失败：%s（%s）\n" % (path, error))

    print()
    print("清理完成：已删除 %d 个结果文件。" % removed)
    if failed:
        sys.stderr.write("[提示] 有 %d 个目录未能清理干净（可能被占用），请关闭相关进程后重试。\n"
                         % len(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
