/// <file>
/// 测试 fixture - 条件分支注释缺失。
/// </file>

/// <summary>测试类。</summary>
public class ConditionUncommented
{
    /// <summary>
    /// 无注释的复杂条件应报告。
    /// </summary>
    /// <param name="x">第一个参数。</param>
    /// <param name="y">第二个参数。</param>
    public void Uncommented(int x, int y)
    {
        if (x > 100 && y < 50)
        {
        }
    }
}
