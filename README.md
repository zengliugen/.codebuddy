# .codebuddy —— CodeBuddy 共享工作流引擎

本仓库是**可跨项目共享的 CodeBuddy 工作流引擎**（技能 / 规则 / Agent / 配置注册表）。
它**不绑定任何具体项目**：与项目绑定的配置、产物、专有技能全部外置到**消费项目**根下，
由本仓库的 `project.index.json` 索引。

> **共享方式**：将本仓库作为 **git submodule** 纳入各项目，检出到项目的 `.codebuddy/` 路径。
> 多项目共享同一引擎、各自维护独立的项目侧内容；引擎升级只需 `git submodule update`。

## 第三方来源组件（vendor）

`lib/` 下部分包并非本项目原创，而是随引擎分发的上游组件。这类包分两档：
**只读 vendor**（保留原文 + 来源标记 + 不可改边界）与 **本地维护分支**（正文已中文化、允许本地改造）。
两档均**不调整目录布局**：

| 组件 | 来源 | 版本 | 维护档位 | 可否修改 |
|------|------|------|---------|---------|
| `lib/yao-meta-skill/` | 上游 yao-meta-skill（skill 工程化工具链） | 2.1.0 | 只读 vendor | 仅允许最小可行性补丁，须记录在 `references/cli-changelog.md` |
| `lib/unity-pipeline/` | `com.unity.pipeline` 0.9.0-exp.1 | 2.0 | **本地维护** | 允许本地改造：正文已中文化，补丁记录在 `references/cli-changelog.md` |
| `lib/grilling/` | 源出上游 grilling（方案拷问） | 2.0 | **本地维护** | 允许本地改造：正文、参考文档、评测与治理产物均归本仓库维护 |

**为什么 `yao-meta-skill` 不做中文转换**：它的触发评估与回归测试依赖原文措辞（`evals/semantic_config.json` 的
中英短语权重、`tests/` 快照），翻译会使工具链失效并导致上游 `git pull` 永久冲突。

**为什么不做目录布局调整**：`lib/<pack>/` 已是正式的 vendor 边界——`lib/packs.json` 据此推导路径，
`scripts/pack_install.py` 据此建桥接链接；再套一层 `vendor/` 会打断这两个脚本。

**语言规则豁免**：仅 `yao-meta-skill` 的正文文档保留上游原语言，不受 `rules/core/core-language/`
「人类可读文本一律中文」约束；但**本仓库新增的元数据**（`agents/interface.yaml`）与外层说明仍须中文。

**`unity-pipeline` 与 `grilling` 为本地维护分支**：两包正文（`SKILL.md`、规则、`references/`）均已中文化，
**受语言规则约束**。转向本地维护的共同原因：上游正文为英文，与本项目「人类可读文本一律中文」的底线直接冲突。
两者都不产出需与上游逐字比对的评测快照，语义忠实度可由本地评测（`evals/`）保障。
`reports/` 下为脚本生成产物，标题随生成脚本输出为英文，不计入正文语言范围——需要中文报告时
改生成器而非手改产物（手改会被下次生成覆盖）。

判据来源：`agents/interface.yaml` 的 `source.origin` 为 `local` 且 `editable` 为 `full` 即本地维护分支；
`origin` 为 `third-party` 则受上表「只读 vendor」约束。

## 目录结构

