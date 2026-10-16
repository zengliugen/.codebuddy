/// <file>
/// 测试 fixture - 方法 typeparam 标签缺失。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class TestClass
{
    /// <summary>
    /// 转换方法。
    /// </summary>
    /// <param name="value">值。</param>
    public T Convert<T>(T value) { return value; }
}
