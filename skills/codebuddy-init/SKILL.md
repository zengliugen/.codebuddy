---
name: codebuddy-init
description: 项目配置初始化技能。当新项目拉取（或以 submodule 接入）本 .codebuddy 引擎后，需要创建项目侧配置目录 .codebuddy.project 时触发；用户说"初始化配置"、"接入 codebuddy"、"生成项目配置"、"配置骨架"、"新项目接入"时调用。依据引擎侧配置注册表 .codebuddy/project.index.json 生成全部占位骨架（configs/）、运行时产物目录（caches/）与持久化结果骨架（store/）、项目侧 .gitignore/清理入口、项目专有技能目录骨架与根级软链接外置（settings.json），并建立软链接使其生效，最后询问是否立即按项目情况填写。不含任何项目专有值。
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

本技能负责**新项目接入的第一步**：依据注册表在项目侧生成配置骨架，使各技能首次运行时能定位到配置文件。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | 依据 `.codebuddy/project.index.json` 在项目根生成 `.codebuddy.project/` 下的配置骨架（`configs/`）、运行时产物空目录（`caches/`）、持久化结果骨架（`store/`）、`.gitignore`、清理入口，以及 `.codebuddy.project/skills/` 骨架与根级软链接外置文件（`settings.json`），并**建立软链接** |
| 输出 | 项目侧配置目录（`configs/` 占位骨架 + `caches/` 产物空目录 + `store/` 骨架 + `.gitignore` + `cleanup-caches.cmd`）+ 项目专有技能目录骨架 `.codebuddy.project/skills/` + 根级源文件骨架 `.codebuddy.project/configs/settings.json` + **软链接**（`.codebuddy/skills/project-skills`、`.codebuddy/settings.json`）+ 创建清单；随后询问是否立即填写 |
| 排除 | 填写具体项目值（仅在用户确认"立即填写"后作为后续动作进行）；修改引擎侧文件；覆盖已填写内容 |
| 安全保证 | **幂等**：已存在文件默认跳过不覆盖；索引缺失/损坏即报错退出，不猜测 |

## 与引擎和项目侧的边界

| 位置 | 归属 | 由谁维护 |
|------|------|---------|
| `.codebuddy/` | 引擎（可迁移、可 submodule 共享） | 引擎维护者；本技能**只读** |
| `.codebuddy/project.index.json` | 引擎侧配置注册表（入库共享，含路径与骨架） | 引擎维护者；本技能**只读** |
| `.codebuddy.project/` | 项目侧配置（随项目独立） | 本项目；本技能**据此生成** |
| `.codebuddy/models.json` 等 | 机器级/本机级（不入库） | 本机；本技能**不涉及** |

## 工作流程

### 阶段一：定位与索引校验

1. 自当前目录向上查找含 `.codebuddy` 子目录的目录，得项目根（`.codebuddy` 的父目录）。
2. 读取 `.codebuddy/project.index.json`。**索引缺失、JSON 损坏或缺少必需键（`project_config_root`、`files`）时报错退出（退出码 3）**，并提示"索引由引擎随包提供，请确认引擎包完整"。

### 阶段二：生成占位骨架与产物目录

运行脚本（脚本依据索引遍历 `files`、`rule_shells`、`artifacts.dirs` 与 `root_symlinks.entries` 生成，**技能自身零项目值**）：

```bash
python .codebuddy/skills/codebuddy-init/scripts/init_project_config.py
```

- `files` 中 `format: json` 项 → 写入 `template`（占位值原样落盘，UTF-8 无 BOM、2 空格缩进）。
- `files` 中 `format: markdown` 项 → 按 `template_outline` 生成章节骨架，每节留 `<填写说明>`。
- `rule_shells` 项 → 生成规则项目事实正文骨架（Markdown 章节占位）。
- **`artifacts.dirs` 项 → 创建运行时产物空目录**（`caches/` 下的各技能 `check_logs/`、`.cache/`、`.vcs-lock/` 等），供脚本落盘。
- 额外生成固定文件/骨架：
  - `.codebuddy.project/README.md`（目录用途与维护约定）；
  - `.codebuddy.project/.gitignore`（**整体忽略 `caches/` 运行时产物根目录**，不入库）；
  - `.codebuddy.project/store/`（持久化项目结果目录骨架：`README.md` + `.gitkeep`，**入库**）；
  - `.codebuddy.project/cleanup-caches.cmd`（清理入口，薄入口调用引擎侧
    `.codebuddy/scripts/cleanup_artifacts.py`）；
  - `.codebuddy.project/skills/`（**项目专有技能目录**：`README.md` + `.gitkeep`），
    并**建立软链接** `.codebuddy/skills/project-skills` → `../../.codebuddy.project/skills`，
    使项目专有技能被 CodeBuddy 自动加载（失败则告警并给出手工命令，不阻断）。
  - **`root_symlinks.entries` 项** → 生成项目侧源文件骨架（如 `.codebuddy.project/configs/settings.json`）并
    **建立软链接**（如 `.codebuddy/settings.json` → `../.codebuddy.project/configs/settings.json`），使 CodeBuddy
    经软链接读取外置的根级文件（失败则告警并给出手工命令，不阻断）。
