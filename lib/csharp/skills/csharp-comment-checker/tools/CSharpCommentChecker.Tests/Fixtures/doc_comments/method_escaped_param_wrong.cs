/// <file>
/// 测试 fixture - 关键字转义参数名（@object/@enum）的 <param> 标签带 @ 时的错误写法。
/// </file>

/// <summary>
/// 测试类，包含 <param> 标签错误携带 @ 转义符的方法。
/// </summary>
public class MethodEscapedParamWrongTest
{
    /// <summary>
    /// 处理目标对象。
    /// </summary>
    /// <param name="@object">目标对象。</param>
    /// <param name="@enum">枚举值。</param>
    public void Process(Object @object, Int32 @enum)
    {
    }
}
