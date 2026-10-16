# .codebuddy —— CodeBuddy 共享工作流引擎

本仓库是**可跨项目共享的 CodeBuddy 工作流引擎**（技能 / 规则 / Agent / 配置注册表）。
它**不绑定任何具体项目**：与项目绑定的配置、产物、专有技能全部外置到**消费项目**根下，
由本仓库的 `project.index.json` 索引。

> **共享方式**：将本仓库作为 **git submodule** 纳入各项目，检出到项目的 `.codebuddy/` 路径。
> 多项目共享同一引擎、各自维护独立的项目侧内容；引擎升级只需 `git submodule update`。

## 目录结构

```
.codebuddy/                     # 本仓库根 = CodeBuddy 引擎内容
├── project.index.json          # 配置注册表：逻辑名 → 项目侧路径 + 骨架，规则薄壳映射
├── update.cmd                  # 仓库更新双击入口（薄入口，调用 scripts/update_repo.py）
├── README.md                   # 本文件：引擎结构与约定
├── .gitignore                  # 排除项目侧绑定链接、机器级配置与运行产物
├── .gitattributes              # 行尾与二进制/文本归属声明
├── skills/                     # 技能（SKILL.md + scripts/ + tools/ + references/ + agents/ + evals/ + reports/）
│   ├── codebuddy-init/         # 新项目接入：依据索引生成项目侧配置骨架与软链接
│   └── third-party/            # 外部引入的三方技能（整体照搬上游）
├── rules/                      # 规则（入口 RULE.mdc + 子规则；项目事实正文薄壳引用）
├── agents/                     # 子代理
└── scripts/                    # 引擎级通用脚本（清单校验、产物清理、仓库更新）
```

> **检出位置约定**：本仓库应检出为消费项目的 **`.codebuddy/`**（如 `Program/Client/.codebuddy/`）。
> 引擎内所有相对路径推导均以「`.codebuddy` 的父目录 = 项目根」为基准，故检出路径名必须是 `.codebuddy`。

## 引擎与项目侧的边界

| 位置 | 归属 | 说明 |
|------|------|------|
| 本仓库（检出为 `.codebuddy/`） | 引擎 | 纯通用内容；跨项目共享 |
| `.codebuddy/project.index.json` | 引擎 | 配置注册表；路径 + 骨架，**无项目专有值** |
| `.codebuddy/skills/**/tools/**/<工具>.json` | 引擎 | **分层配置的通用部分**（规则、算法参数等） |
| `.codebuddy.project/` | 项目 | 项目侧配置**与运行时产物**（含 `settings.json` 源文件）；随项目独立维护 |
| `.codebuddy/settings.json` | 项目（链接） | **软链接** → `.codebuddy.project/settings.json`（由项目侧创建，**不入本库**） |
| `.codebuddy.project-skills/` | 项目 | 项目专有技能（经 `.codebuddy/skills/project-skills` 软链接被加载，**不入本库**） |
| `.codebuddy/models.json` / `settings.local.json` | 机器 | 机器级/本机级；不入库 |

## 新项目接入（三步）

1. **引入引擎**：把本仓库作为 submodule 检出到项目根下的 `.codebuddy/`：
   ```bash
   git submodule add https://github.com/zengliugen/.codebuddy.git .codebuddy
   ```
   （或复制本仓库内容到项目根的 `.codebuddy/`。）
2. **生成项目侧配置**：调用 `codebuddy-init` 技能（或直接运行脚本）：
   ```bash
   python .codebuddy/skills/codebuddy-init/scripts/init_project_config.py
   ```
   依据 `project.index.json` 在项目根生成 `.codebuddy.project/` 的占位配置骨架、运行时产物空目录、
   `.gitignore` 与 `cleanup-check-logs.cmd` 清理入口；并建立项目侧软链接
   （`.codebuddy/skills/project-skills` 与 `.codebuddy/settings.json`）。
3. **按项目填写**：按各技能 `references/config-guide.md` 填写占位值（`codebuddy-init` 会询问是否立即填写）。

> 未填写的配置在首次运行对应技能时会**明确报错**（配置缺失即报错，不静默使用默认值）。

## 配置注册表（project.index.json）

引擎与项目侧之间的**唯一索引**。各技能脚本经它按**逻辑名**定位项目侧配置；`codebuddy-init` 经它生成骨架。

