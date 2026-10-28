#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""devflow-guard：开发流程的过程文档骨架生成与契约体检。

三个模式：

  init          按项目配置把文档目录结构、目录说明与文档模板复制到项目侧
  new <能力名>  生成设计、计划、测试三份骨架并登记能力总览表
  audit         只读体检文档契约，按三档输出缺口

设计前提（与项目侧的同类工具刻意不同）：

1. **不按固定层级数定位项目根**。自脚本所在目录向上查找含 .git 或 .codebuddy 的目录，
   因此同一份脚本在引擎侧与项目侧两种挂载深度下都能工作。
2. **一切形状来自项目配置**。文档根、五个子目录名、总览表列序、状态取值、文件头字段、
   生成器标识全部读配置，脚本不内置任何默认值。配置缺失或缺少必需键时直接报错退出（退出码 3），
   不回退默认值——否则「配置写了但没生效」会表现成「检查莫名通过」。
3. **只查机械可判定的契约**，不查代码落位。落位原则属规则判据，抽象后无法机械校验。

用法：
    python devflow_guard.py init
    python devflow_guard.py new <能力名>
    python devflow_guard.py audit
    python devflow_guard.py audit --root <项目根>

退出码：
    0 —— 通过（audit 可能附提示级输出）
    1 —— 存在警告（需人工判断）
    2 —— 存在错误，或参数错误、文件冲突
    3 —— 配置不可用（缺失、损坏、缺少必需键）
"""

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import date

# 配置在项目索引中的逻辑名
CONFIG_CODENAME = "devflow.docs.config"

# 模板根目录（相对本脚本）：scripts/ -> devflow-guard/ -> references/templates
TEMPLATES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "templates")
)

# 五份文档骨架所在子目录。命名避开 docs/templates 这类与实际用途不符的词：
# 这里装的是「骨架源文件」，与文档根（docs_root）无关。
SKELETON_DIR = "skeletons"

# 需要创建说明文件的子目录（键名对应配置 dirs 下的键，缺失即报错）。
# explore 是必需键：需求确认是这个流程的一部分，不是可选附加项——
# 做成可选会产生两种「new 的行为不一样」的项目，而规则文本无法同时说清两者。
DOC_SUBDIR_KEYS = ("explore", "design", "plans", "testing", "decisions", "archive")

# 配置必需键（缺失即报错，不回退默认值）
REQUIRED_CONFIG_KEYS = (
    "docs_root",
    "dirs",
    "overview",
    "file_header",
    "capability_name_pattern",
)
REQUIRED_DIR_KEYS = DOC_SUBDIR_KEYS
REQUIRED_OVERVIEW_KEYS = (
    "file",
    "header",
    "status_values",
    "placeholder_dash",
    "placeholder_todo",
    "capability_column",
    "status_column",
)
REQUIRED_HEADER_KEYS = ("fields", "status_field", "generator_field", "generator_values")

# 分级
LEVEL_ERROR = "错误"
LEVEL_WARN = "警告"
LEVEL_INFO = "提示"


class ConfigError(Exception):
    """配置不可用。"""


class Finding:
    """一条缺口记录。"""

    def __init__(self, level, check, message):
        """初始化缺口。

        参数：
            level: 分级（错误 / 警告 / 提示）
            check: 检查项名称
            message: 面向人的说明
        """
        self.level = level
        self.check = check
        self.message = message

    def __str__(self):
        """输出为一行可读文本。"""
        return "[" + self.level + "] " + self.check + "：" + self.message


# ---------------------------------------------------------------------------
# 定位与配置
# ---------------------------------------------------------------------------


def find_project_root(start):
    """自 start 向上查找含 .git 或 .codebuddy 的目录作为项目根。

    参数：
        start: 起始目录

    返回：
        项目根绝对路径；找不到时返回起始目录本身
    """
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, ".git")) or os.path.isdir(
            os.path.join(current, ".codebuddy")
        ):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def find_codebuddy_dir(root):
    """自 root 向上查找含 .codebuddy 子目录的目录，返回该 .codebuddy 的绝对路径。

    参数：
        root: 起始目录

    返回：
        .codebuddy 绝对路径；找不到返回 None
    """
    current = os.path.abspath(root)
    while True:
        candidate = os.path.join(current, ".codebuddy")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def resolve_config_path(root):
    """经索引解析配置路径，拒绝绝对路径。

    参数：
        root: 项目根

    返回：
        配置文件绝对路径

    异常：
        ConfigError: 索引缺失、无该逻辑名、路径为绝对路径
    """
    codebuddy_dir = find_codebuddy_dir(root)
    if not codebuddy_dir:
        raise ConfigError("未能定位 .codebuddy 目录：%s" % root)
    index_path = os.path.join(codebuddy_dir, "project.index.json")
    if not os.path.isfile(index_path):
        raise ConfigError("未找到项目配置索引：%s" % index_path)
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("项目配置索引读取失败（%s）：%s" % (error, index_path))
    if not isinstance(index, dict):
        raise ConfigError("项目配置索引顶层必须是 JSON 对象：%s" % index_path)
    entry = (index.get("files") or {}).get(CONFIG_CODENAME)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ConfigError(
            "索引缺少配置项 files.%s.path：%s（该包是否已正确登记？）"
            % (CONFIG_CODENAME, index_path)
        )
    rel = entry["path"]
    if os.path.isabs(rel):
        raise ConfigError("索引 files.%s.path 必须为相对路径：%s" % (CONFIG_CODENAME, rel))
    return os.path.normpath(os.path.join(root, rel))


def load_config(root):
    """经索引加载并校验配置；任何缺失都抛 ConfigError，不回退默认值。

    参数：
        root: 项目根

    返回：
        配置字典

    异常：
        ConfigError: 文件不存在、JSON 损坏、顶层非对象、缺必需键、docs_root 为空
    """
    config_path = resolve_config_path(root)
    if not os.path.isfile(config_path):
        raise ConfigError(
            "配置未找到：%s\n请先由 core-init 生成该配置，或按索引中的 template 手工创建。"
            % config_path
        )
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("配置读取失败（%s）：%s" % (error, config_path))
    if not isinstance(config, dict):
        raise ConfigError("配置顶层必须是 JSON 对象：%s" % config_path)

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigError("配置缺少必需键：%s（%s）" % ("、".join(missing), config_path))

    if not str(config.get("docs_root") or "").strip():
        raise ConfigError(
            "配置 docs_root 为空：%s\n必须声明文档根目录（相对项目根的路径），"
            "脚本不提供默认值。" % config_path
        )
    if not isinstance(config["docs_root"], str):
        raise ConfigError("配置 docs_root 必须是字符串：%s" % config_path)
    if os.path.isabs(config["docs_root"]):
        raise ConfigError("配置 docs_root 必须为项目根相对路径：%s" % config["docs_root"])

    dirs = config.get("dirs")
    if not isinstance(dirs, dict):
        raise ConfigError("配置 dirs 必须是对象：%s" % config_path)
    missing_dirs = [key for key in REQUIRED_DIR_KEYS if not str(dirs.get(key) or "").strip()]
    if missing_dirs:
        raise ConfigError("配置 dirs 缺少子目录名：%s" % "、".join(missing_dirs))

    overview = config.get("overview")
    if not isinstance(overview, dict):
        raise ConfigError("配置 overview 必须是对象：%s" % config_path)
    missing_overview = [key for key in REQUIRED_OVERVIEW_KEYS if key not in overview]
    if missing_overview:
        raise ConfigError("配置 overview 缺少键：%s" % "、".join(missing_overview))

    header = config.get("file_header")
    if not isinstance(header, dict):
        raise ConfigError("配置 file_header 必须是对象：%s" % config_path)
    missing_header = [key for key in REQUIRED_HEADER_KEYS if key not in header]
    if missing_header:
        raise ConfigError("配置 file_header 缺少键：%s" % "、".join(missing_header))
    if not header.get("fields"):
        raise ConfigError("配置 file_header.fields 不能为空（至少包含状态与关联能力）")
    if not header.get("generator_values"):
        raise ConfigError("配置 file_header.generator_values 不能为空（否则生成器字段无从校验）")

    try:
        re.compile(config["capability_name_pattern"])
    except (re.error, TypeError) as error:
        raise ConfigError("配置 capability_name_pattern 不是合法正则：%s" % error)

    _validate_shapes(config, config_path)
    return config


def _validate_shapes(config, config_path):
    """校验配置各值的形状与取值范围。

    只校验「键存在」不足以保证可用：空数组会让索引报 IndexError、
    字符串会被当成数组按字符取值、负数列索引会静默取到最后一列。
    这些错误一旦放过，表现是「检查莫名通过」或「输出 traceback」，
    因此统一在这里转成可操作的配置错误（退出码 3）。

    参数：
        config: 配置字典
        config_path: 配置路径，用于错误信息定位

    异常：
        ConfigError: 任一形状或范围不合法
    """
    overview = config["overview"]
    header = overview["header"]
    if not isinstance(header, list) or not all(isinstance(item, str) and item for item in header):
        raise ConfigError("overview.header 必须是非空字符串数组：%s" % config_path)

    for key in ("capability_column", "status_column"):
        value = overview[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError("overview.%s 必须是整数：%s" % (key, config_path))
        if not 0 <= value < len(header):
            raise ConfigError(
                "overview.%s = %d 超出表头范围 0..%d：%s"
                % (key, value, len(header) - 1, config_path)
            )
    if overview["capability_column"] == overview["status_column"]:
        raise ConfigError("overview 的能力列与状态列不能是同一列：%s" % config_path)

    status_values = overview["status_values"]
    if not isinstance(status_values, list) or not all(
        isinstance(item, str) and item for item in status_values
    ):
        raise ConfigError("overview.status_values 必须是非空字符串数组：%s" % config_path)
    if len(status_values) < 4:
        raise ConfigError(
            "overview.status_values 至少需要 4 个取值（第 3、4 个用于判断计划与偏差是否成对）：%s"
            % config_path
        )

    for key in ("placeholder_dash", "placeholder_todo"):
        value = overview[key]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("overview.%s 必须是非空字符串：%s" % (key, config_path))
    if overview["placeholder_dash"] == overview["placeholder_todo"]:
        raise ConfigError("overview 的两种占位符不能相同：%s" % config_path)

    header_cfg = config["file_header"]
    for key in ("fields", "generator_values"):
        value = header_cfg[key]
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ConfigError("file_header.%s 必须是非空字符串数组：%s" % (key, config_path))
    if not isinstance(header_cfg["generator_field"], str) or not header_cfg["generator_field"].strip():
        raise ConfigError("file_header.generator_field 必须是非空字符串：%s" % config_path)
    if header_cfg["status_field"] not in header_cfg["fields"]:
        raise ConfigError(
            "file_header.status_field=%s 必须出现在 file_header.fields 中：%s"
            % (header_cfg["status_field"], config_path)
        )

    # 类型必须先校验：_validate_rel_component 用 str() 归一化，会把 123 变成 "123" 放过，
    # 随后 os.path.join(target_root, 123) 抛 TypeError（非退出码 3）。
    for key, value in (("docs_root", config["docs_root"]), ("overview.file", overview["file"])):
        if not isinstance(value, str):
            raise ConfigError("%s 必须是字符串：%s" % (key, config_path))
    for key in DOC_SUBDIR_KEYS:
        if not isinstance(config["dirs"][key], str):
            raise ConfigError("dirs.%s 必须是字符串：%s" % (key, config_path))
    if not isinstance(config["capability_name_pattern"], str):
        raise ConfigError("capability_name_pattern 必须是字符串：%s" % config_path)

    _validate_rel_component("docs_root", config["docs_root"], config_path)
    seen = set()
    for key in DOC_SUBDIR_KEYS:
        name = config["dirs"][key]
        _validate_rel_component("dirs." + key, name, config_path)
        if name in seen:
            raise ConfigError("配置 dirs 中目录名重复：%s：%s" % (name, config_path))
        seen.add(name)
    _validate_rel_component("overview.file", overview["file"], config_path)


def _validate_rel_component(name, value, config_path):
    """校验一个配置项是「不含穿越的相对路径」。

    docs_root 允许带层级（如 docs/dev），但不得是绝对路径、不得含 .. 段；
    dirs.* 与 overview.file 同理。这挡住了配置把文件写到项目外的路径。

    参数：
        name: 配置项名，用于报错
        value: 待校验值
        config_path: 配置文件路径

    异常：
        ConfigError: 值为绝对路径或含上跳段
    """
    text = str(value or "").strip()
    if not text:
        raise ConfigError("%s 不能为空：%s" % (name, config_path))
    if os.path.isabs(text):
        raise ConfigError("%s 必须是相对路径：%s" % (name, text))
    # Windows 上 "C:foo" 不是绝对路径但会跳盘，join 后逃出项目根
    if len(text) > 1 and text[1] == ":":
        raise ConfigError("%s 不得包含盘符：%s" % (name, text))
    normalized = os.path.normpath(text)
    if normalized == ".." or normalized.startswith(".." + os.sep) or normalized.startswith(".." + "/"):
        raise ConfigError("%s 不得包含上跳路径 ../：%s" % (name, text))


def docs_dir(root, config):
    """返回文档根绝对路径。"""
    return os.path.normpath(os.path.join(root, config["docs_root"]))


def rel(root, path):
    """返回相对项目根的 POSIX 路径，用于输出。"""
    return os.path.relpath(path, root).replace("\\", "/")


def die(message, code=2):
    """输出错误并退出。"""
    print(message, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# init 模式
# ---------------------------------------------------------------------------


def read_text(path):
    """读取 UTF-8 文本。

    参数：
        path: 文件路径

    返回：
        (正文, 错误说明)；成功时错误说明为 None
        区分「读失败」与「文件不存在」是必要的：把两者都返回 None 会让调用方
        用空串兜底，最终产出 0 字节文件而退出码仍是 0。
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read(), None
    except FileNotFoundError:
        return None, "文件不存在"
    except UnicodeDecodeError as error:
        return None, "编码不是 UTF-8（%s）" % error
    except OSError as error:
        return None, "读取失败（%s）" % error


