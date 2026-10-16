---
name: git-commit
description: Git 提交执行技能。当用户要求提交 Git 代码（"git commit"、"提交到 git"，或由 vcs-router 技能路由）时触发，分析 Git 变更并生成标准化提交摘要，提交前按项目配置自动触发代码审查门禁（默认 C# 变更，error 级别问题阻塞提交）。不支持 amend、rebase、cherry-pick、revert、stash、分支操作。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.9"
  skills_os: "2.0"
---

## 运行模式

`Production` —— 团队复用技能，需通过触发评估和输出风险检查。

## 与 vcs-router 的关系

`vcs-router` 是提交操作的**统一入口**：用户提交请求先由 vcs-router 检测仓库类型并路由，本技能作为 Git 仓库的**提交执行者**。用户显式指定 Git 上下文（如"git commit"）时，本技能也可直接触发。

提交规范入口与强制路由条款定义在 `.codebuddy/rules/vcs-router/RULE.mdc`（始终生效），详细规范按需加载自同目录子规则：`common-commit-spec.mdc`（提交摘要）、`common-submission-safety-spec.mdc`（授权与安全）、`git-commit-spec.mdc`（Git 特定安全约束）。本技能执行时遵循上述规则，本文件仅保留 Git 特定流程与命令。

**提交前审查门禁不在规则目录**：其**机制**由本技能 `references/project-config.md` §2 承载，**参数**由项目侧配置（经索引 `git_commit.project_config` 定位）承载；作为 §3 H1 暂存前的**首个步骤**执行（见阶段五）。

**项目可配置项（均外置到项目侧 `.codebuddy.project/`，经 `.codebuddy/project.index.json` 定位）**：提交摘要确定性参数（type 枚举、subject/scope 长度、subject 语言）见索引逻辑名 `git_commit.config`；流程级配置（scope 规则、审查门禁参数、钩子步骤取值）见逻辑名 `git_commit.project_config`。目标项目只改项目侧配置，不改本技能与规则文件。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | Git 仓库的 `git commit` 标准化提交流程（变更分析 → 提交计划 → 项目专有钩子 → 安全检查 → 用户授权 → 执行提交） |
| 输出 | 符合 `<type>(<scope>): <subject>` 格式的提交，附带安全检查与代码审查证据 |
| 排除 | `git commit --amend`、`git rebase`、`git cherry-pick`、`git revert`、`git stash`、分支操作、`git merge` |
| 提交规范 | `.codebuddy/rules/vcs-router/RULE.mdc`（入口+强制路由，始终生效）与同目录子规则（`common-commit-spec`、`common-submission-safety-spec`、`git-commit-spec`，按需加载）；审查门禁机制见本技能 `references/project-config.md` §2（参数见项目侧 `project-config.md`） |

## 参考文献

| 文件 | 内容 |
|------|------|
| `references/commit-spec.md` | 提交摘要详细规范：近似 type 区分规则、subject 正确/错误示例、提交正文、提交信息的传入方式（`-F` 文件传参、`@` 污染成因）、多模块拆分与编排顺序 |
| `references/submission-safety.md` | 安全规范：提交/推送发起权（按项目配置）、授权要求、提交推送分离、敏感信息检查、.gitignore 检查流程 |
| `references/project-config.md` | **引擎侧机制**：§2 审查门禁机制（触发时机/审查对象/派发要素/阻塞规则）、§3 钩子步骤字段语义与执行规则。**项目参数**外置到项目侧（索引 `git_commit.project_config`） |
| 项目侧 `skills/git-commit/config.json` | 提交摘要确定性配置：type 枚举、subject_max_len、scope_max_len、subject_language（索引 `git_commit.config`） |
| `references/vcs-lock.md` | 多会话防冲突：VCS 写操作互斥锁机制、命令用法、暂存区校验，集成到阶段七 |

接口契约定义在 `agents/interface.yaml`，包含输入/输出/排除的完整契约。

---

## 工作流程