- **路径基准**：项目根（`.codebuddy` 的父目录）；全部**相对路径**，**禁止绝对路径**。
- **`files`**：配置类文件 → 逻辑名 + `path` + `format` + `template`（JSON 骨架 / Markdown 大纲）。
- **`rule_shells`**：规则薄壳 → 键为薄壳相对 `.codebuddy` 的路径，值为项目事实正文路径。
- **`artifacts.dirs`**：运行时产物目录（check_logs / .cache / .vcs-lock 等）→ 逻辑名 + 项目侧镜像路径；
  供脚本落盘与清理工具枚举，不入库。
- **`root_symlinks.entries`**：引擎根下需**软链接外置**的单个文件（如 `settings.json`）→ 链接路径 + 项目侧源文件路径 + 骨架；
  由 `codebuddy-init` 生成源文件并建链，CodeBuddy 本体经软链接直接读取。
- **入库共享**：内容须是**纯约定 + 相对路径 + 占位值**，对所有消费项目一致。

schema 与逻辑名约定详见 `skills/codebuddy-init/references/index-spec.md`。

## 项目侧软链接（**由项目侧创建，不入本库**）

两个软链接是**项目侧绑定**，指向消费项目独有的目录：

```
<项目根>/.codebuddy/settings.json          ──软链接──▶  ../.codebuddy.project/settings.json
<项目根>/.codebuddy/skills/project-skills  ──软链接──▶  ../../.codebuddy.project-skills
```

- **为什么不入本库**：链接目标（`.codebuddy.project/`、`.codebuddy.project-skills/`）是本项目独有的；
  若纳入共享库，其他项目 clone 后链接会**悬空**，并可能与同名路径**冲突污染**。故本库 `.gitignore` 已排除
  （`/settings.json`、`/skills/project-skills`）。
- **如何创建**：消费项目 clone 本引擎后，运行 `codebuddy-init` 自动创建（幂等；失败时告警并给出手工 `mklink` 命令）。
- **机制依据**：实测 CodeBuddy **会解引用符号链接**——技能目录的链接下技能被正常扫描，`settings.json`
  链接的目标改变后回复语言随之变化。
- **跨机器**：克隆者需 `git config core.symlinks true`（Windows 默认 `false`）；未开时重跑 `codebuddy-init` 重建。

## 运行时产物（外置到项目侧）

脚本执行过程中生成的产物（各技能 `check_logs/`、`.cache/`、根 `.vcs-lock/`）**外置到项目侧**
`.codebuddy.project/`（镜像引擎结构），由项目侧 `.gitignore` 统一忽略、**不入库**。

- 产物目录清单由索引 `artifacts.dirs` 声明；各脚本经**逻辑名**解析（不硬编码到技能目录）。
- 清理：项目侧 `cleanup-check-logs.cmd`（薄入口）调用引擎侧通用工具
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
- 项目事实正文移到 `.codebuddy.project/rules/`，薄壳内声明「见索引 `rule_shells` 指向的正文」。

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

**安全约束**：

- 工作区存在**未提交改动**时，**仅报告不自动拉取**（打印领先/落后与改动清单，避免冲突或丢失改动）。
- 默认 `--ff-only`（仅快进）：本地与远程**分叉**时报错提示手动处理，不产生意外合并提交。
- 检测到进行中的合并 / 变基（`MERGE_HEAD` / `REBASE_HEAD` 等）时**直接中止**，不做网络操作。
- 退出码：`0` 成功（含已最新、报告模式）；`1` 执行错误；`3` 非 git 仓库 / 无远程 / 无法确定分支。

> **子模块提醒**：子模块更新后其 HEAD 前移，但**父仓仍锁定旧提交**。若不提交父仓的指针更新，
> 他人拉取到的仍是旧版本，且父仓 `git submodule update` 会把子模块**重置回**旧提交。
> 脚本会在子模块模式下打印所需命令（父仓 `git add <子模块> && git commit`）。

## 仓库维护约定

1. **新增需项目配置的技能配置**时，须在 `project.index.json` 登记（逻辑名/路径/骨架），
   详见 `rules/codebuddy-project-config/config-isolation-spec.mdc` §3.6。
2. **不把项目专有值写入本库**（脚本、配置、索引、示例均不得硬编码）；项目值只出现在消费项目侧。
3. **技能/规则清单维护**：本 README 的目录结构节即引擎构成清单；新增/删除技能或规则时同步更新本节。
   运行 `python scripts/check_manifest.py` 核对一致性。
4. **迁移机制已废除**：不再使用导出 zip + 补丁分发（旧 `MIGRATION.md` / `INVENTORY.md` /
   `CHANGES.md` / `export_codebuddy.cmd` / `codebuddy-migration-sync` 规则均已删除），改由 git
   （submodule）版本化分发；历史版本查询用 `git log`。

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
