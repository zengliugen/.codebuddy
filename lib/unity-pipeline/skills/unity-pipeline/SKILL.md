---
name: unity-pipeline
description: 通过命令行打开 Unity 项目并驱动正在运行的 Unity Editor 或开发版 Player。项目启动使用 Unity CLI 内置的 `unity open` 命令（非 pipeline 包提供）；实例控制依赖 unity-pipeline 包（`unity pipeline` / `unity command`）。当智能体需要打开/启动 Unity 项目、控制实时 Unity 实例、自动化 Unity 测试（运行/列出/重编译）、无头重编译脚本、评估 C# 代码，或应用运行时代码重载（`script.methodreload reload` / `reload_editor` / `reload_player`）时使用。前提：`unity` CLI 未安装时，技能通过内置离线安装包自动安装（`tools/unity-cli-offline/install.ps1`，离线优先 + 在线回退）。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "2.0"
---

<!--
  来源：com.unity.pipeline 0.9.0-exp.1（上游已把 agent skill 移出包，正文以 `Documentation~/` 与
  `Runtime/Common/CommandNames.cs` 为准重建）。本文件为项目内可编辑副本。

  相对上游保留的本地改动：
    - 新增"打开 Unity 项目"章节（必须 `unity open`，禁止直接启动 Unity.exe）；
    - CLI 安装检查与离线自动安装（0.1 / 0.2 / 0.3）；
    - `--runtime` / `--runtime-path` 实例定位；`script eval` 在编辑器上同样可用；
    - 异步命令"按 JSON 字段判终态"，禁止关键字匹配；`unity_wait.py` 等辅助脚本；
    - 命令层超时的可覆盖写法（`unity command --timeout <秒>`）。

  2026-10-21 从 0.7.0-exp.1 同步到 0.9.0-exp.1（0.8 + 0.9 一并吸收）：
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
  之后若再升级包，以 `Library/PackageCache/com.unity.pipeline@<hash>/Documentation~/` 与
  `Runtime/Common/CommandNames.cs` 为准重放本同步。
-->

# Unity Pipeline（智能体控制）

命令一律按 **`unity command "<分组> <名称>" [参数]`** 调用（0.9 起强制分组，旧扁平名已不可用）。
**分组与名称必须作为同一个参数传入**——实测 `unity command editor status`（不加引号）会被当成
"执行名为 editor 的命令"而失败，必须写成 `unity command "editor status"`。
不带参数执行 `unity command` 列出所有命令及其参数（输出里的第一列就是 `分组 名称`）。
存在两个服务器：**编辑器**（`7800-7849`，随编辑器自动启动）和**运行时**（`7900-7949`，
仅存在于启用了 Pipeline 的 Player 构建中）。完整参数见包内 `Documentation~/`；
常用命令速查见本技能 [`references/commands.md`](references/commands.md)（不依赖上游包，迁移/排障可直接查阅）。

## 0. Unity CLI 安装检查与自动安装

使用 `unity` 命令前，先确认 CLI 是否已安装；未安装则使用技能内置的离线安装包自动安装。

### 0.1 检查是否已安装（含本地缓存）

先运行环境检查脚本（含缓存，避免重复检查）：

```bash
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/check_unity_cli.py
```

> **本地缓存机制**：检查通过后，脚本将结果连同环境指纹写入
> 项目侧 `.codebuddy.project/caches/skills/unity-pipeline/.cache/unity_cli_ok.json`（已 git 忽略，Unity CLI 为机器级安装，不按项目隔离）。
> 在 **24 小时有效期**内且环境指纹（`unity` 命令路径、`unity --version` 输出）未变化时，
> 脚本直接复用上次通过结论，跳过重复检查，并提示"缓存命中"。
> 卸载/重装/升级 CLI 会使指纹失效自动重查；**失败结果不缓存**，修复后重跑立即重查。
> 如需强制重查，加 `--no-cache`：
>
> ```bash
> python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/check_unity_cli.py --no-cache
> ```

脚本等价于手动执行以下命令（缓存未命中时才实际执行）：

```powershell
Get-Command unity -ErrorAction SilentlyContinue    # 返回路径则已安装
unity --version                                    # 验证可执行
```

`unity` 命令安装位置：`%LOCALAPPDATA%\Unity\bin\unity.exe`（已加入用户 PATH）。