def fill_placeholders(text, config, keep_generator=False):
    """把模板占位符替换为配置中的实际名称。

    参数：
        text: 模板正文
        config: 配置字典
        keep_generator: 为 True 时保留生成器占位符不替换。
            复制到项目模板目录时必须为 True——否则项目侧模板里就已经是合法生成器值，
            用户照 README 手工复制一份即可通过 audit，生成器校验形同虚设。

    返回：
        替换后的正文
    """
    mapping = {
        "{{dir_" + key + "}}": config["dirs"][key] for key in DOC_SUBDIR_KEYS
    }

    mapping["<设计目录>"] = config["dirs"]["design"]
    mapping["<计划目录>"] = config["dirs"]["plans"]
    mapping["<测试目录>"] = config["dirs"]["testing"]
    mapping["<决策目录>"] = config["dirs"]["decisions"]
    # 总览表头由配置决定，模板里不该出现具体列名——否则改配置后 init 产出的表头
    # 与配置不符，new 会因 find_table 匹配不上而直接失败。
    overview_header = config["overview"]["header"]
    separator = "|" + "|".join(["---"] * len(overview_header)) + "|"
    mapping["{{overview_header}}"] = (
        "| " + " | ".join(overview_header) + " |" + "\n" + separator
    )
    if not keep_generator:
        mapping["{{generator}}"] = config["file_header"]["generator_values"][0]
    for token, value in mapping.items():
        text = text.replace(token, value)
    return text


def _rollback(created, root):
    """删除本次已创建的文件，用于失败时回滚。

    参数：
        created: 相对项目根的文件路径列表
        root: 项目根
    """
    for item in created:
        try:
            os.remove(os.path.join(root, item))
        except OSError:
            pass


def run_init(root, config):
    """按配置复制文档目录结构、目录说明与文档模板。

    **只创建不覆盖**：目标已存在即中止，避免毁掉已写内容。

    参数：
        root: 项目根
        config: 配置字典

    返回：
        退出码
    """
    target_root = docs_dir(root, config)
    plan = []

    # 顶层总览 README
    plan.append(
        (
            os.path.join(TEMPLATES_DIR, SKELETON_DIR, "README.md"),
            os.path.join(target_root, config["overview"]["file"]),
        )
    )
    # 必需子目录的目录说明
    for key in DOC_SUBDIR_KEYS:
        plan.append(
            (
                os.path.join(TEMPLATES_DIR, key, "README.md"),
                os.path.join(target_root, config["dirs"][key], "README.md"),
            )
        )
    # 文档骨架不复制到项目侧：new / adr 直接从包内读取并实例化，
    # 复制一份会在项目侧留下没有消费者的副本，且副本与源模板的差异无法机械判定。

    missing_templates = [src for src, _ in plan if not os.path.isfile(src)]
    if missing_templates:
        die(
            "包内模板缺失，已中止（不写任何文件）：\n  "
            + "\n  ".join(missing_templates)
            + "\n该包可能未完整安装，请检查安装状态。"
        )

    conflicts = [dst for _, dst in plan if os.path.exists(dst)]
    if conflicts:
        die(
            "以下文件已存在，已中止（不覆盖已有内容）：\n  "
            + "\n  ".join(rel(root, item) for item in conflicts)
            + "\n若确认要重新初始化，请先手工移走这些文件。"
        )

    created = []
    for src, dst in plan:
        # 项目模板目录保留 {{generator}} 原样，使生成器标记只能由 new 写入
        raw, error = read_text(src)
        if raw is None:
            _rollback(created, root)
            die("包内模板读取失败：%s（%s）" % (rel(root, src), error))
        text = fill_placeholders(raw, config, keep_generator=True)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as write_error:
            # 中途失败时回滚已写部分，避免留下半套文档结构
            # （残缺结构在下次执行时会被冲突检查挡住，用户很难恢复）
            _rollback(created, root)
            die("初始化写入失败（%s），已回滚：%s" % (write_error, rel(root, dst)))
        created.append(rel(root, dst))

    print("已初始化文档结构：" + config["docs_root"])
    for item in created:
        print("  " + item)
    print("")
    print("下一步：用 new <能力名> 生成第一份能力文档骨架。")
    return 0


# ---------------------------------------------------------------------------
# 总览表解析
# ---------------------------------------------------------------------------


# 总览表各列与文档类别的对应：列名里出现左侧关键词即视为该类别。
# 顺序有意义——「实施偏差」同时含「计划」语义，必须先于「计划」判定。
OVERVIEW_COLUMN_KINDS = (
    ("偏差", "deviation"),
    ("设计", "design"),
    ("测试", "testing"),
    ("计划", "plan"),
)

# 类别到归档后文件名的映射。归档统一重命名，避免「按原名」与「改名」两种风格并存。
ARCHIVE_FILENAMES = {
    "design": "design.md",
    "plan": "plan.md",
    "deviation": "deviation.md",
    "testing": "testing.md",
}


def resolve_doc_columns(header, config):
    """把总览表表头解析为 {文档类别: 列序号}。

    列名靠关键词识别，因此列名被改成不含关键词的写法时，这里会解析不到对应列。
    这种情况必须显式报错：静默退化为「该列填占位符」会让 new 生成的文件没有登记路径，
    而 audit 只看到占位符、照样判通过——一个改配置就失效的链路最难排查。

    参数：
        header: 总览表表头列表
        config: 配置字典

    返回：
        (列映射, 缺失的类别列表)
    """
    cap_index = config["overview"]["capability_column"]
    status_index = config["overview"]["status_column"]
    columns = {}
    for index, column in enumerate(header):
        kind = column_kind(column, cap_index, status_index, index)
        if kind and kind not in columns:
            columns[kind] = index
    missing = [kind for kind in SCAFFOLD_DIRS if kind not in columns]
    return columns, missing


def require_doc_columns(header, config, action):
    """解析文档列，缺任何一类即中止。

    参数：
        header: 总览表表头列表
        config: 配置字典
        action: 动作名，用于错误信息

    返回：
        {文档类别: 列序号}
    """
    columns, missing = resolve_doc_columns(header, config)
    if missing:
        labels = {"design": "设计", "plan": "计划", "deviation": "偏差", "testing": "测试"}
        die(
            "总览表缺少可识别的文档列：" + "、".join(labels[kind] for kind in missing) + "\n"
            "当前表头：" + " | ".join(header) + "\n"
            "列名须包含上述关键词之一（如「方案设计」「实施计划」「实施偏差」「验证测试」），"
            "否则 " + action + " 无法确定该把文件登记到哪一列。"
        )
    return columns


def column_kind(column_name, cap_index, status_index, index):
    """判断总览表某一列承载哪类文档。

    参数：
        column_name: 该列的表头名
        cap_index: 能力列序号
        status_index: 状态列序号
        index: 当前列序号

    返回：
        "design" / "plan" / "deviation" / "testing"，非文档列返回 None
    """
    if index in (cap_index, status_index):
        return None
    for keyword, kind in OVERVIEW_COLUMN_KINDS:
        if keyword in column_name:
            return kind
    return None


def is_placeholder(cell, config):
    """判断单元格是否为占位符（不应被当作路径处理）。

    参数：
        cell: 单元格文本
        config: 配置字典

    返回：
        是占位符或空串时为 True
    """
    overview = config["overview"]
    return cell in ("", overview["placeholder_dash"], overview["placeholder_todo"])