```
.codebuddy/                     # 本仓库根 = CodeBuddy 引擎内容
├── project.index.json          # 配置注册表：逻辑名 → 项目侧路径 + 骨架，规则薄壳映射
├── update.cmd                  # 仓库更新双击入口（薄入口，调用 scripts/update_repo.py）
├── setup.cmd / setup.sh        # 项目侧一键配置入口（薄入口，调用 init_project_config.py --setup）
├── README.md                   # 本文件：引擎结构与约定
├── .gitignore                  # 扫描根全忽略+默认包放行；另排除机器级配置与运行产物
├── .gitattributes              # 行尾与二进制/文本归属声明
│
├── lib/                        # 可选组件池：按包（pack）分层
│   ├── packs.json              #   包注册表（唯一事实源）：组件清单、依赖、默认标记
│   ├── csharp/                 #   包 csharp：rules/ skills/ agents/
│   ├── unity-pipeline/         #   包 unity-pipeline（本地维护：Unity 实例驱动）
│   ├── grilling/               #   包 grilling（本地维护：设计树逐轮诘问）
│   └── yao-meta-skill/         #   包 yao-meta-skill（rules/ skills/：技能工程强制入口）
│
├── rules/                      # 规则扫描根：默认包真实目录 + 可选包链接
│   ├── core/                   #   默认包（6 条）：core-language/ core-project-guide/
│   │                           #            core-tooling/（始终生效：命令形状 + 结果校验）
│   │                           #            core-engine/（.codebuddy/**：内容隔离 + 登记同步）
│   │                           #            core-rule-governance/（规则命名与分类元规则）
│   │                           #            core-init.entry/（初始化强制入口）
│   ├── vcs/                    #   默认包（4 条）：vcs-router/（+ vcs-router.entry/ 强制入口）
│   │                           #            vcs-engine-commit/（.codebuddy/**：引擎仓库提交）
│   │                           #            vcs-git-commit/ vcs-git-merge/（提交与合并执行）
│   ├── tool/                   #   默认包（5 条，均为 .entry/ 入口形态）：
│   │                           #            tool-cmd-script-writing/ tool-engine-sync/
│   │                           #            tool-export-zipped-dir/ tool-rule-consolidation/
│   │                           #            tool-session-lesson-distill/
│   ├── project ──链接──▶ 项目侧 #   项目专有规则（.codebuddy.project/rules/project/，gitignore）
│   └── <pack>                  #   可选包：链接 → 项目侧（gitignore）
│
├── skills/                     # 技能扫描根：默认包真实目录 + 可选包链接
│   ├── core/ core-init/
│   ├── vcs/                    #   vcs-router/ git-commit/ git-merge/
│   ├── tool/                   #   cmd-script-writing/ engine-sync/ export-zipped-dir/ rule-consolidation/ session-lesson-distill/
│   ├── project ──链接──▶ 项目侧 #   项目专有技能（.codebuddy.project/skills/project/，gitignore）
│   └── <pack>                  #   可选包：链接 → 项目侧（gitignore）
│
├── agents/                     # 子代理扫描根：本引擎默认无 agent
│   ├── project ──链接──▶ 项目侧 #   项目专有代理（.codebuddy.project/agents/project/，gitignore）
│   └── <pack>                  #   可选包：链接 → 项目侧（gitignore）
│
├── hooks/                      # git 钩子（入库，经 core.hooksPath 生效，setup 自动配置）
│   └── pre-commit             #   提交前跑 check_manifest.py，登记表不一致即阻断
│
├── dev-design-docs/            # 引擎包开发设计文档（仅 README.md 入库，其余本地保留）
│   ├── README.md               #   目录索引：用途、入库规则、按包登记文档
│   └── <pack>/                 #   各包的开发期文档（gitignore，不入库）
│
└── scripts/                    # 引擎级通用脚本（包安装、清单校验、产物清理、仓库更新）
    ├── pack_install.py         #   可选包安装/卸载/校验（list/install/remove/status/verify）
    ├── check_manifest.py       #   包注册表与磁盘结构一致性校验
    ├── cleanup_artifacts.py    #   运行时产物清理
    └── update_repo.py          #   仓库更新（含包链接重建）
```

> **检出即可用**：默认包 `core`、`vcs`、`tool` 的组件是引擎内的**真实目录**，克隆本仓库即有完整基础能力，
> 无需先跑 setup。可选包（`csharp`、`unity-pipeline`、`grilling`、`yao-meta-skill`）需显式安装。

> **检出位置约定**：本仓库应检出为消费项目的 **`.codebuddy/`**（如 `Program/Client/.codebuddy/`）。
> 引擎内所有相对路径推导均以「`.codebuddy` 的父目录 = 项目根」为基准，故检出路径名必须是 `.codebuddy`。