当 vcs-router 路由到本技能（或用户直接要求提交 Git 代码）时，按以下七个阶段执行规范化提交。

### 阶段一：获取变更信息

按以下优先级获取变更信息：

1. **从本次对话中提取修改信息**（优先）：
   - 回顾本次对话中所有文件编辑、新增、删除操作。
   - 提取每个修改的意图、涉及的模块和功能点。
   - 将对话中的修改按功能逻辑分组。

2. **回退至 Git 变更分析**（若对话中无修改信息）：
   ```bash
   git status --short
   git diff --cached --stat
   git diff --cached --name-status
   git diff --stat
   git diff --name-status
   ```
   深入分析变更内容以推断改动意图。

3. **处理未暂存变更**：若存在 modified-but-not-staged 文件，通过 `AskUserQuestion` 询问用户是否需要暂存：
   - 列出未暂存变更文件及其简要差异。
   - 确认用户是否要包含这些文件。
   - 若拒绝，仅处理已暂存文件；若接受，在阶段七统一暂存。

4. **合并对话上下文与 Git 变更**（部分重叠时）：
   - 对话中涉及的文件：使用对话上下文中的意图信息生成摘要。
   - 对话外变更的文件：通过 `git diff` 分析推断意图。
   - 合并后统一定义模块和规划提交粒度。

### 阶段二：确定修改模块

根据变更文件路径，按 `references/project-config.md` §1 中定义的优先级规则提取 scope（该节为项目的 scope 配置，迁移或模块调整时修改）：

1. 框架包路径 → 包名对应的模块
2. 领域运行时程序集路径 → 程序集名
3. 领域 Editor 路径 → Editor 模块
4. 通用路径（`Tools/`、`ProjectSettings/`、`.codebuddy/` 等）→ 按 project-config.md §1 映射

scope 的具体取值以 `references/project-config.md` §1 中的项目配置为准。新增模块、无匹配路径等边界情况的处理同样参见该节。

### 阶段三：规划提交粒度

- 单功能变更 → 一次提交。
- 多功能变更 → 按功能拆分为多次提交：
  - 新功能与 Bug 修复分开。
  - 重构与功能变更分开。
  - 文档变更与代码变更分开。
  - 不同模块变更尽量分开。

拆分规则与提交编排顺序详见 `references/commit-spec.md`（编排顺序遵循"底层先于上层、重构先于功能、独立变更按目录层级排序"）。

### 阶段四：生成提交摘要

按 `<type>(<scope>): <subject>` 格式生成。**type 定义、subject 规范、授权确认方式遵循 `.codebuddy/rules/vcs-router/common-commit-spec.mdc` 与 `common-submission-safety-spec.mdc` 公共子规则**，近似 type 的详细区分规则见 `references/commit-spec.md`。

默认 type 枚举（读取自项目侧 `skills/git-commit/config.json`，索引逻辑名 `git_commit.config`，目标项目可调整）：

| 类型 | 说明 | 类型 | 说明 |
|------|------|------|------|
| `feat` | 新功能 | `fix` | Bug 修复 |
| `docs` | 文档变更 | `style` | 代码格式调整 |
| `refactor` | 代码重构 | `perf` | 性能优化 |
| `test` | 测试 | `chore` | 构建/工具链 |
| `ci` | CI/CD | `revert` | 回退提交 |

**生成后自动化校验**：每条提交摘要生成后，运行格式校验脚本确认合规。type 枚举、subject 长度上限、scope 长度上限、subject 语言均读取项目侧 `skills/git-commit/config.json`（索引逻辑名 `git_commit.config`，配置为唯一来源，缺失或字段非法时脚本报错退出码 3），无句号结尾为通用约定：

```bash
python .codebuddy/skills/git-commit/scripts/validate_commit_subject.py "<type>(<scope>): <subject>"
```

校验失败（退出码 1）时，按错误提示修正后重新校验；全部提交摘要校验通过后进入阶段五。

### 阶段五：执行项目专有钩子（H1 暂存前）

