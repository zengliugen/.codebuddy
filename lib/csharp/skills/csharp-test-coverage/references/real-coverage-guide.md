# 真实覆盖率采集指南

本文件记录 Unity Code Coverage 的**实测事实与操作流程**。所有结论均在
Unity 6000.5.7f1 + `com.unity.testtools.codecoverage@1.3.0` 上实测验证，
非源码推测。

---

## 1. 核心结论速查

| 事项 | 结论 | 实测证据 |
|------|------|---------|
| **状态读取** | 必须走 `unity command "script eval"` 读内存 | 同一时刻 `Settings.json` 为 `true` 而内存 `Coverage.enabled=false`，文件不可信 |
| **配置写入** | 必须经 `CodeCoverageWindow` 的 setter | 直接反射调 `CoveragePreferences.SetString` 不落盘；窗口 setter 内部走 `Settings.Save` 才落盘 |
| **域重载 API** | 必须用 `EditorUtility.RequestScriptReload()` | `CompilationPipeline.RequestScriptCompilation()` 调用后 AppDomain 哈希不变，域未重载 |
| **写入时序** | 先写内存偏好，再触发域重载 | 域重载会用内存缓存回写偏好文件；「改文件→重载」会被覆盖 |
| **程序集过滤** | 必须写显式清单，不可用 `<all>` | 非 batchmode 路径不展开别名，`Parse("<all>")` 实测返回字面量 `"<all>"` |
| **`script recompile` 状态** | 不可信 | 首次轮询即返回 `completed`，但域实际未重载 |

---

## 2. 为什么不能读文件判断状态

实测同一时刻两个来源给出**相反答案**：

| 来源 | 值 |
|------|-----|
| `Settings.json` 文件 | `EnableCodeCoverage = true` |
| `unity command "script eval"` 内存 | `Coverage.enabled = false` |

**根因**：`CoverageReporterStarter` 是 `[InitializeOnLoad]` 静态构造类，
只在**编辑器进程启动时**执行一次。启动时若 `Coverage.enabled == false`，
则在校验处提前 `return`，跳过 `TestRunnerApi.RegisterTestCallback`
与 `CoverageReporterManager` 创建，**回调链永久不注册**。

典型场景：编辑器长时间未重启（实测有一个实例连续运行约 29.5 小时），
期间偏好文件被改成 `true`，但内存状态仍是启动时的 `false`。

**因此**：判断覆盖率是否开启，一律用：

```bash
unity command "script eval" --code "return UnityEngine.TestTools.Coverage.enabled;"
```

判断回调链是否注册：

```bash
unity command "script eval" --code "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); var t = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CoverageReporterStarter\"); var f = t.GetField(\"CoverageReporterManager\", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static); var v = f.GetValue(null); return v == null ? \"NULL\" : \"REGISTERED\";"
```

`REGISTERED` 才算回调链就绪（这是测试运行时能采集到覆盖率的前提）。

---

## 3. 为什么必须经窗口 setter 写配置

`CodeCoverageWindow` 的 `AssembliesToInclude` / `PathsToExclude` 属性
setter 内部调用 `CoveragePreferences.SetString(...)` → `Settings.Save()`，
**同时更新内存缓存与磁盘文件**。

**踩坑记录**：直接反射调用 `CoveragePreferences.SetString` 时，
若 `SettingsScope` 参数传错（例如传了 `User` 而非 `Project`），
内存缓存会更新但**文件不落盘**——表现为「内存 25 个、文件 21 个」的脑裂状态。

**正确调用**（经窗口）：

```csharp
var wt = asm.GetType("UnityEditor.TestTools.CodeCoverage.CodeCoverageWindow");
var w = UnityEditor.EditorWindow.GetWindow(wt, false, "Code Coverage", false);
var prop = wt.GetProperty("AssembliesToInclude",
    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
prop.SetValue(w, "<逗号分隔的程序集清单>");
```

---

## 4. 为什么必须用 RequestScriptReload

| API | 实测效果 |
|-----|---------|
| `CompilationPipeline.RequestScriptCompilation()` | **无效**——调用后 AppDomain 哈希不变、`DomainId` 恒为 1 |
| `EditorUtility.RequestScriptReload()` | **有效**——AppDomain 哈希连续变化，探针数据被清空 |

验证域是否真的重载，用这两个探针（比 `script recompile_status` 可靠）：

```csharp
// 探针 1：域哈希，重载后会变化
return "Hash=" + System.AppDomain.CurrentDomain.GetHashCode();

// 探针 2：域数据，重载后被清空
System.AppDomain.CurrentDomain.SetData("Probe", "v1");   // 重载前设置
var d = System.AppDomain.CurrentDomain.GetData("Probe");  // 重载后应为 null
```

**注意**：`test run` / `script recompile` 的首次轮询即返回 `completed` 属于
「复用上一轮状态」，不能据此认定改动已生效。

---

## 5. 为什么必须先写内存再重载

域重载过程中，`Settings` 单例会把**内存缓存**序列化回写偏好文件。

隔离实验（实测）：

1. 只改 `Settings.json` 文件（改为 3 个测试值），不重载 → 20 秒后文件**保持 3 个**。
2. 触发域重载 → 文件被**回写为 21 个**（内存缓存值）。

