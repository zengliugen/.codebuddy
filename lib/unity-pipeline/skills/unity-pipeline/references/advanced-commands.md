# 高级命令：方法重载、批处理、控制台、审计

> 本文件由 `SKILL.md` 拆分而来，承载低频但高价值的进阶命令细节。日常编辑循环只需 SKILL.md 的 0–4 章。

## 5. 方法重载（Method Reload）

在**运行中**的游戏里修改玩法代码，无需域重载。游戏必须处于运行状态：进入编辑器播放模式
（`unity command "editor.playmode start"`）或运行开发版 Player。运行时 Pipeline 驱动（经
Project Settings > Pipeline > Runtime 启用）会在启动时自动发现带标签的方法（无需手动注册）。
本地请求会自动注入 token。

> **0.9 起改名**：`Code Reload` → `Method Reload`。`[CodeReload]` → `[MethodReload]`、
> `[OnCodeReload]` → `[OnMethodReloaded]`，命名空间 `Unity.Pipeline.MethodReload`。
> 命令 `reload_file` → `script.methodreload reload`，`reload_file_editor_interpreter` →
> `script.methodreload reload_editor`，`reload_file_player_interpreter` → `script.methodreload reload_player`，
> `codereload_status` → `script.methodreload status`，`cleanup_codereload` → `script.methodreload cleanup`。

`[MethodReload]` 属性必须在进入播放模式或构建 Player **之前**就打上——派发检查是编译期织入的。
可用的方法必须为 **`public`**（实例或静态），且返回 **`void` 或 `System.Collections.IEnumerator`**
（协程）；返回其他类型的方法会在构建期被跳过并告警。

两种后端：

| 命令 | 后端 | 适用位置 | 语言支持 | Player 是否需 Pipeline 服务器 |
|------|------|---------|---------|------------------------------|
| `script.methodreload reload` | `Assembly.Load`（默认） | 编辑器播放模式、桌面 Mono 开发构建 | 完整 C# | 需要 |
| `script.methodreload reload_editor` / `reload_player` | IlInterpreter | 任意开发构建，**含 IL2CPP** | C# 子集 | 不需要（`reload_player` 由编辑器推 IL） |

### 标记方法并应用

1. 在 MonoBehaviour 上给方法打 `[MethodReload]` 标签（命名空间 `Unity.Pipeline.MethodReload`）。
2. 在磁盘上编辑其方法体。
3. 应用（重复运行以迭代）：
   ```bash
   unity command "script.methodreload reload" "Assets/Example.cs"
   ```
   加 `--pdb` 可使其可调试——生成映射到你源码的可移植 PDB，使断点在原文件中生效
   （附加 IDE + 启用 Editor Attaching；以未优化方式编译）：
   ```bash
   unity command "script.methodreload reload" "Assets/Example.cs" --pdb
   ```

`script.methodreload reload` 参数：`filename`（必填）、`timeout`（秒，默认 60）、
`assemblyDir`（可选，将编译结果落盘，默认仅内存）、`pdb`（默认 false）。

**仅 public 成员**：`Assembly.Load` 后端重载的方法体只能访问宿主类型的 **public** 成员——编译产物
作为独立程序集加载，Mono 会强制可访问性，访问 private 字段/方法会在派发时失败；重载会预先拒绝
并列出违规成员。解释器后端无此限制（经反射可达 private 成员）。

### 解释器后端（IL2CPP 安全）

编辑器侧编译为 IL，由 IlInterpreter 在重载落点执行（编辑器进程或已连接的 Player），不使用
`Assembly.Load`，因此**在 IL2CPP Player 上也可用**。两个命令都在编辑器编译，故推送 Player 需要
编辑器运行且 Player 已连接。

```bash
# 在编辑器进程中经解释器执行（用于推送设备前先自检子集约束）
unity command "script.methodreload reload_editor" "Assets/Scripts/Player.cs"

# 编译并推送到已连接的开发版 Player（-1 = 广播，默认）
unity command "script.methodreload reload_player" "Assets/Scripts/Player.cs"
unity command "script.methodreload reload_player" "Assets/Scripts" --player 2   # 指定 Player id
```

