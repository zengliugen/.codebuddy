# -*- coding: utf-8 -*-
"""提交摘要格式校验脚本（提交类技能的阶段四辅助）。

校验提交摘要是否符合项目规范。**摘要的格式、type 枚举、长度上限、subject 语言、禁用结尾字符
全部读取项目侧配置**（经 `.codebuddy/project.index.json` 的指定逻辑名定位），配置缺失、
损坏或缺少字段时**直接报错退出**，不静默回退内置默认值。

为什么格式必须来自配置而不是写死在引擎里：Git 与 SVN 的摘要约定**可能不同**（例如 SVN 侧团队
习惯 `[<scope>] <subject>` 或纯 `<subject>`）。把某一种格式写进引擎，
另一侧只有两种结局：校验一律失败，或被绕过。因此引擎只定义「怎么用配置校验」，
不定义「长什么样」。

配置结构（commit_subject 段）：

| 键 | 必填 | 说明 |
|---|---|---|
| format | 否 | 人类可读的格式描述，用于报错提示；缺失时回退为 pattern 原文 |
| pattern | 是 | **校验依据**。正则，用命名组 (?P<type>...) / (?P<scope>...) / (?P<subject>...) 标记字段 |
| types | 是 | type 枚举。元素为字符串，或 {"name": ..., "description": ...}；**数组顺序即决策优先级** |
| subject_max_len | pattern 含 subject 组时必填 | subject 长度上限 |
| scope_max_len | pattern 含 scope 组时必填 | scope 长度上限 |
| subject_language | pattern 含 subject 组时必填 | zh 简体中文 / en 英文 |
| forbid_trailing | 否 | subject 不允许的结尾字符数组 |

**判定以 pattern 为准**：format 只是给人看的描述，与 pattern 不一致时脚本只信 pattern。
这样判定标准始终只有一个来源，不会出现「文档说可以、脚本说不行」。

用法：
    python validate_commit_subject.py --config-key <逻辑名> "<提交摘要>"
    python validate_commit_subject.py --config-key <逻辑名> --file <含摘要的文件>

    逻辑名取值：Git 提交用 git_commit.config，SVN 提交用 svn_commit.config。
    --config-key **必填且无默认值**：设了默认值就等于给 SVN 一条「悄悄读 Git 配置」的路径，
    两份配置一旦分叉（格式恰恰允许不同），表现是「配置改了却不生效」而不会有任何报错。

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


# pattern 中允许被识别的字段名；未出现的字段不参与校验
KNOWN_FIELDS = ("type", "scope", "subject")
# pattern 缺省示例（仅用于报错提示，不参与判定）
PATTERN_HINT = "^(?P<type>[a-z]+)(?:\\((?P<scope>[^)]+)\\))?: (?P<subject>.+)$"


def init_stdout():
    """Windows 下统一以 UTF-8 输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def find_codebuddy_dir():
    """从脚本位置向上查找 .codebuddy 目录；找不到返回 None。

    脚本位于 <项目>/.codebuddy/skills/vcs/vcs-router/scripts/，逐级向上
    匹配目录名 .codebuddy，可定位项目配置根目录。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(current) == ".codebuddy":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def resolve_config_path(codebuddy_dir, config_key):
    """经索引注册表按逻辑名解析项目配置路径（相对路径基准为项目根）。

    索引 .codebuddy/project.index.json 为跨项目共享的入库文件，只读
    files[逻辑名].path；路径必须是相对路径（拒绝绝对路径，防索引污染）。
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
    entry = (index.get("files") or {}).get(config_key)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError("索引缺少配置项 files.%s.path：%s" % (config_key, index_path))
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 files.%s.path 必须为相对路径（当前为绝对路径）：%s"
                          % (config_key, rel))
    project_root = os.path.dirname(codebuddy_dir)
    return os.path.normpath(os.path.join(project_root, rel))


def format_label(commit_subject, config_path):
    """读取格式描述；缺失时回退为 pattern 原文（仍来自配置，不引入引擎默认值）。"""
    value = commit_subject.get("format")
    if isinstance(value, str) and value.strip():
        return value.strip()
    pattern_text = commit_subject.get("pattern")
    if isinstance(pattern_text, str) and pattern_text.strip():
        return pattern_text.strip()
    raise ConfigError("配置项 commit_subject.format 缺失，且无 pattern 可回退：%s" % config_path)


