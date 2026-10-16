# Unity CLI 常用命令速查

> 本文件固化 `unity-pipeline` 技能常用命令清单，作为独立参考（不依赖上游 `com.unity.pipeline` 包的 README）。技能执行时以 `SKILL.md` 为准，本文件用于迁移/排障时快速查阅。

## CLI 与打开项目

```bash
# 环境检查（含缓存）
python .codebuddy/skills/unity-pipeline/scripts/check_unity_cli.py [--no-cache]

# 未安装时自动安装（离线优先 + 在线回退）
powershell -ExecutionPolicy Bypass -File "<技能目录>\tools\unity-cli-offline\install.ps1" [-Proxy <代理URL>]

# 打开项目（必须用 unity open，禁止直接启动 Unity.exe）
unity open <项目路径> --args "-automated"
# 常用参数：--editor-version <目标Unity版本> / --non-interactive / -e,--editor-path <路径>
```

## 实例控制

```bash
unity pipeline install            # 安装 pipeline 包到项目
unity pipeline list               # 列出实例 + 服务器可达性
unity command editor_status       # 编辑器服务器状态
```

## 自主编辑循环（编辑器）

```bash
unity command set_autotick --enable true      # 保活（失焦不节流），无头工作前必做
unity command recompile                        # 重编译（异步触发）
unity command recompile_status                 # 轮询至 completed / up_to_date；failed=true 读 errors
                                               # compilationFailed=true 表示编译失败抑制了域重载，勿据 up_to_date 判通过
unity command list_tests --mode editor         # 列出测试（mode: all | editor | playmode）
unity command run_tests --mode editor --filter MyFixture.MyTest
unity command run_tests --mode playmode --async_tests true   # playmode 必须异步
unity command run_tests --mode editor --async_tests true     # editor 预计 >30s 也必须异步
unity command test_status                       # 异步测试轮询；cancel_tests 中止

# 辅助脚本（替代手写轮询与内联解析）
python .codebuddy/skills/unity-pipeline/scripts/unity_wait.py --command recompile_status
python .codebuddy/skills/unity-pipeline/scripts/unity_test_summary.py --file Temp/pipeline_test_status.json
```

> **退出码语义**：`2` = 参数错误（什么都没执行，改命令行后重试）；`6` = 命令已执行但失败
> （或编辑器无法服务），重试同一调用无帮助。不要把 `2` 的调用原样重试，也不要在 `6` 时改写命令行。

> **command 层超时**：`run_tests` 命令层硬超时约 30 秒，**editor 模式同样会命中**
> （性能/压实基准测试等）。预计总时长 > 30 秒的用例集一律 `--async_tests true` + 轮询 `test_status`；
> 同步调用仅用于秒级用例集。

> **编译结果正向确认**：`recompile` 触发后 `recompile_status` 可能立即返回 `completed`
> （复用上一轮编译状态，实测首次轮询即 completed），仅凭该状态不足以证明改动已生效。
> 需要确认时用 `eval` 做正向验证：
> `unity command eval "return typeof(<新命名空间类型>).FullName;"`，
> 返回预期全名即证明新程序集已加载；未确认生效前不要进入后续验证步骤。
>
> **「是否真的重编译」的独立探针**（比 `recompile_status` 可靠）：
> ```bash
> # 探针 1：域哈希，重载后会变化
> unity command eval --code "return \"Hash=\" + System.AppDomain.CurrentDomain.GetHashCode();"
> # 探针 2：域数据，重载后被清空
> unity command eval --code "System.AppDomain.CurrentDomain.SetData(\"Probe\",\"v1\"); return \"set\";"   # 重载前设置
> unity command eval --code "var d = System.AppDomain.CurrentDomain.GetData(\"Probe\"); return d == null ? \"GONE\" : d;"
> # 探针 3：DLL 时间戳
> ls -la --time-style=full-iso Library/ScriptAssemblies/<程序集>.dll
> ```
> 实测场景：`recompile_status` 首次轮询即报 `completed`，但 `AppDomain` 哈希与 `DomainId` 恒定、
> DLL 时间戳仍为旧值——域实际**未**重载，改动未生效。

> **`up_to_date` 不可信（DLL 缺失场景）**：比「复用旧状态」更严重的一种情况是——目标程序集 DLL
> **根本不存在**，Unity 仍可能报 `"No scripts needed recompilation."` / `up_to_date` 并拒编。
> 此时测试会**按旧行为运行**，表现为「测试失败但源码明显正确」。
>
> 排障步骤：
> 1. 比对 `Library/ScriptAssemblies/<程序集>.dll` 与源文件的 mtime，DLL 更旧即过期；
> 2. **判定跑在旧程序集上的快捷方法**：取失败消息中的文本 grep 当前源码，**计数为 0** 即证实用例
>    代码根本不是当前版本（此时断言错误、消息文本都会是旧版的）；
> 3. 强制重建：删除残留的 `.pdb`、触碰对应 `.asmdef`、改动源文件触发重扫；必要时用 `eval` 正向验证。
> 4. 仅当 `recompile_status` 报 `failed=true` 时才去读 `errors`；`up_to_date` 需结合上一条交叉确认。

