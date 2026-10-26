---
name: tool-session-lesson-distill
description: 会话经验固化技能。当用户要求把本次会话的经验沉淀下来（如"把这次的经验固化一下"、"沉淀到技能里"、"复盘这次踩的坑"、"/session-lesson-distill"），或会话中出现明确的可复用经验信号（用户纠正了做法、同类问题重复出现、发现技能/规则文档与实际实现不符、复杂任务收尾）时触发。从当前会话提取可复用经验（教训、约定、坑、验证方式、流程改进），按证据溯源映射到本次会话实际使用过的技能（.codebuddy/skills/**）与规则（.codebuddy/rules/**），先产出固化清单，经用户确认后写回。不创建新技能、不执行代码审查、不执行版本控制提交。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，需通过触发评估和结构检查。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 从当前会话提取可复用经验，映射并写回本次会话实际使用过的技能与规则 |
| 输出 | 固化报告（项目侧产物目录，经索引 `artifacts.dirs.session_distill.reports` 定位）、经用户确认后的目标文件改动、改动摘要 |
| 排除 | 创建新技能（走 `yao-meta-skill`）、技能结构审计（走 `yao-meta-skill`）、规则拆分合并（走 `tool-rule-consolidation`）、C# 代码审查（走 `csharp-code-review`）、版本控制提交（走 `vcs-router` / `vcs-git-commit`）、与本次会话无关的既有问题 |
| 前提 | 存在可回溯的当前会话上下文；目标落点位于 `.codebuddy/skills/**` 或 `.codebuddy/rules/**` |

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/lesson-extraction.md` | 经验提取标准：何为可复用经验、证据要求、反例与不写入边界 |
| `references/target-mapping.md` | 落点判定：技能与规则的选择、入口与子规则的选择、去重与归并 |
| `references/write-back-rules.md` | 写入规范：最小改动、去重、语言与编码、确认门与回滚边界 |
| `scripts/list_targets.py` | 落点清单扫描：列出 `.codebuddy/skills/**` 与 `.codebuddy/rules/**` 的落点及描述 |

接口契约定义在 `agents/interface.yaml`。

---

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 工作流程
- 与相邻技能的边界
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 5 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 5 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
