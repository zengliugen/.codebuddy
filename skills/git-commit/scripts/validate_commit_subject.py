# -*- coding: utf-8 -*-
"""提交摘要格式校验脚本（git-commit 技能阶段四辅助）。

校验提交摘要是否符合项目规范。**type 枚举、subject/scope 长度上限、subject 语言
全部读取项目侧配置（经 `.codebuddy/project.index.json` 的 `git_commit.config` 定位
到 `.codebuddy.project/configs/skills/git-commit/config.json`）的 `commit_subject` 配置**；配置缺失、损坏
或缺少字段时**直接报错退出**，不静默回退内置默认值（配置是这些约定的唯一来源）：
- 格式 `<type>(<scope>): <subject>`
- type 属于配置的合法枚举
- subject 语言按配置、不超过 `subject_max_len` 字符、不以句号/分号结尾
- scope 不超过 `scope_max_len` 字符

用法：
    python validate_commit_subject.py "<提交摘要>"
    python validate_commit_subject.py --file <含摘要的文件>

退出码：
    0 —— 通过
    1 —— 格式/type/subject 校验失败
    2 —— 参数错误
    3 —— 配置缺失、损坏或缺少字段
"""

import argparse
import json
import os
import re
import sys


class ConfigError(RuntimeError):
    """配置缺失、损坏或缺少必需字段时抛出；由入口转为退出码 3。"""


# 格式：type(scope): subject（scope 可选）
SUBJECT_PATTERN = re.compile(r"^([a-z]+)(?:\(([^)]+)\))?: (.+)$")


def init_stdout():
    """Windows 下统一以 UTF-8 输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def find_codebuddy_dir():
    """从脚本位置向上查找 .codebuddy 目录；找不到返回 None。

    脚本位于 `<项目>/.codebuddy/skills/git-commit/scripts/`，逐级向上
    匹配目录名 `.codebuddy`，可定位项目配置根目录。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(current) == ".codebuddy":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def resolve_config_path(codebuddy_dir):
    """经索引注册表解析 git-commit 项目配置路径（相对路径基准为项目根）。

    索引 `.codebuddy/project.index.json` 为跨项目共享的入库文件，只读
    `files[逻辑名].path`；路径必须是相对路径（拒绝绝对路径，防索引污染）。
    """
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
    entry = (index.get("files") or {}).get("git_commit.config")
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError("索引缺少配置项 `files.git_commit.config.path`：%s" % index_path)
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 `files.git_commit.config.path` 必须为相对路径（当前为绝对路径）：%s" % rel)
    project_root = os.path.dirname(codebuddy_dir)
    return os.path.normpath(os.path.join(project_root, rel))


def load_commit_subject_config():
    """读取 git-commit 项目配置的 commit_subject 段（经索引定位）。

    配置是提交摘要约定的**唯一来源**：配置缺失、JSON 解析失败、缺少字段或字段
    非法时一律抛出 ConfigError，不再静默回退内置默认值。
    """
    codebuddy_dir = find_codebuddy_dir()
    if not codebuddy_dir:
        raise ConfigError("未能定位 .codebuddy 目录（脚本应位于 <项目>/.codebuddy/skills/git-commit/scripts/ 下）")

    # 配置经索引注册表定位到项目侧 .codebuddy.project/（见 project.index.json）
    config_path = resolve_config_path(codebuddy_dir)
    if not os.path.isfile(config_path):
        raise ConfigError(
            "未找到提交摘要配置：%s\n"
            "       请先按项目约定创建该配置（字段见该技能 references/project-config.md §0）。" % config_path
        )

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError) as exc:
        raise ConfigError("提交摘要配置读取失败（%s）：%s" % (exc, config_path))

    commit_subject = data.get("commit_subject") if isinstance(data, dict) else None
    if not isinstance(commit_subject, dict):
        raise ConfigError("配置缺少对象字段 `commit_subject`：%s" % config_path)

    # type 枚举：必须为非空字符串数组
    raw_types = commit_subject.get("types")
    if not isinstance(raw_types, list):
        raise ConfigError("配置项 `commit_subject.types` 必须是数组：%s" % config_path)
    types = {str(t).strip() for t in raw_types if str(t).strip()}
    if not types:
        raise ConfigError("配置项 `commit_subject.types` 不能为空：%s" % config_path)

    # 长度限制：必须为正整数
    subject_max_len = _require_positive_int(commit_subject, "subject_max_len", config_path)
    scope_max_len = _require_positive_int(commit_subject, "scope_max_len", config_path)

    # subject 语言：仅支持 zh/en
    subject_language = commit_subject.get("subject_language")
    if subject_language not in ("zh", "en"):
        raise ConfigError(
            "配置项 `commit_subject.subject_language` 必须为 `zh` 或 `en`，当前为：%r（%s）"
            % (subject_language, config_path)
        )

    return {
        "types": types,
        "subject_max_len": subject_max_len,
        "scope_max_len": scope_max_len,
        "subject_language": subject_language,
    }


