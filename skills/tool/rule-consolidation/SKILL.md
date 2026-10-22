---
name: rule-consolidation
description: .codebuddy 规则文件整合拆分技能。当用户要求对规则文件进行拆分（如"规则内容太多，拆分子规则"、"按入口+子规则模式调整"）、合并（如"规则拆得太细，合并一下"、"子规则太小可以放一起"）、或评估规则结构是否合理（如"评估是否过度拆分"、"规则结构是否符合项目模式"）时触发。按项目统一模式（入口 RULE.mdc 始终生效 + 子规则按需加载）评估并执行规则文件重组。仅处理 .codebuddy/rules/ 下的规则文件，不处理技能文件（SKILL.md/agents）、不处理代码文件。
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
| 拥有的任务 | 评估并重组 `.codebuddy/rules/` 下的规则文件：拆分（大规则 → 入口 + 子规则）、合并（过小子规则 → 合并）、结构评估（是否过度拆分） |
| 输出 | 重组后的规则文件、入口与子规则路由表同步、引用同步（技能/文档中指向旧路径的引用）、结构评估结论 |
| 排除 | 技能文件（`SKILL.md`、`agents/interface.yaml`、`scripts/`）、代码文件、技能功能逻辑本身 |
| 前提 | 目标规则存在且为 `.codebuddy/rules/**/RULE.mdc`（或该目录下待重组的规则文件） |

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/split-criteria.md` | 拆分评估标准：何时拆、何时不该拆、拆分模式规范（入口+子规则） |
| `references/merge-criteria.md` | 合并评估标准：过度拆分识别、合并粒度、合并后路由表同步 |
| `references/pattern-spec.md` | 项目规则统一模式：入口 frontmatter（alwaysApply/paths）、子规则路由表、加载机制说明 |

接口契约定义在 `agents/interface.yaml`。

---

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 工作流程
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 5 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 6 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