H1 钩子步骤由**项目侧配置**声明（经索引 `git_commit.project_config` 定位到
`.codebuddy.project/skills/git-commit/project-config.md`）。读取其 §3「H1 暂存前」步骤列表，
**按表内顺序**执行 `enabled=true` 的步骤；`blocking=false` 失败仅告警，`blocking=true` 失败即中止并询问用户。

本项目 H1 默认含两个步骤，按序为：

1. **提交前审查**——匹配审查文件模式时触发代码审查，`error` 级别问题阻塞提交（参数见项目侧 §2，机制见引擎侧 `references/project-config.md` §2）。
2. **提交前格式检查**——含 `.cs` 时跑 `csharp-format-checker` **变更工程**格式校验（机制见引擎侧 §3.1）。

步骤的具体配置、参数与启用状态以**项目侧配置**为准；机制（触发时机、阻塞边界、字段语义）以
引擎侧 `references/project-config.md` 为准。本文件不重复维护；增删步骤只改项目侧配置。

### 阶段六：安全检查

执行 `.gitignore` 交叉比对（详见 `references/submission-safety.md` 与公共子规则 `common-submission-safety-spec.mdc` 中的敏感信息检查）：

```bash
cat .gitignore                                    # 读取当前忽略规则
git diff --cached --name-only                     # 查看暂存区文件
git ls-files --cached --ignored --exclude-standard # 检查是否有被忽略文件
git status --ignored --short                       # 辅助排查
```

若发现误添加了已忽略文件：
```bash
git rm --cached <file>    # 仅从暂存区移除，保留本地文件
```

同时扫描暂存区变更中的敏感信息（密码、密钥、Token、API Key 等），检测到则阻止提交并警告用户。

**计划外已修改文件核对（全仓）**：仅按某个目录过滤核对容易漏看被工具自动改写的文件
（典型如 Unity 自动改写的 `ProjectSettings/ProjectSettings.asset`，实测会移除图形 API 列表项）。
提交前必须执行**全仓** `git status --short`，对本轮提交计划之外的文件：**显式排除**，
并在提交计划中**告知用户**这些计划外改动，由用户决定（保持 / 还原 / 单独提交），禁止默认静默带入。

```bash
git status --short    # 全仓核对，逐一确认是否属于本次提交计划
```

边界情况（空提交、合并冲突、hook 失败、detached HEAD、submodule、大文件、未配置用户信息、文件名大小写变更）的处理参见 `rules/vcs-router/git-commit-spec.mdc`「Git 边界情况」。

### 阶段七：执行提交（含多会话互斥锁）

> **防冲突机制**：提交会修改暂存区与 HEAD，而 git 的暂存区/HEAD 是仓库级共享状态。多个 CodeBuddy
> 会话并发执行提交、回滚等写操作会互相污染（暂存区混入他会话文件、提交被回滚）。
> 本阶段通过 VCS 互斥锁串行化写操作（详见 `references/vcs-lock.md`），并在提交前校验暂存区，
> 双保险防止多会话冲突。
>
> **锁粒度（关键）**：**逐笔加锁**——`acquire` 与 `release` 之间只完成**一笔**提交
> （`git add` → 暂存区校验 → `git commit`），提交完成立即释放，再处理下一笔。
> 锁**必须覆盖 `git add`**：暂存区污染（他会话已 `git add` 的文件被本次 `git commit` 一并带走）
> 正是锁要防的首要场景，因此暂存与提交不可拆到锁外。
> **锁窗口最短化**：所有检查（阶段一~六，含审查门禁与 H1 钩子）、提交计划展示与用户授权
> **全部在锁外完成**，锁内只保留三个 git 写操作与一次暂存区校验。
>
> **锁同样适用于引擎仓库提交**：在 `.codebuddy/`（引擎仓库，独立仓库/submodule）内提交时，
> 同样须 `acquire` → 提交 → `release`，且**不得遗漏释放**。提交前还须先判定本次变更归属哪个仓库
> （见 `rules/codebuddy-engine-vcs/`），跨仓库变更拆为两笔、各自加锁释放。