### 0.2 未安装时自动安装

执行技能内置的离线安装脚本（离线优先 + 在线回退）：

```powershell
powershell -ExecutionPolicy Bypass -File "<技能目录>\tools\unity-cli-offline\install.ps1"
```

安装脚本行为：

| 场景 | 行为 |
|------|------|
| 离线包存在当前平台二进制 | **离线安装**：本地复制 → SHA-256 校验 → 添加用户 PATH，无网络依赖 |
| 离线包缺少二进制（如 clone 后未拷贝） | **在线回退**：从官方 CDN `public-cdn.cloud.unity3d.com` 下载安装（可传 `-Proxy <代理URL>` 走代理） |

**离线包位置与内容**（`tools/unity-cli-offline/`）：

| 文件 | 说明 |
|------|------|
| `install.ps1` | 安装脚本（离线优先 + 在线回退，SHA-256 校验） |
| `latest-beta.json` | Beta 通道版本清单（manifest） |
| `unity-windows-x64.exe` | win32-x64 二进制（约 106MB，**git 忽略**、不随引擎分发，缺失时在线下载回退） |

**版本通道**：默认读取环境变量 `UNITY_CLI_CHANNEL`（`beta`/`alpha`/stable），离线包当前内置 `beta` 通道（`1.0.0-beta.3`）。安装后建议：

```powershell
$env:UNITY_CLI_CHANNEL='beta'   # 与离线包通道一致
```

> **注意**：离线包的 `unity-windows-x64.exe` 因体积大被 `.gitignore` 排除，不随 git/引擎包分发；clone 仓库后缺失时安装脚本会自动回退**在线下载**（或手动拷贝到该目录）。

### 0.3 国内网络与代理

- **国内直连官方 CDN 可能拿到缓存的旧版本**（如 `latest-beta.json` 被中间网络缓存返回旧版）。实测直连返回 `0.1.0-beta.3`，经代理 `127.0.0.1:7897` 返回真实最新 `1.0.0-beta.3`。
- 在线回退下载时，如需走代理，给安装脚本传 `-Proxy` 参数：
  ```powershell
  powershell -ExecutionPolicy Bypass -File "<技能目录>\tools\unity-cli-offline\install.ps1" -Proxy "http://127.0.0.1:7897"
  ```
- Unity CLI 自身也支持代理：全局选项 `--proxy <url>` 或环境变量 `UNITY_PROXY`（如 `http://127.0.0.1:7897`），可让 `unity` 的网络请求走代理。

## 1. 打开 Unity 项目

**启动 Unity 项目必须使用 `unity open`，禁止直接启动 Unity.exe 可执行文件**。`open` 会按 Hub
注册表匹配正确的编辑器版本与路径；直接启动 exe 会绕过版本匹配，且无法与 Pipeline 服务器正常衔接。
注意：`unity open` 是 **Unity CLI 内置命令**（与 `pipeline` 平级），不属于 unity-pipeline 包；
该包仅提供 `unity pipeline` / `unity command` 来控制已运行的实例。

```bash
unity open <项目路径>                          # 按路径打开（也支持 Hub 注册表名称 / Glob 模式）
unity open .                                   # 打开当前目录的项目
unity open . --editor-version <目标Unity版本>  # 指定编辑器版本（替换为目标项目实际版本）
unity open . --non-interactive                 # 配合全局 --non-interactive 用于 CI 场景
```

**驱动命令工作流必须加 `-automated` 参数**（通过 `--args` 传给 Unity）。否则模态弹窗可能中断连续命令。
0.9 起缺少该参数不再打印控制台警告，而是写入实例描述符的 `info` 字段——读取描述符时应先看它。
标准打开方式：

```bash
unity open <项目路径> --args "-automated"
```

**注意 `open` 的阻塞行为**：`open` 启动编辑器后进程会**一直挂起直到编辑器退出**，不会自动返回。
因此智能体应使用后台方式执行（如 `run_in_background: true`），或另开终端；启动后即可用以下命令
确认实例与 Pipeline 服务器已就绪（必要时轮询直至有响应），不要等待 `open` 本身返回：

```bash
unity pipeline list                    # 确认编辑器实例 + 服务器可达
unity command "editor status"            # 确认编辑器服务器有响应
```

如果项目不在 Hub 注册表中，用 `-e, --editor-path <路径>` 显式指定编辑器可执行文件。