`reload_player` 支持传入**文件夹**（递归遍历；仅编译提及 `MethodReload` 的 `.cs` 文件，
未提及的跳过而非报错）。推送使用 **Player 的**预处理符号，而非编辑器的。
它与监视器不同：**全量推送**文件里所有打了标签的方法，而不只是改动过的。

**解释器子集约束**（随包的 Roslyn 分析器以 MR002–MR023 标记，仅作用于 `[MethodReload]` 方法体）：
不支持 `await`/`Task`、`try`/`catch`/`finally`、`lock`、LINQ 查询语法、`checked`、`decimal`、
`dynamic`、反射类型、线程类型、`ref`/`out`/`in` 参数、`ref` 返回与局部、多维数组（交错数组可用）、
泛型方法、声明静态字段、值类型可空（`T?`）、文件内新类型声明、局部函数内 `yield`。
`long`/`ulong`/`double`、Lambda、闭包、委托、`goto`、字符串插值、协程 `yield` 均可用。

### 重载回调 `[OnMethodReloaded]`

给**无参数的实例方法**打 `[OnMethodReloaded]`，可在重载落地后执行初始化逻辑（相当于无域重载的
`OnEnable`）：每次有方法被替换时，在**每个存活实例**上（仅限 `UnityEngine.Object` 派生类型）
于主线程触发一次；异常只记录不传播。

```csharp
[OnMethodReloaded]
void OnMethodReloaded()
{
    StopAllCoroutines();
    StartCoroutine(MainLoop()); // 重启循环以拾取新方法体
}
```

典型用途：重启长生命周期协程、禁用再启用 MonoBehaviour、刷新由旧代码计算的缓存。

### 协程注意

`[MethodReload] IEnumerator` 方法在迭代器**创建时**拾取新方法体——每次 `StartCoroutine` 使用最新
重载，而**已在运行**的协程继续执行其创建时的版本（用 `[OnMethodReloaded]` 停掉并重启长生命周期协程）。

### 监管命令与监视器

- `unity command "script.methodreload status"` — 列出当前已应用重载的方法与统计。
- `unity command "script.methodreload cleanup" --assemblyDir <目录>` — 删除保存的重载程序集并回退到编译版本。
- `unity command "script.methodreload generate_link_xml"` — 生成 IL2CPP 裁剪用的 `link.xml`
  （`ProjectSettings/Packages/com.unity.pipeline/MethodReload.link.xml`），`--delete true` 删除。

> 0.9 起 `status` / `cleanup` 在**编辑器服务器上也可用**（0.8 之前仅限 Player）。
> `cleanup` 会请求域重载，因此在 `job batch` 内被排除。

`--assemblyDir <目录>` 可将编译 DLL 持久化到磁盘；`cleanup --assemblyDir <目录>` 清理旧 DLL。

监视器（**Window → Pipeline → Settings… → Method Reload Interpreter Watch → Start Watching**）可替代
手工推送：保存 `.cs` 即自动重载，覆盖整个 Assets 树，且总是走解释器后端。监视期间 **Auto-refresh 会被关闭**
（保存触发重载而非域重载；其他资源需手动 Ctrl+R 刷新），**Stop Watching** 恢复原设置。

### IL2CPP 裁剪

IL2CPP Player 只保留构建期没被裁掉的成员，重载代码调用被裁成员会抛异常（推送时会告警）。
在 Project Settings → Pipeline → Runtime → Method Reload 点 **Generate link.xml**（等价于
`script.methodreload generate_link_xml`）可一次性保留：游戏自身程序集引用到的引擎/包类型、
游戏自有类型、解释器宿主面、`[MethodReload]` 目标。它不保留整个模块或整个用户程序集；
大改代码后需重新生成。该文件只对**开发构建**生效。

## 6. 批量构建：`script run`（构造器模式）

