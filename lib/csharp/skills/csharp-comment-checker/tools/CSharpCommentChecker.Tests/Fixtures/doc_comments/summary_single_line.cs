// <file>
// 单行 summary 检测的测试夹具，覆盖单行报错、多行合规与正文字样不误报三种情况。
// </file>

/// <summary>
/// 单行检测夹具类。
/// </summary>
public class SummarySingleLineFixture
{
    /// <summary>单行的公开字段。</summary>
    public int SingleLineField;

    /// <summary>
    /// 合规的多行公开字段。
    /// </summary>
    public int MultiLineField;

    /// <summary>
    /// 正文含单行标签字面量的字段，不应误报。
    /// </summary>
    /// <remarks>
    /// 示例：<summary>正文中的字样</summary>。
    /// </remarks>
    public int LiteralInRemarksField;
}
