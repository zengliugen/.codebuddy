---
name: tool-engine-sync
description: 引擎仓库更新同步技能。当用户要求"更新引擎到最新并同步项目侧"、"升级 .codebuddy 引擎"、"引擎有更新看看要同步什么"、"同步引擎新技能/新规则到项目"、"/engine-sync"，或引擎子模块指针前移后需要落实项目侧影响时触发。执行引擎仓库快进更新，对比前后两个版本的「项目侧契约」（索引 files / rule_shells / artifacts / root_symlinks 与包注册表包/组件）变化，产出影响清单（必须处理 / 建议处理 / 仅告知），经用户确认后落实：迁移路径变更、生成缺失骨架、重建包链接、提示新增技能与规则、清理残留。不做版本控制提交与推送、不创建新技能、不审查代码。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式

<!-- pack-ref-ok: vcs-router, git-commit, yao-meta-skill, csharp-code-review, rule-consolidation —— 「排除项 / 交给谁」职责分流表，纯说明性，不调用这些组件。 -->
`Production` —— 团队复用技能，需通过触发评估和结构检查。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 更新引擎仓库到最新，并把版本间的「项目侧契约」变化落实到项目侧 |
| 输出 | 影响分析清单（三档严重度）、经用户确认后的项目侧改动（文件迁移/骨架生成/链接重建）、同步报告 |
| 排除 | 版本控制提交与推送（走 `vcs-router` / `vcs-git-commit`）、创建或重构技能（走 `yao-meta-skill`）、规则拆分合并（走 `tool-rule-consolidation`）、C# 代码审查（走 `csharp-code-review`）、首次初始化（走 `core-init`） |
| 前提 | 目标目录为 git 仓库且配置了 origin；`.codebuddy/project.index.json` 可读 |

## 与相邻技能的分工

| 技能 | 管什么 | 边界 |
|------|--------|------|
| `core-init` | **首次**接入：生成全部项目侧骨架、装包 | 本项目已初始化 |
| **本技能** | **增量**同步：引擎版本变化后落实项目侧影响 | 承接 `core-init` 之后的持续维护 |
| `update_repo.py` | 纯 git 更新 + 包链接重建 | 不做契约差异分析，不迁移项目侧文件 |
| `vcs-router` / `vcs-git-commit` | 提交与推送 | 本技能只改文件，不提交 |

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/impact-model.md` | 影响模型：哪些引擎变更会触及项目侧、三档严重度的判定标准、各变更类型的标准动作 |
| `references/sync-playbook.md` | 落实手册：按变更类型给出的执行步骤、验证方法与回滚边界 |
| `scripts/analyze_impact.py` | 影响分析：对比两版本的索引与包注册表，交叉项目侧磁盘现状输出清单 |

接口契约定义在 `agents/interface.yaml`。

---

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 工作流程
- 三档严重度与处理原则
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 3 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 4 |
| `agents/` | 接口契约与子代理定义 | 1 |