批量工作——创建大量对象、连线字段、生成内容——应把代码放进**受版本管理的项目脚本**，
用 `script run` 执行一个具名静态入口。无需域重载，协议不携带代码；迭代成本是一次内存编译
（< ~2 秒），而非 15–20 秒的重编译。

```bash
# 1. 把构造脚本写在 Assets/ 之外（写入即不触发资源导入 / 域重载），
#    例如 AgentScripts/Build.cs:  public static class Build { public static int All() { ... } }
# 2. 执行——相对路径以项目根（Assets/ 的父目录）为基准解析：
unity command "script run" --file AgentScripts/Build.cs --entry Build.All
# 3. 迭代：改文件，重跑。常用扩展参数：
unity command "script run" --file AgentScripts/Build.cs --dry_run true   # 仅编译检查：诊断信息，不加载不执行
unity command "script run" --file AgentScripts/Build.cs --entry Build.All --args '[3, "Green"]'
```

经验规则：

- **代码写进磁盘文件用 `script run`；`script eval` 只用于真正临时的单行表达式。**
  绝不要通过 `eval` 传递多行转义 C# 字符串——写文件，跑入口。
- 编译看到项目的**当前编辑器宏**（`UNITY_EDITOR`、版本/平台符号）；`--defines` 在其上追加符号。
- 入口可以是 `async Task`/`Task<T>`——会异步等待（编辑器持续泵消息，在 Unity 上下文上恢复的
  await 可正常工作），返回 `Task<T>.Result`。等待受 `timeout` 限制；超时后任务转为独立继续运行。
- 运行时异常会带 `file:line` 映射到你的源码（执行运行总会生成源码映射 PDB；以未优化方式编译）。
- `--mode hotpatch` 改为应用 `[MethodReload]` 原地方法替换（委托给 `script.methodreload reload`）；
  该模式下 `entry`/`args`/`dry_run` 会被拒绝，`references`/`defines` 不适用。

## 7. 快速 C# 求值（编辑器 & 运行时）

`script eval` / `script eval_file` 在**两个**服务器上都可用——编辑器（甚至在播放模式外）和开发版 Player
运行时。**只用于真正临时的单行表达式**——更长的代码应写成文件经 `script run` 执行。

> **语法要求**：求值内容必须是完整语句，以 `return <表达式>;` 结尾（必须带 `return` 与分号）。
> 直接书写裸表达式（如 `2 + 2`、`SomeType.Method()`）会报 `Compilation Failed: ; expected`。

```bash
unity command "script eval" "return 2 + 2;"
unity command "script eval" "return UnityEngine.Application.unityVersion;"
# 或求值磁盘上的 .cs 文件（文件内容须同样为可求值语句）：
unity command "script eval_file" Assets/Scratch.cs
```

`timeout` 参数以**秒**为单位（默认 30），超时报 `Main thread operation timed out`。
**超时不等于未执行**：被调用的操作可能已在主线程继续执行，应等待后检查产物或状态，不要盲目重跑。

## 8. 服务端条件等待（`job wait`）

`job wait` 在编辑器逐帧循环上求值，等待某个运行时/编辑器成员条件成立，并可在条件首次成立的
**同一帧**执行动作（例如比赛结束界面出现的瞬间截图）。它替代了客户端轮询（`script eval` 读值 →
客户端 sleep → 重复）这一反模式：该循环既费 token 又慢，且 1–2 秒的往返会完全错过短暂状态。

### 同步 vs 异步——先选对模式

`/api/exec` **一次只执行一个命令**——同步 `job wait` 会在其整个持续期间占住队列。编辑器本身
不会冻结（每次轮询在 sleep 之间被编组到主线程），但**其他所有命令都会排在等待之后**，包括
你等待条件所依赖的命令——若条件需要某个尚未发出的变更才能满足，该变更永远无法执行，
等待会自死锁直到超时。

**仅当以下两条同时成立**时才用**同步**等待：