## 开发设计文档（dev-design-docs/）

引擎包在**开发期**产生的文档（实施计划、契约快照、调研结论等）放 `dev-design-docs/<包名>/`。

**入库规则：只有 `dev-design-docs/README.md` 入库**，其余全部由 `.gitignore` 忽略：

```gitignore
/dev-design-docs/*
!/dev-design-docs/README.md
```

| 要点 | 说明 |
|------|------|
| 为什么入库 README | 说明目录用途与规则，告诉后来者「文档为什么提交不上去」；**不登记具体文档清单**（那些文件不入库，列出来对其他人全是死链） |
| 为什么文档不入库 | 属开发过程产物；计划在实施后失去价值，契约快照随引擎频繁改写，入库会产生无意义 diff |
| 为什么不用 `lib/<pack>/docs/` | 该位置在包内，不提交会让**子模块指针长期显示 dirty**，干扰两仓状态判断 |
| 是否需要分发给项目 | 不需要——`scripts/pack_install.py` 只物化 `rules`/`skills`/`agents`，文档本就不会到消费项目 |
| 换机器后是否还在 | **不在**。需要长期保留的结论必须落到包内组件文档（`rules/`、`skills/references/`） |

**生命周期一律为「临时」**：本目录文档服务于包开发，**包开发完成后即失去价值**，随整个目录
一并归档或删除；文档头须标注并写明终止条件。**不设「长期维护」档**——内容都不入库，宣称长期保留
与实际不符；开发完成后仍需保留的结论，应移入包的组件文档（`rules/`、`skills/references/`）。

本目录文档**不随仓库分发、不随 clone 恢复**，`git clean -fdx` 会静默丢失；
重要的本地文档请自行备份。需跨机器共享的结论必须落到包内组件文档。详见
[`dev-design-docs/README.md`](dev-design-docs/README.md)。

## 引擎与项目侧的边界

| 位置 | 归属 | 说明 |
|------|------|------|
| 本仓库（检出为 `.codebuddy/`） | 引擎 | 纯通用内容；跨项目共享 |
| `.codebuddy/project.index.json` | 引擎 | 配置注册表；路径 + 骨架，**无项目专有值** |
| `.codebuddy/skills/**/tools/**/<工具>.json` | 引擎 | **分层配置的通用部分**（规则、算法参数等） |
| `.codebuddy.project/` | 项目 | 项目侧内容根：`configs/` 配置、`caches/` 运行时产物（不入库）、`store/` 持久化结果、`skills/` 项目专有技能（含 `settings.json` 源文件）；随项目独立维护 |
| `.codebuddy/settings.json` | 项目（链接） | **软链接** → `.codebuddy.project/configs/settings.json`（由项目侧创建，**不入本库**） |
| `.codebuddy.project/<类型>/project/` | 项目 | **项目专有包**内容（与其他包同构）：`rules/project/`、`skills/project/`、`agents/project/`，经 `.codebuddy/<类型>/project` 链接被加载，**不入本库** |
| `.codebuddy.project/skills/` | 项目 | 可选包在项目侧的组件链接（由 setup 创建） |
| `.codebuddy/models.json` / `settings.local.json` | 机器 | 机器级/本机级；不入库 |

### 项目侧 `settings.json` 不写 `teamMemory.userId`

项目侧 `settings.json`（源文件在 `.codebuddy.project/configs/settings.json`）**不写入**
`memory.teamMemory.userId`，该值由 CodeBuddy 本机自动推导：

| 顺序 | 来源 |
|------|------|
| 1 | 环境变量 `CODEBUDDY_TEAMMATE_OWNER_KEY` |
| 2 | `settings.json` 的 `memory.teamMemory.userId`（**新项目不生成此键**） |
| 3 | `git config user.name` |
| 4 | 系统登录名 |

原因（实测自 `dist/codebuddy.js` 的 `getTeamUserId()`）：`userId` 位于推导链第 2 位，**高于**
`git user.name`。写入项目共享文件后，所有使用者被统一为同一标识，团队记忆会写进同一个
`@<userId>/` 目录而串号。个人需要固定标识时写入 `.codebuddy/settings.local.json`
（本机项目级，自动 git 忽略）。

