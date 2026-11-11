# 配置注册表约定（project.index.json）

<!-- pack-ref-ok: csharp, csharp-format-checker, csharp-code-review, csharp-test-coverage, csharp-comment-checker, git-commit —— 索引条目按「已安装包集合」过滤消费，未安装包的条目既不生成也不判缺失。 -->

<!-- pack-ref-ok: csharp, csharp-format-checker, csharp-code-review, csharp-test-coverage, csharp-comment-checker, git-commit
 本文件列举的索引条目来自各可选包；消费者（core-init、各脚本）按「已安装包集合」过滤：
 未安装的包对应条目既不生成也不判定缺失，故不构成硬依赖。 -->

本文件说明 `.codebuddy/project.index.json`（引擎侧配置注册表）的结构与约定，供 `core-init` 技能与引擎维护者参照。

## 1. 作用

`.codebuddy` 引擎不绑定具体项目；项目相关配置全部外置到项目根下的 `.codebuddy.project/`。注册表是**引擎与项目侧之间的唯一索引**，承担两件事：

1. **定位**：各技能脚本经逻辑名查到项目侧配置的实际路径，读取时使用。
2. **初始化**：`core-init` 依据注册表内的骨架，在项目侧生成占位配置。

注册表**入库共享**（随引擎版本控制），因此其内容必须是**纯约定 + 相对路径 + 占位值**——对所有消费项目完全一致，不含任何项目专有值。

## 2. 结构

