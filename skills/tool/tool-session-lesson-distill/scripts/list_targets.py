#!/usr/bin/env python3
"""落点清单扫描：列出可写回的技能与规则落点。

用途：session-lesson-distill 技能在阶段一执行本脚本，获取
`.codebuddy/skills/**` 与 `.codebuddy/rules/**` 的落点清单（名称、描述、
细节文件），用于确定本次会话的写回白名单与经验落点。

输出：默认输出 Markdown 清单；加 `--json` 输出结构化 JSON。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
DESCRIPTION_MAX_LEN = 120


def find_codebuddy_root(start: Path) -> Path | None:
    """从起点向上查找 .codebuddy 目录。"""
    for candidate in [start, *start.parents]:
        if candidate.name == ".codebuddy" and candidate.is_dir():
            return candidate
    return None


def parse_frontmatter(text: str) -> dict:
    """解析文件头部的 YAML frontmatter（仅提取顶层标量字段，避免引入依赖）。"""
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}
    fields: dict = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def shorten(text: str, limit: int = DESCRIPTION_MAX_LEN) -> str:
    """截断过长描述，便于清单扫读。"""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def list_skills(codebuddy_root: Path) -> list[dict]:
    """收集技能落点：skills/ 下的全部技能（含 third-party/ 嵌套与模板目录过滤）。"""
    skills_root = codebuddy_root / "skills"
    if not skills_root.is_dir():
        return []

    results: list[dict] = []
    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        # 跳过技能内部的示例/模板目录，避免把模板当成真实落点
        relative = skill_dir.relative_to(skills_root)
        if any(part in {"examples", "templates", "fixtures"} for part in relative.parts):
            continue

        text = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)

        details = []
        for sub in ("references", "scripts", "agents", "evals", "reports", "tools"):
            sub_dir = skill_dir / sub
            if sub_dir.is_dir():
                count = sum(1 for item in sub_dir.rglob("*") if item.is_file())
                if count:
                    details.append(f"{sub}/={count}")

        results.append(
            {
                "name": frontmatter.get("name", skill_dir.name),
                "path": skill_dir.as_posix().replace(
                    codebuddy_root.parent.as_posix() + "/", ""
                ),
                "mode": frontmatter.get("mode", ""),
                "description": shorten(frontmatter.get("description", "")),
                "details": details,
            }
        )
    return results


def list_rules(codebuddy_root: Path) -> list[dict]:
    """收集规则落点：入口 RULE.mdc 与其子规则。"""
    rules_root = codebuddy_root / "rules"
    if not rules_root.is_dir():
        return []

    results: list[dict] = []
    for rule_mdc in sorted(rules_root.rglob("RULE.mdc")):
        rule_dir = rule_mdc.parent
        entry_text = rule_mdc.read_text(encoding="utf-8", errors="replace")
        entry_frontmatter = parse_frontmatter(entry_text)

        sub_rules = [
            item.name
            for item in sorted(rule_dir.glob("*.mdc"))
            if item.name != "RULE.mdc"
        ]

        results.append(
            {
                "name": rule_dir.name,
                "path": rule_dir.as_posix().replace(
                    codebuddy_root.parent.as_posix() + "/", ""
                ),
                "always_apply": entry_frontmatter.get("alwaysApply", ""),
                "sub_rules": sub_rules,
            }
        )
    return results


def render_markdown(skills: list[dict], rules: list[dict]) -> str:
    """渲染 Markdown 清单。"""
    lines: list[str] = ["# 落点清单", ""]

    lines += [f"## 技能（{len(skills)}）", ""]
    if skills:
        lines += ["| 技能 | 运行模式 | 细节文件 | 描述 |", "|------|---------|---------|------|"]
        for skill in skills:
            details = "、".join(skill["details"]) or "—"
            lines.append(
                f"| `{skill['name']}` | {skill['mode'] or '—'} | {details} | {skill['description'] or '—'} |"
            )
    else:
        lines.append("（未发现技能）")

    lines += ["", f"## 规则（{len(rules)}）", ""]
    if rules:
        lines += ["| 规则 | alwaysApply | 子规则 |", "|------|-------------|--------|"]
        for rule in rules:
            sub = "、".join(f"`{name}`" for name in rule["sub_rules"]) or "—"
            lines.append(f"| `{rule['name']}` | {rule['always_apply'] or '—'} | {sub} |")
    else:
        lines.append("（未发现规则）")

    lines += ["", "> 写回白名单应仅取本次会话**实际使用过**的落点。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="列出可写回的技能与规则落点")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    parser.add_argument(
        "--only",
        choices=["skills", "rules"],
        help="仅输出技能或仅输出规则",
    )
    parser.add_argument("--root", help=".codebuddy 目录路径（默认从脚本位置向上查找）")
    args = parser.parse_args()

    if args.root:
        codebuddy_root = Path(args.root).resolve()
    else:
        codebuddy_root = find_codebuddy_root(Path(__file__).resolve().parent)

    if not codebuddy_root or not codebuddy_root.is_dir():
        print("[FAIL] 未找到 .codebuddy 目录，请用 --root 指定。", file=sys.stderr)
        return 2

    skills = [] if args.only == "rules" else list_skills(codebuddy_root)
    rules = [] if args.only == "skills" else list_rules(codebuddy_root)

    if args.json:
        print(json.dumps({"skills": skills, "rules": rules}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(skills, rules))

    print(
        f"[PASS] 扫描完成：技能 {len(skills)} 个，规则 {len(rules)} 个。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
