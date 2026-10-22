# Unity CLI 常用命令速查（0.9 分组命名）

> 本文件固化 `unity-pipeline` 技能的常用命令清单，作为独立参考（不依赖上游 `com.unity.pipeline` 包的文档）。技能执行时以 `SKILL.md` 为准，本文件用于迁移/排障时快速查阅。
>
> **0.9 起命令一律写成 `unity command "<分组> <名称>"`**（整串一个参数，引号不可省），0.7 的扁平名（`recompile` / `run_tests` / `eval` / `console` 等）全部失效。

## CLI 与打开项目

```bash
# 环境检查（含缓存）
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/check_unity_cli.py [--no-cache]

# 未安装时自动安装（离线优先 + 在线回退）
powershell -ExecutionPolicy Bypass -File "<技能目录>\tools\unity-cli-offline\install.ps1" [-Proxy <代理URL>]

# 打开项目（必须用 unity open，禁止直接启动 Unity.exe）
unity open <项目路径> --args "-automated"
# 常用参数：--editor-version <目标Unity版本> / --non-interactive / -e,--editor-path <路径>
```

## 实例与命令发现

```bash
unity pipeline install            # 安装 pipeline 包到项目
unity pipeline upgrade            # 已装包落后时升级到最新
unity pipeline list               # 列出实例 + 服务器可达性 + 包版本
unity command                     # 列出所有可用命令与参数（含所属分组）
unity command --help              # 查看 CLI 侧选项（--project-path / --runtime / --timeout）
unity status [--json]             # 列出已连接实例（端口/项目/版本/PID/状态）
unity command "editor status"       # 编辑器服务器状态
```

## 自主编辑循环（编辑器）

```bash
unity command "editor set_auto_tick" --enable true   # 保活（失焦不节流），无头工作前必做
unity command "script recompile"                     # 重编译（异步触发）
unity command "script recompile_status"              # 轮询至 completed / up_to_date；failed=true 读 errors
                                                   # compilationFailed=true 表示编译失败抑制了域重载，勿据 up_to_date 判通过
unity command "test list" --mode editor              # 列出测试（mode: all | editor | playmode）
unity command "test run" --mode editor --filter MyFixture.MyTest
unity command "test run" --mode playmode --async_tests true   # playmode 必须异步
unity command "test run" --mode editor --async_tests true     # 预计 >30s 也必须异步
unity command "test status"                          # 异步测试轮询；test cancel 中止

# 辅助脚本（替代手写轮询与内联解析；分组命令名整体加引号）
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_wait.py --command "script recompile_status"
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_test_summary.py --file Temp/pipeline_test_status.json
```

> **超时**：每个请求只有一个超时，按「请求顶层 timeout（毫秒）→ 命令自身 timeout 参数 → 命令默认值」
> 解析。CLI `--timeout` **默认 30 秒**且覆盖命令默认值，所以长同步调用要么显式放宽
> （`unity command --timeout 900 "test run" --mode editor ...`），要么改异步 + 轮询。
> `job wait` / `job batch` / `test run` / `script run` 会在自身预算内提前收尾，不会硬断连接。

> **退出码语义**：`2` = 参数错误（什么都没执行，改命令行后重试）；`6` = 命令已执行但失败
> （或编辑器无法服务），重试同一调用无帮助。不要把 `2` 的调用原样重试，也不要在 `6` 时改写命令行。

> **编译结果正向确认**：`script recompile` 触发后 `script recompile_status` 可能立即返回 `completed`
> （复用上一轮编译状态，实测首次轮询即 completed），仅凭该状态不足以证明改动已生效。
> 需要确认时用 `script eval` 做正向验证：
> `unity command "script eval" "return typeof(<新命名空间类型>).FullName;"`，
> 返回预期全名即证明新程序集已加载；未确认生效前不要进入后续验证步骤。
>
> **「是否真的重编译」的独立探针**（比 `script recompile_status` 可靠）：
> ```bash
> # 探针 1：域哈希，重载后会变化
> unity command "script eval" --code "return \"Hash=\" + System.AppDomain.CurrentDomain.GetHashCode();"
> # 探针 2：域数据，重载后被清空
> unity command "script eval" --code "System.AppDomain.CurrentDomain.SetData(\"Probe\",\"v1\"); return \"set\";"   # 重载前设置
> unity command "script eval" --code "var d = System.AppDomain.CurrentDomain.GetData(\"Probe\"); return d == null ? \"GONE\" : d;"
> # 探针 3：DLL 时间戳
> ls -la --time-style=full-iso Library/ScriptAssemblies/<程序集>.dll
> ```
> 实测场景：`script recompile_status` 首次轮询即报 `completed`，但 `AppDomain` 哈希与 `DomainId` 恒定、
> DLL 时间戳仍为旧值——域实际**未**重载，改动未生效。