def split_row(line):
    """把一行表格拆成去空白的单元格列表。

    参数：
        line: 一行文本

    返回：
        单元格列表；非表格行返回空列表
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    body = stripped.strip("|")
    return [cell.strip() for cell in body.split("|")]


def find_table(text, header):
    """定位总览表，返回 (表头行号, 数据行列表)。

    参数：
        text: 文档全文
        header: 期望的表头列名列表

    返回：
        (表头行号, [(行号, 单元格列表), ...])；未找到时表头行号为 None
    """
    expected = [cell.strip() for cell in header]
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if split_row(line) == expected:
            start = index
            break
    if start is None:
        return None, []
    rows = []
    for index in range(start + 2, len(lines)):
        line = lines[index]
        if not line.strip().startswith("|"):
            break
        rows.append((index, split_row(line)))
    return start, rows


def parse_overview(text, config):
    """解析总览表，返回 (行列表, 错误说明)。

    参数：
        text: 文档全文
        config: 配置字典

    返回：
        ([{能力, 状态, 单元格, 行号}], None) 或 (None, 错误说明)
    """
    overview = config["overview"]
    header = overview["header"]
    cap_index = overview["capability_column"]
    status_index = overview["status_column"]

    start, rows = find_table(text, header)
    if start is None:
        return None, "未找到总览表（表头应与配置声明一致：" + " | ".join(header) + "）"

    parsed = []
    for line_no, cells in rows:
        if len(cells) != len(header):
            return None, "总览表第 %d 行列数与表头不符（期望 %d 列，实际 %d 列）" % (
                line_no + 1,
                len(header),
                len(cells),
            )
        if cap_index >= len(cells) or status_index >= len(cells):
            return None, "配置中的列索引超出表头范围"
        parsed.append(
            {
                "能力": cells[cap_index],
                "状态": cells[status_index],
                "单元格": cells,
                "行号": line_no,
            }
        )
    return parsed, None


def insert_row(text, start, rows, new_row):
    """在总览表末尾插入一行，返回新正文。

    参数：
        text: 原正文
        start: 表头行号
        rows: 数据行列表
        new_row: 待插入的表格行

    返回：
        新正文
    """
    # keepends=True 保留每行原有的换行符（CRLF/LF 混排、末行无换行都能原样保留）。
    # 用 splitlines() + "\n".join 会把整份 CRLF 文件改写成 LF，产生全文件 diff，
    # 而本次操作语义上只是「追加一行」。
    lines = text.splitlines(keepends=True)
    anchor = rows[-1][0] if rows else start + 1
    target_line = lines[anchor]
    newline = "\r\n" if target_line.endswith("\r\n") else "\n"
    lines.insert(anchor + 1, new_row + newline)
    return "".join(lines)


def replace_row(text, line_no, cells):
    """改写总览表的指定行，保留该行原有的换行风格。

    参数：
        text: 原正文
        line_no: 目标行号（0 起）
        cells: 新的单元格列表

    返回：
        新正文
    """
    lines = text.splitlines(keepends=True)
    if line_no >= len(lines):
        raise ValueError("行号超出范围：%d" % line_no)
    target = lines[line_no]
    if target.endswith("\r\n"):
        newline = "\r\n"
    elif target.endswith("\n"):
        newline = "\n"
    else:
        newline = ""
    lines[line_no] = "| " + " | ".join(cells) + " |" + newline
    return "".join(lines)


# ---------------------------------------------------------------------------
# archive 模式
# ---------------------------------------------------------------------------


def _is_under(path, parent):
    """判断 path 是否位于 parent 目录之下（含相等）。

    参数：
        path: 待判断路径
        parent: 父目录路径

    返回：
        位于其下或相等时为 True
    """
    path = os.path.normpath(path)
    parent = os.path.normpath(parent)
    return path == parent or path.startswith(parent + os.sep)


def run_archive(root, config, capability):
    """把一个能力的过程文档整包移入归档目录，并回写总览表路径。

    为什么需要这个命令：归档要同时完成「移动文件」与「改总览表路径」两件事。
    只做前者，audit 会报四个「引用的文件不存在」；两件都做，才是一致的归档状态。
    手工做时第二步最容易漏，而漏了之后的报错看不出「这是归档做了一半」。
    把两步绑成一次操作，半归档状态就不可能产生。

    保护：
    - 能力必须在总览表登记；
    - 能力名不得含路径分隔符或 ..（防越出归档目录）；
    - 待移动的源文件必须存在；
    - 归档目标文件名不得已存在；
    - 任一移动失败，已移动的文件全部移回原位；
    - 总览表写入失败，已移动的文件同样全部移回。

    参数：
        root: 项目根
        config: 配置字典
        capability: 能力名

    返回：
        退出码
    """
    name = (capability or "").strip()
    if not name:
        die("能力名不能为空。")
    if name in (".", "..") or os.sep in name or (os.altsep and os.altsep in name):
        die("能力名不得包含路径分隔符或 ..：「" + name + "」")

    target_root = docs_dir(root, config)
    overview_path = os.path.join(target_root, config["overview"]["file"])
    overview_text, overview_error = read_text(overview_path)
    if overview_text is None:
        die(
            "无法读取能力总览表：%s（%s）\n请先执行 init 初始化文档结构。"
            % (rel(root, overview_path), overview_error)
        )

    rows, error = parse_overview(overview_text, config)
    if error:
        die("总览表不可解析，已中止（不移动任何文件）：" + error)

    matched = [row for row in rows if row["能力"] == name]
    if not matched:
        die("总览表中没有能力「" + name + "」。归档前必须先登记该能力。")
    if len(matched) > 1:
        die("能力「" + name + "」在总览表出现多行，无法确定归档哪一行。请先修正重复行。")
    row = matched[0]

    # 只允许把「完成」或「废弃」的能力归档。规则里归档的对象是已完成能力；
    # 提前归档会让活跃目录看起来比实际干净，而总览表状态仍是草稿——
    # 此后没人会去翻归档目录找它。
    status_values = config["overview"]["status_values"]
    archivable = {status_values[3], status_values[-1]}
    if row["状态"] not in archivable:
        die(
            "能力「" + name + "」当前状态为「" + row["状态"] + "」，不能归档。\n"
            "归档对象是已完成或已废弃的能力；请先用 status 命令推进状态：\n"
            "  python devflow_guard.py status " + name + " " + status_values[3]
        )

    header = config["overview"]["header"]
    cap_index = config["overview"]["capability_column"]
    status_index = config["overview"]["status_column"]
    archive_root = os.path.join(target_root, config["dirs"]["archive"])
    dest_dir = os.path.join(archive_root, name)

    # 先算出完整的移动计划，任一不满足即整体中止——避免移了一半才发现冲突。
    doc_columns = require_doc_columns(header, config, "archive")
    moves = []
    for kind, index in sorted(doc_columns.items(), key=lambda item: item[1]):
        column = header[index]
        cell = row["单元格"][index]
        if is_placeholder(cell, config):
            continue
        source = os.path.normpath(os.path.join(target_root, cell))
        if _is_under(source, archive_root):
            continue  # 已归档，保持原样
        if not os.path.isfile(source):
            die(
                "总览表第 %d 行列「%s」指向的文件不存在：%s\n"
                "归档前须先修正总览表，否则会把错误路径带进归档目录。"
                % (row["行号"] + 1, column, cell)
            )
        destination = os.path.join(dest_dir, ARCHIVE_FILENAMES[kind])
        if os.path.exists(destination):
            die("归档目标已存在，已中止（不覆盖）：" + rel(root, destination))
        moves.append((source, destination, index))

    if not moves:
        print("能力「" + name + "」的四类文档均已在归档目录，未做任何改动。")
        return 0

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as make_error:
        die("无法创建归档目录（%s）：%s" % (make_error, rel(root, dest_dir)))

    done = []
    for source, destination, _ in moves:
        try:
            shutil.move(source, destination)
        except OSError as move_error:
            # 逐份回滚：归档是「要么全部就位、要么原地不动」，
            # 半套归档会让总览表与磁盘两侧都处于难以判断的状态。
            for moved_source, moved_dest in reversed(done):
                try:
                    shutil.move(moved_dest, moved_source)
                except OSError:
                    pass
            die(
                "移动失败（%s）：%s\n已移回本次移动的文件，未产生归档。"
                % (move_error, rel(root, source))
            )
        done.append((source, destination))

    cells = list(row["单元格"])
    for _, destination, index in moves:
        cells[index] = os.path.relpath(destination, target_root).replace(os.sep, "/")
    updated = replace_row(overview_text, row["行号"], cells)
    try:
        with open(overview_path, "w", encoding="utf-8") as handle:
            handle.write(updated)
    except OSError as write_error:
        for moved_source, moved_dest in reversed(done):
            try:
                shutil.move(moved_dest, moved_source)
            except OSError:
                pass
        die(
            "写入总览表失败（%s），已把文件移回原位：%s"
            % (write_error, rel(root, overview_path))
        )

    # 归档改变了设计文档的路径，探索记录的采纳行必须跟着改，否则指针立刻悬空。
    # 这里改的是路径、不是采纳事实，因此与「采纳后不得回改」不冲突。
    path_root = os.path.join(target_root, config["dirs"]["explore"])
    changed_records = []
    for index, column in enumerate(header):
        kind = column_kind(column, cap_index, status_index, index)
        if kind != "design":
            continue
        old_rel = row["单元格"][index].replace(os.sep, "/")
        new_rel = os.path.relpath(
            os.path.join(archive_root, name, ARCHIVE_FILENAMES["design"]), target_root
        ).replace(os.sep, "/")
        if old_rel and not is_placeholder(old_rel, config):
            changed_records = rewrite_adoption_targets(path_root, old_rel, new_rel, config)

    print("已归档能力：" + name)
    for source, destination in done:
        print("  " + rel(root, source) + "  ->  " + rel(root, destination))
    print("总览表路径已更新为归档位置。")
    for record in changed_records:
        print("探索记录采纳行已同步为归档路径：" + record)
    print("")
    print("注意：状态未改动（归档是存放位置，不是生命周期阶段）；决策记录不归档。")
    return 0


# ---------------------------------------------------------------------------
# new 模式
# ---------------------------------------------------------------------------


SCAFFOLD_SPECS = (
    ("design.md", "design", "{name}.md"),
    ("plan.md", "plans", "{name}-plan.md"),
    ("deviation.md", "plans", "{name}-deviation.md"),
    ("testing.md", "testing", "{name}-testing.md"),
)

# 文档类别 → 配置 dirs 键 / 落盘文件名模板。new 填总览表与 archive 定位文件共用。
SCAFFOLD_DIRS = {
    "design": "design",
    "plan": "plans",
    "deviation": "plans",
    "testing": "testing",
}
SCAFFOLD_FILENAMES = {
    "design": "{dir_name}/{name}.md",
    "plan": "{dir_name}/{name}-plan.md",
    "deviation": "{dir_name}/{name}-deviation.md",
    "testing": "{dir_name}/{name}-testing.md",
}


def inject_explore_note(text, explore_rel):
    """在设计文档「背景」一节写入需求探索来源。

    与重开注入的区别：这里指向的是「这个能力为什么该做」的确认记录，
    而重开指向的是「旧能力为什么不够」。两者可以同时存在，故各插一行。

    参数：
        text: 设计文档全文
        explore_rel: 需求探索记录相对文档根的路径

    返回：
        新正文；未定位到「## 背景」时返回 None
    """
    marker = "## 背景"
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        newline = ""
        if line.endswith(chr(13) + chr(10)):
            newline = chr(13) + chr(10)
        elif line.endswith(chr(10)):
            newline = chr(10)
        note = (
            "> 需求已确认，探索记录见 " + explore_rel
            + "（含已排除方向与重新可行的前提）。" + newline
        )
        lines.insert(index + 1, newline)
        lines.insert(index + 2, note)
        return "".join(lines)
    return None


def inject_rework_note(text, archive_rel):
    """在设计文档「背景」一节写入重开来源，返回新正文。

    只加一行引用，不复制旧文档内容：旧文档留在归档目录里，作为「当时怎么想」的唯一记录；
    新文档只声明「我从它重开」，读者据此可回溯。二者职责不重叠，因此不合并、不搬运。

    参数：
        text: 设计文档全文
        archive_rel: 被重开的归档目录相对路径（如 archive/alpha）

    返回：
        (新正文, 是否成功定位「背景」一节)
    """
    marker = '## 背景'
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        newline = ''
        if line.endswith(chr(13) + chr(10)):
            newline = chr(13) + chr(10)
        elif line.endswith(chr(10)):
            newline = chr(10)
        note = (
            '> 本能力重开自 ' + archive_rel + ' 的设计文档。旧文档记录的是当时的推理与盲区，'
            '已冻结、不再修改；本次为何重开见下方「背景」。' + newline
        )
        lines.insert(index + 1, newline)
        lines.insert(index + 2, note)
        return ''.join(lines), True
    return text, False


def run_explore(root, config, slug, title):
    """创建一份需求探索记录。

    探索阶段与能力文档阶段的区别在于**允许反复改写**：需求在确认之前本就该变，
    而能力文档一旦建立就是承诺。把两者分开，才能让「还没想清楚」不至于污染
    「已经决定要做」的记录。

    参数：
        root: 项目根
        config: 配置字典
        slug: 探索记录名（英文 kebab-case）
        title: 主题；为空时取 slug

    返回：
        退出码
    """
    if not ADR_SLUG_PATTERN.fullmatch(slug or ""):
        die(
            "探索记录名不合法：" + repr(slug) + chr(10) +
            "必须是英文 kebab-case（如 cache-policy），因为它会直接成为文件名。"
        )
    folder = explore_dir(config)

    target_root = docs_dir(root, config)
    target_dir = os.path.join(target_root, folder)
    if not os.path.isdir(target_dir):
        # 已初始化的项目无法靠 init 补目录：init 在任一目标已存在时整体中止。
        # 而「给老项目后加探索」是常见诉求，因此这里自行补齐目录与说明文件。
        # 只创建缺的，不碰任何已有文件。
        readme_src = os.path.join(TEMPLATES_DIR, "explore", "README.md")
        try:
            os.makedirs(target_dir, exist_ok=True)
            if os.path.isfile(readme_src):
                raw_readme, read_error = read_text(readme_src)
                if raw_readme is not None:
                    with open(
                        os.path.join(target_dir, "README.md"), "w", encoding="utf-8"
                    ) as handle:
                        handle.write(fill_placeholders(raw_readme, config))
                else:
                    print("提示：目录说明读取失败（" + str(read_error) + "），已跳过写入 README。")
            else:
                print("提示：包内缺少 explore 目录说明模板，已跳过写入 README。")
        except OSError as make_error:
            die("无法创建需求探索目录（%s）：%s" % (make_error, rel(root, target_dir)))

    target = os.path.join(target_dir, slug + ".md")
    if os.path.exists(target):
        die("目标文件已存在，已中止（不覆盖）：" + rel(root, target))

    template = os.path.join(TEMPLATES_DIR, SKELETON_DIR, "explore.md")
    if not os.path.isfile(template):
        die("包内模板缺失：" + template + chr(10) + "该包可能未完整安装。")

    raw, error = read_text(template)
    if raw is None:
        die("包内模板读取失败：%s（%s）" % (rel(root, template), error))

    text = fill_placeholders(raw, config)
    text = text.replace("<主题>", (title or "").strip() or slug)
    text = text.replace("YYYY-MM-DD", date.today().isoformat())
    # 初始状态取配置状态集合的第一个取值，与 check_explore_confirmed 的判据一致：
    # 两处若各写各的字面，改配置后会出现「刚创建就满足确认条件」或「永远无法确认」。
    text = text.replace("{{initial_status}}", config["overview"]["status_values"][0])

    leftover = [
        token for token in ("<主题>", "{{generator}}", "{{initial_status}}") if token in text
    ]
    if leftover:
        die(
            "模板中仍有未替换的占位符：" + "、".join(leftover) + chr(10) +
            "说明包内模板与本命令的替换规则不一致，已中止（不写文件）。"
        )

    try:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as write_error:
        die("写入失败（%s）：%s" % (write_error, rel(root, target)))

    print("已创建需求探索记录：")
    print("  " + rel(root, target))
    print("")
    print("下一步：填写「要解决的问题」「未定项」与「结论」，确认后把状态改为已确认，")
    print("       再用 new <能力名> --from-explore " + slug + " 建立能力文档。")
    return 0


def explore_dir(config):
    """返回需求探索目录名（相对文档根）。

    参数：
        config: 配置字典

    返回：
        目录名；配置缺失时由 load_config 提前以退出码 3 拦下，此处不再兜底
    """
    return str(config["dirs"]["explore"]).strip()


def check_explore_confirmed(root, config, slug):
    """校验需求探索记录存在且「结论」已填写，返回其相对文档根的路径。

    为什么要求「结论非空」：探索阶段的价值就在于把未定项收敛成一个决定。
    结论为空说明还在讨论中，此时建立能力文档等于把「想清楚」这一必经步骤降级为可选项，
    它留下的正是那种「有文档但什么都没说」的骨架。

    参数：
        root: 项目根
        config: 配置字典
        slug: 探索记录名（不含 .md）

    返回：
        探索文档相对文档根的路径

    异常：
        SystemExit: 校验不通过时由 die 抛出
    """
    folder = explore_dir(config)
    if not folder:
        die(
            "本项目未启用需求探索（配置 dirs 未声明 explore）。\n"
            "启用方式：在配置 dirs 中加 explore 键并指向 explore 目录，再重新执行 init。"
        )
    target_root = docs_dir(root, config)
    path = os.path.join(target_root, folder, slug + ".md")
    if not os.path.isfile(path):
        die(
            "找不到需求探索记录：" + folder + "/" + slug + ".md\n"
            "先用 explore 子命令创建并完成它，再建立能力文档。"
        )
    text, error = read_text(path)
    if text is None:
        die("读取需求探索记录失败：" + rel(root, path) + "（" + str(error) + "）")

    values = parse_header_fields(extract_header_table(text))
    status_field = config["file_header"]["status_field"]
    # 探索记录用两态：初始「探索中」与终态「已确认」。
    # 初始值取配置里能力状态的第一个取值（即「草稿」这一档语义），
    # 只要与它不同就视为已推进——探索阶段不需要更细的档位。
    initial = config["overview"]["status_values"][0]
    known = set(config["overview"]["status_values"])
    status = values.get(status_field, "").strip()
    if not status or status == initial:
        hint = ("、".join(v for v in config["overview"]["status_values"] if v != initial))
        die(
            "需求探索尚未确认：" + folder + "/" + slug + ".md 状态为「" + (status or "空") + "」" + "\n" +
            "请先补齐「结论」一节，并把状态改为 " + hint + " 中的任一档，再建立能力文档。"
        )

    # 「已确认的决定」必须至少有一条实质内容：结论只说明最终做什么，
    # 而这一节记录「凭什么这么定」。缺它的话，探索记录退化成一张结论贴纸——
    # 后来者能看到决定，看不到判据，等于把同一个问题原样推给他重推一遍。
    decisions = extract_section(text, "已确认的决定")
    if not has_table_rows(decisions):
        die(
            "需求探索记录缺少已确认的决定：" + folder + "/" + slug + ".md" + chr(10) +
            "「## 已确认的决定」一节须至少写一条（决定 / 为什么这么定 / 成立前提）。" + chr(10) +
            "这一节应由逐轮向用户提问得出，不能自问自答地填。"
        )

    conclusion = extract_section(text, "结论")
    if not has_conclusion(conclusion):
        die(
            "需求探索记录缺少结论：" + folder + "/" + slug + ".md\n"
            "「## 结论」一节必须写明做什么、不做什么；仅保留填写提示视为未确认。"
        )
    return folder + "/" + slug + ".md"


def extract_section(text, title):
    """取出某一节的正文（第二个参数为标题去掉 ## 后的部分）。

    参数：
        text: 文档全文
        title: 节标题（不含 ##）

    返回：
        该节正文；未找到返回空串
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## " + title:
            start = index + 1
            break
    if start is None:
        return ""
    collected = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        collected.append(line)
    return chr(10).join(collected)