## 2. 安装与校验

```bash
unity pipeline install            # 安装到当前项目（或 --project-path）
unity pipeline upgrade            # 已装包落后时升级到最新版
unity pipeline list               # 确认编辑器实例 + 服务器可达 + 包版本
unity command "editor status"       # 确认编辑器服务器有响应
```

> **升级包后必须重启编辑器**才能加载新命令表：命令注册是编译期特性（`[CliGroupCommand]`），
> 旧进程里不会出现新分组。升级后先用 `unity command` 确认命令表已是分组形式，再执行后续流程。

## 3. 命令模型（0.9 起）

命令按**分组**注册，写法固定为 `unity command "<分组> <名称>" [参数]`（引号不可省）；
批次操作、JSON 请求里同样写 `"<分组> <名称>"`。常用分组：

| 分组 | 覆盖内容 | 典型命令 |
|------|---------|---------|
| `editor` | 编辑器状态、焦点、菜单、自动 tick | `editor status`、`editor focus`、`editor set_auto_tick`、`editor invoke_menu` |
| `editor.playmode` | 播放模式 | `editor.playmode start` / `stop` / `pause` |
| `script` | 重编译、求值、构造器脚本 | `script recompile`、`script recompile_status`、`script eval`、`script run` |
| `script.methodreload` | 方法重载 | `script.methodreload reload` / `status` / `cleanup` |
| `test` | 测试 | `test list`、`test run`、`test status`、`test cancel` |
| `job` | 批处理与条件等待 | `job batch`、`job wait`、`job wait_status`、`job wait_cancel` |
| `console` | 控制台 | `console get`、`console status`、`console clear`、`console write` |
| `diagnostics` | 性能与审计 | `diagnostics get_performance`、`diagnostics run_audit`、`diagnostics audit_status` |
| `build` / `build.target` | 构建与目标平台 | `build run`、`build status`、`build.target switch` |
| `package` | 包管理 | `package add`、`package list`、`package status` |
| `runtime` | Player 侧（tag `runtime`） | `runtime status`、`runtime quit`、`runtime set_time_scale` |
| `capture` / `asset` / `scene` / `gameobject` / `component` / `prefab` | 内容创作 | 见速查表 |

发现命令不要靠记忆：`unity command` 输出全部命令、描述、参数数量与参数名（第一列为 `分组 名称`）；
往命令名后才补参数，如 `unity command "test run" --mode editor`。
每个命令都接受 `--verbose`（展开细节）与 `--omit-nulls`（省略空字段，省上下文）。

> **0.7 的扁平命令名已全部失效**，例如 `recompile`、`run_tests`、`batch`、`wait_for`、`eval`、
> `console`、`editor_status`、`set_autotick`、`reload_file` 都不再工作。包里对旧名会给出
> "did you mean" 提示，但不会执行。

## 4. 自主编辑循环（编辑器）

这是核心智能体工作流：保持编辑器存活、修改代码、重编译、测试。

```bash
# 1. 保持编辑器在失焦/最小化时仍持续 tick。无头工作前必需——
#    Unity 在非前台应用时否则会节流或停滞 update/compile。
unity command "editor set_auto_tick" --enable true

# 2. 正常在磁盘上编辑 C# 源文件。

# 3. 重编译（异步：触发域重载，然后轮询直至完成）。
unity command "script recompile"
unity command "script recompile_status"   # 重复执行直至 "completed" 或 "up_to_date"
#   域重载进行中会容忍连接错误——这是预期行为。
#   若 failed=true，读取 "errors" 数组并在测试前修复。
#   若 compilationFailed=true，说明编译失败抑制了域重载、
#   错误仍在原地——不要据 up_to_date 判定通过。
#   轮询可交给脚本（**按 JSON 字段判终态**，避免关键字匹配误命中）：
#   python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_wait.py --command "script recompile_status"

# 4. （可选）列出可用测试而不运行它们。
unity command "test list" --mode editor            # mode: all | editor | playmode

# 5. 运行测试（使用过滤器以保持快速）。
unity command "test run" --mode editor --filter MyFixture.MyTest
```

