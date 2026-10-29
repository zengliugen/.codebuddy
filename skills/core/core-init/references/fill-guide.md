# 项目配置填写指导（fill-guide）

<!-- pack-ref-ok: csharp, csharp-format-checker, csharp-code-review, csharp-test-coverage, csharp-comment-checker, git-commit, vcs
 本文件列的配置项来自各可选包技能，core-init 按「已安装包集合」（active_packs）过滤后使用：
 未安装的包，其条目既不生成骨架也不判缺失，因此不构成硬依赖。新增/改动条目须复核该过滤仍生效。 -->

本文件是 `core-init` 阶段四「按项目情况填写」的**填写指导入口**：当用户选择「立即填写」时，逐项按本文件指向的技能配置指南进行探测与填写。

## 通用原则

1. **实际探测，不套经验值**：每项填写前必须读取项目实际内容（构建清单、目录结构、依赖声明、模块/程序集清单、格式化配置等），不得凭记忆或套用其他项目的值。
2. **探测不到就问**：无法从项目自动探测的值（如团队约定的提交 type 枚举、术语白名单的用户偏好），**向用户询问**，不猜测。
3. **填写后复述确认**：写入前向用户复述「键 → 值」供确认。
4. **口径一致**：同一份清单出现在多处时（如排除目录）须同步，避免漂移。
5. **占位未填即报错**：保留 `<...>` 的配置在首次运行对应技能时会报错——这是**预期行为**（配置缺失即报错），不是缺陷。

## 逐项指导