def has_table_rows(section_text):
    """判断某一节的表格里是否至少有一行实际内容。

    排除表头行、对齐行与全空单元格的行——模板留的空行不算填写。

    参数：
        section_text: 该节正文

    返回：
        至少有一行实质内容为 True
    """
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        # 表头与对齐行
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        if cells[0] in ("决定", "未定项", "方向", "约束"):
            continue
        if any(cells):
            return True
    return False


def has_conclusion(section_text):
    """判断「结论」一节是否写了实际内容（而非只剩填写提示）。

    三条排除规则，任一条命中即不算内容：
    1. 空行；
    2. 引用块（模板里的提示语一律写成 > 引用），用于说明怎么写而不是写了什么；
    3. 只有标签没有内容——形如「- 做：」的行，冒号后为空，属于未填写的骨架。

    这样判定的目的不是判断结论好坏，而是区分「填了」与「没填」。
    好坏交给评审——机械检查不该假装能判断论证是否站得住。

    参数：
        section_text: 该节正文

    返回：
        有实际内容为 True
    """
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        body = stripped.lstrip("-*").strip()
        if not body:
            continue
        # 只有标签、冒号后没有内容
        if body.endswith("：") or body.endswith(":"):
            continue
        return True
    return False


def explore_adoption_section(text):
    """取出需求探索记录的「## 采纳」一节正文。

    参数：
        text: 探索记录全文

    返回：
        该节正文；未找到返回空串
    """
    return extract_section(text, "采纳")


def parse_adoption_targets(section_text):
    """解析「采纳」节里记录的设计文档路径。

    行形如「- 采纳于：design/cache-ttl.md（2026-10-29）」，取冒号后的路径部分，
    去掉日期括注与反引号，统一成正斜杠——比对时不因书写差异误报。

    参数：
        section_text: 「采纳」节正文

    返回：
        相对文档根的设计文档路径列表
    """
    targets = []
    for line in section_text.splitlines():
        stripped = line.strip().lstrip("-*").strip()
        if not stripped.startswith("采纳于"):
            continue
        body = stripped[len("采纳于"):].lstrip("：:").strip()
        for sep in ("（", "("):
            body = body.split(sep)[0]
        body = body.strip().strip(chr(96)).strip().replace(chr(92), "/")
        if body:
            targets.append(body)
    return targets


def rewrite_adoption_targets(path_root, old_rel, new_rel, config):
    """把探索记录里指向 old_rel 的采纳行改写为 new_rel，返回已改写的记录路径列表。

    为什么归档要动采纳行：采纳行记的是设计文档的路径，归档后该路径变了。
    不改的话，「采纳行 → 设计文档」这条指针立刻悬空——而它记录的采纳事实本身没变，
    变的只是文件位置。因此这是**位置迁移**，不是内容改写，与「采纳后不得回改」不冲突。

    只改路径部分，日期与其余文字原样保留。

    参数：
        path_root: 探索目录绝对路径
        old_rel: 原设计文档相对路径（正斜杠）
        new_rel: 归档后相对路径（正斜杠）
        config: 配置字典

    返回：
        已改写的探索记录相对路径列表
    """
    changed = []
    if not os.path.isdir(path_root):
        return changed
    for name in sorted(os.listdir(path_root)):
        if name == "README.md" or not name.endswith(".md"):
            continue
        path = os.path.join(path_root, name)
        if not os.path.isfile(path):
            continue
        text, _ = read_text(path)
        if text is None:
            continue
        targets = parse_adoption_targets(explore_adoption_section(text))
        if old_rel not in targets:
            continue
        lines = text.splitlines(keepends=True)
        touched = False
        for index, line in enumerate(lines):
            if old_rel in line and "采纳于" in line:
                lines[index] = line.replace(old_rel, new_rel)
                touched = True
        if not touched:
            continue
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("".join(lines))
        except OSError:
            continue
        changed.append(explore_dir(config) + "/" + name)
    return changed


def append_adoption_note(text, design_rel, today):
    """在探索记录里追加一条采纳记录，返回新正文。

    由 new 写入而非人工填写：「是否被采纳、被谁采纳」必须是工具当场留下的痕迹。
    人工填写等于让人事后自证，而事后合理化正是这条记录要防的东西。

    参数：
        text: 探索记录全文
        design_rel: 采纳它的设计文档相对路径
        today: 日期字符串

    返回：
        新正文
    """
    line = "- 采纳于：" + design_rel + "（" + today + "）"
    lines = text.splitlines(keepends=True)
    start = None
    for index, item in enumerate(lines):
        if item.strip() == "## 采纳":
            start = index + 1
            break

    crlf = chr(13) + chr(10)
    newline = crlf if crlf in text else chr(10)

    if start is None:
        body = text
        if body and not body.endswith(newline):
            body += newline
        return body + newline + "## 采纳" + newline + newline + line + newline

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].strip().startswith("## "):
            end = index
            break
    last = start - 1
    for index in range(start, end):
        if lines[index].strip():
            last = index
    lines.insert(last + 1, line + newline)
    return "".join(lines)