## 新项目接入（三步）

1. **引入引擎**：把本仓库作为 submodule 检出到项目根下的 `.codebuddy/`：
   ```bash
   git submodule add https://github.com/zengliugen/.codebuddy.git .codebuddy
   ```
   （或复制本仓库内容到项目根的 `.codebuddy/`。）
2. **生成项目侧配置并装包**：运行一键配置入口
   ```bash
   .codebuddy/setup.cmd                                   # Windows（双击亦可）
   ./.codebuddy/setup.sh                                  # macOS / Linux
   .codebuddy/setup.cmd --pack csharp,unity-pipeline       # 首次指定可选包
   ```
   依据 `project.index.json` 在项目根生成 `.codebuddy.project/` 的占位配置骨架、运行时产物空目录、
   `.gitignore` 与 `cleanup-caches.cmd` 清理入口；建立 `settings.json` 与各可选包的 pack 链接；
   并按 `.codebuddy.project/configs/packs.json` 物化组件；同时配置引擎的提交前校验钩子
   （`core.hooksPath` → 入库的 `hooks/` 目录）。
   （等价底层命令：`python .codebuddy/skills/core/core-init/scripts/init_project_config.py --setup`）

   > **克隆后必须运行 setup**。除生成配置骨架外，它还负责建立各类软链接与
   > `core.hooksPath`——这三类产物都存在 `.git/` 或磁盘上、**不随仓库分发**。
   > 不运行则表现为：`settings.json` 链接缺失（CodeBuddy 读不到配置）、可选包技能不加载、
   > 引擎提交时没有一致性校验。改动引擎内容后如怀疑钩子失效，
   > 可执行 `git -C .codebuddy config --get core.hooksPath` 确认（应为 `hooks`）。
3. **按项目填写**：按各技能 `references/config-guide.md` 填写占位值（`core-init` 会询问是否立即填写）。

> 未填写的配置在首次运行对应技能时会**明确报错**（配置缺失即报错，不静默使用默认值）。

## 配置注册表（project.index.json）

引擎与项目侧之间的**唯一索引**。各技能脚本经它按**逻辑名**定位项目侧配置；`core-init` 经它生成骨架。

- **路径基准**：项目根（`.codebuddy` 的父目录）；全部**相对路径**，**禁止绝对路径**。
- **按包分层**：项目侧路径含包层（`configs/skills/<pack>/<技能>/`、`configs/rules/<pack>/<规则>/`、
  `caches/skills/<pack>/<技能>/`），与 `lib/<pack>/` 一一对应。`core-init` 据此判定条目归属，
  **未安装的包不生成配置与产物目录**；包名相同则不加重复层（如 `unity-pipeline` 包下的同名技能）。
- **`files`**：配置类文件 → 逻辑名 + `path` + `format` + `template`（JSON 骨架 / Markdown 大纲）。
- **`rule_shells`**：规则薄壳 → 键为薄壳相对 `.codebuddy` 的路径，值为项目事实正文路径。
- **`artifacts.dirs`**：运行时产物目录（check_logs / .cache / .vcs-lock 等）→ 逻辑名 + 项目侧镜像路径；
  供脚本落盘与清理工具枚举，不入库。
- **`root_symlinks.entries`**：引擎根下需**软链接外置**的单个文件（如 `settings.json`）→ 链接路径 + 项目侧源文件路径 + 骨架；
  由 `core-init` 生成源文件并建链，CodeBuddy 本体经软链接直接读取。
- **入库共享**：内容须是**纯约定 + 相对路径 + 占位值**，对所有消费项目一致。

schema 与逻辑名约定详见 `skills/core-init/references/index-spec.md`。

## 项目侧软链接（**由项目侧创建，不入本库**）

软链接均为**项目侧绑定**，指向消费项目独有的目录：