## 触发脚本域重载（domain reload）

需要让 Unity **重新加载脚本域**时（场景：运行时开启 `Coverage.enabled`、切换预处理符号、
让 `[InitializeOnLoad]` 静态构造重跑），必须用：

```bash
unity command eval --code "UnityEditor.EditorUtility.RequestScriptReload(); return \"requested\";"
```

> **`CompilationPipeline.RequestScriptCompilation()` 不会触发域重载**（实测：调用后 `AppDomain`
> 哈希与 `DomainId` 均不变）。该方法只请求重新编译程序集，不等价于重载脚本域。
>
> **域重载必然重编译**：`RequestScriptReload()` 会连带触发脚本重编译，故无需先单独调 `recompile`。
>
> **重载为多轮异步过程**：期间 `unity command` 会返回 `Connection reset by server`（属正常现象），
> 需等待并重试；实测从触发到可稳定响应约 20–40 秒。
>
> **重载完成判据**：用上文探针 1/2 确认域哈希变化与探针清空，**不要**只看 `recompile_status`。

> **域重载会反写偏好文件**：Unity 的 `Settings` 单例在域重载时会把**内存缓存**序列化回写磁盘。
> 因此「先改配置文件 → 再触发重载」的顺序**会被覆盖**；正确顺序是「经官方 setter 改内存（同时落盘）
> → 再触发重载」。实测：只改文件不重载时保持 20 秒不变；一旦重载即被回写为内存中的旧值。

## 代码重载（需游戏运行）

```bash
unity command editor_play                       # 进入编辑器播放模式
unity command reload_file --filename Assets/Example.cs [--pdb]     # Assembly.Load 后端，完整 C#
unity command reload_file_editor_interpreter --filename Assets/Example.cs   # 解释器后端（IL2CPP 安全）
unity command reload_file_player_interpreter --filename Assets/Scripts --player -1  # 推送到连接的 Player
# codereload_status / cleanup_codereload 仅 Player（RuntimeOnly），编辑器播放模式不可用
```

> **0.6.0 起改名**：`[HotReload]` → `[CodeReload]`（命名空间 `Unity.Pipeline.CodeReload`）、
> `hotreload_status` → `codereload_status`、`cleanup_hotreload` → `cleanup_codereload`。
>
> **`reload_file_override` 与 `[HotReloadWithOverrides]` / `HotReloadHelper` 已被移除**（0.6.0）：
> 改用原地替换——打 `[CodeReload]` 标签后直接编辑方法体，再 `reload_file`。
>
> 约束：方法须为 `public`（实例或静态）、返回 `void` 或 `IEnumerator`；`Assembly.Load` 后端的方法体
> 只能访问宿主类型的 **public** 成员（解释器后端无此限制）。调试需 `--pdb`（默认不生成符号）。
>
> `[OnCodeReload]` 标签的无参实例方法在每次重载落地后于每个存活实例上触发，可用来重启长生命周期协程。

## 批量构建与求值

```bash
# 构造器模式：代码写进 Assets/ 之外的 .cs 文件，执行具名静态入口（内存编译，免域重载）
unity command run_script --file AgentScripts/Build.cs --entry Build.All
unity command run_script --file AgentScripts/Build.cs --dry_run true      # 仅编译检查
unity command run_script --file AgentScripts/Build.cs --entry Build.All --args '[3, "Green"]'

# 事务化批处理：单请求最多 200 个有序操作，支持跨操作引用 $<id>.<jsonPath>
unity command batch --operations '[{"id":"go","command":"...","params":{...}}]'
unity command batch --operations '...' --dry_run true

# 服务端条件等待（替代客户端轮询循环）
unity command wait_for --condition '{"member":"UnityEditor.EditorApplication.isPlaying"}' --timeout_s 60
unity command wait_for --condition '...' --async true     # 长等待/依赖后续命令时必须异步
unity command wait_status                                  # 异步等待轮询；wait_cancel 取消

# eval 使用遥测聚合（API 指纹频次、单行占比、错误率、命令覆盖建议）
unity command report_evals --top 20
```

> **`run_script` 优先于 `eval`**：多行代码一律写进磁盘文件用 `run_script`，不要把多行转义 C# 字符串
> 塞进 `eval`。`run_script` 相对路径以项目根（`Assets/` 的父目录）为基准解析，入口可为
> `async Task`/`Task<T>`。
>
> **`wait_for` 同步模式会占住 exec 队列**——条件若依赖你尚未发出的命令会自死锁。仅当等待 < 30 秒
> 且条件不依赖后续命令时用同步，其他一律 `--async true`。

## 控制台输出

```bash
unity command console --tail 50 --level warn           # 取最近 50 条，最低 warn 级别
unity command console --since <cursor> --since_session <session>   # 跟随：只取更新条目
unity command console_status                            # 只要计数与编译失败标志，无条目负载
unity command clear_console                             # 清空捕获缓冲（编辑器下也清 Unity 控制台）
```

