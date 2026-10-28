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
2. **一切形状来自项目配置**。文档根、六个子目录名、总览表列序、状态取值、文件头字段、
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
import sys
import unicodedata
from datetime import date

# 配置在项目索引中的逻辑名
CONFIG_CODENAME = "devflow.docs.config"

# 模板目录（相对本脚本）：scripts/ -> devflow-guard/ -> references/templates
TEMPLATES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "templates")
)

# 需要复制的六个子目录（键名对应配置 dirs 下的键）
DOC_SUBDIR_KEYS = ("design", "plans", "testing", "decisions", "archive", "templates")

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
        (os.path.join(TEMPLATES_DIR, "docs", "README.md"), os.path.join(target_root, config["overview"]["file"]))
    )
    # 六个子目录的目录说明
    for key in DOC_SUBDIR_KEYS:
        plan.append(
            (
                os.path.join(TEMPLATES_DIR, key, "README.md"),
                os.path.join(target_root, config["dirs"][key], "README.md"),
            )
        )
    # 五份文档模板
    for name in ("design.md", "plan.md", "deviation.md", "testing.md", "adr.md"):
        plan.append(
            (
                os.path.join(TEMPLATES_DIR, "docs", name),
                os.path.join(target_root, config["dirs"]["templates"], name),
            )
        )

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


# ---------------------------------------------------------------------------
# new 模式
# ---------------------------------------------------------------------------


SCAFFOLD_SPECS = (
    ("design.md", "design", "{name}.md"),
    ("plan.md", "plans", "{name}-plan.md"),
    ("testing.md", "testing", "{name}-testing.md"),
)


def run_new(root, config, name):
    """生成能力文档骨架并登记总览表。

    三道运行时保护，任一不满足即中止且不写任何文件：
    能力名格式、目标文件已存在、总览表可解析且插入点可定位。

    参数：
        root: 项目根
        config: 配置字典
        name: 能力名

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

    targets = []
    for template_name, dir_key, pattern_name in SCAFFOLD_SPECS:
        template = os.path.join(TEMPLATES_DIR, "docs", template_name)
        if not os.path.isfile(template):
            die("包内模板缺失：" + template)
        target = os.path.join(target_root, config["dirs"][dir_key], pattern_name.format(name=name))
        targets.append((template, target))

    conflicts = [dst for _, dst in targets if os.path.exists(dst)]
    if conflicts:
        die(
            "以下文件已存在，已中止（不覆盖）：\n  "
            + "\n  ".join(rel(root, item) for item in conflicts)
        )

    today = date.today().isoformat()
    generator = config["file_header"]["generator_values"][0]

    created = []
    for template, target in targets:
        raw, error = read_text(template)
        if raw is None:
            die("包内模板读取失败：%s（%s）" % (template, error))
        text = fill_placeholders(raw, config)
        text = text.replace("<能力名>", name)
        text = text.replace("YYYY-MM-DD", today)
        text = text.replace("{{generator}}", generator)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
        created.append(target)

    header_names = config["overview"]["header"]
    dash = config["overview"]["placeholder_dash"]
    cap_index = config["overview"]["capability_column"]
    status_index = config["overview"]["status_column"]

    cells = []
    for index, column in enumerate(header_names):
        if index == cap_index:
            cells.append(name)
        elif index == status_index:
            cells.append(config["overview"]["status_values"][0])
        elif "设计" in column:
            cells.append(config["dirs"]["design"] + "/" + name + ".md")
        elif "计划" in column and "偏差" not in column:
            cells.append(config["dirs"]["plans"] + "/" + name + "-plan.md")
        elif "测试" in column:
            cells.append(config["dirs"]["testing"] + "/" + name + "-testing.md")
        else:
            cells.append(dash)
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

    print("已生成：")
    for item in created:
        print("  " + rel(root, item))
    print("已在能力总览表登记：" + name)
    print("")
    print("下一步：填写设计文档的方案与取舍，方案定稿后补计划，开发完成后补验收记录。")
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
    findings.extend(check_adr_numbering(root, target_root, config))

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

    sub.add_parser("init", help="按项目配置初始化文档目录结构与模板")
    new_parser = sub.add_parser("new", help="生成能力文档骨架并登记总览表")
    new_parser.add_argument("name", help="能力名（须匹配配置声明的命名模式）")
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
        return run_new(root, config, args.name)
    return run_audit(root, config)


if __name__ == "__main__":
    sys.exit(main())
