---
name: codebuddy-init
description: 项目配置初始化与可选包管理技能。当新项目拉取（或以 submodule 接入）本 .codebuddy 引擎后需要接入配置，或需要查看/追加安装/移除引擎可选包时触发；用户说"初始化配置"、"接入 codebuddy"、"生成项目配置"、"配置骨架"、"新项目接入"、"装了哪些包"、"装个 XX 包"、"卸载 XX 包"时调用。运行先做只读状态检测（--status：是否已初始化、缺失配置与产物目录、已装/未装可选包、链接是否漂移），再据现状用 AskUserQuestion 询问意图，可选动作包括生成配置骨架（依据 .codebuddy/project.index.json 生成 configs/ 占位骨架、caches/ 产物目录、store/ 骨架、.gitignore、清理入口、项目专有包目录与 settings.json 软链接）、按项目情况填写配置、列出已安装包、追加安装包、移除包、修复链接漂移。不含任何项目专有值。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，是 `.codebuddy` 引擎接入新项目的**唯一入口**，需通过触发评估与输出风险检查。

## 定位
`.codebuddy` 是**可任意迁移的纯工作流引擎**：技能、规则薄壳、Agent 等引擎内容不绑定任何具体项目；与项目绑定的配置全部外置到项目根下的 `.codebuddy.project/`，由引擎侧的配置注册表 `.codebuddy/project.index.json` 索引。

本技能是引擎接入与包管理的**统一入口**：先只读检测现状（是否已初始化、缺什么、装了哪些包、链接是否漂移），再按现状询问用户意图；可生成配置骨架、填写配置，也可列出已装包、追加安装、移除包、修复链接漂移。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | ① **状态检测**（只读，`--status`）；② 依据 `.codebuddy/project.index.json` 在项目根生成 `.codebuddy.project/` 下的配置骨架（`configs/`）、运行时产物空目录（`caches/`）、持久化结果骨架（`store/`）、`.gitignore`、清理入口，以及 `.codebuddy.project/skills/` 骨架与根级软链接外置文件（`settings.json`），并**建立软链接**；③ **可选包管理**：列出已装包、追加安装、移除、修复链接漂移 |
| 输出 | 状态检测结论与候选动作清单；项目侧配置目录（`configs/` 占位骨架 + `caches/` 产物空目录 + `store/` 骨架 + `.gitignore` + `cleanup-caches.cmd`）+ 项目专有技能目录骨架 `.codebuddy.project/skills/` + 根级源文件骨架 `.codebuddy.project/configs/settings.json` + **软链接**（`.codebuddy/settings.json` 与各 pack 桥接）+ 创建清单；包安装/卸载/修复的执行结果 |
| 排除 | 修改引擎侧文件；覆盖已填写内容；替用户决定装哪些包；卸载默认包（`core`/`vcs`/`tool`/`project`，安装器本身拒绝） |
| 安全保证 | **幂等**：已存在文件默认跳过不覆盖；索引缺失/损坏即报错退出，不猜测；**检测只读**；包管理一律经引擎侧安装器 |

## 配置注册表约定（摘要）
详见 `references/index-spec.md`。要点：

- 路径基准为**项目根**（`.codebuddy` 的父目录），索引内全部为**相对路径**（拒绝绝对路径）。
- `files` 键为**逻辑名**（跨项目稳定的契约）；`path` 为项目侧镜像路径；`format` 为 `json` / `markdown`。
- `rule_shells` 键为薄壳相对 `.codebuddy` 的路径；值为项目事实正文路径与章节大纲。
- 索引**入库共享**：内容必须是纯约定 + 相对路径 + 占位值，对所有消费项目一致。

## 参考文献
| 文件 | 内容 |
|------|------|
| `references/index-spec.md` | 配置注册表 schema、逻辑名与镜像路径约定、骨架生成规则 |
| `references/fill-guide.md` | 各类配置的填写指导入口（指向各技能 `references/config-guide.md`） |
| `scripts/init_project_config.py` | 骨架生成（索引驱动、幂等）与 `--status` 只读状态检测 |
| `.codebuddy/scripts/pack_install.py` | 引擎侧包安装器：`list` / `install` / `remove` / `status` / `verify --repair` |
| `agents/interface.yaml` | 输入/输出/排除契约 |

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 与引擎和项目侧的边界
- 工作流程
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 4 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 3 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 1 |
| `agents/` | 接口契约与子代理定义 | 1 |