> **`up_to_date` 不可信（DLL 缺失场景）**：比「复用旧状态」更严重的一种情况是——目标程序集 DLL
> **根本不存在**，Unity 仍可能报 `"No scripts needed recompilation."` / `up_to_date` 并拒编。
> 此时测试会**按旧行为运行**，表现为「测试失败但源码明显正确」。
>
> 排障步骤：
> 1. 比对 `Library/ScriptAssemblies/<程序集>.dll` 与源文件的 mtime，DLL 更旧即过期；
> 2. **判定跑在旧程序集上的快捷方法**：取失败消息中的文本 grep 当前源码，**计数为 0** 即证实用例
>    代码根本不是当前版本（此时断言错误、消息文本都会是旧版的）；
> 3. 强制重建：删除残留的 `.pdb`、触碰对应 `.asmdef`、改动源文件触发重扫；必要时用 `script eval` 正向验证。
> 4. 仅当 `script recompile_status` 报 `failed=true` 时才去读 `errors`；`up_to_date` 需结合上一条交叉确认。

## 触发脚本域重载（domain reload）

需要让 Unity **重新加载脚本域**时（场景：运行时开启 `Coverage.enabled`、切换预处理符号、
让 `[InitializeOnLoad]` 静态构造重跑），必须用：

```bash
unity command "script eval" --code "UnityEditor.EditorUtility.RequestScriptReload(); return \"requested\";"
```

> **`CompilationPipeline.RequestScriptCompilation()` 不会触发域重载**（实测：调用后 `AppDomain`
> 哈希与 `DomainId` 均不变）。该方法只请求重新编译程序集，不等价于重载脚本域。
>
> **域重载必然重编译**：`RequestScriptReload()` 会连带触发脚本重编译，故无需先单独调 `script recompile`。
>
> **重载为多轮异步过程**：期间 `unity command` 会返回 `Connection reset by server`（属正常现象），
> 需等待并重试；实测从触发到可稳定响应约 20–40 秒。
>
> **重载完成判据**：用上文探针 1/2 确认域哈希变化与探针清空，**不要**只看 `script recompile_status`。

> **域重载会反写偏好文件**：Unity 的 `Settings` 单例在域重载时会把**内存缓存**序列化回写磁盘。
> 因此「先改配置文件 → 再触发重载」的顺序**会被覆盖**；正确顺序是「经官方 setter 改内存（同时落盘）
> → 再触发重载」。实测：只改文件不重载时保持 20 秒不变；一旦重载即被回写为内存中的旧值。

## 方法重载（需游戏运行）

```bash
unity command "editor.playmode start"                                  # 进入编辑器播放模式
unity command "script.methodreload reload" "Assets/Example.cs" [--pdb]             # Assembly.Load 后端，完整 C#
unity command "script.methodreload reload_editor" "Assets/Example.cs"              # 解释器后端（IL2CPP 安全）
unity command "script.methodreload reload_player" "Assets/Scripts" --player -1     # 推送到连接的 Player
unity command "script.methodreload status"                             # 已应用重载的方法与统计
unity command "script.methodreload cleanup" --assemblyDir <目录>        # 清理重载 DLL（会请求域重载）
unity command "script.methodreload generate_link_xml"                  # 生成 IL2CPP 裁剪用 link.xml
```

> **0.7 → 0.9 改名链**：`[HotReload]` → `[CodeReload]`（0.6）→ `[MethodReload]`（0.9）；
> `reload_file` → `script.methodreload reload`、`reload_file_editor_interpreter` → `script.methodreload reload_editor`、
> `reload_file_player_interpreter` → `script.methodreload reload_player`、
> `codereload_status` → `script.methodreload status`、`cleanup_codereload` → `script.methodreload cleanup`。
> 命名空间：`Unity.Pipeline.MethodReload`；回调 `[OnMethodReloaded]`。
>
> 约束：方法须为 `public`（实例或静态）、返回 `void` 或 `IEnumerator`；`Assembly.Load` 后端的方法体
> 只能访问宿主类型的 **public** 成员（解释器后端无此限制）。调试需 `--pdb`（默认不生成符号）。
>
> `status` / `cleanup` 在 0.9 起**编辑器服务器上也可用**（0.8 之前仅限 Player）；`cleanup` 会请求
> 域重载，因此在 `job batch` 内被排除。

## 批量构建与求值

