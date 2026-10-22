# -*- coding: utf-8 -*-
"""扫描 .cmd/.bat 脚本，检查含中文行是否以 ASCII 字符结尾（规避 chcp 65001 乱码）。

规则（详见技能 references/utf8-garbled.md）：
1. 在 chcp 65001（UTF-8）环境下，任何含中文的行（echo、rem 注释等）
   末尾字符必须是 ASCII（空格、英文标点、引号、! 等）。
2. 若某行含非 ASCII 字符（中文/全角标点）且该行的末尾字符也是非 ASCII，
   则存在概率性乱码/被误判为命令的风险（is not recognized）。
3. 仅含 ASCII 的行无需检查。

用法：
    python check_cmd_trailing.py <脚本路径或目录> [--fix]
    --fix：自动给风险行行尾补一个英文空格（幂等，重复运行不会叠加空格）。
    --recursive：target 为目录时递归扫描子目录。

示例：
    python check_cmd_trailing.py example.cmd
    python check_cmd_trailing.py scripts/ --fix --recursive
"""
import argparse
import os
import sys

# 判定是否为非 ASCII 字节（中文/全角标点的 UTF-8 首字节均 >= 0x80）
def is_non_ascii(byte):
    """判断单个字节是否为非 ASCII（>= 0x80，可能是中文/全角字符的组成部分）。"""
    return byte >= 0x80


def split_keep_newline(data):
    """按换行拆分，返回 [(行内容(不含换行), 换行符), ...]。

    兼容 CRLF、LF 以及混合换行文件：每行（除最后一行）以 \\n 结尾，
    若行内容以 \\r 结尾则判定为 CRLF，把 \\r 归入换行符。
    """
    parts = data.split(b"\n")
    result = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            if part.endswith(b"\r"):
                result.append((part[:-1], b"\r\n"))
            else:
                result.append((part, b"\n"))
        else:
            result.append((part, b""))
    return result


def read_lines(path):
    """按字节读取文件，返回去除换行符的行内容列表（含 UTF-8 BOM 时跳过 BOM）。

    字节级处理不依赖文件编码，对 GBK 等编码的脚本同样可完成行尾判定与修复；
    编码合规性由 main() 中的 validate_utf8() 另行提示。
    """
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]  # 跳过 UTF-8 BOM
    return [content for content, _ in split_keep_newline(data)]


def validate_utf8(data):
    """验证字节序列是否为合法 UTF-8。返回 (是否合法, 错误说明或 None)。"""
    try:
        data.decode("utf-8")
        return True, None
    except UnicodeDecodeError as e:
        return False, "非 UTF-8 编码（错误偏移 {}）".format(e.start)


def detect_newline_mix(data):
    """检测换行风格。返回 (是否混合换行, 描述)。"""
    crlf = data.count(b"\r\n")
    bare_lf = data.count(b"\n") - crlf
    if crlf and bare_lf:
        return True, "{} 处 CRLF + {} 处孤立 LF".format(crlf, bare_lf)
    return False, ""


def line_has_non_ascii(line):
    """判断一行是否包含非 ASCII 字节（即含中文/全角字符）。"""
    return any(is_non_ascii(b) for b in line)


def trailing_is_ascii(line):
    """判断一行的末尾字符（去掉换行后最后字节）是否为 ASCII。

    返回 (是否安全, 行尾字节)。
    """
    if not line:
        return True, None
    last = line[-1]
    # ASCII 可打印字符、空格、常见标点、引号、!、%、^ 等都是安全行尾
    return not is_non_ascii(last), last


def scan_file(path, fix=False):
    """扫描单个文件，返回风险行列表。

    风险行：含非 ASCII 字符，且行尾字符也是非 ASCII。
    返回 [(行号, 原始行字节, 修复后行字节或 None), ...]
    """
    lines = read_lines(path)
    problems = []
    for idx, line in enumerate(lines, start=1):
        # 空行（含文件末尾无换行时的空串）跳过
        if not line:
            continue
        if not line_has_non_ascii(line):
            continue  # 纯 ASCII 行无需检查
        safe, last = trailing_is_ascii(line)
        if safe:
            continue  # 行尾是 ASCII，安全
        fixed = line + b" " if fix else None  # 行尾补英文空格
        problems.append((idx, line, fixed))
    return problems


def format_problem(path, lineno, line):
    """格式化输出单个风险行，附带行尾字符说明。"""
    last = line[-1]
    last_repr = chr(last) if last < 128 else "非ASCII"
    return "  {}:{} 行尾[{}]: {}".format(path, lineno, last_repr, line.decode("utf-8", errors="replace"))


def write_fixed(path, problems):
    """将修复后的内容写回文件。problems 为 (行号, 原行, 修复行) 列表。"""
    with open(path, "rb") as f:
        raw = f.read()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    data = raw[3:] if had_bom else raw
    # 保留每行原始换行符拆分，混合换行文件也能正确写回
    split = split_keep_newline(data)
    problem_map = {lineno: fixed for lineno, _, fixed in problems if fixed is not None}
    new_lines = []
    for idx, (content, nl) in enumerate(split, start=1):
        if idx in problem_map:
            content = problem_map[idx]
        new_lines.append(content + nl)
    out = b"".join(new_lines)
    if had_bom:
        out = b"\xef\xbb\xbf" + out
    with open(path, "wb") as f:
        f.write(out)


def main():
    parser = argparse.ArgumentParser(description="检查 .cmd/.bat 脚本含中文行的行尾是否为 ASCII")
    parser.add_argument("target", help="要检查的 .cmd/.bat 文件或目录")
    parser.add_argument("--fix", action="store_true", help="自动给风险行行尾补英文空格")
    parser.add_argument("--recursive", action="store_true", help="target 为目录时递归扫描子目录")
    args = parser.parse_args()

    if os.path.isdir(args.target):
        if not args.recursive:
            print("提示：target 是目录，使用 --recursive 递归扫描子目录")
            return 0
        targets = []
        for root, dirs, files in os.walk(args.target):
            for f in files:
                if f.lower().endswith((".cmd", ".bat")):
                    targets.append(os.path.join(root, f))
    elif os.path.isfile(args.target):
        targets = [args.target]
    else:
        print("错误：目标不存在：{}".format(args.target))
        return 1

    total_problems = 0
    for target in targets:
        # 预先读取原始字节，做编码与换行风格检查（仅提示，不阻断）
        try:
            with open(target, "rb") as f:
                raw = f.read()
            body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
            is_utf8, err = validate_utf8(body)
            if not is_utf8:
                print("警告：{} {}。本项目规范要求 UTF-8 无 BOM，建议先转码再处理。".format(target, err))
            mixed, detail = detect_newline_mix(raw)
            if mixed:
                print("警告：{} 存在混合换行（{}）。CMD 要求 CRLF，建议统一为 CRLF 再处理。".format(target, detail))
        except OSError as e:
            print("错误：无法读取 {}: {}".format(target, e))
            continue
        try:
            problems = scan_file(target, fix=args.fix)
        except Exception as e:
            print("错误：扫描 {} 失败: {}".format(target, e))
            continue
        if problems:
            total_problems += len(problems)
            print("风险文件：{}（{} 处风险）".format(target, len(problems)))
            for lineno, line, _ in problems:
                print(format_problem(target, lineno, line))
            if args.fix:
                write_fixed(target, problems)
                print("  已修复：{} 处补空格".format(len(problems)))
        else:
            if not args.fix:
                print("通过：{} 无行尾中文风险".format(target))

    if total_problems and not args.fix:
        print("\n共发现 {} 处风险。可加 --fix 自动补空格修复。".format(total_problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
