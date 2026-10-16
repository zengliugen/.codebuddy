/// <summary>
/// 注释检查结果，记录单条注释合规性问题。
/// </summary>
public class CommentIssue
{
    /// <summary>
    /// 文件路径。
    /// </summary>
    public string File { get; set; } = "";

    /// <summary>
    /// 行号（1-based）。
    /// </summary>
    public int Line { get; set; }

    /// <summary>
    /// 严重程度：error / warning / info。
    /// </summary>
    public string Severity { get; set; } = "";

    /// <summary>
    /// Issue 类别（对应 Issues 字典的 key）。
    /// </summary>
    public string Category { get; set; } = "";

    /// <summary>
    /// 触发规则名称（对应配置文件中的规则 key）。
    /// </summary>
    public string RuleName { get; set; } = "";

    /// <summary>
    /// 触发问题的代码摘要。
    /// </summary>
    public string CodeSnippet { get; set; } = "";

    /// <summary>
    /// 成员名称。
    /// </summary>
    public string Member { get; set; } = "";

    /// <summary>
    /// 成员类型（class / method / property / field 等）。
    /// </summary>
    public string MemberType { get; set; } = "";

    /// <summary>
    /// 问题描述消息。
    /// </summary>
    public string Message { get; set; } = "";
}