- 等待较短——明显低于客户端 HTTP 超时（通常 **< 30 秒**），且
- 条件**不依赖**你后续还需发出的任何命令（由已在推进的事物满足：播放模式玩法、正在进行的烘焙、计时器等）。

**其他所有情况**都传 `--async true`：立即得到 `waitId`，其他命令继续执行，轮询 `job wait_status`
（用 `job wait_cancel` 取消）。长等待以及任何"发出命令再等其效果"的流程，默认选异步。

```bash
# 条件对象 + 超时（--timeout 单位为秒，默认 30）
# 注意：op=equals（默认）时 value 必填，否则报 "condition.value is required"；
#       确实要比 null 就显式写 "value": null
unity command "job wait" --condition '{"member":"UnityEditor.EditorApplication.isPlaying","value":false}' --timeout 60
# 长等待或依赖后续命令时用异步 + 轮询
unity command "job wait" --condition '{"member":"...","value":1}' --async true
unity command "job wait_status" --wait_id <id>
unity command "job wait_cancel" --wait_id <id>
```

条件对象字段：`member`（必填，点分成员路径；无 `target`/`findType` 时为全限定**静态**路径，
有则为**实例**成员路径；仅支持只读字段/属性）、`target`（对象句柄，每次轮询重新解析，故可等待
中途出现的对象）、`findType`（`UnityEngine.Object` 类型全名，从存活实例开始遍历；持久化对象与
隐藏编辑器内部对象被排除）、`op`（`equals` 默认 / `notEquals` / `greaterThan` / `lessThan` /
`contains` / `changed`）、`value`（比较操作数，按成员类型强制转换；**除 `changed` 外必填——比 null 也要显式写 `null`**，
漏传会报 `condition.value is required for op 'equals'`）。

其他参数：`timeout`（默认 30，钳制到 0–600）、`poll_interval_ms`（默认 100，钳制到 16–5000）、
`on_met`（条件首次成立的同帧后续动作：`{ capture: {...}, pause }`）、`return_history`（返回观测样本，
环形缓冲保留**最后 200** 条）、`tolerate_missing`（解析失败视作条件未满足并重试，用于"等待 X 出现"）、
`async`。

结果字段：`state`（`pending` | `met` | `timedOut` | `interrupted` | `canceled` | `failed` | `not_found`）、
`met`、`timedOut`、`value`、`initialValue`、`elapsedMs`、`framesObserved`、`waitId`。
**按 `state` 判终态**（`pending` 之外即终态）。

## 9. 批量命令（`job batch`）

`job batch` 在单次请求中运行多个已注册命令，支持跨操作结果引用、原子 Undo 与 dry-run 校验。
用于把"创建 → 加组件 → 连线字段"这类工作（否则需 10–90 次顺序调用）压缩为一次请求，并补上
`eval` 结构上缺失的**事务性与回滚**能力。

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `operations` | 是 | – | 有序操作列表，每项 `{ id?, command, params }`，最多 200 个；`command` 写 `"<分组> <名称>"`。 |
| `transactional` | 否 | `true` | 所有操作归入一个 Undo 步骤，任一失败则回滚全部。`on_error=continue` 时强制为 `false`。 |
| `on_error` | 否 | `abort` | `abort` 首个失败即停；`continue` 全部执行并收集错误（强制 `transactional=false`）。 |
| `dry_run` | 否 | `false` | 校验命令名、参数、引用拓扑与被排除命令，不做任何变更。 |
| `result_fields` | 否 | – | 按操作投影结果字段（节省上下文）。 |
| `timeout` | 否 | `60` | 整批超时（秒）；耗尽后剩余操作跳过，事务批回滚。长批次改用 detached job。 |

跨操作引用：后续操作 `params` 中的**任意字符串**可引用前序操作结果，格式
`$<id-或索引>.<jsonPath>`（如 `"$0.instanceId"`；`$$` 转义字面 `$`）。
单操作结果 > 16 KiB 会被截断标记，整批回显上限 256 KiB——大对象用 `result_fields` 投影。

