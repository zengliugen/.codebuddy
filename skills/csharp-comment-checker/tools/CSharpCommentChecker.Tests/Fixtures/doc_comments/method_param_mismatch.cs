/// <file>
/// 测试 fixture - 方法 param 标签与参数不匹配。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class TestClass
{
    /// <summary>
    /// 测试方法。
    /// </summary>
    /// <param name="x">参数x。</param>
    /// <param name="wrong">不存在的参数。</param>
    public void Test(int x) { }
}