```bash
# 构造器模式：代码写进 Assets/ 之外的 .cs 文件，执行具名静态入口（内存编译，免域重载）
unity command "script run" --file AgentScripts/Build.cs --entry Build.All
unity command "script run" --file AgentScripts/Build.cs --dry_run true      # 仅编译检查
unity command "script run" --file AgentScripts/Build.cs --entry Build.All --args '[3, "Green"]'

# 事务化批处理：单请求最多 200 个有序操作，command 写 "<分组> <名称>"，支持 $<id>.<jsonPath> 引用
unity command "job batch" --operations '[{"id":"go","command":"gameobject create","params":{"name":"Ball"}}]'
unity command "job batch" --operations '...' --dry_run true

# 服务端条件等待（替代客户端轮询循环）
unity command "job wait" --condition '{"member":"UnityEditor.EditorApplication.isPlaying","value":false}' --timeout 60
unity command "job wait" --condition '{"member":"...","value":1}' --async true   # 长等待/依赖后续命令时必须异步
unity command "job wait_status" --wait_id <id>              # 异步等待轮询；job wait_cancel 取消

# eval 使用遥测聚合（API 指纹频次、单行占比、错误率、命令覆盖建议）
unity command "diagnostics report_evals" --top 20
```

> **`script run` 优先于 `eval`**：多行代码一律写进磁盘文件用 `script run`，不要把多行转义 C# 字符串
> 塞进 `eval`。`script run` 相对路径以项目根（`Assets/` 的父目录）为基准解析，入口可为
> `async Task`/`Task<T>`。
>
> **`op=equals`（默认）时 `value` 必填**——漏传会报 `condition.value is required for op 'equals'`；
> 要比 null 就显式写 `"value": null`。仅 `op=changed` 不需要 `value`。
>
> **`job wait` 同步模式会占住 exec 队列**——条件若依赖你尚未发出的命令会自死锁。仅当等待 < 30 秒
> 且条件不依赖后续命令时用同步，其他一律 `--async true`。终态按 `state` 字段判定
> （`pending` 之外即终态）。

## 控制台输出

```bash
unity command "console get" --tail 50 --level warn           # 取最近 50 条，最低 warn 级别
unity command "console get" --since <cursor> --since_session <session>   # 跟随：只取更新条目
unity command "console status"                               # 只要计数与编译失败标志，无条目负载
unity command "console clear"                                # 清空捕获缓冲（编辑器下也清 Unity 控制台）
unity command "console write" --message "..." --level info    # 由服务端写日志（tag runtime）
```

> **命令改名**：`console` → `console get`、`console_status` → `console status`、
> `clear_console` → `console clear`。三者同属运行时程序集，Player 构建中也可用。
> 响应另带 `counts`（分级计数）与 `groundTruth`（编辑器自身编译失败标志/控制台计数）。
> 编辑器编译错误是粘性条目，Unity 自身 clear 会跳过；`console clear` 保留游标，跟随方下次轮询见 `dropped=true`。

## C# 求值（编辑器 & 运行时）

```bash
unity command "script eval" "return 2 + 2;"
unity command "script eval_file" Assets/Scratch.cs
```

> **主线程超时按命令声明**（`timeout` 单位为**秒**，`script eval` 默认 30），超时原文为
> `Main thread operation timed out after <n>ms`。需要更长时显式传 `--timeout <秒>`；
> 但**长耗时批处理仍应改用 `script run` 或 Editor 菜单入口**，不要靠加大 eval 超时硬扛。
>
> **超时不等于未执行**：`eval` 返回超时后，被调用的操作**可能已在主线程继续并完成**。
> 应等待若干秒后**检查产物或状态**再判断，不要据超时直接判定失败并重跑（会造成重复执行）。

## 项目审计（编辑器，需 Project Auditor + 规则）

```bash
unity command "diagnostics run_audit"              # 可选：--categories Code,ProjectSetting --output my.csv
unity command "diagnostics audit_status"           # 轮询至终态 completed / failed / unavailable / interrupted
# 需要 Project Auditor；内置模块版编辑器另装规则包：
unity command "package add" --identifier com.unity.project-auditor-rules --confirm true
# 终态 completed 返回 csvPath + issueCount；busy=已有扫描在跑；无取消命令
```

## 构建与包管理