**被排除的命令**（不可作为子操作）：`build run`、`build.target switch`、`package *` 全组、
`editor.playmode start`/`stop`/`pause`、`script recompile`、`script eval`/`eval_file`/`run`、
`editor invoke_menu`、同步 `job wait`、嵌套 `job batch`、异步命令（`test run`/`test list`）、
仅运行时（tag `runtime`）命令、以及 `scene open`/`scene create`（会清空 Undo 栈）。

**事务限制**：Undo 无法回滚的写入（资产/文件、场景保存、构建设置、项目设置、烘焙数据、
材质落盘等）在 `transactional=true` 时被拒绝（`not_batchable_transactional`）——
改用 `transactional=false` 或单独调用。

## 10. 控制台输出（`console`）

```bash
unity command "console get" --tail 50 --level warn          # 取最近 50 条，最低 warn 级别
unity command "console get" --since <cursor> --since_session <session>   # 跟随
unity command "console status"                              # 只要计数与编译失败标志，无条目负载
unity command "console clear"                               # 清空捕获缓冲（编辑器下也清 Unity 控制台）
unity command "console write" --message "..." --level info   # 由服务端写一条日志（tag runtime）
```

`console get` 参数：`tail`（默认 100）、`level`（最低严重级别 `log` | `warn` | `error`）、
`since`（游标，配合上次响应的 `cursor` 实现跟随）、`since_session`（`since` 游标所属会话，
传上次响应的 `session`；跨会话游标会被拒绝并返回尾部且 `reset=true`）。

`console get` 响应携带：
- `logType` — Unity 精确的 `LogType` 名（保留 Exception/Assert 区分，`level` 会将其合并）；
- `counts` — 缓冲按严重级别保留的条目数；
- `groundTruth` — 编辑器自身的 `compilationFailed`、`compiling`、控制台条目计数与缓冲是否被播种、
  样本 `ageMs`，一次往返即可发现缓冲与 Console 窗口不一致（Player 下为 null）。

> **命令改名**：`console` → `console get`、`console_status` → `console status`、
> `clear_console` → `console clear`。三者同属运行时程序集，Player 构建中也可用
> （Player 下 `console clear` 清空捕获缓冲，无编辑器控制台可清）。
> 编辑器编译错误是粘性条目，Unity 自身的 clear 会跳过它们——它们保留到下一次编译结束。
> `console clear` 保留游标，跟随方下次轮询会看到 `dropped=true` 而不是静默跳过。

## 11. 项目审计（`diagnostics`）

通过 Project Auditor 进行静态分析扫描，产出待修复问题的 CSV。触发 → 轮询 → 读取。

```bash
unity command "diagnostics run_audit"              # 可选：--categories Code,ProjectSetting --output my.csv
unity command "diagnostics audit_status"           # 重复执行直至终态
```

`audit_status` 的终态包括：`completed`（返回 `csvPath` + `issueCount`）、`failed`、`unavailable`、
`interrupted`（域重载中断了扫描——直接重跑 `diagnostics run_audit` 即可）。Code 类目扫描期间会
编译程序集并占用主线程，但轮询仍保持响应。同一时间只能运行一个扫描：再次执行会返回 `busy`。
没有取消命令——停止轮询即放弃扫描。

CSV 列：`Category, Severity, Areas, Description, RelativePath, Line, DescriptorId, Recommendation`
（仅含诊断项，因此每一行都是需要修复的问题；`Recommendation` 说明如何修复）。

> **需要 Project Auditor 及其规则。** `unavailable` 表示编辑器没有 Project Auditor，或缺少分析规则——
> 在内置模块版编辑器中，规则位于独立的 `com.unity.project-auditor-rules` 包
> （`unity command "package add" --identifier com.unity.project-auditor-rules --confirm true`）。
> 请读取 `message` 字段；该命令绝不会返回空的 `completed` 扫描结果来伪装成干净项目。

## 附：安装、打开与命令模型细节

### CLI 检查缓存

