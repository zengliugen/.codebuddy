# unity-pipeline 变更记录

> **本文件由引擎仓库维护，不是上游内容。** 上游原文仅作语义对照，正文以本仓库为准。

本包维护档位：**本地维护分支**（`packs.json` 分类「领域（本地维护）」；`agents/interface.yaml`
的 `source.origin` 为 `local`、`editable` 为 `full`）。

| 项 | 只读 vendor | 本包（本地维护） |
|---|---|---|
| 正文语言 | 保留上游原文 | 已中文化，受语言规则约束 |
| 可否改造 | 仅最小可行性补丁 | 允许本地改造 |
| 与上游关系 | 需与上游逐字比对 | 正文以本仓库为准，无需逐字比对 |

来源：com.unity.pipeline 0.9.0-exp.1（上游已把 agent skill 移出包，正文以 `Documentation~/` 与
`Runtime/Common/CommandNames.cs` 为准重建）。本文件为项目内可编辑副本。

## 记录规范

- 一个变更一节，**按时间倒序**，标题为 `## YYYY-MM-DD 主题`。
- 每节写明**为什么改**；只记措辞调整的不写。跨版本同步在节内按条目编号列出。
- 纯错别字修订不单独成节。

## 改动前必读

1. **本文件是唯一细节来源**，其它文档只做入口索引，不复制其内容。
2. 上游仍可能更新 `Documentation~/` 与 `Runtime/Common/CommandNames.cs`；升级时按「从 0.7.0 同步到 0.9.0」一节重放同步。
3. `reports/` 下是脚本生成产物，标题与字段名随生成器输出为英文，**不计入正文语言范围**；
   需要中文报告时改生成器，不要手改产物（会被下次生成覆盖）。
4. 不译之物：frontmatter 键名、命令名、JSON 字段名、路径——翻译即失效。
5. 改完跑 `check_manifest.py` 与 `pack_install.py status`，均须退出码 0。

## 相对上游保留的本地改动

- 新增「打开 Unity 项目」章节（必须 `unity open`，禁止直接启动 Unity.exe）；
- CLI 安装检查与离线自动安装（0.1 / 0.2 / 0.3）；
- `--runtime` / `--runtime-path` 实例定位；`script eval` 在编辑器上同样可用；
- 异步命令「按 JSON 字段判终态」，禁止关键字匹配；`unity_wait.py` 等辅助脚本；
- 命令层超时的可覆盖写法（`unity command --timeout <秒>`）。

## 2026-10-29 文档归位：PATCHES.md 与 references/cli-changelog.md 合并到根目录

| 项 | 内容 |
|---|---|
| 文件 | 新增根目录 `CHANGELOG.md`；删除 `PATCHES.md` 与 `references/cli-changelog.md` |
| 原因 | 同一类信息散在两处、文件名不一致，且不同包的记录文件放法各异，检索与维护都要先猜位置 |
| 补丁 | 维护档位、改动前必读、相对上游改动、版本同步记录合并为单一 `CHANGELOG.md` |
| 边界 | 只搬内容不改语义；引擎 `README.md` 的 vendor 表引用同步更新 |

## 2026-10-27 转为本项目本地维护分支（正文已中文化）

| 项 | 内容 |
|---|---|
| 元数据 | `agents/interface.yaml` 的 `source`：`origin` 由 `third-party` 改为 `local`、`editable` 由 `local-patches-documented` 改为 `full`，新增 `maintenance_note` |
| 正文语言 | `SKILL.md`、`rules/unity-pipeline/`、`rules/unity-pipeline.entry/`、`references/` 已全部为简体中文，此后受 `rules/core/core-language/` 约束，不再享有 vendor 语言豁免 |
| 正文范围勘定 | `reports/` 下产物标题与字段名随生成器输出为英文，**不计入正文语言范围**，也不手改 |
| 与上游关系 | 上游仍可能更新，升级时按本文件重放同步；正文措辞以本仓库为准，无需逐字比对 |
| 判据 | `source.origin=local` 且 `editable=full` 即本地维护分支，引擎 `README.md` 的 vendor 表同步标注 |

## 2026-10-21 从 0.7.0-exp.1 同步到 0.9.0-exp.1（0.8 + 0.9 一并吸收）

1. **命令改为分组命名**：一律 `unity command "<分组> <名称>"`（**整体一个参数，必须加引号**），
   0.7 的扁平名全部失效。
   `recompile`→`script recompile`、`run_tests`→`test run`、`batch`→`job batch`、
   `wait_for`→`job wait`、`eval`→`script eval`、`run_script`→`script run`、
   `console`→`console get`、`audit`→`diagnostics run_audit`、`editor_status`→`editor status`、
   `set_autotick`→`editor set_auto_tick`、`screenshot`→`capture screenshot` 等。
2. **代码重载改名为方法重载**：`[CodeReload]`→`[MethodReload]`、`[OnCodeReload]`→`[OnMethodReloaded]`、
   命名空间 `Unity.Pipeline.CodeReload`→`Unity.Pipeline.MethodReload`；
   `reload_file`→`script.methodreload reload`、`*_interpreter`→`reload_editor`/`reload_player`、
   `codereload_status`→`script.methodreload status`、`cleanup_codereload`→`script.methodreload cleanup`；
   新增 `script.methodreload generate_link_xml`（IL2CPP 裁剪用）。
3. **超时改为按命令声明**（秒），默认 60 秒；CLI `--timeout <秒>` 可覆盖，不再有写死的 30 秒硬超时。
4. 服务器只绑定 `127.0.0.1`，并用 Host 头校验挡住 DNS 重绑定；客户端不能用 `localhost`。
5. 实例描述符统一列出所有连接方式（`endpoints`），心跳每 15 秒刷新；`-automated` 缺失改为
   描述符 `info` 字段提示（不再是控制台警告）。
6. 新增探索类命令：`build list_platforms` / `create_profile` / `set_profile`、
   `editor.playmode set_run_in_background`、`console write`、`script.methodreload generate_link_xml`、
   `authoring get_root` / `set_root`、`editor search`、`runtime simulate_key` / `simulate_pointer`。
7. 每个命令都接受 `--verbose` 与 `--omit-nulls`；`/api/commands` 支持按组过滤、分组与索引。
8. 构建门控改为两个开关两条宏：`ENABLE_RUNTIME_PIPELINE_DEV`（开发/带插桩构建）与
   `ENABLE_RUNTIME_PIPELINE`（发布构建），旧版单条 `ENABLE_RUNTIME_PIPELINE` 语义已变。
9. 样例迁到独立包 `com.unity.pipeline.samples`。

**之后若再升级包**，以 `Library/PackageCache/com.unity.pipeline@<hash>/Documentation~/` 与
`Runtime/Common/CommandNames.cs` 为准重放本同步。