`test run` 模式：`all` | `editor` | `playmode`。`filter_type`：`testName` | `assembly` | `category`。
**playmode 运行必须使用 `--async_tests true`**——进入播放模式会触发域重载并丢弃同步 HTTP 请求，
同步调用必然失败——然后轮询 `unity command "test status"`（用 `unity command "test cancel"` 中止）。
注意：`--mode all` 不支持 `--async_tests true`（EditMode 结果内联返回，PlayMode 转异步）。

### 超时（0.9 起按命令声明，可覆盖）

每个请求只有一个超时，按以下顺序解析（详见包内 `Documentation~/connectivity.md`）：

1. 请求的顶层 `timeout`（毫秒）——CLI 的 `--timeout <秒>` 写在这里；
2. 命令自身的 `timeout` 参数（若请求未设）；
3. 命令声明的默认值（多数命令 60 秒，`test run` 600 秒）。

CLI 的 `--timeout` **默认为 30 秒**，因此它会覆盖命令自身的默认值。这意味着：

- 预计超过 30 秒的同步调用需要显式放宽：`unity command --timeout 900 "test run" --mode editor ...`；
- 或者改走异步（推荐）：`--async_tests true` + 轮询 `test status`；
- `job wait` / `job batch` / `test run` / `script run` 超时后会在**自身**预算内提前收尾，
  而不是让连接被硬切断。

> **终态判定必须按字段，禁止关键字匹配**：不要用 `grep -qE 'completed|up_to_date|failed'` 之类
> 对整段 JSON 做关键字匹配——`"failed":false` 会被 `failed` 命中，导致轮询在首轮即误判"成功"退出，
> 掩盖真实进行中的状态。正确做法是**取 `status` 字段值**与终态集合比较（`unity_wait.py` 已内置该逻辑）。

### 退出码语义（区分"改写调用"与"编辑器真失败"）

| 退出码 | 含义 | 处理方式 |
|--------|------|---------|
| `2` | **参数错误**——拼错的 flag、类型不对、位置参数过多。什么都没执行。 | 修正命令行后重试。错误信息会指明问题，常会建议正确 flag。 |
| `6` | **命令已执行但失败**，或编辑器无法服务该命令。 | 读错误；重试同一调用不会有帮助。 |

**不要把退出码 2 的调用原样重试，也不要在退出码 6 时改写命令行。**

> **已知警告：** 当任意选中的测试*失败*时，`test run` 可能返回不透明结果而非失败详情。
> 改用更窄的 `--filter` 重跑，或查看编辑器的 Test Runner / 日志以获取真实失败信息。

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

## 12. 辅助脚本（轮询 / 结果解析 / 版本检查）

> **0.9 为什么仍需要这些脚本**（升级后逐条复核的结论）：
> - 包新增的 `job wait` 是**条件等待**（等某个成员条件成立），不是"等某条命令跑完"，
>   无法替代 `script recompile_status` / `test status` / `build status` 的状态轮询；
> - 只有 `package add/remove` 提供 `--wait` 同步开关，测试与构建**没有**等价参数
>   （`test run` 的同步模式仍会在域重载时断连、`build run` 永远只返回 queued）；
> - CLI `--timeout` 默认 30 秒，跑长任务仍要 3 步走（触发 → 轮询 → 取结果），手写轮询极易踩
>   "关键字匹配误判"和"CLI `--json` 外壳字段错位"两个坑——脚本封装了这两处。
>
> 结论：三个脚本**继续保留**，职责不变，仅命令名随分组命名更新。

技能内置三个 Python 脚本，替代手写轮询与内联解析，均遵循「按 JSON 字段解析 + 可退出码判定」：

| 脚本 | 用途 | 关键退出码 |
|------|------|-----------|
| `scripts/unity_wait.py` | 异步命令轮询至终态（`--command "script recompile_status"` / `"test status"`）；**按字段判终态**，解析失败重试而非误判成功 | `0` 终态 / `1` 失败态 / `2` 超时 |
| `scripts/unity_test_summary.py` | 解析测试结果（兼容「结果 JSON + 参数回显」拼接），输出总数/通过/失败/跳过与失败清单（消息 + 堆栈首 3 行） | `0` 全通过 / `1` 有失败 / `2` 解析失败 |
| `scripts/unity_version_check.py` | 比对 `editor status` 的 `unityVersion` 与 `ProjectSettings/ProjectVersion.txt`；并扫描规则文档中残留的硬编码版本号 | `0` 一致 / `1` 版本不一致 / `2` 无法确定 |