**逐笔执行以下步骤（每笔提交重复 1~7；多笔提交时无需在锁内连续完成）：**

1. 展示提交计划（**全部笔数**的摘要与文件范围，以及审查报告路径/问题摘要）——
   多笔提交须在**一次**授权询问中给出完整计划（详见 `common-submission-safety-spec.mdc`）。
2. 通过 `AskUserQuestion` 工具发起确认询问，**一次性获得全部笔数的明确授权**。
3. **获取 VCS 锁**（**授权之后、暂存之前**）：
   ```bash
   python .codebuddy/skills/vcs-router/scripts/vcs_lock.py acquire --op "git commit"
   ```
   - 授权后才加锁，锁窗口不含用户思考/确认的等待时间。
   - 锁被其他会话占用时，脚本输出占用摘要（会话标识/操作/开始时间/PID）并**自动轮询等待**
     对方释放；等待超时仍未获取则中止，向用户说明冲突来源，可稍后重试或主动加 `--force` 接管。
   - 记录输出中的 `LOCK_SESSION=<id>`，本笔提交完成后用于释放。
4. **暂存本笔文件**：用 `git add -- <本笔路径…>` 显式列出本笔文件，避免 `git add -A` 误纳计划外文件。
   - **索引预置项需先清理**：`git mv` / `git rm` 会把变更**预置进索引**，导致"本笔暂存区多出后续笔文件"而校验失败。
     正确做法是提交前先 `git reset`（仅清空索引、保留工作区改动），再按笔显式暂存。
   - 若因统一审查等原因已一次性暂存全部变更文件，执行本笔提交前必须先用 `git reset -- <非本笔文件>`
     将不属于本笔的文件移出暂存区。
   - **重命名检测的干扰**：删除旧目录 `.meta` + 新建目录 `.meta`（内容仅 GUID 不同）会被 git 识别为
     `rename (77%)`（如 `<旧目录>.meta → <新目录>.meta`），并非"文件被改"；提交计划中应预先说明，
     避免复核时误判。测试目录搬迁与内容修改同笔提交会显示为 `R091`（重命名 + 修改），属正常。
5. **提交前暂存区校验**（防暂存区污染与跨笔误提交）：执行 `git diff --cached --name-only`，与**本笔**
   提交计划文件列表比对。若**多出**本笔之外的文件（无论其是否属于整体提交计划）或**缺失**本笔计划内
   文件，立即中止并释放锁，调整暂存区后重新规划。多笔拆分提交时，`git commit` 前必须保证暂存区仅含
   本笔文件。推荐用校验脚本做确定性集合比对：
   ```bash
   # 每行一个本笔计划路径；不一致退出码 1，并提示先释放 VCS 锁
   python .codebuddy/skills/git-commit/scripts/verify_staged.py --expect-file <本笔计划清单.txt>
   ```
   **计划清单须先归一化路径前缀**：脚本期望仓库相对路径，而 `git diff --cached --name-only`
   在子目录执行时带当前目录前缀（本仓库为 `<仓库前缀>/`，按 `git rev-parse --show-prefix` 实测值替换），直接使用会误报「多出」。
   先按 `git rev-parse --show-prefix` 得到前缀并 `sed` 去除（详见 `references/vcs-lock.md`）。
   另：全仓 `git status` 等大范围核对应在阶段六完成，避免其后台化后争用 `.git/index.lock`。
6. **执行 `git commit`**（已获授权，直接提交本笔）。
   - **提交信息用 `git commit -F <临时文件>` 传入**，不要依赖 shell 引号或 here-string 语法
     （跨工具语法混用会把 `@` 当字面量写入消息，实测污染过摘要与正文）。临时文件放系统临时目录，
     不写 `.git/`，用完删除。
   - 提交后用 `git log -1 --format="%s%n%b"` **复核实际落盘的消息**，确认无误再释放锁
     （详见 `references/commit-spec.md`「提交信息的传入方式」）。
