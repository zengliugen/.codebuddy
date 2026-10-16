using System.Text.Json;
using System.Text.Json.Serialization;

namespace CSharpTestCoverage;

/// <summary>
/// 覆盖率检查的运行时配置。
///
/// **配置为唯一事实来源**：所有字段（运行时源码根、排除路径、分母口径、映射策略、
/// 程序集前缀、包名→命名空间映射等）都必须由同目录的 `coverage_config.json` 显式声明。
/// 本类不提供任何内置默认值——配置缺失、解析失败或缺少必需字段时，
/// <see cref="Load"/> 会抛出 <see cref="CoverageConfigException"/>，由调用方转为明确的错误退出，
/// 避免「配置写了但没生效」被静默掩盖。
/// </summary>
public class CoverageConfig
{
    /// <summary>配置版本。</summary>
    public int Version { get; set; }

    /// <summary>排除规则。</summary>
    public ExcludeConfig Exclude { get; set; } = new();

    /// <summary>运行时源码根路径前缀（相对项目根）。由配置的 `runtimeRoots` 声明。</summary>
    public List<string> RuntimeRoots { get; set; } = new();

    /// <summary>测试目录标识（路径含其中之一即视为测试代码）。</summary>
    public List<string> TestRootMarkers { get; set; } = new();

    /// <summary>分母口径。</summary>
    public MemberScopeConfig MemberScope { get; set; } = new();

    /// <summary>引用强度配置。</summary>
    public ReferenceStrengthConfig ReferenceStrength { get; set; } = new();

    /// <summary>映射策略。</summary>
    public MatchingConfig Matching { get; set; } = new();

    /// <summary>骨架生成配置。</summary>
    public SkeletonConfig Skeleton { get; set; } = new();

    /// <summary>真实采集配置。</summary>
    public RealCoverageConfig RealCoverage { get; set; } = new();

    /// <summary>UPM 包名 → C# 根命名空间映射（用于由包路径推断命名空间）。</summary>
    public NamespaceMappingConfig NamespaceMapping { get; set; } = new();

    /// <summary>严重程度配置。</summary>
    public Dictionary<string, string> Severity { get; set; } = new();