def _require_positive_int(commit_subject, key, config_path):
    """读取必须为正整数的配置项；缺失或非法时抛出 ConfigError。"""
    value = commit_subject.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(
            "配置项 `commit_subject.%s` 必须为正整数，当前为：%r（%s）" % (key, value, config_path)
        )
    return value


def validate(subject_line, config):
    """校验单行提交摘要，返回 (是否通过, 错误列表)。"""
    errors = []
    line = subject_line.strip()

    if not line:
        return False, ["提交摘要是空行"]

    m = SUBJECT_PATTERN.match(line)
    if not m:
        return False, [
            "格式不符合 `<type>(<scope>): <subject>`，示例：`feat(Core): 新增对象池`"
        ]

    commit_type, scope, subject = m.group(1), m.group(2), m.group(3)

    if commit_type not in config["types"]:
        errors.append("type `{}` 不在合法枚举内（{}）".format(commit_type, "、".join(sorted(config["types"]))))

    if len(subject) > config["subject_max_len"]:
        errors.append("subject 长度 {} 超过上限 {} 字符".format(len(subject), config["subject_max_len"]))

    if subject.endswith(("。", "；", "：", ".", ";")):
        errors.append("subject 不应以句号/分号结尾：`{}`".format(subject[-1]))

    # subject 语言检测：zh（默认）要求含中文字符；en 要求含英文字母
    if config["subject_language"] == "en":
        if not re.search(r"[a-zA-Z]", subject):
            errors.append("subject 应使用英文：`{}`".format(subject))
    else:
        if not re.search(r"[\u4e00-\u9fff]", subject):
            errors.append("subject 应使用简体中文：`{}`".format(subject))

    if scope and len(scope) > config["scope_max_len"]:
        errors.append("scope 长度 {} 超过 {} 字符".format(len(scope), config["scope_max_len"]))

    return len(errors) == 0, errors


def main():
    init_stdout()
    parser = argparse.ArgumentParser(description="git-commit 提交摘要格式校验")
    parser.add_argument("subject", nargs="?", help="提交摘要（如 'feat(Core): 新增对象池'）")
    parser.add_argument("--file", default=None, help="含提交摘要的文件路径（读取第一行）")
    args = parser.parse_args()

    if args.subject and args.file:
        print("[FAIL] 不能同时指定 subject 与 --file", file=sys.stderr)
        return 2

    # 配置是提交摘要约定的唯一来源；放在参数解析之后，保证 --help 不受配置影响
    try:
        config = load_commit_subject_config()
    except ConfigError as exc:
        print("[FAIL] {}".format(exc), file=sys.stderr)
        return 3

    subject_line = args.subject
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                subject_line = f.readline()
        except OSError as exc:
            print("[FAIL] 读取文件失败：{}".format(exc), file=sys.stderr)
            return 2

    if not subject_line:
        print("[FAIL] 未提供提交摘要", file=sys.stderr)
        return 2

    ok, errors = validate(subject_line, config)
    if ok:
        print("[PASS] 提交摘要格式合规：{}".format(subject_line.strip()))
        return 0

    print("[FAIL] 提交摘要格式不合规：{}".format(subject_line.strip()))
    for err in errors:
        print("  - {}".format(err))
    return 1


if __name__ == "__main__":
    sys.exit(main())