**结论**：「改文件 → 重载」的顺序会被覆盖；必须「改内存 → 重载」。
这也是第 3 节必须用窗口 setter 的原因——只有它同时更新内存与文件。

---

## 6. 程序集过滤：为何不能用 `<all>`

非 batchmode 路径下，程序集过滤从偏好读取（`OpenCoverReporterFilter`），
走的是 `AssemblyFiltering.Parse` 直接建正则——**别名不展开**。

实测：

```
Parse("<all>", "")  →  includedAssemblies = "<all>"
```

原样写 `<all>` 会变成一个匹配不到任何程序集的正则，导致**覆盖率为空**。

**别名仅在命令行解析路径展开**（`CommandLineManager.ParseAssemblyFilters`），
而本方案不走命令行（命令行方式需关闭编辑器，与「不关闭编辑器」诉求冲突）。

**因此必须写入显式清单**。清单内容由配置 `realCoverage.assemblyIncludePrefixes` 与
`assemblyExcludeSuffixes` 在运行时枚举生成，无需手工维护。

> **以下为本项目实测的清单示例**（25 个程序集，其中框架包 21 个）。迁移到其他项目时，
> 该清单会随目标项目的 `assemblyIncludePrefixes` 配置自动变化，无需照抄本例。

```
Assembly-CSharp-firstpass, Battle, Battle.Data, Battle.Editor, Battle.Excel,
Battle.Logic, Battle.Render, Game, Game.Editor, Game.Entrance, Game.Excel,
Game.Protocol, LittleBaby.Framework.AssetBundle(+.Editor), Core(+.Editor),
FixedMathematics(+.Editor), Game, Graph(+.Editor), LogTrack(+.Editor), UI(+.Editor)
```

---

## 7. 标准流程

```bash
# 0) 前置检查（不写入），确认编辑器状态与当前覆盖率状态
python .codebuddy/lib/csharp/skills/csharp-test-coverage/scripts/collect_real_coverage.py --dry-run

# 1) 实际采集（会写入配置、触发域重载、跑测试、解析产物）
python .codebuddy/lib/csharp/skills/csharp-test-coverage/scripts/collect_real_coverage.py --confirm

# 2) 仅解析已有产物
python .codebuddy/lib/csharp/skills/csharp-test-coverage/scripts/parse_unity_coverage.py
```

脚本内部步骤：

1. `unity status` 判定编辑器是否在运行。
   - 已运行 → 直接采集。
   - 未运行 → `unity open . --args "-automated"`（后台）→ 等 `pipeline list` 就绪。
2. 备份 `Settings.json`。
3. 枚举项目程序集 → 经窗口 setter 写入 `IncludeAssemblies`。
4. 经窗口 setter 写入 `PathsToExclude = **/Tests/**`。
5. `CoveragePreferences.SetBool("EnableCodeCoverage", true)` +
   `Coverage.enabled = true`。
6. `EditorUtility.RequestScriptReload()` → 轮询等待 → 校验
   `enabled=true` 且回调链 `REGISTERED`。
7. `editor set_auto_tick` → 检查 `codeOptimization` → `run_tests --async_tests true`
   → 轮询 `test status`。
8. 解析 `CodeCoverage/Report/Summary.json`。
9. 还原 `Settings.json`（`--no-restore` 可跳过）。

**耗时参考**：域重载等待约 20–40 秒；1219 个 EditMode 用例的完整采集
（含覆盖率插桩）约 2.5 分钟。

---

## 8. 已知限制

| 限制 | 说明 |
|------|------|
| **分支覆盖率恒为 0** | 实测 `numBranchPoints="0"`，Coverage 包未采集分支数据，报告中不做分支维度结论 |
| **域重载后偏好文件被回写** | 域重载会用内存缓存回写偏好文件（脚本会打印实际值以便对照）；生效过滤取自内存，不影响采集结果 |
| **需重启编辑器才能让 UI 完全同步** | 包 UI 的开关提示为「will not take effect until Unity is restarted」，但实测**运行时开启 + 域重载**即可让回调链注册，无需重启进程 |
| **`codeOptimization` 为 Release 时会弹模态框** | 生成报告时 `EditorUtility.DisplayDialog` 会阻断流程；脚本会检查并告警，`Debug` 模式无此问题 |
| **仅 Mono/主机平台有效** | IL2CPP 与 HybridCLR 热更 dll 不在覆盖范围 |
| **报告目录每次被整目录清空** | 只保留最新一次报告；需累积历史可用 `-coverageHistoryPath` |

---

## 9. 排障

| 现象 | 排查 |
|------|------|
| 回调链始终 `NULL` | 确认用的是 `EditorUtility.RequestScriptReload()`（不是 `RequestScriptCompilation`）；确认内存偏好 `EnableCodeCoverage` 为 `true` |
| 覆盖率数据无框架包 | 检查窗口 setter 写入后内存清单是否含框架包前缀（由配置 `realCoverage.frameworkPackagePrefix` 指定）；确认域重载已完成 |
| 内存与文件清单数不一致 | 正常现象（域重载回写）；以**内存值**为准，采集结果取决于内存 |
| `Connection reset by server` | 域重载正在进行的正常表现，等待后重试即可 |
| 产物未生成 | 检查 `CodeCoverage/Report/Summary.json` 是否存在；确认测试确实执行过 |