```
<项目根>/.codebuddy/settings.json   ──软链接──▶  ../.codebuddy.project/configs/settings.json
<项目根>/.codebuddy/<类型>/<pack>   ──软链接──▶  ../../.codebuddy.project/<类型>/<pack>
<项目根>/.codebuddy.project/<类型>/<pack> ──软链接──▶  ../../../.codebuddy/lib/<pack>/<类型>
<项目根>/.codebuddy/<类型>/project  ──软链接──▶  ../../.codebuddy.project/project/<类型>
```

可选包的链接为**两级**：引擎扫描根 → 项目侧 pack 目录 → `lib/<pack>/`；
其中**项目侧 pack 目录本身即为链接**（整目录指向 `lib/<pack>/<类型>`），不逐组件建链。
`lib/packs.json` 的 `location=lib` 项即需建立链接的包清单。

**项目专有包**（`project`）只需一层：引擎扫描根 → `.codebuddy.project/<类型>/project`，
内容直接是项目真实文件，随项目入库。它在 `.codebuddy.project/<类型>/` 下与其他包**同级并列**，
区别仅在于它是真实目录（其他包是指向 `lib/` 的链接）。


- **为什么不入本库**：链接目标全在项目侧（`.codebuddy.project/`），是本项目独有的；
  若纳入共享库，其他项目 clone 后链接会**悬空**，并可能与同名路径**冲突污染**。
  故本库 `.gitignore` 对扫描根 `rules/`、`skills/`、`agents/` 采取**目录内全忽略 + 逐包放行**：
  默认包（`location=engine` 的 `core` / `vcs` / `tool`）显式 `!` 放行，其余同名条目（可选包与 `project` 的桥接链接）
  一律忽略；`agents/` 无默认包故整目录忽略。`/settings.json` 单独另列。
- **如何创建**：消费项目 clone 本引擎后，运行 `core-init` 自动创建（幂等；失败时告警并给出手工 `mklink` 命令）。
- **机制依据**：实测 CodeBuddy **会解引用符号链接**——技能目录的链接下技能被正常扫描，`settings.json`
  链接的目标改变后回复语言随之变化。
- **跨机器**：克隆者需 `git config core.symlinks true`（Windows 默认 `false`）；未开时重跑 `core-init` 重建。

## 运行时产物（外置到项目侧）

脚本执行过程中生成的产物（各技能 `check_logs/`、`.cache/`、`.vcs-lock/` 等）**外置到项目侧**
`.codebuddy.project/caches/`（镜像引擎结构），由项目侧 `.gitignore` 整体忽略、**不入库**；
需持久化保留的项目结果放 `.codebuddy.project/store/`（入库）。

- 产物目录清单由索引 `artifacts.dirs` 声明；各脚本经**逻辑名**解析（不硬编码到技能目录）。
- 清理：项目侧 `cleanup-caches.cmd`（薄入口）调用引擎侧通用工具
  `.codebuddy/scripts/cleanup_artifacts.py`（清单由索引驱动，删除文件并重建空目录）。

## 分层配置（通用留引擎、项目值外置）

一份配置若同时含通用部分与项目相关部分，按此拆分（如覆盖率的算法参数通用、源码根项目相关）：

- 通用部分留引擎侧（随引擎版本演进，`tools/<工具>/xxx_config.json`）；
- 项目相关部分外置（`xxx_config.project.json`，登记到索引 `files`）；
- 读取时**深度合并**（项目侧覆盖引擎侧，数组取并集）。

## 规则薄壳（rule_shells）

规则加载器只扫描 `.codebuddy/rules/**/*.mdc`，因此 `.mdc` 本体**必须留在引擎内**。
规则的项目事实（目录结构、包依赖、存量清单等）外置到项目侧，引擎侧保留**薄壳**：

- 薄壳保留 frontmatter、`description`/触发条件、强制条款与**通用规范**；
- 项目事实正文移到 `.codebuddy.project/configs/rules/`，薄壳内声明「见索引 `rule_shells` 指向的正文」。

## 包管理（lib/packs.json）

