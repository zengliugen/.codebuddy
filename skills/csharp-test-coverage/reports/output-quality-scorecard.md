# 输出质量评分卡（csharp-test-coverage）

对技能产出的报告、骨架与 JSON 数据做质量评估。评分基于实际运行结果，非设想。

## 1. 报告质量

| 维度 | 评分 | 依据 |
|------|------|------|
| **结构完整性** | 5/5 | 含概览、模块分布、零测试清单、未覆盖成员、弱引用、分歧、骨架说明、统计口径全部章节 |
| **数据可核对** | 5/5 | 每条未覆盖成员含文件、类型、成员、签名、建议落地方式；可逐条回源码核对 |
| **口径透明** | 5/5 | 明确标注分母口径（public+internal）、豁免规则、弱引用不计入已覆盖 |
| **限制披露** | 5/5 | 分支覆盖率显式标注「不可用」；分歧段落说明口径为类级近似 |
| **可操作性** | 4/5 | 给出 `append_partial` / `new_test_file` 建议与具体骨架路径；但骨架需人工补断言，不能直接可用 |

### 实测样例（core 包）

```
成员总数 6398 | 已覆盖 811 | 仅弱引用 11 | 未覆盖 5576 | 覆盖率 12.68%
零测试文件 408 个
```

覆盖率 12.68% 与真实采集的 24.8%（该包行覆盖率）处于同一量级偏低一侧——静态分析按「成员是否被引用」判定，比「行是否被执行」更严格，符合预期。

## 2. 骨架质量

| 维度 | 评分 | 依据 |
|------|------|------|
| **命名合规** | 5/5 | 落地方式符合 `naming-layout.mdc`：已有测试类 → partial 专项；不存在 → 镜像路径新建 |
| **不误起 fixture** | 5/5 | 有对应测试类时强制 partial，实测 `MemoryAllocatorTests.Methods.cs` 等均正确 |
| **聚合合理** | 4/5 | 按语义主题聚合（Methods/Fields/Construction/Operators/Coverage），避免每成员一文件；但 `Coverage` 兜底桶语义偏弱 |
| **编译通过** | 5/5 | 实测 `failed=false`、`errors=[]` |
| **不猜断言** | 5/5 | 仅生成 `Assert.Inconclusive` + TODO 注释，不臆造期望值 |
| **注释合规** | 5/5 | 文件头 `/// <file>`（不嵌 remarks）、类/方法 `///`、TODO 用行内注释 |
| **防误提交** | 5/5 | 文件头、方法 remarks、控制台三处标注「骨架不可当已补测试提交」 |

### 实测样例

生成 2 个文件 / 16 个用例，编译通过。片段：

```csharp
/// <file>
/// AssetCheckInfo 的 NUnit 测试集合（覆盖率检查生成的骨架）。
/// 对应运行时文件：Packages/com.littlebaby.framework.core/Editor/Core/AssetChecker/AssetCheckInfo.cs。
/// 本文件为骨架，所有用例均以 Assert.Inconclusive 占位，尚未补完断言，
/// 补断言前不可视为有效测试。
/// </file>

namespace LittleBaby.Framework.Core.Tests.Editor.Core.AssetChecker
{
    /// <summary>
    /// 用例：验证 Path 的行为。
    /// </summary>
    /// <remarks>
    /// TODO(待补完)（签名：String AssetCheckInfo.Path）。
    /// </remarks>
    [Test]
    public void TestFieldPath()
    {
        // TODO(待补完)：构造被测对象并补断言（当前为骨架，未覆盖任何真实断言）

        Assert.Inconclusive("骨架用例：断言待补完。");
    }
```

## 3. JSON 数据质量

| 维度 | 评分 | 依据 |
|------|------|------|
| **字段完整** | 5/5 | 含 File/Assembly/Namespace/TypeName/Member/MemberKind/MemberSignature/MemberId/CoverageState/ReferenceCount/ReferenceSites/CounterpartTestFile/SuggestedAction/RealCoverageLineRate/Divergence/Line |
| **可追溯** | 5/5 | `ReferenceSites` 记录每条引用的文件与行号，可回源码核对 |
| **管道友好** | 5/5 | `--json` 模式进度信息走 stderr，`> out.json` 可直接消费（已修复混入日志的缺陷） |

## 4. 边界处理

| 场景 | 处理 | 评分 |
|------|------|------|
| 无测试的包 | 返回「零测试」，不报错 | 5/5 |
| 程序集引用缺失 | 告警并降级为语法分析，不中断 | 5/5 |
| 骨架文件已存在 | 跳过而非覆盖 | 5/5 |
| 计划内方法名重复 | 中止写入并列出冲突（而非产出编译不过的文件） | 5/5 |
| 报告超长 | 未覆盖成员限 300 条、零测试限 200 条，并注明完整数据见 JSON | 4/5 |

## 5. 已知不足

| 项 | 说明 | 影响 |
|----|------|------|
| 反射字符串类型匹配偏宽 | 无法确定 receiver 类型时退化为全局成员名匹配 | 可能高估弱引用命中，但弱引用不计入已覆盖，影响可控 |
| `Coverage` 兜底主题桶 | 不属于已知种类的成员归入 `Coverage` 桶 | 骨架文件命名语义偏弱 |
| 真实分歧仅类级 | `Summary.json` 只有类级数据，成员级分歧无法判定 | 已明确标注口径，避免误导 |
| 单成员分歧不可判 | 同一类内部分成员未执行时，类覆盖率仍可能较高 | 已在报告中说明，避免用户误读 |

## 6. 综合评分

| 类别 | 得分 |
|------|------|
| 报告质量 | 4.8 / 5 |
| 骨架质量 | 4.9 / 5 |
| JSON 数据 | 5.0 / 5 |
| 边界处理 | 4.8 / 5 |
| **综合** | **4.9 / 5** |

达到 `Production` 运行模式要求（团队复用技能，需通过触发评估与输出风险检查）。
