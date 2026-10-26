---
name: csharp-comment-checker
description: C# 代码注释合规性检查工具。使用基于 Roslyn 的 .NET 工具解析 .cs 文件，检查 XML 文档注释（///）和行内注释（//）是否符合项目规范。所有规则的严重程度可通过 JSON 配置文件定制。返回结构化问题列表（含代码摘要）。使用场景：检查 C# 文件注释是否合规、扫描目录中注释缺失情况、验证注释质量。当用户要求检查/扫描 C# 注释，或要求"扫描后补全/修复注释"时，应主动调用此技能完成扫描并产出 .md + .json 报告；扫描产出报告后如需修复，由 csharp-comment-generator 技能基于报告逐项修复，修复完成后可再次调用本技能验证清零。调用时将用户指定的目录或文件路径直接传递给技能，无需预扫描或分析文件列表。
license: MIT
compatibility: 需要 .NET 10.0+ SDK 和 Python 3.8+。无需额外 Agent，由 CodeBuddy Code 直接执行。
metadata:
  author: zengliugen
  version: "1.3"
---

## 快速上手
```bash
# 检查单个文件
python scripts/check_comments.py path/to/MyClass.cs

# 检查整个目录
python scripts/check_comments.py path/to/MyProject/

# JSON 输出（便于程序处理）
python scripts/check_comments.py path/to/MyClass.cs --json
```

运行后自动生成：
- `.md` 报告文件（可读的问题表格 + 类别分布统计）
- `.json` 数据文件（完整结构化数据）

结果保存在技能目录下的 `check_logs/` 中。

---

## 规则文件
项目的注释规范定义在 `.codebuddy/lib/csharp/rules/csharp-comment/` 目录下，读取该目录下的全部规则文件（文件名因项目而异），通常包括：

| 规则内容 | 说明 |
|---------|------|
| 文档注释规范 | XML 格式、标签、各成员示例 |
| 行内注释规范 | 触发场景、正反示例 |
| 注释修正规则 | 四维度质量检查 |
| 合规要求 | 禁止事项、豁免、检查清单 |
| 代码修改注释同步规则 | 新增/修改/删除时注释同步 |

以上 `.mdc` 文件为人工维护的规范文档。本技能的检查逻辑由配置驱动：引擎侧 `tools/CSharpCommentChecker/comment_config.json`（规则与严重程度）+ 项目侧（索引 `comment.project_config`，排除目录与术语），读取时深度合并。

> **注意：** 修改规范文件（`.mdc`）后，需同步更新 `comment_config.json` 中的对应规则配置。

## 检查范围
技能覆盖三类检查：
- **文档注释检查**（///）：12 种成员类型的注释存在性、标签完整性、语言检测、语义一致性
- **行内注释检查**（//）：14 种触发场景的方法体行内注释检测
- **文件级别检查**：文件头注释、解析错误、Generated/ 和 Gen/ 目录豁免

> **补充说明（非中文注释修正）**：`language` 规则用于检测注释语言——当注释内容不含中文字符（如英文注释）时报告警告。检测时会先剥离 `comment_config.json` 中 `knownTerms` 配置的技术术语白名单（大小写不敏感），避免将术语误判为英文。修复时须将非中文注释修正为简体中文注释，技术术语可保留英文；修复动作由 `csharp-comment-generator` 技能完成。

详细规则表和默认严重程度见 [检查范围详情](references/check-scope.md)。

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 前置规则：直接传递目标路径，禁止预分析
- 强制规则：必须生成结果文件
- 架构
- 配置
- 已知限制
- 如何使用
- 修复链路：执行顺序与并行编排
- 输出格式

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 5 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 4 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 2 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