引擎组件按**包**组织。默认包随引擎分发、检出即用；可选包需显式安装，装到项目侧后再经链接进入扫描根。

| 包 | 类别 | 默认 | 组件 |
|---|---|---|---|
| `core` | 基础 | ✅ | rules: core-language、core-project-guide、core-tooling、core-engine、core-init、core-rule-governance；skills: core-init |
| `project` | 项目专属 | ✅ | 项目自有的规则/技能/代理，内容在 `.codebuddy.project/project/` |
| `vcs` | 基础 | ✅ | rules: vcs-router、vcs-engine-commit、vcs-git-commit、vcs-git-merge；skills: vcs-router、vcs-git-commit、vcs-git-merge |
| `tool` | 基础 | ✅ | rules: tool-cmd-script-writing、tool-engine-sync、tool-export-zipped-dir、tool-rule-consolidation、tool-session-lesson-distill；skills: 同名 5 个 |
| `csharp` | C# | ❌ | rules: csharp-code-review、csharp-comment、csharp-lsp、csharp-test、csharp-test-coverage、csharp-format-checker；skills: csharp-code-review、csharp-comment-checker、csharp-comment-generator、csharp-format-checker、csharp-lsp、csharp-test-coverage；agents: 2 个 |
| `unity-pipeline` | 领域（本地维护） | ❌ | rules: unity-pipeline；skills: unity-pipeline |
| `python` | Python | ❌ | rules: python-code-review、python-comment、python-test、python-env、python-lint、python-test-coverage；skills: python-env、python-lint、python-code-review、python-comment、python-test-coverage；agents: 2 个 |
| `grilling` | third-party（本地维护） | ❌ | skills: grilling |
| `yao-meta-skill` | third-party | ❌ | rules: yao-meta-skill；skills: yao-meta-skill |

### 组件命名约定

**组件名（规则 / 技能 / 智能体的目录名）必须以 `<包名>-` 开头**，让归属一目了然：

| 情形 | 规则 | 示例 |
|---|---|---|
| 一般组件 | `<包名>-<语义名>` | `core-tooling`、`vcs-git-commit`、`tool-engine-sync` |
| **组件名等于包名**（可选包自名组件） | **豁免**，保持与包名一致 | `unity-pipeline`、`grilling`、`yao-meta-skill` |

豁免的第二个情形来自 vendor 约束：`yao-meta-skill` 仍是只读 vendor，改名会让上游 `git pull` 永久冲突；
`unity-pipeline` 与 `grilling` 虽已转本地维护，但组件名与包名相同，加前缀会得到
`unity-pipeline-unity-pipeline` 这类无信息量的名字。

校验由 `check_manifest.py` 执行（校验项 8）：组件名不以 `<包名>-` 开头且不等于包名时报错。
新建组件时照着命名即可，漏改会在提交前的 `pre-commit` 钩子被拦下。

### 规则分类与命名

规则分三类，详见 `rules/core/core-rule-governance/`：

| 类型 | 文件名 | 触发方式 | 职责 |
|---|---|---|---|
| **入口规则** | `<技能名>.entry.mdc` | `alwaysApply: true` | 只定义「必须经该技能执行」 |
| **规范规则** | `RULE.mdc` | `alwaysApply: false` | 具体规范，由技能加载 |
| **底线规范** | `RULE.mdc`（无对应技能） | `alwaysApply: true` | 无条件适用的底线（语言、项目结构、工具纪律） |

**任何规则都不得写 `paths`**：`paths` 是「文件命中该路径后」才注入的事后触发，赶不上
「还没动手就该走技能」的决策点。技能侧同规——`activation.mode` 不得为 `path_scoped`，
`activation.paths` 必须为空。判据见 `rules/core/core-rule-governance/`。

规范命名：**单技能使用 → 与技能同名；多技能共用 → 取共同前缀**。
被其他技能拉起的技能**不建入口规则**（链路已固定，再加会造成两个入口）。

校验项 9 覆盖：入口规则必须有对应技能（或为其前缀）；有同名技能的包内，规范规则不得
`alwaysApply: true`。