| 逻辑名 | 项目侧文件 | 填写指导 | 探测线索 |
|--------|-----------|---------|---------|
| `format_checker.config` | `.codebuddy.project/configs/skills/csharp/csharp-format-checker/config.json` | `.codebuddy/lib/csharp/skills/csharp-format-checker/references/config-guide.md` | 解决方案/工程文件（`.slnx`/`.sln`/`.csproj`）；三方库与生成代码目录（`Assets/Plugins`、`Library/PackageCache`、各 `Gen/`、`Generated/`）；项目根 `.editorconfig` 必须存在 |
| `code_review.config` | `.codebuddy.project/configs/skills/csharp/csharp-code-review/config.json` | 该技能 `SKILL.md` 与 `references/` | 纳入审查的文件模式（默认 `*.cs`）；排除清单（生成目录、三方库、审查范围外目录）；**口径须与 format-checker 的 `exclude_dirs` 一致** |
| `git_commit.config` | `.codebuddy.project/configs/skills/vcs/vcs-git-commit/config.json` | `.codebuddy/skills/vcs/vcs-git-commit/references/project-config.md` §0 | **摘要格式 `pattern`（正则 + 命名组，判定依据）**、type 枚举及含义、subject/scope 长度上限、subject 语言、禁用结尾字符 |
| `git_commit.project_config` | `.codebuddy.project/configs/skills/vcs/vcs-git-commit/project-config.md` | 该文件自身的章节骨架 + 引擎侧 `references/project-config.md` §1.5/§2 | 项目目录结构 → scope 映射；**提交/推送发起权**（`commit_initiation`/`push_initiation`：`user_only` 或 `llm_allowed`）；审查门禁参数（`enabled`/`include_patterns`/`exclude_patterns`/`blocking_level`）；H1 钩子步骤 |
| `svn_commit.config` | `.codebuddy.project/configs/skills/vcs/vcs-svn-commit/config.json` | `.codebuddy/skills/vcs/vcs-svn-commit/references/project-config.md` §0 | SVN 的**摘要格式 `pattern`**、type 枚举及含义、subject/scope 长度上限、subject 语言、禁用结尾字符。**格式可与 Git 侧不同**（与 `git_commit.config` 相互独立、互不继承） |
| `svn_commit.project_config` | `.codebuddy.project/configs/skills/vcs/vcs-svn-commit/project-config.md` | 该文件自身的章节骨架 + 引擎侧 `references/project-config.md` §1.5/§2 | 项目目录结构 → scope 映射（按项目根相对路径）；**SVN 提交/远端同步发起权**（`commit_initiation`/`sync_initiation`，**注意不是 `push_initiation`**）；审查门禁参数；H1 钩子步骤 |
| `coverage.project_config` | `.codebuddy.project/configs/skills/csharp/csharp-test-coverage/tools/CSharpTestCoverage/coverage_config.project.json` | `.codebuddy/lib/csharp/skills/csharp-test-coverage/references/config-guide.md` | 运行时源码根、扫描范围、UPM 包名前缀 → 命名空间映射、真实采集程序集前缀、覆盖率产物目录 |
| `comment.project_config` | `.codebuddy.project/configs/skills/csharp/csharp-comment-checker/tools/CSharpCommentChecker/comment_config.project.json` | `.codebuddy/lib/csharp/skills/csharp-comment-checker/references/config-guide.md` | 排除目录（三方库、生成代码）；保留英文的项目术语（自研库名、选用库名）；`rules` 通用规则在引擎侧，无需填写 |
| `coverage.golden_samples` | `.codebuddy.project/configs/skills/csharp/csharp-test-coverage/scripts/golden_samples.json` | 该技能 `SKILL.md` | 项目已知正确的覆盖率样本（目标路径 + 期望）；新项目可先留空 `samples: []`，后续按需补充 |
| `coverage.trigger_cases` | `.codebuddy.project/configs/skills/csharp/csharp-test-coverage/scripts/trigger_cases.json` | 该技能 `references/` | 触发评估用例（应/不应触发样例）；含项目路径的用例仅为举例，可替换 |
| `format_checker.trigger_cases` | `.codebuddy.project/configs/skills/csharp/csharp-format-checker/evals/trigger/trigger_cases.json` | 该技能 `references/` | 同上 |
| `comment_checker.trigger_cases` | `.codebuddy.project/configs/skills/csharp/csharp-comment-checker/scripts/trigger_cases.json` | 该技能 `references/` | 触发评估用例（应/不应触发样例）；含项目路径与术语的用例仅为举例，可替换 |
| `codebuddy.settings`（根级软链接外置） | `settings.json`（项目根 `.codebuddy.project/configs/settings.json`） | 本节下方「根级软链接外置文件」 | `language`（界面/回复语言）；`env`（会话环境变量，含 `CODEBUDDY_REPL_NESTED_TIMEOUT_MS` 嵌套交互超时）；`permissions`/`enabledPlugins` 按团队约定；**`memory.teamMemory.userId` 不写**（由使用者本机自动推导，见下方说明）；**不含凭据**（凭据在引擎根 `models.json`/`settings.local.json`，不外置） |
| `rule_shells.*`（规则项目事实正文） | `rules/**` | 各技能 `references/` 与 `rules/` 薄壳内的强制条款 | 项目目录结构、依赖关系、启动流程、第三方依赖、测试目录现状等**项目事实**；须实测核对（依赖方向读构建清单、版本读依赖锁定文件、忽略范围用 `git check-ignore` 验证） |

## 运行时产物目录（无需填写）

索引 `artifacts.dirs` 声明的产物目录（各技能 `check_logs/`、`.cache/`、根 `.vcs-lock/`）由 `core-init`
创建为空目录，**无需填写任何值**；它们由项目侧 `.gitignore` 忽略、不入库。清理用项目侧
`cleanup-caches.cmd`。本项不属"填写"范畴，仅作说明。

## 根级软链接外置文件（root_symlinks.entries）

索引 `root_symlinks.entries` 声明的文件（如 `settings.json`）是**项目级单文件**，外置为：
项目侧源文件 `.codebuddy.project/configs/settings.json` + 引擎内软链接 `.codebuddy/settings.json`。
`core-init` 生成源文件骨架并建链；**CodeBuddy 本体经软链接直接读取**（无需脚本解析），实测其会解引用符号链接。

- **需填**：`language`、`env`、`permissions`、`enabledPlugins` 等**项目级**值（不含凭据）。