def parse_types(raw_types, config_path):
    """归一化 type 枚举：兼容「字符串数组」与「对象数组」两种写法。

    对象写法 {"name": "feat", "description": "新功能"} 可携带 type 含义，供 LLM 按配置决策；
    字符串写法仅为纯枚举。两种写法返回同一结构，使校验与决策顺序共用一份实现。

    参数：
        raw_types：配置中的 commit_subject.types 原始值。
        config_path：配置文件路径，用于报错定位。

    返回：
        [(type 名, 含义或 None)]，顺序与配置一致（即决策优先级）。
    """
    if not isinstance(raw_types, list):
        raise ConfigError("配置项 commit_subject.types 必须是数组：%s" % config_path)
    types = []
    for item in raw_types:
        if isinstance(item, str):
            name = item.strip()
            description = None
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            description = item.get("description")
            if description is not None and not isinstance(description, str):
                raise ConfigError(
                    "配置项 commit_subject.types[].description 必须是字符串：%s" % config_path)
        else:
            raise ConfigError(
                "配置项 commit_subject.types 的元素必须是字符串或 {name, description} 对象：%s"
                % config_path)
        if not name:
            raise ConfigError("配置项 commit_subject.types 中存在空 type 名：%s" % config_path)
        types.append((name, description))
    if not types:
        raise ConfigError("配置项 commit_subject.types 不能为空：%s" % config_path)
    return types


def require_positive_int(commit_subject, key, config_path, reason):
    """读取必须为正整数的配置项；缺失或非法时抛出 ConfigError。

    参数：
        commit_subject：commit_subject 段字典。
        key：键名。
        config_path：配置文件路径，用于报错定位。
        reason：为什么该键在此配置下必填（写进报错，说明依据）。
    """
    value = commit_subject.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(
            "配置项 commit_subject.%s 必须为正整数，当前为：%r（%s；%s）"
            % (key, value, config_path, reason)
        )
    return value


def load_commit_subject_config(config_key):
    """读取指定逻辑名下项目配置的 commit_subject 段（经索引定位）。

    配置是提交摘要约定的**唯一来源**：配置缺失、JSON 解析失败、缺少字段或字段
    非法时一律抛出 ConfigError，不回退内置默认值——一旦回退，项目换了格式也不会生效。
    """
    codebuddy_dir = find_codebuddy_dir()
    if not codebuddy_dir:
        raise ConfigError("未能定位 .codebuddy 目录（脚本应位于 <项目>/.codebuddy/skills/vcs/vcs-router/scripts/ 下）")

    config_path = resolve_config_path(codebuddy_dir, config_key)
    if not os.path.isfile(config_path):
        raise ConfigError(
            "未找到提交摘要配置：%s\n"
            "       请先按项目约定创建该配置（字段见提交技能的 references/project-config.md §0）。"
            % config_path
        )

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError) as exc:
        raise ConfigError("提交摘要配置读取失败（%s）：%s" % (exc, config_path))

    commit_subject = data.get("commit_subject") if isinstance(data, dict) else None
    if not isinstance(commit_subject, dict):
        raise ConfigError("配置缺少对象字段 commit_subject：%s" % config_path)

    # 先校验 pattern（判定依据），再取展示标签：顺序反了会让「缺 pattern」报成「缺 format」，
    # 而 format 是可选的，报错会把人引向错误的方向。
    pattern_text = commit_subject.get("pattern")
    if not isinstance(pattern_text, str) or not pattern_text.strip():
        raise ConfigError(
            "配置项 commit_subject.pattern 必须是正则字符串（校验以它为准）：%s\n"
            "       缺省示例（与 Git 侧常用写法一致，仅供参考）：%s"
            % (config_path, PATTERN_HINT)
        )
    try:
        pattern = re.compile(pattern_text)
    except re.error as error:
        raise ConfigError("配置项 commit_subject.pattern 不是合法正则（%s）：%s"
                          % (error, config_path))

    label = format_label(commit_subject, config_path)

    fields = [name for name in KNOWN_FIELDS if name in pattern.groupindex]
    if not fields:
        raise ConfigError(
            "配置项 commit_subject.pattern 不含任何命名组，无法校验内容：%s\n"
            "       须用 (?P<type>...) / (?P<scope>...) / (?P<subject>...) 标记要校验的字段。"
            % config_path
        )

    config = {
        "label": label,
        "pattern": pattern,
        "fields": fields,
        "types": parse_types(commit_subject.get("types"), config_path),
    }

    if "subject" in fields:
        config["subject_max_len"] = require_positive_int(
            commit_subject, "subject_max_len", config_path, "pattern 含 subject 组")
        language = commit_subject.get("subject_language")
        if language not in ("zh", "en"):
            raise ConfigError(
                "配置项 commit_subject.subject_language 必须为 zh 或 en，当前为：%r（%s；pattern 含 subject 组）"
                % (language, config_path)
            )
        config["subject_language"] = language
        forbid = commit_subject.get("forbid_trailing") or []
        if not isinstance(forbid, list) or any(not isinstance(x, str) for x in forbid):
            raise ConfigError(
                "配置项 commit_subject.forbid_trailing 必须是字符串数组：%s" % config_path)
        config["forbid_trailing"] = forbid

    if "scope" in fields:
        config["scope_max_len"] = require_positive_int(
            commit_subject, "scope_max_len", config_path, "pattern 含 scope 组")

    return config