```bash
python .codebuddy/scripts/pack_install.py list             # 列出全部包与安装状态
python .codebuddy/scripts/pack_install.py install csharp   # 安装（自动带出 requires）
python .codebuddy/scripts/pack_install.py remove csharp    # 卸载（被依赖时拒绝）
python .codebuddy/scripts/pack_install.py status           # 报告漂移
python .codebuddy/scripts/pack_install.py verify --repair  # 修复漂移
```

约定：

- **组件路径推导**：`location=engine` → `.codebuddy/<类型>/<pack>/<名>`；`location=lib` → `.codebuddy/lib/<pack>/<类型>/<名>`。
  `packs.json` 的 `comps` 只写组件名，不写路径。
- **安装状态**：只记可选包，落在项目侧 `.codebuddy.project/configs/packs.json`；默认包不入清单（避免双份事实）。
- **agents 特殊**：文件级符号链接会被扫描器的路径白名单拒绝，故项目侧用**硬链接**（跨卷降级复制）。
- **顺序**：先 `install`（物化链接）再启动新会话，否则扫描不到新组件。
- **项目专有包 `project`**：默认启用、无需安装。内容与其他包**同构**放在
  `.codebuddy.project/<类型>/project/` 下，经 `.codebuddy/<类型>/project` 一层链接进入扫描根。
  它不属于引擎 `lib/`，`packs.json` 中 `comps` 为空数组（内容由项目自由增删，不做声明式校验）。
```bash
# 项目专有内容示例（与其他包同级并列）
.codebuddy.project/rules/project/my-rule/RULE.mdc
.codebuddy.project/skills/project/my-skill/SKILL.md
.codebuddy.project/agents/project/my-agent.md
```

## 仓库更新（update_repo.py）

引擎以 git（submodule）分发，更新到最新由 `scripts/update_repo.py` 承担。脚本**自动识别仓库形态**
并采用不同更新方式：

| 形态 | 判定依据 | 更新方式 |
|------|---------|---------|
| **普通仓库** | `.git` 为目录、无父仓 | `git fetch` → 对当前分支 `git pull --ff-only` |
| **子模块** | `.git` 为文件（gitdir 指针）或有父仓 | 同上拉取当前分支最新，**并额外提示**父仓需提交指针更新 |

```bash
python .codebuddy/scripts/update_repo.py              # 更新 .codebuddy 引擎（默认目标=脚本所在仓库）
python .codebuddy/scripts/update_repo.py --dir <目录>  # 更新指定目录所在仓库
python .codebuddy/scripts/update_repo.py --branch main # 显式指定目标分支
python .codebuddy/scripts/update_repo.py --fetch-only  # 只取不拉，仅报告差异
```

**双击入口**：`.codebuddy/update.cmd` 是薄入口，可直接双击运行（内部调用上述脚本，自动查找
`python`/`py`，结束前 `pause` 便于查看输出）。参数同样透传：
`update.cmd --json`、`update.cmd --fetch-only`。

**进度输出**：脚本按 6 步输出 `[n/6]` 进度（检测形态 → 前置检查 → 获取远程 → 比较差异 →
快进拉取 → 重建包链接），拉取前会列出待拉取的提交清单（最多 20 条），拉取后打印
`HEAD: 旧哈希 → 新哈希`，结束时输出「仓库更新报告」汇总。

- 进度与细节一律写 **stderr** 并逐条 flush，因此双击运行时进度实时可见；
  `--json` 时 stdout 仅输出结构化结果，可直接重定向/解析，进度不会污染 JSON。
- 提前退出的分支会说明剩余步骤是否执行（如工作区有未提交改动时跳过第 5 步）。

**安全约束**：

- 工作区存在**未提交改动**时，**仅报告不自动拉取**（打印领先/落后与改动清单，避免冲突或丢失改动）。
- 默认 `--ff-only`（仅快进）：本地与远程**分叉**时报错提示手动处理，不产生意外合并提交。
- 检测到进行中的合并 / 变基（`MERGE_HEAD` / `REBASE_HEAD` 等）时**直接中止**，不做网络操作。
- 退出码：`0` 成功（含已最新、报告模式）；`1` 执行错误；`3` 非 git 仓库 / 无远程 / 无法确定分支。

