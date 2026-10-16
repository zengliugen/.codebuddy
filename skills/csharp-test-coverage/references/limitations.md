# 已知限制

本文件列出静态分析与真实采集各自的限制，以及可能产生误报的场景。汇报结果时应据此说明置信度边界。

---

## 1. 静态分析的限制

### 1.1 引用识别的固有盲区

| 场景 | 表现 | 应对 |
|------|------|------|
| **反射字符串成员名** | `GetField("mSlotIndex")` 中的成员名是字符串，符号解析无法绑定 | 归为弱引用单列，不并入强引用计数 |
| **动态调用** | `dynamic`、`MethodInfo.Invoke` 间接调用 | 无法静态识别；属已知盲区 |
| **字符串拼接的成员名** | `GetField("m" + suffix)` | 无法识别，会误报为未覆盖 |
| **条件编译分支** | `#if UNITY_EDITOR` 下才存在的成员 | 依赖预处理器符号设置；符号不全时会漏采 |
| **泛型方法的封闭实例化** | 仅通过 `MakeGenericMethod` 调用 | 符号层面可能绑定到开放泛型，判定不稳定 |
| **外部程序集调用** | 被测代码被其他项目引用 | 只统计本仓测试引用 |

### 1.2 `[Test]` 识别

**必须使用 `AttributeSyntax` 判定**，禁止字符串匹配。

反例（本项目实测）：某代码生成器源文件含 `"[Test]"` 字符串字面量（生成器模板）。文本匹配会将其误计为测试代码。

### 1.3 命名空间消歧是硬要求

同名类型必须靠命名空间区分，**不能按短名匹配**：

| 运行时文件 | 命名空间 | 类型 |
|---|---|---|
| `Runtime/Core/Collections/Managed/Normal/Queue.cs` | `…Collections.Managed` | `class Queue<TValue>` |
| `Runtime/Core/Collections/Unmanaged/Normal/Queue.cs` | `…Collections.Unmanaged` | `struct Queue<TValue>` |

本项目 `Unmanaged/` 下 `Normal`、`Fixed`、`Unsafe`、`Pool` **共用同一命名空间**，只能靠类型名前缀区分。

若按短名匹配，`Managed/Foo` 与 `Unmanaged/Foo` 会互相串味，覆盖率判定完全失真。

### 1.4 目录镜像不可只按文件名匹配

映射必须优先**目录镜像**：

```
Runtime/<层级A>/<层级B>/Foo.cs
  → Tests/Editor/<层级A>/<层级B>/FooTests.cs
```

若只按文件名全局匹配，`Managed/Foo.cs` 会被 `Unmanaged/FooTests.cs` 误判为「有测试」——镜像路径不同，实为两个不同的被测类型。

### 1.5 生成代码豁免的双刃性

`Generated/` 与 `Gen/` 目录豁免后不计入分母，好处是避免拉低覆盖率；代价是**生成器模板自身的覆盖缺口被掩盖**。

本项目某包的 `Runtime/Gen/` 下有 58 个生成文件，其对应测试在 `Tests/Editor/Gen/`（549 个 `[Test]`）。分母豁免意味着「生成代码是否被充分测试」这一维度不在报告中体现。

### 1.6 测试替身与辅助类

`Tests/Runtime/**` 下的测试替身（如 `ExampleType.cs`）**不能作为运行时成员**计入分母，但它们继承运行时类型、标注运行时的特性是**真实引用**，应计入分子。

判定原则：**运行时成员只从运行时目录采集**，测试目录只贡献引用。

### 1.7 弱引用造成的假阴性

弱引用（`cref`、反射字符串）不计入强引用覆盖，可能出现：

- 报告中标记「未覆盖」，但代码实际上被反射调用了
- 报告中标记「已覆盖」，但引用只是文档 `cref`，测试从未执行

第二类尤其危险——它会给出虚假的安全感。报告中单列弱引用就是为了暴露这种不确定性。

---

## 2. 真实采集的限制

### 2.1 必须重启域才能让回调链生效

`CoverageReporterStarter` 是 `[InitializeOnLoad]` 静态构造类，只在**域加载时**执行一次。若编辑器启动时 `Coverage.enabled == false`，则回调链**永久不注册**。

因此运行时开启覆盖率必须：

1. 写入内存偏好（`EnableCodeCoverage = true`）
2. 触发域重载（`EditorUtility.RequestScriptReload()`）

**不需要**重启编辑器进程，但**必须**经历一次域重载。

### 2.2 域重载会回写偏好文件

域重载时 `Settings` 单例会把**内存缓存**序列化回写 `Settings.json`。因此：

- 「改文件 → 重载」的顺序会被覆盖
- 必须「改内存（经窗口 setter）→ 重载」

**副作用**：采集结束后 `Settings.json` 可能与采集前不同（被内存值回写）。脚本会备份并在结束时自动还原。

### 2.3 非 batchmode 路径不展开程序集别名

`<all>`、`<packages>` 等别名**只在命令行解析路径展开**。运行时开启覆盖率走的是偏好读取路径，`AssemblyFiltering.Parse` 直接按字面量建正则：