用法速查：

```bash
# 轮询至终态（分组命令名整体加引号；默认 --field status --until completed,up_to_date）
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_wait.py --command "script recompile_status"
# 测试结果摘要（--file / --stdin，--filter / --fail-only / --json）
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_test_summary.py --file Temp/pipeline_test_status.json
# 版本一致性（编辑器未运行时加 --skip-editor）
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/unity_version_check.py
```

> 脚本输出格式可能随上游包变化调整；脚本按字段解析并对缺失字段重试，不把当前 JSON 文本结构写死。
>
> **两个已内置的兼容点**（手写脚本最容易在这两处出错）：
> 1. **CLI `--json` 的外壳**：真实结果在 `data.result` 里，而 `--json` 之外（human 表格）结果就在
>    `result` 列。`unity_wait.py` 会自动下钻剥壳，直接取 `status`/`failed` 不会扑空。
> 2. **命令名必须整串传参**：`"分组 名称"` 拆成两个参数，CLI 会报 `No command named '<分组>'`，
>    脚本里已按单参数传递。

## 注意事项

- **先执行 `editor set_auto_tick`。** 否则编辑器失焦时重编译和测试可能挂起。包内看门狗依赖 tick
  循环持续存活。播放模式下另可用 `editor.playmode set_run_in_background --enable true`
  （或 Project Settings → Pipeline → Editor 的 "Ensure editor runs in background in PlayMode"），
  只影响编辑器、不会泄漏进构建。
- **卡住的命令可能是模态弹窗，而非挂起**——弹窗会阻塞主线程直到被关闭。命令长时间运行时可查
  `unity command "editor status"`（即使被阻塞也即时响应）；`status: "blocked_by_dialog"` 表示
  应停止重试并告知人工是什么在阻塞（其 `dialog.title`/`message`/`buttons`）——CLI 无法点击它。
- **方法重载需要游戏在运行。** `script.methodreload reload` 应用于运行中的游戏——先进入编辑器播放模式
  （`unity command "editor.playmode start"`），或运行开发版 Player。
- **tag 为 `runtime` 的命令需要开发版 Player。** `runtime *`、`console write` 等指向运行时服务器，
  该服务器不随编辑器运行；它们在编辑器的命令表里可见，但 `job batch` 会拒绝它们。
- **异步命令需要轮询。** `script recompile`→`script recompile_status`、`test run --async_tests`→
  `test status`、`package add`→`package status`、`build run`→`build status`、
  `lighting bake`→`lighting bake_status`。永远不要假定触发调用的响应即代表完成。轮询**必须按 JSON
  字段判终态**（取 `status` 字段值），**禁止对整段 JSON 做关键字匹配**（`"failed":false` 会误命中
  `failed`）；可用 `scripts/unity_wait.py` 替代手写循环。
- **超时是每命令可配的。** CLI `--timeout` 默认 30 秒并**覆盖**命令自身默认值；长同步调用要么
  `unity command --timeout 900 "<分组> <名称>" ...`，要么改用异步 + 轮询。
- **退出码区分失败类型。** `2` = 参数错误（改命令行重试）；`6` = 已执行但失败（重试无意义）。
- **定位特定实例**：多实例时编辑器用 `--project-path <路径>`、Player 用 `--runtime <可执行名>` /
  `--runtime-path <端口文件目录>`，两者放在命令名前后均可（实测都生效）；先 `unity status` 看清
  端口与 PID。注意 `--instance host:port` **不是 CLI 选项**（会被透传成命令参数而被服务端忽略）。
- **只走环回**：两个服务器只绑定 `127.0.0.1` 并校验 Host 头，用 `localhost` 访问会被拒绝；
  端口一律用 IP 直连。
- **构建门控（0.9）。** 运行时程序集与 Roslyn DLL 由两个开关决定是否进入构建：
  "Enable in Development & Profiled Builds"（写 `ENABLE_RUNTIME_PIPELINE_DEV`）与
  "Enable in Release Builds"（写 `ENABLE_RUNTIME_PIPELINE`）。二者独立，只开后者会让开发构建
  完全不含 Pipeline。开关是唯一受支持的方式，不要手写宏。`[MethodReload]` 属性位于不受约束的
  `Unity.Pipeline.Attributes` 程序集，故打了标签的方法在发布构建中仍可编译（只是执行原方法体）。