def run_new(root, config, name, rework_from='', from_explore=''):
    """生成能力文档骨架并登记总览表。

    三道运行时保护，任一不满足即中止且不写任何文件：
    能力名格式、目标文件已存在、总览表可解析且插入点可定位。

    参数：
        root: 项目根
        config: 配置字典
        name: 能力名
        rework_from: 被重开的已归档能力名；为空表示全新能力
        from_explore: 需求探索记录名；项目启用探索时必填，且该记录须已确认

    返回：
        退出码
    """
    # re 的 $ 允许匹配结尾换行，fullmatch 仍可能放过 "abc\n"，
    # 而换行写入表格会伪造出一整行。因此先显式剔除控制字符与应用空白。
    # 不只查 \r\n\t：全角空格 U+3000、垂直制表、换页、行分隔符、零宽字符
    # 都会产生不可见但破坏文件名与表格结构的名字，统一按 Unicode 类别拦截。
    if name != (name or "").strip() or any(
        ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf", "Zs", "Zl", "Zp")
        for ch in (name or "")
    ):
        die(
            "能力名不得包含空白、控制字符或不可见字符：「" + repr(name) + "」"
        )
    pattern = re.compile(config["capability_name_pattern"])
    if not pattern.fullmatch(name or ""):
        die(
            "能力名不合法：「" + str(name) + "」\n"
            "必须匹配配置声明的模式 " + config["capability_name_pattern"]
            + "（典型写法：config-overrides）。\n"
            "理由：能力名同时用作文件名、总览表「能力」列与文件头「关联能力」字段的值，"
            "必须是无需转义的标识。"
        )

    # 需求确认是必经步骤：不带 --from-explore 直接拒绝。
    # 这是把「先想清楚再做」从纪律变成结构的关键——否则 new 只校验名字格式，
    # 需求完全没成形也能建出四份空骨架，而 audit 只查契约、查不出「全是模板话术」。
    if not (from_explore or '').strip():
        die(
            "建立能力文档前必须先确认需求。\n"
            "1) 创建探索记录：python devflow_guard.py explore <主题名>\n"
            "2) 填写「要解决的问题」「未定项」「结论」，状态推进一档\n"
            "3) 再建立能力文档：python devflow_guard.py new " + name + " --from-explore <主题名>"
        )
    explore_slug = (from_explore or '').strip()
    explore_rel = check_explore_confirmed(root, config, explore_slug)

    target_root = docs_dir(root, config)
    overview_path = os.path.join(target_root, config["overview"]["file"])
    overview_text, overview_error = read_text(overview_path)
    if overview_text is None:
        die(
            "无法读取能力总览表：%s（%s）\n请先执行 init 初始化文档结构。"
            % (rel(root, overview_path), overview_error)
        )

    rows, error = parse_overview(overview_text, config)
    if error:
        die("总览表不可解析，已中止（不写任何文件）：" + error)

    for row in rows:
        if row["能力"] == name:
            die("能力已存在于总览表：" + name + "。若需重建请手工处理，本脚本不提供覆盖。")

    # 重开来源：必须是已归档的能力。校验放在写文件之前，避免生成了一半才发现来源写错。
    rework_dir = ""
    rework_capability = (rework_from or "").strip()
    if rework_capability:
        archive_root = os.path.join(target_root, config["dirs"]["archive"])
        rework_dir = os.path.join(archive_root, rework_capability)
        if not os.path.isdir(rework_dir):
            die(
                "找不到被重开的归档能力：" + config["dirs"]["archive"] + "/" + rework_capability + "\n"
                + "重开只能指向已归档的能力；若原能力仍在活跃目录，直接在它上面继续即可，不必新建。"
            )
        if rework_capability == name:
            die("新能力名不能与被重开的能力同名：" + name)
        # 归档里的设计文档必须存在，否则引用落空
        if not os.path.isfile(os.path.join(rework_dir, "design.md")):
            die(
                "被重开的归档能力缺少设计文档：" + config["dirs"]["archive"] + "/"
                + rework_capability + "/design.md"
            )

    targets = []
    for template_name, dir_key, pattern_name in SCAFFOLD_SPECS:
        template = os.path.join(TEMPLATES_DIR, SKELETON_DIR, template_name)
        if not os.path.isfile(template):
            die("包内模板缺失：" + template)
        target = os.path.join(target_root, config["dirs"][dir_key], pattern_name.format(name=name))
        targets.append((template_name, template, target))

    conflicts = [dst for _, _, dst in targets if os.path.exists(dst)]
    if conflicts:
        die(
            "以下文件已存在，已中止（不覆盖）：\n  "
            + "\n  ".join(rel(root, item) for item in conflicts)
        )

    today = date.today().isoformat()
    generator = config["file_header"]["generator_values"][0]

    created = []
    for template_name, template, target in targets:
        raw, error = read_text(template)
        if raw is None:
            die("包内模板读取失败：%s（%s）" % (template, error))
        text = fill_placeholders(raw, config)
        text = text.replace("<能力名>", name)
        text = text.replace("YYYY-MM-DD", today)
        text = text.replace("{{generator}}", generator)
        if explore_rel and template_name == "design.md":
            text = inject_explore_note(text, explore_rel)
            if text is None:
                die(
                    "设计文档骨架缺少「## 背景」一节，无法写入需求探索来源，已中止（不写任何文件）。"
                )
        if rework_dir and template_name == "design.md":
            archive_rel = config["dirs"]["archive"] + "/" + rework_capability
            text, located = inject_rework_note(text, archive_rel)
            if not located:
                die(
                    "设计文档骨架缺少「## 背景」一节，无法写入重开来源，已中止（不写任何文件）。"
                )
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
        created.append(target)

    header_names = config["overview"]["header"]
    dash = config["overview"]["placeholder_dash"]
    cap_index = config["overview"]["capability_column"]
    status_index = config["overview"]["status_column"]

    # 列与文档类别的对应统一走 require_doc_columns，避免与 archive 各写一套关键词匹配。
    # 列名改到无法识别时直接中止：否则生成的骨架没有登记路径，而 audit 只看到占位符、照样通过。
    doc_columns = require_doc_columns(header_names, config, "new")
    cells = []
    for index in range(len(header_names)):
        if index == cap_index:
            cells.append(name)
        elif index == status_index:
            cells.append(config["overview"]["status_values"][0])
        else:
            kind = next((k for k, i in doc_columns.items() if i == index), None)
            if kind is None:
                cells.append(dash)
            else:
                cells.append(
                    SCAFFOLD_FILENAMES[kind].format(
                        dir_name=config["dirs"][SCAFFOLD_DIRS[kind]], name=name
                    )
                )
    new_row = "| " + " | ".join(cells) + " |"

    start, data_rows = find_table(overview_text, header_names)
    updated = insert_row(overview_text, start, data_rows, new_row)
    try:
        with open(overview_path, "w", encoding="utf-8") as handle:
            handle.write(updated)
    except OSError as error:
        # 写总览表失败时回滚已落盘的骨架，避免「有文档但没登记」的半成品
        for item in created:
            try:
                os.remove(item)
            except OSError:
                pass
        die("写入能力总览表失败（%s），已回滚生成的文件：%s" % (error, rel(root, overview_path)))

    # 采纳写回：登记成功后才回写，顺序不能颠倒。
    # 若先写采纳再登记，登记失败回滚骨架时，探索记录里会留下一条指向不存在文档的采纳行。
    # 回写失败不中止：骨架与登记都已完成，此时中止会留下半套状态，
    # 而缺失的采纳行由 audit 的「被引用却未采纳」检查兜住，可事后补。
    if explore_rel:
        explore_path = os.path.join(target_root, explore_rel)
        explore_text, explore_error = read_text(explore_path)
        if explore_text is None:
            print(
                "警告：需求探索记录读取失败（" + str(explore_error) + "），未能写回采纳行："
                + explore_rel
            )
        else:
            design_rel = SCAFFOLD_FILENAMES["design"].format(
                dir_name=config["dirs"]["design"], name=name
            )
            adopted = append_adoption_note(explore_text, design_rel, today)
            try:
                with open(explore_path, "w", encoding="utf-8") as handle:
                    handle.write(adopted)
            except OSError as adopt_error:
                print(
                    "警告：采纳写回失败（" + str(adopt_error) + "）：" + explore_rel
                )

    print("已生成：")
    for item in created:
        print("  " + rel(root, item))
    print("已在能力总览表登记：" + name)
    if explore_rel:
        print("已在需求探索记录写回采纳：" + explore_rel)
    if rework_capability:
        print("")
        print(
            "重开自：" + config["dirs"]["archive"] + "/" + rework_capability
            + "（旧文档已冻结，本次改为在其上叠加新能力；旧文档不再修改）"
        )
        print("若推翻了原决策，请用 adr 新建一份并在「取代」字段写旧编号。")
    print("")
    print("下一步：填写设计文档的方案与取舍，方案定稿后补计划，开发完成后补验收记录。")
    return 0


# ---------------------------------------------------------------------------
# adr 模式
# ---------------------------------------------------------------------------

# 决策记录文件名模式。与 check_adr_numbering 的校验口径必须一致，
# 否则本命令产出的文件会在体检时被判文件名不合规。
ADR_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def next_adr_number(decisions_dir):
    """推算下一个可用的决策编号。

    audit 要求编号从 0001 起连续、无重复，因此取现有最大编号加一；
    目录为空时从 1 开始。已归档的 ADR 不会离开本目录，故无需考虑归档。

    参数：
        decisions_dir: 决策目录绝对路径

    返回：
        下一个编号（整数）；目录不存在时返回 1
    """
    if not os.path.isdir(decisions_dir):
        return 1
    numbers = []
    for name in os.listdir(decisions_dir):
        match = re.match(r"^(\d{4})-", name)
        if match and name.endswith(".md"):
            numbers.append(int(match.group(1)))
    return max(numbers) + 1 if numbers else 1


def run_adr(root, config, slug, title, capability):
    """创建一份决策记录（ADR）骨架。

    为什么需要这个入口：ADR 没有对应的能力命名规则，无法由 new 产出；
    而 audit 对「生成器」字段是 error 级校验，手工建必须自填合法值，
    否则体检不过。把编号推算与字段填充收进脚本，才不必让人记住这些约定。

    参数：
        root: 项目根
        config: 配置字典
        slug: 决策文件名描述部分（英文 kebab-case）
        title: 决策标题；为空时取 slug
        capability: 关联能力；为空时写「全局」

    返回：
        退出码
    """
    if not ADR_SLUG_PATTERN.fullmatch(slug or ""):
        die(
            "决策 slug 不合法：「" + str(slug) + "」\n"
            "必须是英文 kebab-case（如 cache-policy），因为它会直接成为文件名的一部分。"
        )
    if any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in (slug or "")):
        die("决策 slug 不得包含空白或不可见字符：「" + repr(slug) + "」")

    heading = (title or "").strip() or slug
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in heading):
        die("决策标题不得包含控制字符或换行：「" + repr(title) + "」")

    capability_text = (capability or "").strip() or "全局"
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in capability_text):
        die("关联能力不得包含控制字符或换行：「" + repr(capability) + "」")

    target_root = docs_dir(root, config)
    decisions_dir = os.path.join(target_root, config["dirs"]["decisions"])
    if not os.path.isdir(decisions_dir):
        die(
            "决策目录不存在：" + rel(root, decisions_dir) + "\n请先执行 init 初始化文档结构。"
        )

    number = next_adr_number(decisions_dir)
    target = os.path.join(decisions_dir, "%04d-%s.md" % (number, slug))
    if os.path.exists(target):
        die("目标文件已存在，已中止（不覆盖）：" + rel(root, target))

    template = os.path.join(TEMPLATES_DIR, SKELETON_DIR, "adr.md")
    if not os.path.isfile(template):
        die("包内模板缺失：" + template + "\n该包可能未完整安装，请检查安装状态。")

    raw, error = read_text(template)
    if raw is None:
        die("包内模板读取失败：%s（%s）" % (rel(root, template), error))

    text = fill_placeholders(raw, config)
    # 只替换一级标题里的编号：「取代」小节的 ADR-NNNN 是待人工填写的占位符，
    # 若一并替换，新文档会写成「本决策取代 ADR-00NN」——指向自己。
    heading_token = "ADR-NNNN"
    if text.startswith("# "):
        first_newline = text.find("\n")
        head_line = text if first_newline < 0 else text[:first_newline]
        rest = "" if first_newline < 0 else text[first_newline:]
        text = head_line.replace(heading_token, "ADR-%04d" % number) + rest
    else:
        text = text.replace(heading_token, "ADR-%04d" % number, 1)
    text = text.replace("<决策标题>", heading)
    # 关联能力单元格在模板里写的是两种可选值，需整格替换，否则会残留「或」
    text = text.replace("全局 或 <能力名>", capability_text)
    text = text.replace("YYYY-MM-DD", date.today().isoformat())

    leftover = [token for token in ("<决策标题>", "<能力名>", "{{generator}}") if token in text]
    if leftover:
        die(
            "模板中仍有未替换的占位符：" + "、".join(leftover)
            + "\n说明包内模板与本命令的替换规则不一致，已中止（不写文件）。"
        )

    try:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as write_error:
        die("写入失败（%s）：%s" % (write_error, rel(root, target)))

    print("已生成：")
    print("  " + rel(root, target))
    print("")
    print("下一步：补齐背景、考虑过的方案与后果；定稿后状态改为已定，之后不再改写。")
    return 0


