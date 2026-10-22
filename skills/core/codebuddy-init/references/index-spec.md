# 配置注册表约定（project.index.json）

本文件说明 `.codebuddy/project.index.json`（引擎侧配置注册表）的结构与约定，供 `codebuddy-init` 技能与引擎维护者参照。

## 1. 作用

`.codebuddy` 引擎不绑定具体项目；项目相关配置全部外置到项目根下的 `.codebuddy.project/`。注册表是**引擎与项目侧之间的唯一索引**，承担两件事：

1. **定位**：各技能脚本经逻辑名查到项目侧配置的实际路径，读取时使用。
2. **初始化**：`codebuddy-init` 依据注册表内的骨架，在项目侧生成占位配置。

注册表**入库共享**（随引擎版本控制），因此其内容必须是**纯约定 + 相对路径 + 占位值**——对所有消费项目完全一致，不含任何项目专有值。

## 2. 结构

```json
{
  "version": 1,
  "_comment": "…",
  "project_config_root": ".codebuddy.project",
  "artifacts": {
    "dirs": { "<逻辑名>": ".codebuddy.project/caches/skills/<技能>/check_logs" }
  },
  "root_symlinks": {
    "entries": {
      "<逻辑名>": {
        "link": ".codebuddy/settings.json",
        "path": ".codebuddy.project/configs/settings.json",
        "format": "json",
        "template": { "<字段>": "<占位值>" }
      }
    }
  },
  "files": {
    "<逻辑名>": {
      "path": ".codebuddy.project/configs/skills/<技能>/<配置文件名>",
      "format": "json",
      "template": { "<字段>": "<占位值>" }
    }
  },
  "rule_shells": {
    "rules/<规则名>/RULE.mdc": {
      "path": ".codebuddy.project/configs/rules/<规则名>/RULE.mdc",
      "format": "markdown",
      "template_outline": ["# 标题", "## 章节"]
    }
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `version` | 是 | 注册表结构版本 |
| `_comment` | 否 | 说明本文件用途、路径基准与缺失行为 |
| `project_config_root` | 是 | 项目侧配置根（相对项目根），如 `.codebuddy.project` |
| `files` | 是（非空） | 配置类文件：脚本读取的目标 + 初始化骨架来源 |
| `files.<逻辑名>.path` | 是 | 项目侧镜像路径（相对项目根，**禁止绝对路径**） |
| `files.<逻辑名>.format` | 是 | `json` 或 `markdown` |
| `files.<逻辑名>.template` | json 必填 | JSON 骨架（占位值） |
| `files.<逻辑名>.template_outline` | markdown 必填 | Markdown 章节大纲 |
| `rule_shells` | 否 | 规则薄壳的项目事实正文：键为薄壳相对 `.codebuddy` 的路径 |
| `artifacts.dirs` | 否 | 运行时产物目录：逻辑名 → 项目侧镜像路径；供脚本落盘与清理工具枚举，不入库 |
| `root_symlinks.entries` | 否 | 引擎根下需软链接外置的单个文件：`link`（引擎内链接路径）+ `path`（项目侧源文件路径）+ `format` + `template` |
| `rule_shells.<键>.path` | 是 | 项目事实正文路径（相对项目根） |
| `rule_shells.<键>.format` / `template_outline` | 是 | 同 `files` |

## 3. 约定

### 3.1 路径基准与相对性

- 全部路径基准为**项目根**（即 `.codebuddy` 的父目录）。
- **禁止绝对路径**：绝对路径会让注册表在跨项目共享时失效（A 项目的路径泄漏到 B 项目）。各技能脚本读取时**拒绝绝对路径并报错**，作为防污染兜底。

### 3.2 逻辑名（`files` 的键）

- 逻辑名是**跨项目稳定的契约**，脚本按逻辑名取值（而非硬编码路径）。
- 命名约定：`<技能简称>.<用途>`，如 `format_checker.config`、`coverage.project_config`。
- 现有逻辑名一览（引擎维护者新增配置项时沿用）：

| 逻辑名 | 目标配置 | 读取方 |
|--------|---------|--------|
| `format_checker.config` | csharp-format-checker 项目配置 | `dotnet_format.py`、`check_eol.py` |
| `code_review.config` | csharp-code-review 项目配置 | `collect_review_targets.py` |
| `git_commit.config` | git-commit 项目配置 | `validate_commit_subject.py` |
| `git_commit.project_config` | git-commit 流程级配置 | LLM（SKILL.md 引用） |
| `coverage.project_config` | csharp-test-coverage 项目相关配置 | `skill_config.py`、C# 工具 |
| `comment.project_config` | csharp-comment-checker 项目相关配置 | C# 工具 |
| `coverage.golden_samples` / `coverage.trigger_cases` / `format_checker.trigger_cases` | 自测数据（项目专属） | 各技能 eval 脚本 |

### 3.3 镜像路径（`path` 的取值）

- 项目侧路径与引擎侧对应位置**相对路径镜像**，便于人工对照：
  - `.codebuddy/skills/X/a.json` → `.codebuddy.project/configs/skills/X/a.json`
  - `.codebuddy/rules/X/a.mdc` → `.codebuddy.project/configs/rules/X/a.mdc`
- 引擎侧通用配置（不随项目变化的部分）**不进入注册表**，留在 `.codebuddy` 内。

### 3.4 骨架语义（`template` / `template_outline`）

`template`（JSON）与 `template_outline`（Markdown）是 **`codebuddy-init` 为新项目生成初始骨架的模板**，
**不是当前项目侧文件的内容镜像**：

- **JSON `template`**：须与项目侧实际文件的**键结构一致**（同键、同嵌套；值为占位或合理默认），
  否则生成的骨架会被读取方判为"缺字段"。
- **Markdown `template_outline`**：是**建议章节结构**，描述该文档"应涵盖哪些主题"，措辞与编号可不同于
  当前项目的实际章节——**不要求精确镜像**。但主题须是该文档的**应然内容**：
  - `rule_shells`（项目事实正文）应描述**项目事实主题**（目录结构、包依赖、存量现状等），
    **不得**误抄引擎薄壳的审查维度或规则章节（那是引擎侧内容，不属于项目事实）。
  - `files`（配置类 Markdown，如 `git_commit.project_config`）应描述该项目配置应有的**参数分节**。

> 判定标准：`template_outline` 面向"新项目将生成什么"，`path` 指向的文件是"本项目当前实际内容"。
> 两者主题应相符；措辞差异不算漂移，主题错配（如项目事实文档写成审查维度）才是缺陷。

### 3.5 分层配置的拆分原则

当一份配置**同时含通用部分与项目相关部分**时（如注释检查的 `rules` 通用、`exclude/knownTerms` 项目相关），按以下方式拆分：

- **通用部分**留在引擎侧（如 `tools/<工具>/xxx_config.json`），随引擎版本演进。
- **项目相关部分**外置为独立文件（如 `xxx_config.project.json`），登记到 `files`。
- 读取时**深度合并**两层（项目侧覆盖引擎侧；数组取并集），由读取方实现，项目侧无需感知引擎默认。

### 3.6 运行时产物目录（artifacts.dirs）

脚本执行过程中生成的产物（各技能 `check_logs/`、`.cache/`、根 `.vcs-lock/`）也外置到项目侧，
由索引 `artifacts.dirs` 声明：逻辑名（如 `format_checker.check_logs`）→ 项目侧镜像路径。

- 各脚本经**逻辑名**解析产物目录（内联 `resolve_artifact_dir()`），不再硬编码到技能目录。
- `codebuddy-init` 依据本节点创建产物空目录；项目侧 `.gitignore` 统一忽略、不入库。
- 清理：引擎侧 `scripts/cleanup_artifacts.py` 遍历本节点枚举目录，删除文件并重建空目录。

### 3.7 项目专有技能目录（软链接）

项目专有技能放**项目侧**的 `.codebuddy.project/skills/<技能名>/SKILL.md`，经**目录软链接**
`.codebuddy/skills/project-skills → ../../.codebuddy.project/skills` 被 CodeBuddy 自动加载——
**不进入索引**（它不是引擎约定，而是项目内容；引擎只需知道"`.codebuddy/skills/` 支持符号链接"这一事实，
见引擎 README 与 `.codebuddy.project/skills/README.md`）。

`codebuddy-init` 生成其骨架（`README.md` + `.gitkeep`）并**建立软链接**（Windows `mklink /D`，类 Unix
`os.symlink`；失败则告警并给出手工命令，不阻断）。技能本身由项目维护者按需创建。

### 3.8 根级软链接外置（root_symlinks.entries）

引擎根下的**项目级单文件**（如 `settings.json`）以软链接外置，引擎内仅留链接、源文件在项目侧：

- `link`：引擎内的链接路径（相对项目根，如 `.codebuddy/settings.json`）；
- `path`：项目侧源文件路径（相对项目根，如 `.codebuddy.project/configs/settings.json`）；
- `format` / `template`：同 `files`，供 `codebuddy-init` 生成源文件骨架。

依据：实测 CodeBuddy 会**解引用符号链接**读取（如 `settings.json` 改源文件即生效）。链接记 `120000`（相对路径，
跨机器有效），源文件记普通文件；两者均入库。`codebuddy-init` 生成源文件骨架并建链（失败告警给手工命令）。
**不外置**绑定本机的文件（`models.json`、`settings.local.json`）——外置反而跨机器失效且不宜入库。

### 3.9 缺失行为

- 注册表缺失 / JSON 损坏 / 缺少 `project_config_root` 或 `files` → **读取方报错退出（退出码 3）**。
- 注册表指向的项目侧文件缺失 → 亦报错退出，并提示"运行 codebuddy-init 生成"。
- **不回退内置默认值**（沿用引擎全局约定：配置是唯一事实来源）。

## 4. 引擎维护者增改流程

新增一个需项目配置的技能配置时：

1. 在 `.codebuddy.project/` 的镜像路径下定义其**项目侧字段**（仅项目相关项）。
2. 在 `project.index.json` 的 `files` 中登记：逻辑名、`path`、`format`、`template`（占位值，不含项目专有值）。
3. 改造该技能脚本：内联 `resolve_index_path()`（向上找 `.codebuddy` → 读注册表 → 按逻辑名取路径 → 校验相对路径）。
4. 若为分层配置，同时在引擎侧保留通用部分并实现合并。
5. 验证：`python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py`（在临时目录）能生成正确骨架。