    /// <summary>
    /// 从文件加载配置。
    ///
    /// 配置是唯一事实来源：文件不存在、JSON 解析失败或反序列化结果为 null 时，
    /// 一律抛出 <see cref="CoverageConfigException"/>，不再回退内置默认配置。
    /// </summary>
    /// <param name="path">配置文件路径。</param>
    /// <returns>配置对象。</returns>
    /// <exception cref="CoverageConfigException">配置缺失、损坏或解析失败时抛出。</exception>
    public static CoverageConfig Load(string path)
    {
        if (!File.Exists(path))
        {
            throw new CoverageConfigException(
                $"未找到覆盖率配置：{path}。请先按项目实际情况创建该配置（字段说明见该技能 references/config-guide.md）。");
        }

        try
        {
            var json = File.ReadAllText(path);
            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                ReadCommentHandling = JsonCommentHandling.Skip,
                AllowTrailingCommas = true,
            };
            var config = JsonSerializer.Deserialize<CoverageConfig>(json, options);
            if (config == null)
            {
                throw new CoverageConfigException($"覆盖率配置内容为空或无法解析：{path}");
            }
            return config;
        }
        catch (CoverageConfigException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new CoverageConfigException($"覆盖率配置解析失败（{ex.Message}）：{path}");
        }
    }

    /// <summary>
    /// 判断路径是否应被排除（既不采集成员也不计入分母）。
    /// 路径片段匹配大小写不敏感。
    /// </summary>
    /// <param name="normalizedPath">已归一化为正斜杠的绝对路径。</param>
    /// <returns>是否排除。</returns>
    public bool IsExcluded(string normalizedPath)
    {
        foreach (var fragment in Exclude.Paths)
        {
            if (normalizedPath.Contains(fragment, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// 判断路径是否属于测试代码。
    /// </summary>
    /// <param name="normalizedPath">已归一化为正斜杠的路径。</param>
    /// <returns>是否测试代码。</returns>
    public bool IsTestPath(string normalizedPath)
    {
        foreach (var marker in TestRootMarkers)
        {
            if (normalizedPath.Contains(marker, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// 判断路径是否属于运行时源码。
    /// </summary>
    /// <param name="normalizedRelativePath">相对项目根、正斜杠归一化的路径。</param>
    /// <returns>是否运行时源码。</returns>
    public bool IsRuntimePath(string normalizedRelativePath)
    {
        foreach (var root in RuntimeRoots)
        {
            if (normalizedRelativePath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// 获取指定问题类型的严重程度；未配置该键时抛出异常（配置是严重程度的唯一来源）。
    /// </summary>
    /// <param name="kind">问题类型标识。</param>
    /// <returns>error / warning / info。</returns>
    /// <exception cref="CoverageConfigException">配置缺少该问题类型的严重程度时抛出。</exception>
    public string GetSeverity(string kind)
    {
        if (Severity.TryGetValue(kind, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }
        throw new CoverageConfigException(
            $"配置缺少问题类型 `{kind}` 的严重程度（severity 段）。配置为严重程度的唯一来源，请补齐后再运行。");
    }
}

/// <summary>
/// 覆盖率配置不可用（缺失、损坏、缺少必需字段）时抛出。
///
/// 调用方（<c>Program.Main</c>）应捕获该异常并转为明确的错误退出码，
/// 不使用任何内置默认配置继续分析。
/// </summary>
public class CoverageConfigException : Exception
{
    /// <summary>以指定消息初始化。</summary>
    /// <param name="message">错误消息。</param>
    public CoverageConfigException(string message) : base(message)
    {
    }
}

/// <summary>
/// 排除规则配置。
/// </summary>
public class ExcludeConfig
{
    /// <summary>排除路径片段列表（由配置的 `exclude.paths` 声明）。</summary>
    public List<string> Paths { get; set; } = new();

    /// <summary>是否跳过文件头带 auto-generated 标记的文件。</summary>
    public bool AutoGenerated { get; set; }

    /// <summary>auto-generated 标记的扫描行数（只认文件头部区域）。</summary>
    public int AutoGeneratedScanLines { get; set; }
}

/// <summary>
/// 分母口径配置。
/// </summary>
public class MemberScopeConfig
{
    /// <summary>纳入分母的访问级别。</summary>
    public List<string> Accessibilities { get; set; } = new();

    /// <summary>是否纳入 private 成员。</summary>
    public bool IncludePrivateMembers { get; set; }

    /// <summary>是否纳入嵌套类型。</summary>
    public bool IncludeNestedTypes { get; set; }

    /// <summary>是否纳入枚举值。</summary>
    public bool IncludeEnumValues { get; set; }

    /// <summary>是否跳过编译器生成成员。</summary>
    public bool SkipCompilerGenerated { get; set; }

    /// <summary>是否跳过属性访问器。</summary>
    public bool SkipPropertyAccessors { get; set; }

    /// <summary>是否跳过事件访问器。</summary>
    public bool SkipEventAccessors { get; set; }

    /// <summary>是否跳过运算符重载。</summary>
    public bool SkipOperators { get; set; }

    /// <summary>是否跳过析构函数。</summary>
    public bool SkipDestructors { get; set; }
}

/// <summary>
/// 引用强度配置。
/// </summary>
public class ReferenceStrengthConfig
{
    /// <summary>弱引用类别。</summary>
    public List<string> WeakReferenceKinds { get; set; } = new();

    /// <summary>弱引用是否计为已覆盖。</summary>
    public bool CountWeakAsCovered { get; set; }

    /// <summary>识别反射字符串成员名所用的 API 名单。</summary>
    public List<string> ReflectionApiNames { get; set; } = new();
}

/// <summary>
/// 映射策略配置。
/// </summary>
public class MatchingConfig
{
    /// <summary>优先按目录镜像匹配。</summary>
    public bool PreferDirectoryMirror { get; set; }

    /// <summary>镜像未命中时回退「命名空间 + 类型名」匹配。</summary>
    public bool FallbackToNamespaceAndTypeName { get; set; }

    /// <summary>是否仅按类型名匹配（不安全，应保持关闭）。</summary>
    public bool FallbackToTypeNameOnly { get; set; }

    /// <summary>运行时根目录名称。</summary>
    public string RuntimeRootName { get; set; } = "";

    /// <summary>测试根目录名称列表。</summary>
    public List<string> TestRootNames { get; set; } = new();

    /// <summary>测试文件后缀。</summary>
    public string TestFileSuffix { get; set; } = "";
}

/// <summary>
/// UPM 包名 → C# 根命名空间映射配置。
///
/// 用于由包路径推断命名空间（如 `com.example.core` → `Example.Core`）。
/// 映射项由 `coverage_config.json` 的 `namespaceMapping.mappings` 声明；
/// 未配置时不猜测，直接以包名作为命名空间。
/// </summary>
public class NamespaceMappingConfig
{
    /// <summary>映射项列表。</summary>
    public List<NamespaceMappingItem> Mappings { get; set; } = new();
}

/// <summary>
/// 单条包名 → 命名空间映射。
/// </summary>
public class NamespaceMappingItem
{
    /// <summary>UPM 包名前缀，如 `com.example.`。</summary>
    [JsonPropertyName("package_prefix")]
    public string PackagePrefix { get; set; } = "";

    /// <summary>对应的 C# 根命名空间，如 `Example`。</summary>
    [JsonPropertyName("namespace")]
    public string Namespace { get; set; } = "";
}

/// <summary>
/// 骨架生成配置。
/// </summary>
public class SkeletonConfig
{
    /// <summary>默认是否生成骨架（必须保持 false）。</summary>
    public bool EnabledByDefault { get; set; }

    /// <summary>是否需用户确认。</summary>
    public bool RequireConfirmation { get; set; }

    /// <summary>触发二次确认的文件数阈值。</summary>
    public int FileCountThreshold { get; set; }

    /// <summary>骨架用例的未决断言消息。</summary>
    public string InconclusiveMessage { get; set; } = "";

    /// <summary>TODO 标记。</summary>
    public string TodoMarker { get; set; } = "";

    /// <summary>是否推断 partial 专项主题名。</summary>
    public bool PartialTopicInference { get; set; }

    /// <summary>已有对应测试类时禁止另起 fixture 名。</summary>
    public bool ForbidNewFixtureWhenCounterpartExists { get; set; }

    /// <summary>是否检查 partial 分部成员重名。</summary>
    public bool CheckPartialMemberConflicts { get; set; }
}

/// <summary>
/// 真实采集配置。
/// </summary>
public class RealCoverageConfig
{
    /// <summary>报告 Summary.json 相对路径。</summary>
    public string ReportSummaryJson { get; set; } = "";

    /// <summary>报告 Summary.xml 相对路径。</summary>
    public string ReportSummaryXml { get; set; } = "";

    /// <summary>OpenCover XML 根目录（Unity 默认以 &lt;解决方案名&gt;-opencov 命名）。</summary>
    public string OpenCoverRoot { get; set; } = "";

    /// <summary>覆盖率偏好文件相对路径。</summary>
    public string SettingsPath { get; set; } = "";

    /// <summary>纳入采集的程序集前缀（由配置声明，避免硬编码项目程序集名）。</summary>
    public List<string> AssemblyIncludePrefixes { get; set; } = new();

    /// <summary>排除的程序集后缀。</summary>
    public List<string> AssemblyExcludeSuffixes { get; set; } = new();

    /// <summary>采集时排除的路径模式。</summary>
    public string PathsToExclude { get; set; } = "";

    /// <summary>是否优先解析 Summary.json。</summary>
    public bool PreferSummaryJson { get; set; }

    /// <summary>分支覆盖率是否可用。</summary>
    public bool BranchCoverageAvailable { get; set; }

    /// <summary>域重载等待轮次。</summary>
    public int DomainReloadWaitRounds { get; set; }

    /// <summary>域重载等待间隔（秒）。</summary>
    public int DomainReloadWaitIntervalSeconds { get; set; }
}
