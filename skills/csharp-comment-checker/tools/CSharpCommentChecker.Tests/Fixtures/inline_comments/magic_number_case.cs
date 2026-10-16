/// <file>
/// 测试 fixture - case 标签中数字不应报错。
/// </file>

/// <summary>测试类。</summary>
public class MagicNumberCase
{
    /// <summary>
    /// case 标签中的数字不应报。
    /// </summary>
    /// <param name="value">参数。</param>
    public void CaseTest(int value)
    {
        switch (value)
        {
            case 1:
                break;
            case 2:
                break;
            default:
                break;
        }
    }
}