```
Parse("<all>", "")  →  includedAssemblies = "<all>"   ← 匹配不到任何程序集
```

**必须写入显式程序集清单**，否则覆盖率为空。脚本会枚举项目程序集自动生成。

### 2.4 分支覆盖率不可用

本项目实测 `numBranchPoints="0"` 恒成立，Coverage 包未采集分支数据。

**报告中不做分支维度结论**，只输出行覆盖率与方法覆盖率。

### 2.5 代码优化模式影响报告生成

非 batchmode 下若 `CompilationPipeline.codeOptimization == Release`，生成报告时会弹出模态对话框（询问是否切换到 Debug），**阻断自动化流程**。

脚本会在采集前检查并告警。本项目当前为 `Debug`，无此问题。

### 2.6 平台限制

| 平台 | 覆盖情况 |
|------|---------|
| Mono / 编辑器 | 支持 |
| IL2CPP 构建 | 不支持 |
| HybridCLR 热更 dll | 不在覆盖范围 |

### 2.7 报告目录每次清空

`CoverageReportGenerator` 在生成前会 `Directory.Delete(targetDirectory, true)` 清空 `Report/` 目录，**只保留最新一次结果**。

需累积历史时使用 `-coverageHistoryPath`（本项目已配置为项目根，历史落在 `CodeCoverage/Report-history/`）。

### 2.8 采集耗时

覆盖率插桩会显著拖慢测试。本项目参考值：

| 项 | 耗时 |
|---|---|
| 域重载等待 | 20–40 秒 |
| 1219 个 EditMode 用例（含插桩） | 约 2.5 分钟 |

---

## 3. 如何减少误报

1. **优先看零测试文件清单**——整个文件无任何引用的判定，比单个成员未覆盖更可靠。
2. **弱引用单列必看**——若某成员只有弱引用命中，需人工确认是否真的被测试。
3. **开启真实采集交叉验证**——静态判定「已覆盖」但真实行覆盖为 0 的分歧项，说明引用未真正执行到。
4. **对反射密集的模块降低置信度**——反射字符串无法静态绑定，这类模块的静态结论仅供参考。
5. **结合 `csharp-test/authoring.mdc` 判断**——该规则要求回归用例「修复前必然失败」，可据此评估现有用例的有效性，而非只看覆盖率数值。

---

## 4. 边界情况

| 情况 | 处置 |
|------|------|
| `#region` / `#if` 包裹的成员 | 按预处理器符号解析；符号不全时可能漏采 |
| 特性标注的成员 | 特性本身是引用来源，成员声明正常采集 |
| `partial` 类跨多文件 | 成员合并到同一类型下统计 |
| 空文件 / 仅命名空间 | 无成员，不计入统计 |
| 仅含注释的文件 | 无成员，不计入统计 |
| 测试目录不存在 | 正常返回「零测试」，不报错 |

---

## 5. 技术限制汇总

- 仅处理 `.cs` 文件，不支持其他语言
- 静态分析需 .NET 10.0+ SDK；首次运行自动 `dotnet publish`（约 10–30 秒）
- 符号解析依赖 Unity `Library/ScriptAssemblies` 作为程序集引用；该目录缺失时降级为纯语法分析（精度下降）
- 真实采集需 unity CLI 且全程不关闭编辑器
- 覆盖率开关状态必须经 `unity command eval` 读取，**读 `Settings.json` 会得到错误答案**（实测文件与内存可相反）

### 5.1 必须补入 Unity 参考程序集（corlib）

`Library/ScriptAssemblies/*.dll` 由 Unity 的 `mscorlib` 编译而来，**不含 corlib 本身**。
因此除 ScriptAssemblies 外，还须补入 Unity 官方参考程序集：
`<UnityData>/UnityReferenceAssemblies/<profile>` 及其 `Facades` 目录
（`<UnityData>` 由 `Library/EditorInstance.json` 的 `app_contents_path` 定位，
或由 Unity 生成 csproj 中 `mscorlib` 的 `HintPath` 回推）。

缺失时会引入**两类系统性偏差**：

| # | 偏差 | 原因 |
|---|------|------|
| 1 | `<<` / `>>` 与全部 `op_Explicit` / `op_Implicit` **转换运算符绑定失败** | 用户定义运算符解析需要完整类型系统 |
| 2 | 基元类型（`Int32` / `Boolean` / `String` 等）解析失败，`GetDocumentationCommentId` 退化为**短名**（`Int32`），与测试侧全名（`System.Int32`）不一致 | 两侧文档 ID 无法对齐，含基元参数的方法与运算符均会漏配 |

该情况下工具会在报告 `Warnings` 中给出「未找到 Unity 参考程序集（corlib）」告警。
**看到该告警时，覆盖率数值不可用于判断运算符/转换类成员的覆盖情况**，应先恢复 corlib 后重扫。

实测（`fixedmathematics` 包）补齐 corlib 并补全运算符采集后：
运算符覆盖由 0 增至 62（消除假阴性），同时 11 个「仅靠编译错误产生的候选符号覆盖」的
假阳性被修正为未覆盖，成员覆盖率 24.82% → 26.90%，净变化
`607 + 62 - 11 = 658` 完全对账。