检查通过后脚本将结果与环境指纹写入
`项目侧 .codebuddy.project/caches/skills/unity-pipeline/unity-pipeline/.cache/unity_cli_ok.json`（已 git 忽略）。
24 小时内且指纹（`unity` 路径、`unity --version` 输出）未变时直接复用；强制重查加 `--no-cache`。

### 离线安装包内容

| 文件 | 说明 |
|------|------|
| `install.ps1` | 安装脚本（离线优先 + 在线回退，SHA-256 校验） |
| `latest-beta.json` | Beta 通道版本清单 |
| `unity-windows-x64.exe` | win32-x64 二进制（约 106MB，git 忽略，缺失时在线下载） |

版本通道读环境变量 `UNITY_CLI_CHANNEL`（beta / alpha / stable），离线包当前内置 beta。
国内直连官方 CDN 可能拿到缓存的旧版本，必要时用代理 `-Proxy http://127.0.0.1:7897`；
Unity CLI 自身也支持全局 `--proxy` 或环境变量 `UNITY_PROXY`。

### 打开项目的补充说明

```bash
unity open .                                   # 打开当前目录的项目
unity open . --editor-version <目标Unity版本>   # 指定编辑器版本
unity open . --non-interactive                 # CI 场景
```

项目不在 Hub 注册表时用 `-e, --editor-path <路径>` 显式指定编辑器可执行文件。
`open` 是 **Unity CLI 内置命令**（与 `pipeline` 平级），不属于 unity-pipeline 包；
该包仅提供 `unity pipeline` / `unity command` 控制已运行实例。

### 命令分组总表

| 分组 | 覆盖内容 | 典型命令 |
|------|---------|---------|
| `editor` | 编辑器状态、焦点、菜单、自动 tick | `editor status`、`editor focus`、`editor invoke_menu` |
| `editor.playmode` | 播放模式 | `editor.playmode start` / `stop` / `pause` |
| `script` | 重编译、求值、构造器脚本 | `script recompile`、`script eval`、`script run` |
| `script.methodreload` | 方法重载 | `script.methodreload reload` / `status` / `cleanup` |
| `test` | 测试 | `test list`、`test run`、`test status`、`test cancel` |
| `job` | 批处理与条件等待 | `job batch`、`job wait`、`job wait_status` |
| `console` | 控制台 | `console get`、`console status`、`console write` |
| `diagnostics` | 性能与审计 | `diagnostics run_audit`、`diagnostics audit_status` |
| `build` / `build.target` | 构建与目标平台 | `build run`、`build status`、`build.target switch` |
| `package` | 包管理 | `package add`、`package list`、`package status` |
| `runtime` | Player 侧（tag `runtime`） | `runtime status`、`runtime quit` |
| `capture` / `asset` / `scene` / `gameobject` / `component` / `prefab` | 内容创作 | 见速查表 |

**0.7 的扁平命令名已全部失效**（`recompile`、`run_tests`、`batch`、`wait_for`、`eval`、
`editor_status`、`set_autotick`、`reload_file` 等），包里对旧名只给 "did you mean" 提示不执行。

### 超时解析顺序

1. 请求顶层 `timeout`（毫秒），CLI `--timeout <秒>` 写在这里；
2. 命令自身 `timeout` 参数（若请求未设）；
3. 命令声明默认值（多数 60 秒，`test run` 600 秒）。

CLI `--timeout` 默认 30 秒，因此会覆盖命令默认值：长同步调用需显式放宽，或改走异步。

### 退出码

| 退出码 | 含义 | 处理 |
|--------|------|------|
| `2` | 参数错误（拼错 flag、类型不对），什么都没执行 | 修正命令行后重试 |
| `6` | 命令已执行但失败，或编辑器无法服务该命令 | 读错误，重试无意义 |

**不要原样重试退出码 2 的调用，也不要在退出码 6 时改写命令行。**

### 已知限制

`test run` 在任意选中测试失败时可能返回不透明结果而非失败详情；改用更窄的 `--filter` 重跑，
或查看 Test Runner / 编辑器日志。
