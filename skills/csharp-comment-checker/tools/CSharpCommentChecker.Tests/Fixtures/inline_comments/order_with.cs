/// <file>
/// 测试 fixture - 代码顺序依赖有行内注释。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class OrderWithTestClass
{
    /// <summary>
    /// 连续的密集语句有行内注释。
    /// </summary>
    public void WithOrderComment()
    {
        // 先初始化所有依赖数据
        var a = 1;
        var b = 2;
        var c = 3;
        var d = a + b + c;
    }
}
