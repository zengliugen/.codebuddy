/// <file>
/// 测试 fixture - 代码顺序依赖缺少行内注释。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class OrderTestClass
{
    /// <summary>
    /// 连续的密集语句无行内注释。
    /// </summary>
    public void MissingOrderComment()
    {
        var a = 1;
        var b = 2;
        var c = 3;
        var d = a + b + c;
    }
}