> **0.7.0 移除 `get_console_logs`**（与 `console` 各自维护第二份缓冲，导致日志重复捕获、
> `clear_console` 只清一份）。统一用 `console`；其 `logType` 字段提供原本的精确 `LogType`，
> 另有 `counts`（分级计数）与 `groundTruth`（编辑器自身编译失败标志/控制台计数）。
> 三个命令同属运行时程序集，Player 构建中也可用。

## C# 求值（编辑器 & 运行时）

```bash
unity command eval "return 2 + 2;"
unity command eval_file Assets/Scratch.cs
```

> **5 秒主线程硬超时**：`eval` / `eval_file` 有约 **5 秒**的主线程超时，超时原文为
> `Pipeline server returned 400 Bad Request: ... Main thread operation timed out after 5000ms`。
> 因此**长耗时操作不可用 `eval` 触发**——例如运行代码生成器、批量数据计算等，改用对应
> Editor 菜单入口或后台方式执行。
>
> **超时不等于未执行**：`eval` 返回超时后，被调用的操作**可能已在主线程继续并完成**。
> 应等待若干秒后**检查产物或状态**再判断，不要据超时直接判定失败并重跑（会造成重复执行）。

## 项目审计（编辑器，需 Project Auditor + 规则）

```bash
unity command audit                              # 可选：--categories Code,ProjectSetting --output my.csv
unity command audit_status                       # 轮询至终态 completed / failed / unavailable / interrupted
# 需要 Project Auditor；内置模块版编辑器另装规则包：
unity command package_add --identifier com.unity.project-auditor-rules --confirm true
# 终态 completed 返回 csvPath + issueCount；busy=已有扫描在跑；无取消命令
```

## 多实例定位

```bash
unity command <cmd> --instance host:port          # 通用定位方式
unity command <cmd> --project-path <路径>          # 定位编辑器实例
unity command <cmd> --runtime <可执行名>            # 定位 Player
unity command <cmd> --runtime-path <端口文件目录>
```

## 关键约束速记

1. **先 `set_autotick`**，否则失焦时 recompile/test 可能挂起。
2. **异步命令必须轮询，且按 JSON 字段判终态**：recompile→recompile_status、run_tests(async)→test_status。
   **禁止关键字匹配整段 JSON**（`"failed":false` 会被 `failed` 误命中而提前退出）；取 `status` 字段值比较。
3. **`open` 会阻塞到编辑器退出**：用后台方式执行，勿等待其返回。
4. **playmode 测试必须 `--async_tests true`**；`--mode all` 不支持异步。
5. **`run_tests` 命令层 30s 超时**：预计总时长 > 30 秒的用例集（**含 editor 模式**）也必须
   `--async_tests true` + 轮询 `test_status`，否则报 `timed out after 30000ms`。
6. **run_tests 失败时结果可能不透明**：用更窄 `--filter` 重跑或查 Test Runner 日志。
7. **仅 Player 的命令**（log/set_timescale/runtime_status/codereload_status/cleanup_codereload）需要开发版 Player。
8. **代理**：CLI 全局 `--proxy <url>` 或环境变量 `UNITY_PROXY`；安装脚本 `-Proxy`。
9. **审计扫描**：`audit` 单扫描限制（再触发返回 busy）、无取消；`interrupted`（域重载中断）直接重跑即可。
10. **多实例定位**：通用 `--instance host:port`；编辑器 `--project-path`；Player `--runtime` / `--runtime-path`。
11. **`eval` 有 5s 主线程超时**：长耗时操作（如代码生成器）不可用它触发；超时≠未执行，须等待后查产物。
12. **`up_to_date` / `completed` 不可信**：目标 DLL 缺失时 Unity 仍可能报 `up_to_date` 并拒编，
    导致测试按旧行为运行。排障捷径：用失败消息文本 grep 当前源码，**计数为 0** 即跑在旧程序集上。
    0.7.0 起 `recompile_status` 新增 `compilationFailed` 字段，编译失败时不再误报 `up_to_date`。
13. **退出码语义**：`2` = 参数错误（改命令行后重试）；`6` = 已执行但失败（重试无意义）。
14. **`wait_for` 同步模式占住 exec 队列**：条件依赖尚未发出的命令时会自死锁。长等待用 `--async true`。
15. **发布构建不含运行时程序集**（0.7.0 起）：需加 `ENABLE_RUNTIME_PIPELINE` 宏才能在非开发版 Player 启用。
    `[CodeReload]` 位于独立的 `Unity.Pipeline.Attributes` 程序集，发布构建中仍可编译（执行原方法体）。

## 辅助脚本

| 脚本 | 用途 | 退出码 |
|------|------|--------|
| `scripts/unity_wait.py` | 异步命令轮询至终态（按字段判定） | `0` 终态 / `1` 失败态 / `2` 超时 |
| `scripts/unity_test_summary.py` | 测试结果归一化（摘要 + 失败清单） | `0` 全通过 / `1` 有失败 / `2` 解析失败 |
| `scripts/unity_version_check.py` | 编辑器版本与项目声明版本一致性检查 | `0` 一致 / `1` 不一致 / `2` 无法确定 |