```json
{
  "version": 1,
  "_comment": "…",
  "project_config_root": ".codebuddy.project",
  "artifacts": {
    "dirs": { "<逻辑名>": ".codebuddy.project/caches/skills/<pack>/<技能>/check_logs" }
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
      "path": ".codebuddy.project/configs/skills/<pack>/<技能>/<配置文件名>",
      "format": "json",
      "template": { "<字段>": "<占位值>" }
    }
  },
  "rule_shells": {
    "rules/<pack>/<规则名>/RULE.mdc": {
      "path": ".codebuddy.project/configs/rules/<pack>/<规则名>/RULE.mdc",
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
| `git_commit.config` | git-commit 项目配置 | 提交类技能共用的摘要校验脚本（`--config-key git_commit.config`） |
| `git_commit.project_config` | git-commit 流程级配置 | LLM（SKILL.md 引用） |
| `svn_commit.config` | svn-commit 项目配置（与 `git_commit.config` 独立） | 提交类技能共用的摘要校验脚本（`--config-key svn_commit.config`） |
| `svn_commit.project_config` | svn-commit 流程级配置 | LLM（SKILL.md 引用） |
| `coverage.project_config` | csharp-test-coverage 项目相关配置 | `skill_config.py`、C# 工具 |
| `comment.project_config` | csharp-comment-checker 项目相关配置 | C# 工具 |
| `coverage.golden_samples` / `coverage.trigger_cases` / `format_checker.trigger_cases` | 自测数据（项目专属） | 各技能 eval 脚本 |

### 3.3 镜像路径（`path` 的取值）

- 项目侧路径与引擎侧对应位置**相对路径镜像**，且**按包分层**，便于人工对照与按包整体增删：
  - `.codebuddy/lib/<pack>/skills/X/a.json` → `.codebuddy.project/configs/skills/<pack>/X/a.json`
  - `.codebuddy/lib/<pack>/rules/X/a.mdc` → `.codebuddy.project/configs/rules/<pack>/X/a.mdc`
  - 产物目录 → `.codebuddy.project/caches/skills/<pack>/<技能>/check_logs`
- **包名是路径中的固定层级**（紧跟 `skills/`、`rules/`、`agents/` 之后）。初始化脚本据此判断
  条目归属哪个包，**未安装的包不生成配置与产物目录**。
- 无包归属的通用路径（如根级锁目录 `.codebuddy.project/caches/.vcs-lock`）**不加包层**，
  初始化时不做包过滤。- **文档目录**（技能产出的项目文档，如 devflow 的能力文档）同样按包分层：
  `.codebuddy.project/docs/<pack>/`。它**不是** `configs`/`caches` 的下级，而是与二者同级的独立类别；
  路径中不含 `skills`/`rules`/`agents` 段，因此 `pack_of_path()` 返回空串、**不参与包过滤**——
  详见 §3.6.2。
- 引擎侧通用配置（不随项目变化的部分）**不进入注册表**，留在 `.codebuddy` 内。

### 3.4 骨架语义（`template` / `template_outline`）

`template`（JSON）与 `template_outline`（Markdown）是 **`core-init` 为新项目生成初始骨架的模板**，
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
- **路径含包层**：`caches/skills/<pack>/<技能>/`。`core-init` 只创建**已装包**的产物目录；
  未安装包的缓存目录不会出现。
- `core-init` 依据本节点创建产物空目录；项目侧 `.gitignore` 统一忽略、不入库。
- **入库边界由 `.codebuddy.project/.gitignore` 精确划定**：忽略 `caches/`、各组件目录下的 `<pack>` 桥接链接
  与通用临时产物，
  并显式反选 `configs/`（`!configs/` + `!configs/**`）与 `docs/`（`!docs/` + `!docs/**`）。
  两类方向不同，不要混为一谈：
  - **反选（`!`）**：仓库根常有泛化的 `configs/`、`docs/` 规则（Python 运行时配置、站点构建产物等），
    会连带忽略项目侧的入库内容，故必须反选恢复，否则配置与文档**静默不入库**。
  - **主动忽略**：`<pack>` 是派生出来的目录链接（源在 `lib/<pack>/<类型>`），本就不该入库。
    详见 §3.7。
- 清理：引擎侧 `scripts/cleanup_artifacts.py` 遍历本节点枚举目录，删除文件并重建空目录。

### 3.6.1 卸载包后的残留（孤儿）处理

包的安装状态记录在项目侧 `configs/packs.json` 的 `installed`。当某包被卸载（从 `installed` 移除）后，
其项目侧配置与缓存目录会残留，`core-init` 按以下方式处理：

| 阶段 | 行为 |
|------|------|
| `--status` | 检测并列出孤儿项（不属于任何已装包的配置/产物目录），归入候选动作 `prune_orphans`，**不删除** |
| `--prune-orphans` | 由用户确认后执行：删除孤儿配置**文件**与**空**产物目录；非空目录不删（避免误删用户内容），并上溯清理因此变空的上级目录 |

判定依据是路径中的包层（见 §3.3）：包名不在「默认包 ∪ 已装可选包」内即视为孤儿。

**不含包层的路径不在检测范围内**：`.codebuddy.project/docs/<pack>/` 路径中没有 `skills`/`rules`/`agents`
段，`pack_of_path()` 返回空串，因此**卸载包后其文档目录不会被列为孤儿、也不会被 `--prune-orphans` 删除**
（见 §3.6.2）。这类残留须手工清理。

### 3.6.2 文档目录（`.codebuddy.project/docs/`）

技能产出的**项目文档**（如 devflow 的能力设计/计划/测试文档）放 `.codebuddy.project/docs/<pack>/`，
与 `configs/`、`caches/`、`store/` 同级。它**不是运行时产物**（入库、不随清理工具删除），
也**不是配置**（不参与索引 `files` 的骨架生成），故单列一类。

- **位置由各技能的项目配置声明**（如 devflow 的 `files["devflow.docs.config"].template.docs_root`），
  索引只提供骨架值；脚本不内置默认值，读的时候仍旧「配置缺失即报错」。
- **不入 `artifacts.dirs`**：那是运行时产物清单，会被 `cleanup_artifacts.py` 删除；文档必须留下。
- **入库**：`.codebuddy.project/.gitignore` 不忽略 `docs/`。但仓库根若有泛化的 `docs/` 规则
  会把这里一并忽略，故该 `.gitignore` 也显式反选（同 `configs/` 的处理）。
- **不受包过滤与孤儿检测管辖**：路径中不含 `skills`/`rules`/`agents` 段，`pack_of_path()` 返回空串，
  按 §3.3 的规则视为「无包归属」——**未安装的包不会少生成它，卸载包也不会清掉它**。
  卸载包后须**手工删除** `docs/<pack>/`，`--prune-orphans` **不会**碰这些目录。

**引擎自身的文档不走这里**：维护引擎本身时产生的过程文档落在引擎仓库内的 `.codebuddy/dev-docs/`
（随引擎入库），由 `devflow-guard` 技能以 `--scope engine` 管理。理由：它是引擎事实，
放进项目侧会随引擎迁移被带到别的项目，而它的读者是引擎维护者而非装载该引擎的项目。

### 3.7 项目专有包（project，软链接）

项目专有内容放**项目侧** `.codebuddy.project/<类型>/project/` 下（`rules/`、`skills/`、`agents/` 三类，
与各可选包同级并列），经**目录软链接** `.codebuddy/<类型>/project → ../../.codebuddy.project/<类型>/project`
被 CodeBuddy 自动加载——**不进入索引**（它是项目内容而非引擎约定；引擎只需知道"扫描根支持符号链接"这一事实，
见引擎 README 与 `.codebuddy.project/skills/README.md`）。

`core-init --setup` 生成其骨架（三个 `.gitkeep`），并调用 `scripts/pack_install.py verify --repair`
建立桥接（Windows `mklink /D`，类 Unix `os.symlink`；失败则告警并给出手工命令，不阻断）。
`project` 包在 `lib/packs.json` 中声明为 `location=project`、`default=true`、`comps` 为空数组。

**入库边界：`project/` 入库，`<pack>/` 链接不入库**。`.codebuddy.project/<类型>/` 下两类内容同级并列，
但只有真实目录 `project/` 随项目版本控制；`<pack>` 是派生链接（源在引擎 `lib/<pack>/<类型>`），
由 `.codebuddy.project/.gitignore` **逐条列举**全部可选包的链接路径忽略（如 `skills/<pack>`、
`rules/<pack>`、`agents/<pack>` 各一行），而非整目录通配 + 反选。

**为何不用通配 + 反选**：通配会把整个类型目录纳入规则，放行 `project/` 时无论带不带 `**`，
都无法让 `project/` 内部的临时产物（`__pycache__/`、`.cache/` 等）继续受根规则约束。逐条列举只命中
确定的包目录，`project/` 根本不在规则里；其下组件的**专属**产物（`dist/`、`tools/<二进制>`、
`reports/*<专项>.md` 等）由该组件根目录的 `.gitignore` 处理。

`project/` 下组件的**通用**产物（`__pycache__/`、`*.pyc`、`.DS_Store` 等）不要求组件重复声明——
它们与具体组件无关，由 `.codebuddy.project/.gitignore` 统一兜底。该文件是项目仓库内唯一对
`.codebuddy.project/` 生效的规则文件；项目根 `.gitignore` 是宿主工程的标准模板，不承载引擎关注点。
`check_manifest.py` 校验项 16 分别核对引擎根与项目侧组件根两处兜底，**互不替代**——引擎侧有规则
不代表项目侧也有。

**清单须按 `lib/packs.json` 的全部 `location=lib` 包一次列全，与安装状态无关**：忽略规则幂等，
多列未装的包无副作用（目录本不存在），少列已装的包却会让链接在下次 `git add -A` 时悄然入库。
故装包、卸包都无需改 `.gitignore`，只有引擎新增可选包时才须重跑 `core-init` 补上。

不入库的两条独立理由（任一成立即足够）：

1. **派生结果不作事实来源**：`<pack>` 的集合与目标由 `lib/packs.json`（`location`）与
   `configs/packs.json`（`installed`）共同决定，建链由 `pack_install.py` 完成。入库等于把派生结果
   当第三处事实来源——装/卸包时链接增删会持续污染 git 差异，与 `packs.json` 脱节时也无人察觉。
   这与 `root_symlinks` 不登记桥接链接是同一判据（见 §3.8）。
2. **跨机器无效**：Windows 默认 `core.symlinks=false`，克隆后链接落成内容为路径字符串的普通文件
   （git 以 `120000` 记录），PyAppify 复制项目时 `entry.file_type()` 不跟随链接，目录链接既不满足
   `is_dir()` 也读不了内容，Windows 上以文件方式打开即报 `os error 5`；仍须跑 `core-init` 重建。
   入库换不来「克隆即可用」，只增加噪音。

### 3.8 根级软链接外置（root_symlinks.entries）

引擎根下的**项目级单文件**（如 `settings.json`）以软链接外置，引擎内仅留链接、源文件在项目侧：

- `link`：引擎内的链接路径（相对项目根，如 `.codebuddy/settings.json`）；
- `path`：项目侧源文件路径（相对项目根，如 `.codebuddy.project/configs/settings.json`）；
- `format` / `template`：同 `files`，供 `core-init` 生成源文件骨架。

依据：实测 CodeBuddy 会**解引用符号链接**读取（如 `settings.json` 改源文件即生效）。链接记 `120000`（相对路径，
跨机器有效），源文件记普通文件；两者均入库。`core-init` 生成源文件骨架并建链（失败告警给手工命令）。
**不外置**绑定本机的文件（`models.json`、`settings.local.json`）——外置反而跨机器失效且不宜入库。

**收录条件（三条同时满足才可登记）**：① 链接目标是单个文件；② `path` 是**项目侧**真实源文件；
③ 需要 `core-init` 为其生成骨架。缺任一条都不属于本节点。

**可选包 / 项目专有包的桥接链接不登记**：它们是**目录**链接，源在引擎 `lib/<包>/<类型>` 下、内容已存在、
无需生成骨架，三条全不满足。其完整信息由 `lib/packs.json`（`location` 与 `comps`）与项目侧
`configs/packs.json`（`installed`）两处共同确定，路径由 `scripts/pack_install.py` 确定性推导：

```
.codebuddy.project/<类型>/<包>  →  lib/<包>/<类型>          （项目侧落点）
.codebuddy/<类型>/<包>          →  .codebuddy.project/<类型>/<包>   （引擎扫描根桥接）
```

创建、漂移检测与修复全部走该脚本（`verify` / `verify --repair`），`core-init --status` 亦已覆盖。
**不要为图省事把它们塞进 `root_symlinks`**：`core-init` 会把 `path` 当源文件渲染骨架并写入，
即向引擎包目录 `.codebuddy/lib/<包>/<类型>` 写一个 json/markdown 文件，直接破坏引擎内容；
同时会在 `installed` 变更时形成第三份事实来源，与索引脱节。

### 3.9 缺失行为

- 注册表缺失 / JSON 损坏 / 缺少 `project_config_root` 或 `files` → **读取方报错退出（退出码 3）**。
- 注册表指向的项目侧文件缺失 → 亦报错退出，并提示"运行 core-init 生成"。
- **不回退内置默认值**（沿用引擎全局约定：配置是唯一事实来源）。

## 4. 引擎维护者增改流程

新增一个需项目配置的技能配置时：

1. 在 `.codebuddy.project/` 的镜像路径下定义其**项目侧字段**（仅项目相关项）。
2. 在 `project.index.json` 的 `files` 中登记：逻辑名、`path`、`format`、`template`（占位值，不含项目专有值）。
3. 改造该技能脚本：内联 `resolve_index_path()`（向上找 `.codebuddy` → 读注册表 → 按逻辑名取路径 → 校验相对路径）。
4. 若为分层配置，同时在引擎侧保留通用部分并实现合并。
5. 验证：`python .codebuddy/skills/core/core-init/scripts/init_project_config.py`（在临时目录）能生成正确骨架。
