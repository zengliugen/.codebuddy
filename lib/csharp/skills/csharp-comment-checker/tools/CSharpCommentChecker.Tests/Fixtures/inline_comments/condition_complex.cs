/// <file>
/// 测试 fixture - 复杂条件分支有注释。
/// </file>

/// <summary>测试类。</summary>
public class ConditionComplex
{
    /// <summary>
    /// 有注释的复杂条件不应报。
    /// </summary>
    /// <param name="x">第一个参数。</param>
    /// <param name="y">第二个参数。</param>
    public void ComplexWithComment(int x, int y)
    {
        // 当 x 较大且 y 较小时处理
        if (x > 100 && y < 50)
        {
        }
    }
}