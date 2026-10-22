/// <file>
/// 测试 fixture - 关键字转义参数名（@object）的正确 <param> 写法。
/// </file>

/// <summary>
/// 测试类，包含使用关键字转义参数名的方法。
/// </summary>
public class MethodEscapedParamCorrectTest
{
    /// <summary>
    /// 序列化目标对象。
    /// </summary>
    /// <param name="object">目标对象。</param>
    /// <returns>序列化结果。</returns>
    public int Serialize(Object @object)
    {
        return 0;
    }
}
