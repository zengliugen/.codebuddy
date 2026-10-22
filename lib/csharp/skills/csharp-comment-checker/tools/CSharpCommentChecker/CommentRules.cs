/// <file>
/// C# 注释检查工具的规则定义文件，包含规则名称、Issue 类别、严重程度、成员类型等常量表，
/// 以及可配置的注释检查规则管理类（CommentRules），支持从 JSON 配置文件加载规则定义与排除路径。
/// </file>
using System.Text.Json;

/// <summary>
/// 规则名称常量表。
/// </summary>
public static class RuleNames
{
    /// <summary>
    /// 类缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingClass = "doc_missing_class";
    /// <summary>
    /// 接口缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingInterface = "doc_missing_interface";
    /// <summary>
    /// 结构体缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingStruct = "doc_missing_struct";
    /// <summary>
    /// 枚举缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingEnum = "doc_missing_enum";
    /// <summary>
    /// 枚举值缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingEnumValue = "doc_missing_enum_value";
    /// <summary>
    /// 委托缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingDelegate = "doc_missing_delegate";
    /// <summary>
    /// 事件缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingEvent = "doc_missing_event";
    /// <summary>
    /// 方法缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingMethod = "doc_missing_method";
    /// <summary>
    /// 公共属性缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingProperty = "doc_missing_property";
    /// <summary>
    /// 公共字段缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingField = "doc_missing_field";
    /// <summary>
    /// 构造函数缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingConstructor = "doc_missing_constructor";
    /// <summary>
    /// 运算符重载缺少 XML 文档注释规则的名称。
    /// </summary>
    public const string DocMissingOperator = "doc_missing_operator";
    /// <summary>
    /// 文档注释使用禁止的 /** */ 块注释格式规则的名称。
    /// </summary>
    public const string DocBlockCommentFormat = "doc_block_comment_format";
    /// <summary>
    /// 文件头注释检查规则的名称。
    /// </summary>
    public const string FileHeader = "file_header";
    /// <summary>
    /// 文件解析错误规则的名称。
    /// </summary>
    public const string ParseError = "parse_error";
    /// <summary>
    /// 条件分支缺少行内注释规则的名称。
    /// </summary>
    public const string InlineCondition = "inline_condition";
    /// <summary>
    /// 循环中提前退出缺少行内注释规则的名称。
    /// </summary>
    public const string InlineLoopControl = "inline_loop_control";
    /// <summary>
    /// 算法/数据结构选择缺少行内注释规则的名称。
    /// </summary>
    public const string InlineAlgorithm = "inline_algorithm";
    /// <summary>
    /// 性能优化代码缺少行内注释规则的名称。
    /// </summary>
    public const string InlinePerformance = "inline_performance";
    /// <summary>
    /// 临时方案/规避措施未标注 HACK: 注释规则的名称。
    /// </summary>
    public const string InlineWorkaround = "inline_workaround";
    /// <summary>
    /// 硬编码业务规则/阈值缺少行内注释规则的名称。
    /// </summary>
    public const string InlineBusinessRule = "inline_business_rule";
    /// <summary>
    /// 魔法数字缺少行内注释规则的名称。
    /// </summary>
    public const string InlineMagicNumber = "inline_magic_number";
    /// <summary>
    /// 并发同步代码缺少行内注释规则的名称。
    /// </summary>
    public const string InlineConcurrency = "inline_concurrency";
    /// <summary>
    /// 资源管理代码缺少行内注释规则的名称。
    /// </summary>
    public const string InlineResource = "inline_resource";
    /// <summary>
    /// null 检查/防御性编程缺少行内注释规则的名称。
    /// </summary>
    public const string InlineNullCheck = "inline_null_check";
    /// <summary>
    /// 强制类型转换缺少行内注释规则的名称。
    /// </summary>
    public const string InlineTypeCast = "inline_type_cast";
    /// <summary>
    /// 异常处理缺少行内注释规则的名称。
    /// </summary>
    public const string InlineException = "inline_exception";
    /// <summary>
    /// 执行顺序依赖缺少行内注释规则的名称。
    /// </summary>
    public const string InlineOrder = "inline_order";
    /// <summary>
    /// 未完成代码缺少 TODO:/FIXME: 注释规则的名称。
    /// </summary>
    public const string InlineTodoFixme = "inline_todo_fixme";
}

