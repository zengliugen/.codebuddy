using System.Text.Json.Serialization;

namespace CSharpTestCoverage;

/// <summary>
/// 单个运行时成员的覆盖率记录。
/// </summary>
public class CoverageRecord
{
    /// <summary>
    /// 运行时源码文件的绝对路径（正斜杠归一化）。
    /// </summary>
    public string File { get; set; } = string.Empty;

    /// <summary>
    /// 文件相对项目根的路径。
    /// </summary>
    public string RelativeFile { get; set; } = string.Empty;

    /// <summary>
    /// 所属程序集名称（由文件路径推断）。
    /// </summary>
    public string Assembly { get; set; } = string.Empty;

    /// <summary>
    /// 类型所在命名空间。
    /// </summary>
    public string Namespace { get; set; } = string.Empty;

    /// <summary>
    /// 类型名称（不含命名空间；泛型类型保留类型参数占位）。
    /// </summary>
    public string TypeName { get; set; } = string.Empty;

    /// <summary>
    /// 类型种类（class / struct / interface / enum / record / delegate）。
    /// </summary>
    public string TypeKind { get; set; } = string.Empty;

    /// <summary>
    /// 成员名称。
    /// </summary>
    public string Member { get; set; } = string.Empty;

    /// <summary>
    /// 成员种类（method / property / field / constructor / event / operator / enumvalue / type）。
    /// </summary>
    public string MemberKind { get; set; } = string.Empty;

    /// <summary>
    /// 成员签名摘要，用于人工核对。
    /// </summary>
    public string MemberSignature { get; set; } = string.Empty;

    /// <summary>
    /// 成员唯一标识，格式为「类型全名::成员名/参数个数」。
    /// 与测试侧引用符号的标识对齐，用于匹配。
    /// </summary>
    public string MemberId { get; set; } = string.Empty;

    /// <summary>
    /// 覆盖率状态：covered / weak_reference / uncovered。
    /// </summary>
    public string CoverageState { get; set; } = CoverageStates.Uncovered;

    /// <summary>
    /// 强引用次数。
    /// </summary>
    public int ReferenceCount { get; set; }

    /// <summary>
    /// 弱引用次数（XML cref 与反射字符串命中）。
    /// </summary>
    public int WeakReferenceCount { get; set; }

    /// <summary>
    /// 强引用位置列表（文件相对路径 + 行号）。
    /// </summary>
    public List<ReferenceSite> ReferenceSites { get; set; } = new();

    /// <summary>
    /// 弱引用位置列表。
    /// </summary>
    public List<ReferenceSite> WeakReferenceSites { get; set; } = new();

    /// <summary>
    /// 对应的测试文件（相对项目根），无则为空串。
    /// </summary>
    public string CounterpartTestFile { get; set; } = string.Empty;

    /// <summary>
    /// 建议的骨架落地方式：append_partial / new_test_file / none。
    /// </summary>
    public string SuggestedAction { get; set; } = SkeletonActions.None;

    /// <summary>
    /// 骨架文件建议路径（相对项目根），无则为空串。
    /// </summary>
    public string SuggestedSkeletonFile { get; set; } = string.Empty;

    /// <summary>
    /// 真实采集的行覆盖率（百分比），无数据时为 null。
    /// </summary>
    public double? RealCoverageLineRate { get; set; }

    /// <summary>
    /// 静态判定与真实采集的分歧标记。
    /// </summary>
    public string Divergence { get; set; } = string.Empty;

    /// <summary>
    /// 声明所在行号（1 起）。
    /// </summary>
    public int Line { get; set; }
}

/// <summary>
/// 引用位置。
/// </summary>
public class ReferenceSite
{
    /// <summary>
    /// 引用所在文件（相对项目根）。
    /// </summary>
    public string File { get; set; } = string.Empty;

    /// <summary>
    /// 引用所在行号（1 起）。
    /// </summary>
    public int Line { get; set; }

    /// <summary>
    /// 引用形式标识（便于排查漏识别）。
    /// </summary>
    public string Kind { get; set; } = string.Empty;
}

/// <summary>
/// 覆盖率状态常量。
/// </summary>
public static class CoverageStates
{
    /// <summary>已被强引用。</summary>
    public const string Covered = "covered";

    /// <summary>仅被弱引用命中。</summary>
    public const string WeakReference = "weak_reference";

    /// <summary>无任何引用。</summary>
    public const string Uncovered = "uncovered";
}

/// <summary>
/// 骨架落地方式常量。
/// </summary>
public static class SkeletonActions
{
    /// <summary>追加 partial 专项文件到已有测试类。</summary>
    public const string AppendPartial = "append_partial";

    /// <summary>新建测试文件（镜像路径）。</summary>
    public const string NewTestFile = "new_test_file";

    /// <summary>无需生成骨架。</summary>
    public const string None = "none";
}

/// <summary>
/// 工具输出的顶层结果（含记录与汇总统计）。
/// </summary>
public class CoverageReport
{
    /// <summary>
    /// 覆盖率记录列表。
    /// </summary>
    public List<CoverageRecord> Records { get; set; } = new();

    /// <summary>
    /// 采集到的运行时文件数。
    /// </summary>
    public int RuntimeFileCount { get; set; }

    /// <summary>
    /// 采集到的运行时成员总数。
    /// </summary>
    public int MemberCount { get; set; }

    /// <summary>
    /// 被强引用覆盖的成员数。
    /// </summary>
    public int CoveredCount { get; set; }

    /// <summary>
    /// 仅被弱引用命中的成员数。
    /// </summary>
    public int WeakOnlyCount { get; set; }

    /// <summary>
    /// 无任何引用的成员数。
    /// </summary>
    public int UncoveredCount { get; set; }

    /// <summary>
    /// 零测试文件相对路径列表（整文件无任何强引用）。
    /// </summary>
    public List<string> ZeroTestFiles { get; set; } = new();

    /// <summary>
    /// 解析过程中出现的告警信息。
    /// </summary>
    public List<string> Warnings { get; set; } = new();
}

/// <summary>
/// 测试侧采集到的引用信息。
/// </summary>
public class TestReference
{
    /// <summary>
    /// 被引用的类型全名（含命名空间，泛型以 ` 占位与元数据名对齐）。
    /// </summary>
    public string TypeFullName { get; set; } = string.Empty;

    /// <summary>
    /// 被引用的成员名；仅引用类型本身时为空串。
    /// </summary>
    public string MemberName { get; set; } = string.Empty;

    /// <summary>
    /// 成员参数个数；无法判定时为 -1（表示通配）。
    /// </summary>
    public int ParameterCount { get; set; } = -1;

    /// <summary>
    /// 是否为弱引用。
    /// </summary>
    public bool IsWeak { get; set; }

    /// <summary>
    /// 引用形式标识。
    /// </summary>
    public string Kind { get; set; } = string.Empty;

    /// <summary>
    /// 引用所在文件（相对项目根）。
    /// </summary>
    public string File { get; set; } = string.Empty;

    /// <summary>
    /// 引用所在行号（1 起）。
    /// </summary>
    public int Line { get; set; }
}