def validate(subject_line, config):
    """校验单行提交摘要，返回 (是否通过, 错误列表)。

    参数：
        subject_line：提交摘要文本（只取一行，正文不参与校验）。
        config：load_commit_subject_config 的返回值。
    """
    errors = []
    line = subject_line.strip()
    label = config["label"]

    if not line:
        return False, ["提交摘要是空行"]

    match = config["pattern"].match(line)
    if not match:
        return False, ["格式不符合 %s：%s" % (label, line)]

    groups = match.groupdict()
    type_names = [name for name, _desc in config["types"]]

    commit_type = (groups.get("type") or "").strip()
    if "type" in config["fields"] and commit_type not in type_names:
        errors.append("type %s 不在合法枚举内（%s）" % (commit_type, "、".join(type_names)))

    subject = (groups.get("subject") or "").strip()
    if "subject" in config["fields"]:
        if len(subject) > config["subject_max_len"]:
            errors.append("subject 长度 %d 超过上限 %d 字符"
                          % (len(subject), config["subject_max_len"]))
        trailing = config["forbid_trailing"]
        if trailing and subject.endswith(tuple(trailing)):
            errors.append("subject 不应以 %s 结尾" % "、".join(trailing))
        if config["subject_language"] == "en":
            if not re.search(r"[a-zA-Z]", subject):
                errors.append("subject 应使用英文：%s" % subject)
        elif not re.search(r"[\u4e00-\u9fff]", subject):
            errors.append("subject 应使用简体中文：%s" % subject)

    scope = (groups.get("scope") or "").strip()
    if "scope" in config["fields"] and scope and len(scope) > config["scope_max_len"]:
        errors.append("scope 长度 %d 超过 %d 字符" % (len(scope), config["scope_max_len"]))

    return len(errors) == 0, errors


def main():
    """脚本主入口。"""
    init_stdout()
    parser = argparse.ArgumentParser(description="提交摘要格式校验（格式与枚举由项目侧配置声明）")
    parser.add_argument("--config-key", required=True,
                        help="项目配置逻辑名（git_commit.config 或 svn_commit.config）；必填，不设默认值")
    parser.add_argument("subject", nargs="?", help="提交摘要文本")
    parser.add_argument("--file", default=None, help="含提交摘要的文件路径（读取第一行）")
    args = parser.parse_args()

    if args.subject and args.file:
        print("[FAIL] 不能同时指定 subject 与 --file", file=sys.stderr)
        return 2

    try:
        config = load_commit_subject_config(args.config_key)
    except ConfigError as exc:
        print("[FAIL] {}".format(exc), file=sys.stderr)
        return 3

    subject_line = args.subject
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as handle:
                subject_line = handle.readline()
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
    print("       期望格式：{}".format(config["label"]))
    for err in errors:
        print("  - {}".format(err))
    return 1


if __name__ == "__main__":
    sys.exit(main())
