# 项目配置填写指导（fill-guide）

本文件是 `codebuddy-init` 阶段四「按项目情况填写」的**填写指导入口**：当用户选择「立即填写」时，逐项按本文件指向的技能配置指南进行探测与填写。

## 通用原则

1. **实际探测，不套经验值**：每项填写前必须读取项目实际内容（解决方案/工程文件、目录结构、程序集清单、`manifest.json`、`.editorconfig` 等），不得凭记忆或套用其他项目的值。
2. **探测不到就问**：无法从项目自动探测的值（如团队约定的提交 type 枚举、术语白名单的用户偏好），**向用户询问**，不猜测。
3. **填写后复述确认**：写入前向用户复述「键 → 值」供确认。
4. **口径一致**：同一份清单出现在多处时（如排除目录）须同步，避免漂移。
5. **占位未填即报错**：保留 `<...>` 的配置在首次运行对应技能时会报错——这是**预期行为**（配置缺失即报错），不是缺陷。

## 逐项指导

| 逻辑名 | 项目侧文件 | 填写指导 | 探测线索 |
|--------|-----------|---------|---------|
| `format_checker.config` | `skills/csharp-format-checker/config.json` | `.codebuddy/skills/csharp-format-checker/references/config-guide.md` | 解决方案/工程文件（`.slnx`/`.sln`/`.csproj`）；三方库与生成代码目录（`Assets/Plugins`、`Library/PackageCache`、各 `Gen/`、`Generated/`）；项目根 `.editorconfig` 必须存在 |
| `code_review.config` | `skills/csharp-code-review/config.json` | 该技能 `SKILL.md` 与 `references/` | 纳入审查的文件模式（默认 `*.cs`）；排除清单（生成目录、三方库、审查范围外目录）；**口径须与 format-checker 的 `exclude_dirs` 一致** |
| `git_commit.config` | `skills/git-commit/config.json` | `.codebuddy/skills/git-commit/references/project-config.md` §0 | 团队提交 type 枚举、subject/scope 长度上限、subject 语言 |
| `git_commit.project_config` | `skills/git-commit/project-config.md` | 该文件自身的章节骨架 + 引擎侧 `references/project-config.md` §1.5/§2 | 项目目录结构 → scope 映射；**提交/推送发起权**（`commit_initiation`/`push_initiation`：`user_only` 或 `llm_allowed`）；审查门禁参数（`enabled`/`file_patterns`/`exclude_patterns`/`blocking_level`）；H1 钩子步骤 |
| `coverage.project_config` | `skills/csharp-test-coverage/tools/CSharpTestCoverage/coverage_config.project.json` | `.codebuddy/skills/csharp-test-coverage/references/config-guide.md` | 运行时源码根、扫描范围、UPM 包名前缀 → 命名空间映射、真实采集程序集前缀、覆盖率产物目录 |
| `comment.project_config` | `skills/csharp-comment-checker/tools/CSharpCommentChecker/comment_config.project.json` | `.codebuddy/skills/csharp-comment-checker/references/config-guide.md` | 排除目录（三方库、生成代码）；保留英文的项目术语（自研库名、选用库名）；`rules` 通用规则在引擎侧，无需填写 |
| `coverage.golden_samples` | `skills/csharp-test-coverage/scripts/golden_samples.json` | 该技能 `SKILL.md` | 项目已知正确的覆盖率样本（目标路径 + 期望）；新项目可先留空 `samples: []`，后续按需补充 |
| `coverage.trigger_cases` | `skills/csharp-test-coverage/scripts/trigger_cases.json` | `skills/csharp-test-coverage/references/` | 触发评估用例（应/不应触发样例）；含项目路径的用例仅为举例，可替换 |
| `format_checker.trigger_cases` | `skills/csharp-format-checker/evals/trigger/trigger_cases.json` | `skills/csharp-format-checker/references/` | 同上 |
| `codebuddy.settings`（根级软链接外置） | `settings.json`（项目根 `.codebuddy.project/configs/settings.json`） | 本节下方「根级软链接外置文件」 | `language`（界面/回复语言）；`memory.teamMemory.userId`（团队成员标识，通常取 git 用户名）；`permissions`/`enabledPlugins` 按团队约定；**不含凭据**（凭据在引擎根 `models.json`/`settings.local.json`，不外置） |
| `rule_shells.*`（规则项目事实正文） | `rules/**` | 各技能 `references/` 与 `rules/` 薄壳内的强制条款 | 项目目录结构、包依赖、启动流程、第三方依赖、测试目录现状、LSP 受影响程序集等**项目事实**；须实测核对（依赖方向读 asmdef、版本读 manifest、忽略范围用 `git check-ignore` 验证） |

## 运行时产物目录（无需填写）

索引 `artifacts.dirs` 声明的产物目录（各技能 `check_logs/`、`.cache/`、根 `.vcs-lock/`）由 `codebuddy-init`
创建为空目录，**无需填写任何值**；它们由项目侧 `.gitignore` 忽略、不入库。清理用项目侧
`cleanup-caches.cmd`。本项不属"填写"范畴，仅作说明。

## 根级软链接外置文件（root_symlinks.entries）

索引 `root_symlinks.entries` 声明的文件（如 `settings.json`）是**项目级单文件**，外置为：
项目侧源文件 `.codebuddy.project/configs/settings.json` + 引擎内软链接 `.codebuddy/settings.json`。
`codebuddy-init` 生成源文件骨架并建链；**CodeBuddy 本体经软链接直接读取**（无需脚本解析），实测其会解引用符号链接。

- **需填**：`language`、`memory.teamMemory.userId` 等**项目级**值（不含凭据）。
- **无需填**：绑定本机的 `models.json`、`settings.local.json` **不外置**（留引擎根、git 忽略）——外置会跨机器失效且不宜入库。

## 分层配置的填写说明

`coverage.project_config` 与 `comment.project_config` 是**分层配置的项目侧部分**：

- 引擎侧已提供通用部分（如注释检查的 `rules` 全部规则、覆盖率的算法参数与映射策略）。
- 项目侧**只需填项目相关项**（如覆盖率的 `runtimeRoots`/`namespaceMapping`/`realCoverage`，注释检查的 `exclude.paths`/`knownTerms`）。
- 读取时两层深度合并，**项目侧值覆盖引擎侧值，数组取并集**，无需在项目侧重复通用项。

## 填写完成的验证建议

- 格式检查：`python .codebuddy/skills/csharp-format-checker/scripts/dotnet_format.py --help`（脚本能读到配置即无报错）。
- 审查目标收集：`python .codebuddy/skills/csharp-code-review/scripts/collect_review_targets.py`。
- 提交摘要校验：`python .codebuddy/skills/git-commit/scripts/validate_commit_subject.py "feat(Core): 示例"`。
- 覆盖率（静态分析小目标）：`python .codebuddy/skills/csharp-test-coverage/scripts/check_coverage.py <某运行时文件> --no-save`。