> **子模块提醒**：子模块更新后其 HEAD 前移，但**父仓仍锁定旧提交**。若不提交父仓的指针更新，
> 他人拉取到的仍是旧版本，且父仓 `git submodule update` 会把子模块**重置回**旧提交。
> 脚本会在子模块模式下打印所需命令（父仓 `git add <子模块> && git commit`）。

> **包链接重建**：引擎更新可能改名或删除 `lib/` 下的组件，导致项目侧链接悬空。
> 脚本在拉取结束后自动调用 `pack_install.py verify --repair` 对齐；未初始化的纯引擎仓会跳过此步。

## 仓库维护约定

1. **新增需项目配置的技能配置**时，须在 `project.index.json` 登记（逻辑名/路径/骨架），
   详见 `rules/core/core-engine/config-isolation-spec.mdc` §3.6。
2. **不把项目专有值写入本库**（脚本、配置、索引、示例均不得硬编码）；项目值只出现在消费项目侧。
3. **技能/规则清单维护**：本 README 的目录结构节即引擎构成清单；新增/删除技能或规则时同步更新本节。
   运行 `python scripts/check_manifest.py` 核对一致性。
4. **迁移机制已废除**：不再使用导出 zip + 补丁分发（旧 `MIGRATION.md` / `INVENTORY.md` /
   `CHANGES.md` / `export_codebuddy.cmd` / `codebuddy-migration-sync` 规则均已删除），改由 git
   （submodule）版本化分发；历史版本查询用 `git log`。
5. **本仓库自身即「引擎仓库」，改动须提交到本仓库**：`.codebuddy/` 是一个独立 Git 仓库（在消费项目中
   以 submodule 出现），其内文件的提交发生在**引擎仓库**，与「项目仓库」是两个提交目标——不得混为一笔，
   且更新 submodule 指针须**先推送引擎、再提交项目指针**。约定详见
   `rules/vcs/vcs-engine-commit/`。
6. **三条规则按触发面分层，勿合并**：
   - `core-tooling`（core，**始终生效**）：管工具调用的前后两端——命令如何构造（避免权限系统的无谓拦截）、
     结果如何判定（失败可能返回 `{error}` 对象而非抛错）。
   - `core-engine`（core，`.codebuddy/**` 触发）：管内容如何写（项目专有值外置）与改完还要同步哪些登记点。
   - `vcs-engine-commit`（vcs，`.codebuddy/**` 触发）：只治理**引擎仓库**的提交，含 submodule 与独立检出两种形态。
   三者职责互不重叠；**不得合并**——合并会让引擎条款常驻，或让提交归属失去独立加载时机。
   另：`yao-meta-skill` 包的 `rules/yao-meta-skill/` 是**技能工程的强制入口**（技能创建/重构/审计必须走该技能），
   属可选包规则，仅在安装该包时生效。

## 运行环境

| 依赖 | 用途 |
|------|------|
| Python 3.8+ | 各技能编排脚本 |
| .NET 10.0+ SDK | 注释检查 / 覆盖率检查的 C# 工具 |
| `dotnet format` | 格式检查（含于 .NET SDK） |
| `unity` CLI | Unity 操作（缺失时 `unity-pipeline` 自动安装，离线包不入库，需在线下载） |
| `csharp-ls` + `csharp-lsp` 插件 | C# LSP 代码智能（`dotnet tool install --global csharp-ls`） |

## 已知事项

- **Unity CLI 离线安装包**（`skills/unity-pipeline/tools/unity-cli-offline/unity-windows-x64.exe`，约 106MB）
  不入库、不随引擎分发（仓库 pre-commit 拦截 >50MB 文件）；缺失时技能安装脚本回退**在线下载**。
- **机器级文件**：`models.json`（含 API Key）、`settings.local.json` 绑定本机、已被忽略，不入库、不共享。