# ---------------------------------------------------------------------------
# status 模式
# ---------------------------------------------------------------------------


def replace_header_field(text, field, value):
    """改写文件头字段表里某个字段的取值，其余内容原样保留。

    只在首个「| 字段 | 值 |」表格内替换，正文里出现的同名行不受影响。

    参数：
        text: 文档全文
        field: 字段名
        value: 新取值

    返回：
        (新正文, 是否找到该字段)
    """
    lines = text.splitlines(keepends=True)
    in_header = False
    for index, line in enumerate(lines):
        cells = split_row(line)
        if not in_header:
            if len(cells) == 2 and cells[0] == "字段" and cells[1] == "值":
                in_header = True
            continue
        if not line.strip().startswith("|"):
            break
        if len(cells) == 2 and cells[0] == field:
            newline = ""
            if line.endswith("\r\n"):
                newline = "\r\n"
            elif line.endswith("\n"):
                newline = "\n"
            lines[index] = "| " + field + " | " + value + " |" + newline
            return "".join(lines), True
    return text, False


def run_status(root, config, capability, new_status):
    """把一个能力的状态同步到总览表与该能力的全部文档文件头。

    为什么需要这个命令：状态同时写在总览表与该能力的四份文档头里，
    共五处。手工改最容易出现「表已改、文档没改」或反之，
    而 audit 并不比对这两处（它们语义不同：一个是能力状态，一个是文档生命周期），
    因此不一致不会被发现。一次命令改全，才不必依赖记忆。

    参数：
        root: 项目根
        config: 配置字典
        capability: 能力名
        new_status: 目标状态

    返回：
        退出码
    """
    name = (capability or "").strip()
    if not name:
        die("能力名不能为空。")
    allowed = config["overview"]["status_values"]
    if new_status not in allowed:
        die(
            "状态取值不合法：「" + str(new_status) + "」\n"
            "合法取值：" + "、".join(allowed)
        )

    target_root = docs_dir(root, config)
    overview_path = os.path.join(target_root, config["overview"]["file"])
    overview_text, overview_error = read_text(overview_path)
    if overview_text is None:
        die(
            "无法读取能力总览表：%s（%s）"
            % (rel(root, overview_path), overview_error)
        )

    rows, error = parse_overview(overview_text, config)
    if error:
        die("总览表不可解析，已中止（不写任何文件）：" + error)

    matched = [row for row in rows if row["能力"] == name]
    if not matched:
        die("总览表中没有能力「" + name + "」。")
    if len(matched) > 1:
        die("能力「" + name + "」在总览表出现多行，无法确定改哪一行。请先修正重复行。")
    row = matched[0]

    header = config["overview"]["header"]
    doc_columns, _ = resolve_doc_columns(header, config)
    status_field = config["file_header"]["status_field"]

    # 已归档的能力不允许把状态改回非终态。归档是「完成后冻结」的位置，
    # 若允许退回草稿，会造出「状态说还在起草、位置说已完成、体检说没问题」的三方矛盾，
    # 暗示可以继续在原文档上写——而归档文档记录的是当时的状态，不该被续写。
    status_values = config["overview"]["status_values"]
    finalized = {status_values[3], status_values[-1]}
    archive_root = os.path.join(target_root, config["dirs"]["archive"])
    doc_paths = []
    for kind, index in sorted(doc_columns.items(), key=lambda item: item[1]):
        cell = row["单元格"][index]
        if is_placeholder(cell, config):
            continue
        doc_paths.append(os.path.normpath(os.path.join(target_root, cell)))
    archived = any(_is_under(path, archive_root) for path in doc_paths)
    if archived and new_status not in finalized:
        die(
            "能力「" + name + "」已归档，状态不能改回「" + new_status + "」。" + "\n"
            "归档是完成后冻结的位置：后续要改行为，应新建能力并指向它：" + "\n"
            "  python devflow_guard.py new <新能力名> --rework-from " + name + "\n"
            "若只是纠错（错别字、失效链接），直接编辑归档文档即可，不必改状态。"
        )

    # 先收集全部待改文件，任一不存在即整体中止——避免只改了一半。
    targets = []
    for kind, index in sorted(doc_columns.items(), key=lambda item: item[1]):
        cell = row["单元格"][index]
        if is_placeholder(cell, config):
            continue
        path = os.path.normpath(os.path.join(target_root, cell))
        if not os.path.isfile(path):
            die(
                "总览表列「" + header[index] + "」指向的文件不存在：" + cell
                + "\n状态同步会漏掉该文件，请先修正总览表。"
            )
        targets.append(path)

    originals = {}
    for path in targets:
        text, read_error = read_text(path)
        if text is None:
            die("读取失败：%s（%s）" % (rel(root, path), read_error))
        updated, found = replace_header_field(text, status_field, new_status)
        if not found:
            die(
                rel(root, path) + " 的文件头里没有「" + status_field + "」字段，已中止（不写任何文件）。"
            )
        originals[path] = (text, updated)

    written = []
    try:
        for path, (_, updated) in originals.items():
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(updated)
            written.append(path)
        cells = list(row["单元格"])
        cells[config["overview"]["status_column"]] = new_status
        with open(overview_path, "w", encoding="utf-8") as handle:
            handle.write(replace_row(overview_text, row["行号"], cells))
    except OSError as write_error:
        # 回滚已写入的文档，保持「要么全部改、要么全不改」
        for path in written:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(originals[path][0])
            except OSError:
                pass
        die("写入失败（%s），已回滚已写入的文档。" % write_error)

    print("能力「" + name + "」状态已改为：" + new_status)
    print("  " + rel(root, overview_path) + "（总览表）")
    for path in targets:
        print("  " + rel(root, path))
    return 0


# ---------------------------------------------------------------------------
# audit 模式
# ---------------------------------------------------------------------------


def iter_capability_docs(target_root, config):
    """遍历所有应带文件头的能力文档。

    参数：
        target_root: 文档根绝对路径
        config: 配置字典

    返回：
        文档路径列表（已排序）
    """
    dirs = config["dirs"]
    docs = []
    for key in ("design", "plans", "testing"):
        folder = os.path.join(target_root, dirs[key])
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if name.endswith(".md") and name != "README.md" and os.path.isfile(path):
                docs.append(path)

    # 归档目录同样要检查：能力归档后文档仍在维护范围内，
    # 若跳过，归档即可成为「手写文档免检」的后门。
    archive = os.path.join(target_root, dirs["archive"])
    if os.path.isdir(archive):
        for capability in sorted(os.listdir(archive)):
            sub = os.path.join(archive, capability)
            if not os.path.isdir(sub):
                continue
            for name in sorted(os.listdir(sub)):
                path = os.path.join(sub, name)
                if name.endswith(".md") and name != "README.md" and os.path.isfile(path):
                    docs.append(path)
    decisions = os.path.join(target_root, dirs["decisions"])
    if os.path.isdir(decisions):
        for name in sorted(os.listdir(decisions)):
            path = os.path.join(decisions, name)
            if name == "README.md" or not name.endswith(".md"):
                continue
            if os.path.isfile(path):
                docs.append(path)
    return docs


def extract_header_table(text):
    """提取文件头字段表区域。

    定位首个「| 字段 | 值 |」表头行，收集其后连续表格行，遇非表格行即结束。
    只在这段区域内查字段，避免正文里偶然出现的同名行被当作字段。

    参数：
        text: 文档全文

    返回：
        表头区域文本；未找到返回空串
    """
    lines = text.splitlines()
    start = None
    in_fence = False
    for index, line in enumerate(lines):
        # 跳过代码围栏内的内容：正文里的模板示例不应被当作真表头，
        # 否则「只贴一段示例、真实表缺失」的文档会通过文件头检查。
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cells = split_row(line)
        if len(cells) == 2 and cells[0] == "字段" and cells[1] == "值":
            start = index
            break
    if start is None:
        return ""
    collected = []
    for line in lines[start:]:
        if not line.strip().startswith("|"):
            break
        collected.append(line)
    return "\n".join(collected)


def parse_header_fields(header_text):
    """把文件头表格解析为键值字典。

    参数：
        header_text: extract_header_table 返回的表格区域

    返回：
        {字段名: 值}
    """
    found = {}
    for line in header_text.splitlines():
        cells = split_row(line)
        if len(cells) == 2 and cells[0] not in ("字段",) and not set(cells[0]) <= set("-: "):
            found[cells[0]] = cells[1]
    return found


def check_header_fields(root, target_root, config):
    """检查 1：文件头字段齐全、状态取值合法。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        缺口列表
    """
    findings = []
    fields = config["file_header"]["fields"]
    status_values = set(config["overview"]["status_values"])
    for path in iter_capability_docs(target_root, config):
        text, error = read_text(path)
        if text is None:
            findings.append(
                Finding(LEVEL_ERROR, "文件头", rel(root, path) + " " + str(error))
            )
            continue
        header = extract_header_table(text)
        if not header:
            findings.append(
                Finding(LEVEL_ERROR, "文件头", rel(root, path) + " 缺少文件头字段表")
            )
            continue
        values = parse_header_fields(header)
        missing = [name for name in fields if not values.get(name, "").strip()]
        if missing:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "文件头",
                    rel(root, path) + " 缺少字段：" + "、".join(missing),
                )
            )
        status_field = config["file_header"]["status_field"]
        status = values.get(status_field, "").strip()
        if status and status not in status_values:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "文件头",
                    rel(root, path) + " 的状态取值「" + status + "」不在允许集合内："
                    + "、".join(sorted(status_values)),
                )
            )
    return findings


def check_generator_mark(root, target_root, config):
    """检查 2：生成器字段存在且取值合法（适用于全部能力文档，不限状态）。

    与「只查草稿 + 子串匹配」的旧做法不同：字段解析后比对确切取值，
    避免空值或任意文本蒙混通过；也不因文档状态改为评审中而失去检查。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        缺口列表
    """
    findings = []
    header_cfg = config["file_header"]
    field = header_cfg["generator_field"]
    allowed = set(header_cfg["generator_values"])
    for path in iter_capability_docs(target_root, config):
        text, _ = read_text(path)
        if text is None:
            continue  # 读取失败由文件头检查报，避免同一根因报两条
        header = extract_header_table(text)
        if not header:
            continue  # 缺表由文件头检查报，避免重复
        values = parse_header_fields(header)
        value = values.get(field)
        if value is None:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "生成标记",
                    rel(root, path) + " 缺少「" + field + "」字段（应由 new 生成，不得手工省略）",
                )
            )
        elif value.strip() not in allowed:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "生成标记",
                    rel(root, path) + " 的「" + field + "」取值为「" + value.strip()
                    + "」，不在合法集合内：" + "、".join(sorted(allowed)),
                )
            )
    return findings