```bash
unity command "build run" --confirm true                                    # 异步构建，轮询 build status
unity command "build status"                                                # idle | queued | building | completed
unity command "build.target list"                                           # 列目标平台与是否已安装
unity command "build.target switch" --target StandaloneWindows64 --confirm true   # 轮询 switch_status
unity command "build.target switch_status"
unity command "build list_platforms"                                        # Build Profile 可选的平台（Unity 6）
unity command "build create_profile" --name "Meta Quest" --platform "Meta Quest"
unity command "build set_profile" --name "Meta Quest" --scriptingDefines '["QUEST"]'

unity command "package list" --scope installed
unity command "package search" --query <关键字>
unity command "package add" --identifier com.unity.foo@1.2.3 --confirm true   # 默认异步，轮询 package status
unity command "package status"
```

## 多实例定位

```bash
unity command "<分组> <名称>" --project-path <路径>          # 定位编辑器实例（位置前后皆可）
unity status --project-path <路径子串>                     # 先确认实例与端口
unity command --runtime <可执行名> runtime status          # 定位 Player（写在 command 之后、分组之前）
unity command --runtime-path <端口文件目录> runtime status
```

## 关键约束速记

1. **先 `editor set_auto_tick`**，否则失焦时重编译/测试可能挂起。播放模式下另可
   `editor.playmode set_run_in_background --enable true`。
2. **异步命令必须轮询，且按 JSON 字段判终态**：`script recompile`→`script recompile_status`、
   `test run --async_tests`→`test status`、`package add`→`package status`、`build run`→`build status`。
   **禁止关键字匹配整段 JSON**（`"failed":false` 会被 `failed` 误命中而提前退出）；取 `status` 字段值比较。
3. **`open` 会阻塞到编辑器退出**：用后台方式执行，勿等待其返回。
4. **playmode 测试必须 `--async_tests true`**；`--mode all` 不支持异步。
5. **超时按命令声明、CLI 可覆盖**：`unity command --timeout <秒>` 默认 30 秒并覆盖命令默认值；
   长同步调用要么放宽 `--timeout`，要么改异步 + 轮询。
6. **`test run` 失败时结果可能不透明**：用更窄 `--filter` 重跑或查 Test Runner 日志。
7. **tag `runtime` 的命令**（`runtime *`、`console write`）需要开发版 Player；编辑器命令表里可见，
   但 `job batch` 会拒绝。
8. **代理**：CLI 全局 `--proxy <url>` 或环境变量 `UNITY_PROXY`；安装脚本 `-Proxy`。
9. **审计扫描**：单扫描限制（再触发返回 busy）、无取消；`interrupted`（域重载中断）直接重跑即可。
10. **多实例定位**：编辑器用 `--project-path`，Player 用 `--runtime` / `--runtime-path`（放在命令名前后均可）；`--instance host:port` **不是 CLI 选项**，会被透传成命令参数而被服务端忽略。
11. **`script eval` 超时按秒声明**（默认 30）：长耗时操作不可靠加大超时硬扛，改用 `script run`；
    超时≠未执行，须等待后查产物。
12. **`up_to_date` / `completed` 不可信**：目标 DLL 缺失时 Unity 仍可能报 `up_to_date` 并拒编，
    导致测试按旧行为运行。排障捷径：用失败消息文本 grep 当前源码，**计数为 0** 即跑在旧程序集上。
    `compilationFailed` 字段可在编译失败时避免误报 `up_to_date`。
13. **退出码语义**：`2` = 参数错误（改命令行后重试）；`6` = 已执行但失败（重试无意义）。
14. **`job wait` 同步模式占住 exec 队列**：条件依赖尚未发出的命令时会自死锁。长等待用 `--async true`；
    终态按 `state` 判定。
15. **构建门控两条宏**（0.9）：**Enable in Development & Profiled Builds** 写 `ENABLE_RUNTIME_PIPELINE_DEV`、
    **Enable in Release Builds** 写 `ENABLE_RUNTIME_PIPELINE`，二者独立。开关是唯一受支持方式，勿手写宏。
    `[MethodReload]` 位于独立 `Unity.Pipeline.Attributes` 程序集，发布构建中仍可编译（执行原方法体）。
16. **只走环回**：服务器绑定 `127.0.0.1` 并校验 Host 头，`localhost` 会被拒绝。

## 辅助脚本

| 脚本 | 用途 | 退出码 |
|------|------|--------|
| `scripts/unity_wait.py` | 异步命令轮询至终态（按字段判定） | `0` 终态 / `1` 失败态 / `2` 超时 |
| `scripts/unity_test_summary.py` | 测试结果归一化（摘要 + 失败清单） | `0` 全通过 / `1` 有失败 / `2` 解析失败 |
| `scripts/unity_version_check.py` | 编辑器版本与项目声明版本一致性检查 | `0` 一致 / `1` 不一致 / `2` 无法确定 |