### `env.CODEBUDDY_REPL_NESTED_TIMEOUT_MS`（嵌套交互超时）

| 项 | 值 |
|----|-----|
| 作用 | REPL 单元格内发起 `AskUserQuestion` / `ExitPlanMode` 等嵌套交互时，等待用户确认的超时上限 |
| 默认 | `600000`（10 分钟，引擎内硬编码常量） |
| 建议 | `14400000`（4 小时）——默认 10 分钟在需要人工仔细阅读的提问场景下过短，超时后报「Timed out waiting for the user to confirm this nested interaction」 |
| 读取方式 | `process.env.CODEBUDDY_REPL_NESTED_TIMEOUT_MS`，非正整数时回退默认值 |
| 生效范围 | **仅 REPL 单元格内的嵌套交互**；对话层直接调用 `AskUserQuestion` 不走该超时 |
| 生效时机 | 会话启动时注入，**修改后需重启会话** |

> 该变量同时可由进程环境变量设置（优先级更高），`settings.json` 的 `env` 为项目级持久化方式。
- **无需填**：绑定本机的 `models.json`、`settings.local.json` **不外置**（留引擎根、git 忽略）——外置会跨机器失效且不宜入库。

### `memory.teamMemory.userId` 不写入项目侧共享文件

该键**不写入**项目侧 `settings.json`，交由 CodeBuddy 本机自动推导：

| 顺序 | 来源 |
|------|------|
| 1 | 环境变量 `CODEBUDDY_TEAMMATE_OWNER_KEY` |
| 2 | `settings.json` 的 `memory.teamMemory.userId`（**新项目不生成此键**） |
| 3 | `git config user.name` |
| 4 | 系统登录名 |

原因：`userId` 处于推导链第 2 位，**高于** `git user.name`（实测自 `dist/codebuddy.js` 的 `getTeamUserId()`）。若写入项目侧共享文件，所有使用者会被统一成同一标识，团队记忆写进同一个 `@<userId>/` 目录而串号。

个人需要固定标识时，写入 `.codebuddy/settings.local.json`（本机项目级，自动 git 忽略），**不改项目侧 `settings.json`**。

## 分层配置的填写说明

`coverage.project_config` 与 `comment.project_config` 是**分层配置的项目侧部分**：

- 引擎侧已提供通用部分（如注释检查的 `rules` 全部规则、覆盖率的算法参数与映射策略）。
- 项目侧**只需填项目相关项**（如覆盖率的 `runtimeRoots`/`namespaceMapping`/`realCoverage`，注释检查的 `exclude.paths`/`knownTerms`）。
- 读取时两层深度合并，**项目侧值覆盖引擎侧值，数组取并集**，无需在项目侧重复通用项。

## 填写完成的验证建议

- 格式检查：`python .codebuddy/lib/csharp/skills/csharp-format-checker/scripts/dotnet_format.py --help`（脚本能读到配置即无报错）。
- 审查目标收集：`python .codebuddy/lib/csharp/skills/csharp-code-review/scripts/collect_review_targets.py`。
- 提交摘要校验（脚本由 Git / SVN 两个提交技能共用，`--config-key` **必填**）：
  - Git：`python .codebuddy/skills/vcs/vcs-router/scripts/validate_commit_subject.py --config-key git_commit.config "<按该配置 pattern 生成的摘要>"`
  - SVN：`python .codebuddy/skills/vcs/vcs-router/scripts/validate_commit_subject.py --config-key svn_commit.config "<按该配置 pattern 生成的摘要>"`。
  - **摘要形态由配置的 `commit_subject.pattern` 决定**，两侧格式可以不同；示例里不写死任何形态，
    否则换项目/换 VCS 时示例本身就是错的。脚本退出码 3 表示 `pattern` / `types` 缺失、非法，**或仍是占位**
    （未接入 SVN 的项目保留索引生成的占位骨架即可，不必强行填写）。
- 覆盖率（静态分析小目标）：`python .codebuddy/lib/csharp/skills/csharp-test-coverage/scripts/check_coverage.py <某运行时文件> --no-save`。