def check_table_contract(root, target_root, config):
    """检查 3：总览表表头与配置一致，且列数正确。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        (行列表, 缺口列表)
    """
    overview_path = os.path.join(target_root, config["overview"]["file"])
    text, error = read_text(overview_path)
    if text is None:
        return [], [
            Finding(
                LEVEL_ERROR,
                "总览表",
                rel(root, overview_path) + "（" + str(error) + "）",
            )
        ]
    rows, error = parse_overview(text, config)
    if error:
        return [], [Finding(LEVEL_ERROR, "总览表", rel(root, overview_path) + "：" + error)]
    return rows, []


def check_table_vs_disk(root, target_root, config, rows):
    """检查 4/5：总览表引用的文件必须存在；磁盘上的能力文档必须在表里有行。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典
        rows: parse_overview 返回的行列表

    返回：
        缺口列表
    """
    findings = []
    dash = config["overview"]["placeholder_dash"]
    todo = config["overview"]["placeholder_todo"]
    cap_index = config["overview"]["capability_column"]
    status_index = config["overview"]["status_column"]
    registered = set()

    for row in rows:
        registered.add(row["能力"])
        if not row["能力"].strip():
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "总览表",
                    "第 %d 行的能力列为空" % (row["行号"] + 1),
                )
            )
        for index, cell in enumerate(row["单元格"]):
            if not cell:
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "总览表",
                        "能力「" + (row["能力"] or "（空）") + "」第 %d 列为空白（未产出填 %s，应有但暂缺填「%s」）"
                        % (index + 1, dash, todo),
                    )
                )
                continue
            if index in (cap_index, status_index) or cell in (dash, todo):
                continue
            candidate = os.path.normpath(os.path.join(target_root, cell))
            if not os.path.exists(candidate):
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "总览表",
                        "能力「" + row["能力"] + "」引用的文件不存在：" + cell,
                    )
                )

    # 同名能力出现多行：new 会拦住新增，但手工编辑总览表仍可能重复，
    # 重复行的语义不确定（哪个状态生效？），因此报错。
    archive_dir = os.path.normpath(os.path.join(target_root, config["dirs"]["archive"]))
    decisions_dir = os.path.normpath(os.path.join(target_root, config["dirs"]["decisions"]))

    seen_capabilities = {}
    for row in rows:
        name = row["能力"].strip()
        if not name:
            continue
        if name in seen_capabilities:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "总览表",
                    "能力「" + name + "」重复出现（第 %d 行与第 %d 行）"
                    % (seen_capabilities[name] + 1, row["行号"] + 1),
                )
            )
        else:
            seen_capabilities[name] = row["行号"]

    # 总览表行的状态取值必须合法：非法值会让配对检查静默跳过
    status_values = set(config["overview"]["status_values"])
    for row in rows:
        if row["状态"] and row["状态"] not in status_values:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "总览表",
                    "能力「" + row["能力"] + "」第 %d 行的状态「%s」不在合法集合内：%s"
                    % (row["行号"] + 1, row["状态"], "、".join(sorted(status_values))),
                )
            )

    # 提示级信号：已废弃文档仍留在活跃目录（未归档）——不是违规，但值得留意
    for path in iter_capability_docs(target_root, config):
        parent = os.path.normpath(os.path.dirname(path))
        if parent == archive_dir or parent.startswith(archive_dir + os.sep):
            continue
        text, _ = read_text(path)
        if text is None:
            continue
        values = parse_header_fields(extract_header_table(text))
        deprecated = config["overview"]["status_values"][-1]
        if values.get(config["file_header"]["status_field"], "").strip() == deprecated:
            findings.append(
                Finding(
                    LEVEL_INFO,
                    "废弃文档",
                    rel(root, path) + " 状态为「" + deprecated + "」但仍留在活跃目录（可考虑归档或删除）",
                )
            )

    for path in iter_capability_docs(target_root, config):
        # 决策记录不按能力命名，也不要求逐条登记到总览表，跳过
        if os.path.normpath(os.path.dirname(path)) == decisions_dir:
            continue
        # 归档文档放在 archive/<能力名>/ 下，其能力由总览表该行的路径列体现，
        # 不按文件名反推（否则每个归档能力都会被误报“未登记”）
        parent = os.path.normpath(os.path.dirname(path))
        if parent == archive_dir or parent.startswith(archive_dir + os.sep):
            continue
        name = os.path.basename(path)
        stem = name[:-3]
        for suffix in ("-plan", "-deviation", "-testing"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        if stem and stem not in registered:
            findings.append(
                Finding(
                    LEVEL_WARN,
                    "总览表",
                    rel(root, path) + " 对应的能力「" + stem + "」未在总览表登记",
                )
            )
    return findings


def check_adr_numbering(root, target_root, config):
    """检查 6：决策记录编号连续、无重复、文件名合规。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        缺口列表
    """
    findings = []
    folder = os.path.join(target_root, config["dirs"]["decisions"])
    if not os.path.isdir(folder):
        return findings
    pattern = re.compile(r"^(\d{4})-[a-z0-9]+(-[a-z0-9]+)*\.md$")
    numbers = []
    for name in sorted(os.listdir(folder)):
        if name == "README.md" or not name.endswith(".md"):
            continue
        match = pattern.match(name)
        if not match:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "决策编号",
                    config["dirs"]["decisions"] + "/" + name
                    + " 文件名不合规（应为 NNNN-<英文-kebab-case>.md）",
                )
            )
            continue
        numbers.append(int(match.group(1)))

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        findings.append(
            Finding(
                LEVEL_ERROR,
                "决策编号",
                "编号重复：" + "、".join("%04d" % n for n in duplicates),
            )
        )
    if 0 in numbers:
        findings.append(
            Finding(LEVEL_ERROR, "决策编号", "存在 0000 编号，决策编号必须从 0001 起")
        )
    if numbers:
        expected = set(range(1, max(numbers) + 1))
        gaps = sorted(expected - set(numbers))
        if gaps:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "决策编号",
                    "编号不连续，缺少：" + "、".join("%04d" % n for n in gaps),
                )
            )
    return findings


def check_adr_supersede(root, target_root, config):
    """检查 9：ADR「取代」字段指向的编号必须存在。

    决策链的价值在于「顺着编号能查到被取代者」。若指向一个不存在的编号，
    表面上有一条链，实际上断在中间，而读者无从判断是笔误还是链本身缺失。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        缺口列表
    """
    findings = []
    folder = os.path.join(target_root, config["dirs"]["decisions"])
    if not os.path.isdir(folder):
        return findings

    existing = set()
    for name in os.listdir(folder):
        match = re.match(r"^(\d{4})-", name)
        if match and name.endswith(".md"):
            existing.add(int(match.group(1)))

    pattern = re.compile(r"ADR-(\d{4})")
    for name in sorted(os.listdir(folder)):
        if name == "README.md" or not name.endswith(".md"):
            continue
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        text, _ = read_text(path)
        if text is None:
            continue
        section = _supersede_section(text)
        if not section:
            continue
        for number in pattern.findall(section):
            target = int(number)
            if target == 0 or target not in existing:
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "决策取代",
                        rel(root, path) + " 的「取代」指向 ADR-" + number + "，但该编号的决策记录不存在",
                    )
                )
    return findings