/// <summary>
/// Issue Category 常量表。
/// </summary>
public static class IssueCategories
{
    /// <summary>
    /// 成员缺少 XML 文档注释类别的名称。
    /// </summary>
    public const string MissingDocComment = "missing_doc_comment";
    /// <summary>
    /// 缺少 &lt;summary&gt; 标签类别的名称。
    /// </summary>
    public const string MissingSummary = "missing_summary";
    /// <summary>
    /// &lt;summary&gt; 内容不以句号（。）结尾类别的名称。
    /// </summary>
    public const string SummaryNoPeriod = "summary_no_period";
    /// <summary>
    /// 方法参数缺少 &lt;param&gt; 标签类别的名称。
    /// </summary>
    public const string MissingParam = "missing_param";
    /// <summary>
    /// 有返回值的方法缺少 &lt;returns&gt; 标签类别的名称。
    /// </summary>
    public const string MissingReturn = "missing_return";
    /// <summary>
    /// 泛型缺少 &lt;typeparam&gt; 标签类别的名称。
    /// </summary>
    public const string MissingTypeparam = "missing_typeparam";
    /// <summary>
    /// 注释内容应使用简体中文类别的名称。
    /// </summary>
    public const string Language = "language";
    /// <summary>
    /// 缺少文件头注释类别的名称。
    /// </summary>
    public const string FileHeader = "file_header";
    /// <summary>
    /// 文件解析失败类别的名称。
    /// </summary>
    public const string ParseError = "parse_error";
    /// <summary>
    /// &lt;param&gt; 标签名称与实际参数名不一致类别的名称。
    /// </summary>
    public const string ParamMismatch = "param_mismatch";
    /// <summary>
    /// &lt;returns&gt; 标签存在但方法返回 void 类别的名称。
    /// </summary>
    public const string ReturnsMismatch = "returns_mismatch";
    /// <summary>
    /// &lt;typeparam&gt; 标签名称与实际类型参数名不一致类别的名称。
    /// </summary>
    public const string TypeparamMismatch = "typeparam_mismatch";
    /// <summary>
    /// 文档注释使用禁止的 /** */ 格式、应改用 /// 类别的名称。
    /// </summary>
    public const string BlockCommentFormat = "block_comment_format";
    /// <summary>
    /// 非显而易见的条件分支缺少行内注释类别的名称。
    /// </summary>
    public const string InlineCondition = "inline_condition";
    /// <summary>
    /// 循环中提前退出缺少行内注释类别的名称。
    /// </summary>
    public const string InlineLoopControl = "inline_loop_control";
    /// <summary>
    /// 使用特定算法/数据结构缺少行内注释类别的名称。
    /// </summary>
    public const string InlineAlgorithm = "inline_algorithm";
    /// <summary>
    /// 性能优化代码缺少行内注释类别的名称。
    /// </summary>
    public const string InlinePerformance = "inline_performance";
    /// <summary>
    /// 临时方案/规避措施未标注 HACK: 注释类别的名称。
    /// </summary>
    public const string InlineWorkaround = "inline_workaround";
    /// <summary>
    /// 阈值/硬编码值缺少行内注释解释业务含义类别的名称。
    /// </summary>
    public const string InlineBusinessRule = "inline_business_rule";
    /// <summary>
    /// 魔法数字缺少行内注释类别的名称。
    /// </summary>
    public const string InlineMagicNumber = "inline_magic_number";
    /// <summary>
    /// 并发同步缺少行内注释类别的名称。
    /// </summary>
    public const string InlineConcurrency = "inline_concurrency";
    /// <summary>
    /// 资源管理缺少行内注释类别的名称。
    /// </summary>
    public const string InlineResource = "inline_resource";
    /// <summary>
    /// 非显而易见的 null 检查缺少行内注释类别的名称。
    /// </summary>
    public const string InlineNullCheck = "inline_null_check";
    /// <summary>
    /// 强制类型转换缺少行内注释类别的名称。
    /// </summary>
    public const string InlineTypeCast = "inline_type_cast";
    /// <summary>
    /// 异常处理缺少行内注释类别的名称。
    /// </summary>
    public const string InlineException = "inline_exception";
    /// <summary>
    /// 执行顺序缺少行内注释类别的名称。
    /// </summary>
    public const string InlineOrder = "inline_order";
    /// <summary>
    /// 未完成代码缺少 TODO:/FIXME: 注释类别的名称。
    /// </summary>
    public const string InlineTodoFixme = "inline_todo_fixme";
}

/// <summary>
/// 严重程度默认值常量表。
/// </summary>
public static class SeverityDefaults
{
    /// <summary>
    /// 错误级别严重程度常量。
    /// </summary>
    public const string Error = "error";
    /// <summary>
    /// 警告级别严重程度常量。
    /// </summary>
    public const string Warning = "warning";
    /// <summary>
    /// 信息级别严重程度常量。
    /// </summary>
    public const string Info = "info";
}