- **幂等保护**：目标文件/目录已存在时**跳过不覆盖**（列出"已存在，跳过"）；确需覆盖文件时用 `--force`（须先确认用户知晓将丢失已有内容）。

> **产物目录清单由索引驱动**：新增技能产物目录时，在索引 `artifacts.dirs` 登记（逻辑名 → 项目侧镜像路径），
> 初始化脚本与各技能脚本即自动适配，无需改脚本。

### 阶段三：报告与询问

1. 输出创建清单（路径 + 类型 + 是否跳过）。
2. 经 `AskUserQuestion` 询问：**是否需要现在就按项目情况填写全部外置配置？**
   - **立即填写** → 进入阶段四。
   - **稍后填写** → 结束流程，并提示：未填写的配置在首次运行对应技能时会报错（配置缺失即报错，不静默使用默认值）。

### 阶段四：按项目情况填写（仅在用户选择"立即填写"时）

逐项读取该配置所属技能的 `references/config-guide.md`，并结合项目实际探测（解决方案/工程文件、`Assets/` 与 `Packages/` 目录结构、程序集清单、`manifest.json`、`.editorconfig` 等）填充占位值：

1. **每项填写前须实际读取项目，不得凭经验假设**；探测不到的值明确向用户询问，不猜测。
2. 填写后**向用户复述改动**（键 → 值）供确认；确认无误再写入。
3. 涉及口径一致性的配置（如多处的排除目录清单）必须同步，避免漂移。
4. 全部填写完成后，建议运行对应技能做一次冒烟验证（如格式检查 `--help`、覆盖率静态分析小目标）。

## 配置注册表约定（摘要）

详见 `references/index-spec.md`。要点：

- 路径基准为**项目根**（`.codebuddy` 的父目录），索引内全部为**相对路径**（拒绝绝对路径）。
- `files` 键为**逻辑名**（跨项目稳定的契约）；`path` 为项目侧镜像路径；`format` 为 `json` / `markdown`。
- `rule_shells` 键为薄壳相对 `.codebuddy` 的路径；值为项目事实正文路径与章节大纲。
- 索引**入库共享**：内容必须是纯约定 + 相对路径 + 占位值，对所有消费项目一致。

## 检查清单

- [ ] 是否先定位项目根并校验索引（缺失即报错退出 3）？
- [ ] 生成是否经过脚本（而非手工臆造字段）？
- [ ] 是否依据索引 `artifacts.dirs` 创建了 `caches/` 运行时产物空目录，并生成了 `.gitignore`、`cleanup-caches.cmd` 与 `store/` 骨架？
- [ ] 是否生成了 `.codebuddy.project/skills/` 骨架并**建立了软链接** `.codebuddy/skills/project-skills`（失败时是否已告警并给出命令）？
- [ ] 是否依据索引 `root_symlinks.entries` 生成了根级源文件骨架（如 `.codebuddy.project/configs/settings.json`）并**建立了软链接**（失败时是否已告警并给出命令）？
- [ ] 已存在文件是否跳过未覆盖（未获确认不使用 `--force`）？
- [ ] 是否输出了创建清单？
- [ ] 是否经 `AskUserQuestion` 询问是否立即填写？
- [ ] 「立即填写」时，是否逐项**实际探测项目**而非套用经验值，并向用户复述确认？
- [ ] 是否提示了"未填写配置首次运行会报错"？

## 参考文献

| 文件 | 内容 |
|------|------|
| `references/index-spec.md` | 配置注册表 schema、逻辑名与镜像路径约定、骨架生成规则 |
| `references/fill-guide.md` | 各类配置的填写指导入口（指向各技能 `references/config-guide.md`） |
| `scripts/init_project_config.py` | 骨架生成脚本（索引驱动、幂等） |
| `agents/interface.yaml` | 输入/输出/排除契约 |