7. **立即释放 VCS 锁**（无论本笔提交成功、失败或中止都必须释放，释放后才能开始下一笔）：
   ```bash
   python .codebuddy/skills/vcs-router/scripts/vcs_lock.py release --session <LOCK_SESSION>
   ```
   - 若释放报「会话标识不一致」：通常是 acquire 输出的 `LOCK_SESSION` 被终端输出伪影污染
     （行尾偶发附加字符，如 `X`），脚本已内置容错匹配（归一化 + 安全前缀）自动放行；
     仍失败时先执行 `vcs_lock.py status` 查看锁中真实 session，再以其重新 `release`。
   - **禁止**在未释放锁的情况下开始下一笔（会导致锁窗口跨越用户交互）。

**每笔提交完成后的收尾：**

8. 报告该笔提交哈希和摘要。
9. **提交与推送分离**：推送需等待用户单独指令（详见 `references/submission-safety.md`）。

---

## 检查清单

提交和推送代码前，逐项检查：

- [ ] 本次提交是否由 vcs-router 路由（或用户直接指定 Git 上下文）？
- [ ] 提交发起权是否合规（`commit_initiation`：`user_only` 时需用户主动发起；`llm_allowed` 时 LLM 可自行发起）？
- [ ] H1 步骤是否已按**项目侧配置**（经索引 `git_commit.project_config`）的表内顺序执行（`enabled`/`blocking` 语义见引擎侧 `references/project-config.md` §3）？
- [ ] H1 首个步骤「提交前审查」：本次变更是否包含配置的审查文件模式（默认 `.cs`）？若是，是否已触发代码审查？
- [ ] 用户指示跳过审查时，是否已通过 `AskUserQuestion` 确认跳过理由？
- [ ] 审查是否存在配置 `blocking_level`（默认 `error`）级别问题？若是，是否已修复或获得用户明确授权忽略？
- [ ] 审查报告路径是否已记录进提交计划？
- [ ] H1「提交前格式检查」：含 `.cs` 的提交是否在**暂存前**跑过 `csharp-format-checker`，失败时是否已 fix 或获得用户授权忽略？
- [ ] 提交/推送前是否通过 `AskUserQuestion` 获得明确授权？
- [ ] 提交摘要格式是否正确（type + scope + subject）？
- [ ] subject 是否符合项目侧 `skills/git-commit/config.json`（索引 `git_commit.config`）配置（语言/长度）、无句号结尾？
- [ ] 一次提交是否仅包含一个逻辑功能？
- [ ] 是否已读取 `.gitignore` 并交叉比对暂存区？
- [ ] 暂存区是否包含临时文件或备份文件？
- [ ] 是否已扫描变更中的敏感信息？
- [ ] 是否在**获得授权之后**才获取 VCS 锁（`vcs_lock.py acquire`）？每笔提交完成后是否**立即释放**（含中止/失败路径）？
- [ ] 锁是否**覆盖 `git add`**（暂存与提交不可拆到锁外，否则暂存区污染防护失效）？
- [ ] 提交前暂存区文件列表是否与**本笔**提交计划完全一致（无多出/缺失文件；多笔拆分时暂存区不得包含后续笔文件）？
- [ ] 多笔提交是否**逐笔加锁**（每笔各自 acquire→add→校验→commit→release，锁窗口不跨越用户交互），且逐笔用 `git add -- <本笔路径>` 显式暂存（未用 `-A` 误纳计划外文件）？
- [ ] 若执行过 `git mv` / `git rm`（索引预置），是否已先 `git reset` 清理索引后再按笔暂存？
- [ ] 提交计划是否已说明重命名检测（`rename`/`R0xx`）等易被误判为"文件被改"的情况？
- [ ] 是否已用全仓 `git status --short` 核对**计划外已修改文件**，并在计划中告知用户由其决定（保持/还原/单独提交）？
- [ ] 提交正文是否解释清楚了变更原因？
- [ ] 提交与推送是否已拆分为独立操作？
- [ ] 边界情况（空提交、冲突、hook 失败等）是否已检查？