def _supersede_section(text):
    """取出「取代」一节的正文。

    只在这一节里找编号：一级标题里的自身编号、其余正文里的引用都不算「取代关系」。

    参数：
        text: 文档全文

    返回：
        该节正文；未找到该节返回空串
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("## 取代"):
            start = index + 1
            break
    if start is None:
        return ""
    collected = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        collected.append(line)
    return chr(10).join(collected)


def check_explore_records(root, target_root, config):
    """检查 10：需求探索记录的状态与结论完整性。

    只查两件机械可判定的事：
    1. 状态不得为空，且必须是「初始值」或任一能力状态取值（即已推进）；
    2. 已有能力文档引用它时（设计文档背景写了它的路径），结论不得为空。

    不查「结论写得好不好」——那属评审。这里只保证「确认过」这件事有据可查，
    否则探索记录会退化成一张空表，而它恰恰是用来防止空文档的。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典

    返回：
        缺口列表
    """
    findings = []
    folder = explore_dir(config)
    if not folder:
        return findings
    path_root = os.path.join(target_root, folder)
    if not os.path.isdir(path_root):
        return findings

    status_field = config["file_header"]["status_field"]
    initial = config["overview"]["status_values"][0]
    known = set(config["overview"]["status_values"])

    for name in sorted(os.listdir(path_root)):
        if name == "README.md" or not name.endswith(".md"):
            continue
        path = os.path.join(path_root, name)
        if not os.path.isfile(path):
            continue
        text, _ = read_text(path)
        if text is None:
            continue
        header = extract_header_table(text)
        if not header:
            findings.append(
                Finding(LEVEL_ERROR, "需求探索", rel(root, path) + " 缺少文件头字段表")
            )
            continue
        values = parse_header_fields(header)
        status = values.get(status_field, "").strip()
        if not status:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "需求探索",
                    rel(root, path) + " 的「" + status_field + "」为空",
                )
            )
        elif status not in known:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "需求探索",
                    rel(root, path) + " 的状态「" + status + "」不在允许集合内："
                    + "、".join(config["overview"]["status_values"]),
                )
            )

    findings.extend(check_explore_adoption(root, target_root, config, path_root))
    return findings


def check_explore_adoption(root, target_root, config, path_root):
    """检查 11：采纳指针双向一致。

    两条判据互为反向，缺任一条都会留一个方向的漏洞：

    | 方向 | 判据 | 拦住什么 |
    |---|---|---|
    | 探索记录 → 能力 | 写了「采纳于」的路径必须存在 | 能力被删/改名/归档后指针悬空 |
    | 能力 → 探索记录 | 设计文档「背景」引用某记录的，该记录必须有指向它的采纳行 | 有人重写「背景」时把来源抹掉，或事后补写来源 |

    只查「指针是否成立」，不查内容是否被改过——本地无法证明后者，
    而假装能证明会产出永远消不掉的告警（合法纠错也会报）。真实防线是提交历史。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典
        path_root: 探索目录绝对路径

    返回：
        缺口列表
    """
    findings = []
    folder = explore_dir(config)
    adoptions = {}

    for name in sorted(os.listdir(path_root)):
        if name == "README.md" or not name.endswith(".md"):
            continue
        path = os.path.join(path_root, name)
        if not os.path.isfile(path):
            continue
        text, _ = read_text(path)
        if text is None:
            continue
        rel_record = folder + "/" + name
        targets = parse_adoption_targets(explore_adoption_section(text))
        adoptions[rel_record] = set(targets)
        for target in targets:
            full = os.path.normpath(os.path.join(target_root, target))
            if not os.path.isfile(full):
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "需求采纳",
                        rel_record + " 记录的采纳目标不存在：" + target,
                    )
                )

    # 方向 A：采纳行指向的文档必须仍声明该来源。
    # 若只查「有引用则须有采纳行」，抹掉引用就能让检查失效；
    # 反过来说，只查这一条又会被「删掉采纳行」绕过——因此方向 B 不可省。
    for rel_record, targets in adoptions.items():
        for target in targets:
            full = os.path.normpath(os.path.join(target_root, target))
            if not os.path.isfile(full):
                continue  # 目标不存在已由上一条报，不重复
            text, _ = read_text(full)
            if text is None:
                continue
            if rel_record not in extract_section(text, "背景"):
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "需求采纳",
                        target + " 被 " + rel_record + " 记录为采纳目标，"
                        + "但其「背景」一节已不含该探索记录的引用（来源被抹掉或改写）",
                    )
                )

    # 方向 B：设计文档仍声明来源的，探索记录必须存在且反向留有采纳行。
    # 只有这条能发现「删掉采纳行」——否则删掉一行就能让方向 A 失去依据。
    for design_full, rel_record in explore_references(target_root, config):
        record_path = os.path.join(target_root, rel_record)
        if not os.path.isfile(record_path):
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "需求采纳",
                    rel(root, design_full) + " 声明来源为 " + rel_record + "，但该记录不存在",
                )
            )
            continue
        design_rel = os.path.relpath(design_full, target_root).replace(os.sep, "/")
        if rel_record in adoptions and design_rel not in adoptions[rel_record]:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "需求采纳",
                    rel(root, design_full) + " 声明来源为 " + rel_record
                    + "，但该记录没有指向它的采纳行（采纳行被删或被改）",
                )
            )
    return findings


def explore_references(target_root, config):
    """扫描设计文档「背景」中指向探索记录的引用。

    只认明确写成「探索记录见 <path>」的行，并把路径限定在探索目录内；
    正文里偶然出现的同名路径不计入，避免误判。

    参数：
        target_root: 文档根
        config: 配置字典

    返回：
        [(设计文档绝对路径, 探索记录相对文档根的路径), ...]
    """
    folder = explore_dir(config)
    marker = "探索记录见"
    found = []
    design_dir = os.path.join(target_root, config["dirs"]["design"])
    archive_dir = os.path.join(target_root, config["dirs"]["archive"])
    for base_dir in (design_dir, archive_dir):
        if not os.path.isdir(base_dir):
            continue
        for dirpath, _, filenames in os.walk(base_dir):
            for name in sorted(filenames):
                if not name.endswith(".md") or name == "README.md":
                    continue
                path = os.path.join(dirpath, name)
                text, _ = read_text(path)
                if text is None:
                    continue
                for line in extract_section(text, "背景").splitlines():
                    if marker not in line:
                        continue
                    body = line.split(marker, 1)[1].strip()
                    for sep in ("（", "(", chr(32)):
                        body = body.split(sep)[0]
                    body = body.strip().strip(chr(96)).strip().replace(chr(92), "/")
                    if body.startswith(folder + "/") and body.endswith(".md"):
                        found.append((path, body))
    return found


def check_archive_consistency(root, target_root, config, rows):
    """检查 8：归档目录与总览表一致——归档能力必须登记，且四类文档齐全。

    归档目录此前的检查只覆盖「文档头字段是否合规」，因此
    - 凭空出现在归档里的能力（从未登记、也没有对应总览表行）不会被发现；
    - 归档只移了一半（缺某类文档）也不会被发现。
    这两类都让「归档」变成可以绕过登记的存放点，故补此检查。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典
        rows: parse_overview 返回的行列表

    返回：
        缺口列表
    """
    findings = []
    archive_root = os.path.join(target_root, config["dirs"]["archive"])
    if not os.path.isdir(archive_root):
        return findings

    header = config["overview"]["header"]
    doc_columns, missing = resolve_doc_columns(header, config)
    if missing:
        return findings  # 列无法识别由 new/archive 报，这里不重复

    capability_of_archive = {}
    for row in rows:
        for kind, index in doc_columns.items():
            cell = row["单元格"][index]
            if is_placeholder(cell, config):
                continue
            resolved = os.path.normpath(os.path.join(target_root, cell))
            if _is_under(resolved, archive_root):
                capability_of_archive.setdefault(row["能力"], set()).add(kind)

    for entry in sorted(os.listdir(archive_root)):
        sub = os.path.join(archive_root, entry)
        if not os.path.isdir(sub):
            continue
        if entry not in capability_of_archive:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "归档",
                    config["dirs"]["archive"] + "/" + entry
                    + " 不是任何已登记能力的归档位置（总览表没有该能力的归档路径）",
                )
            )
            continue
        present = {
            name
            for name in os.listdir(sub)
            if name.endswith(".md") and os.path.isfile(os.path.join(sub, name))
        }
        expected = set(ARCHIVE_FILENAMES.values())
        extra = sorted(present - expected - {"README.md"})
        lacking = sorted(ARCHIVE_FILENAMES[kind] for kind in SCAFFOLD_DIRS if ARCHIVE_FILENAMES[kind] not in present)
        if lacking:
            findings.append(
                Finding(
                    LEVEL_WARN,
                    "归档",
                    "能力「" + entry + "」的归档缺少：" + "、".join(lacking),
                )
            )
        if extra:
            findings.append(
                Finding(
                    LEVEL_WARN,
                    "归档",
                    "能力「" + entry + "」的归档目录有无法识别的文件："
                    + "、".join(extra),
                )
            )
    return findings


def check_plan_deviation_pair(root, target_root, config, rows):
    """检查 7：状态为已定或已实施时，计划与偏差成对或显式写明无偏差。

    参数：
        root: 项目根
        target_root: 文档根
        config: 配置字典
        rows: parse_overview 返回的行列表

    返回：
        缺口列表
    """
    findings = []
    overview = config["overview"]
    settled = {overview["status_values"][2], overview["status_values"][3]}
    dash = overview["placeholder_dash"]
    todo = overview["placeholder_todo"]
    cap_index = overview["capability_column"]
    header = overview["header"]

    def column_paths(row):
        """按表头语义取出该行的计划与偏差路径（相对文档根）。

        以表格为准而非按目录猜名：能力归档后路径会变成归档目录下的文件，
        按 <plans>/<能力>-plan.md 猜会对着已归档能力误报「缺少计划」。
        """
        plan_rel = deviation_rel = ""
        for index, column in enumerate(header):
            if index == cap_index:
                continue
            cell = row["单元格"][index]
            if cell in (dash, todo, ""):
                continue
            if "偏差" in column:
                deviation_rel = cell
            elif "计划" in column:
                plan_rel = cell
        return plan_rel, deviation_rel

    for row in rows:
        if row["状态"] not in settled:
            continue
        capability = row["能力"]
        plan_rel, deviation_rel = column_paths(row)
        plan = os.path.join(target_root, plan_rel) if plan_rel else ""
        deviation = os.path.join(target_root, deviation_rel) if deviation_rel else ""
        if not plan or not os.path.isfile(plan):
            findings.append(
                Finding(
                    LEVEL_WARN,
                    "计划/偏差配对",
                    "能力「" + capability + "」状态为「" + row["状态"] + "」但缺少实施计划",
                )
            )
            continue
        if deviation and os.path.isfile(deviation):
            continue
        # 「待补」表示该阶段应产出但暂缺，不能当作「已声明无偏差」
        findings.append(
            Finding(
                LEVEL_WARN,
                "计划/偏差配对",
                "能力「" + capability + "」状态为「" + row["状态"]
                + "」但缺少实施偏差记录（若确无偏差，须在计划中显式写明）",
            )
        )
    return findings


def run_audit(root, config):
    """执行全部检查并输出报告。

    参数：
        root: 项目根
        config: 配置字典

    返回：
        退出码（0 通过 / 1 警告 / 2 错误）
    """
    target_root = docs_dir(root, config)
    print("开发流程文档体检")
    print("项目根：" + root)
    print("文档根：" + config["docs_root"])
    print()

    findings = []
    rows, table_findings = check_table_contract(root, target_root, config)
    findings.extend(table_findings)
    findings.extend(check_header_fields(root, target_root, config))
    findings.extend(check_generator_mark(root, target_root, config))
    if not table_findings:
        findings.extend(check_table_vs_disk(root, target_root, config, rows))
        findings.extend(check_plan_deviation_pair(root, target_root, config, rows))
        findings.extend(check_archive_consistency(root, target_root, config, rows))
    findings.extend(check_adr_numbering(root, target_root, config))
    findings.extend(check_adr_supersede(root, target_root, config))
    findings.extend(check_explore_records(root, target_root, config))

    errors = [item for item in findings if item.level == LEVEL_ERROR]
    warns = [item for item in findings if item.level == LEVEL_WARN]
    infos = [item for item in findings if item.level == LEVEL_INFO]

    for group, label in ((errors, "错误"), (warns, "警告"), (infos, "提示")):
        if not group:
            continue
        print("—— " + label + "（" + str(len(group)) + "）——")
        for item in group:
            print("  " + str(item))
        print("")

    print("结论：错误 %d，警告 %d，提示 %d" % (len(errors), len(warns), len(infos)))
    if errors:
        print("存在错误，需修复后重跑。")
        return 2
    if warns:
        print("无错误，但存在需人工判断的警告。")
        return 1
    print("通过。")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv=None):
    """解析参数并分派模式。

    参数：
        argv: 参数列表；缺省取 sys.argv[1:]

    返回：
        退出码
    """
    parser = argparse.ArgumentParser(
        prog="devflow_guard.py",
        description="开发流程文档骨架生成与契约体检",
    )
    parser.add_argument("--root", default=None, help="项目根目录（默认自动向上查找）")
    sub = parser.add_subparsers(dest="mode")

    sub.add_parser("init", help="按项目配置初始化文档目录结构")
    new_parser = sub.add_parser("new", help="生成能力文档骨架并登记总览表")
    new_parser.add_argument("name", help="能力名（须匹配配置声明的命名模式）")
    new_parser.add_argument(
        "--rework-from",
        default="",
        help="被重开的已归档能力名（在原能力上改行为时，应立新能力并指向旧能力）",
    )
    new_parser.add_argument(
        "--from-explore",
        default="",
        help="需求探索记录名（项目启用探索时必填，且该记录须已确认）",
    )
    explore_parser = sub.add_parser("explore", help="创建需求探索记录（动手前的需求确认）")
    explore_parser.add_argument("slug", help="主题名（英文 kebab-case，成为文件名）")
    explore_parser.add_argument("--title", default="", help="主题标题（默认取 slug）")
    adr_parser = sub.add_parser("adr", help="创建决策记录（ADR），自动推算编号")
    adr_parser.add_argument("slug", help="决策描述（英文 kebab-case，成为文件名的一部分）")
    adr_parser.add_argument("--title", default="", help="决策标题（默认取 slug）")
    adr_parser.add_argument("--capability", default="", help="关联能力（默认「全局」）")
    archive_parser = sub.add_parser("archive", help="把能力的过程文档整包移入归档目录并回写总览表")
    archive_parser.add_argument("name", help="能力名（须已在总览表登记）")
    status_parser = sub.add_parser("status", help="同步能力状态到总览表与全部文档文件头")
    status_parser.add_argument("name", help="能力名（须已在总览表登记）")
    status_parser.add_argument("value", help="目标状态（须在配置声明的取值集合内）")
    sub.add_parser("audit", help="体检文档契约")

    args = parser.parse_args(argv)
    if not args.mode:
        parser.print_help()
        return 2

    root = find_project_root(args.root or os.getcwd())
    try:
        config = load_config(root)
    except ConfigError as error:
        print("配置不可用：" + str(error), file=sys.stderr)
        return 3

    if args.mode == "init":
        return run_init(root, config)
    if args.mode == "new":
        return run_new(root, config, args.name, args.rework_from, args.from_explore)
    if args.mode == "explore":
        return run_explore(root, config, args.slug, args.title)
    if args.mode == "adr":
        return run_adr(root, config, args.slug, args.title, args.capability)
    if args.mode == "archive":
        return run_archive(root, config, args.name)
    if args.mode == "status":
        return run_status(root, config, args.name, args.value)
    return run_audit(root, config)


if __name__ == "__main__":
    sys.exit(main())