/// <summary>
/// 成员类型常量表。
/// </summary>
public static class MemberTypes
{
    /// <summary>
    /// 类成员类型名称常量。
    /// </summary>
    public const string Class = "class";
    /// <summary>
    /// 接口成员类型名称常量。
    /// </summary>
    public const string Interface = "interface";
    /// <summary>
    /// 结构体成员类型名称常量。
    /// </summary>
    public const string Struct = "struct";
    /// <summary>
    /// 枚举成员类型名称常量。
    /// </summary>
    public const string Enum = "enum";
    /// <summary>
    /// 枚举值成员类型名称常量。
    /// </summary>
    public const string EnumValue = "enum_value";
    /// <summary>
    /// 委托成员类型名称常量。
    /// </summary>
    public const string Delegate = "delegate";
    /// <summary>
    /// 事件成员类型名称常量。
    /// </summary>
    public const string Event = "event";
    /// <summary>
    /// 方法成员类型名称常量。
    /// </summary>
    public const string Method = "method";
    /// <summary>
    /// 属性成员类型名称常量。
    /// </summary>
    public const string Property = "property";
    /// <summary>
    /// 字段成员类型名称常量。
    /// </summary>
    public const string Field = "field";
    /// <summary>
    /// 构造函数成员类型名称常量。
    /// </summary>
    public const string Constructor = "constructor";
    /// <summary>
    /// 运算符重载成员类型名称常量。
    /// </summary>
    public const string Operator = "operator";
}

/// <summary>
/// 单个 Issue 类别的配置，包含严重程度和描述。
/// </summary>
public class IssueConfig
{
    /// <summary>
    /// 该 Issue 类别是否启用。默认 true，设为 false 可单独关闭某一类检查。
    /// </summary>
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// 严重程度：error / warning / info。
    /// </summary>
    public string Severity { get; set; } = "warning";

    /// <summary>
    /// Issue 描述。
    /// </summary>
    public string Description { get; set; } = "";
}

/// <summary>
/// 单条规则的配置，包含启用状态和多个 Issue 子项配置。
/// </summary>
public class RuleConfig
{
    /// <summary>
    /// 规则是否启用。
    /// </summary>
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// 规则描述。
    /// </summary>
    public string Description { get; set; } = "";

    /// <summary>
    /// Issue 配置字典，键为 Category（如 "missing_doc_comment"），值为该 Category 的详细配置。
    /// 每个规则可产生多种 Category 的 Issue，每种有独立的严重程度。
    /// </summary>
    public Dictionary<string, IssueConfig> Issues { get; set; } = new();
}

/// <summary>
/// 排除配置，定义扫描时跳过的文件路径模式。
/// </summary>
public class ExcludeConfig
{
    /// <summary>
    /// 应跳过的路径片段列表，支持部分匹配（如 "/Generated/"、"/Assets/Plugins/"），匹配时大小写不敏感。
    /// </summary>
    public List<string> Paths { get; set; } = new();

    /// <summary>
    /// 是否根据文件头 &lt;auto-generated /&gt; 标记跳过自动生成代码文件，默认启用。
    /// </summary>
    public bool AutoGenerated { get; set; } = true;
}

/// <summary>
/// 可配置的注释检查规则管理器，从 JSON 配置文件加载规则定义和排除路径。
/// </summary>
public class CommentRules
{
    /// <summary>
    /// 技术术语白名单列表，注释语言检测时从注释文本中剥离这些术语（大小写不敏感）。
    ///
    /// **配置为唯一来源**：术语表由 comment_config.json 的 "knownTerms" 字段声明，
    /// 代码不内置任何默认术语；配置缺失会在加载时抛出异常。
    /// </summary>
    public List<string> KnownTerms { get; set; } = new();

    /// <summary>
    /// 排除配置，定义应跳过的路径模式。
    /// </summary>
    public ExcludeConfig Exclude { get; set; } = new();

    /// <summary>
    /// 规则定义字典，键为规则名称。
    /// </summary>
    public Dictionary<string, RuleConfig> Rules { get; set; } = new();

    /// <summary>
    /// 获取所有排除路径模式列表。
    /// </summary>
    /// <returns>所有排除路径模式列表。</returns>
    public List<string> GetExcludePaths()
    {
        var paths = new List<string>(Exclude.Paths ?? new List<string>());
        return paths;
    }

