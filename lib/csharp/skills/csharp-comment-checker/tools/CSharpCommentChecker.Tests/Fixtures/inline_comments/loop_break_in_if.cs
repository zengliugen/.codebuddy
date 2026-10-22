/// <file>
/// 测试 fixture - if 内嵌套 break 应报告。
/// </file>

/// <summary>测试类。</summary>
public class LoopBreakInIf
{
    /// <summary>
    /// if 内嵌套的 break 也应报告。
    /// </summary>
    public void BreakInIf()
    {
        for (int i = 0; i < 10; i++)
        {
            if (i > 100)
            {
                break;
            }
        }
    }
}