    /// <summary>
    /// 检查文件路径是否应被排除，排除的文件不参与注释检查。
    /// </summary>
    /// <param name="filePath">文件完整路径。</param>
    /// <returns>是否应被排除。</returns>
    public bool IsExcluded(string filePath)
    {
        var normalizedPath = filePath.Replace('\\', '/');
        foreach (var pattern in GetExcludePaths())
        {
            // 路径与排除片段均按大小写不敏感匹配，避免 Windows 路径大小写差异导致排除失效
            if (normalizedPath.IndexOf(pattern, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// 获取是否启用根据文件头 &lt;auto-generated /&gt; 标记跳过自动生成代码的检查。
    /// </summary>
    /// <returns>是否启用自动生成标记检测。</returns>
    public bool IsAutoGeneratedEnabled()
    {
        return Exclude.AutoGenerated;
    }

    /// <summary>
    /// 检查指定规则是否已启用。
    /// </summary>
    /// <param name="ruleName">规则名称。</param>
    /// <returns>规则是否已启用。</returns>
    public bool IsEnabled(string ruleName)
    {
        return Rules.TryGetValue(ruleName, out var config) && config.Enabled;
    }

    /// <summary>
    /// 获取指定规则下指定 Category 的严重程度。
    ///
    /// 配置为唯一来源：规则与 Issue 的严重程度都必须由 comment_config.json 声明；
    /// 缺少对应配置时抛出异常，不静默回退默认级别。
    /// </summary>
    /// <param name="ruleName">规则名称。</param>
    /// <param name="category">Issue 类别（Issues 字典的 key）。</param>
    /// <returns>严重程度字符串（error/warning/info）。</returns>
    /// <exception cref="CommentRulesConfigException">配置缺少该规则/Issue 的严重程度时抛出。</exception>
    public string GetIssueSeverity(string ruleName, string category)
    {
        if (Rules.TryGetValue(ruleName, out var config) &&
            config.Issues.TryGetValue(category, out var issue))
        {
            return issue.Severity;
        }
        throw new CommentRulesConfigException(
            $"配置缺少规则 `{ruleName}` 的 Issue `{category}` 严重程度。配置为严重程度的唯一来源，请在 comment_config.json 中补齐。");
    }

    /// <summary>
    /// 获取指定规则下指定 Category 是否已配置且已启用。
    /// 检查三个层级：规则启用 → Issues 字典包含该 Category → Issue 自身的 Enabled 为 true。
    /// </summary>
    /// <param name="ruleName">规则名称。</param>
    /// <param name="category">Issue 类别。</param>
    /// <returns>该 Issue 是否应被检查。</returns>
    public bool IsIssueEnabled(string ruleName, string category)
    {
        return Rules.TryGetValue(ruleName, out var config) &&
               config.Enabled &&
               config.Issues.TryGetValue(category, out var issue) &&
               issue.Enabled;
    }

    /// <summary>
    /// 从 JSON 文件加载规则配置。
    ///
    /// 配置为唯一来源：文件不存在、解析失败或反序列化结果为 null 时，
    /// 一律抛出 <see cref="CommentRulesConfigException"/>，不再回退内置默认配置。
    /// </summary>
    /// <param name="configPath">配置文件路径。</param>
    /// <returns>加载的规则配置实例。</returns>
    /// <exception cref="CommentRulesConfigException">配置缺失、损坏或解析失败时抛出。</exception>
    public static CommentRules Load(string configPath)
    {
        if (!File.Exists(configPath))
        {
            throw new CommentRulesConfigException(
                $"未找到注释检查配置：{configPath}。请先按项目实际情况创建该配置（字段说明见该技能 references/config-guide.md）。");
        }

        try
        {
            var json = File.ReadAllText(configPath);
            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                IncludeFields = true
            };
            var result = JsonSerializer.Deserialize<CommentRules>(json, options);
            if (result == null)
            {
                throw new CommentRulesConfigException($"注释检查配置内容为空或无法解析：{configPath}");
            }
            return result;
        }
        catch (CommentRulesConfigException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new CommentRulesConfigException($"注释检查配置解析失败（{ex.Message}）：{configPath}");
        }
    }
}

/// <summary>
/// 注释检查配置不可用（缺失、损坏、缺少必需字段）时抛出。
///
/// 调用方（<c>Program.Main</c>）应捕获该异常并转为明确的错误退出码，
/// 不使用任何内置默认配置继续检查。
/// </summary>
public class CommentRulesConfigException : Exception
{
    /// <summary>以指定消息初始化。</summary>
    /// <param name="message">错误消息。</param>
    public CommentRulesConfigException(string message) : base(message)
    {
    }
}
