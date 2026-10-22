/// <file>
/// 测试 fixture - 简单空值检查不应报错。
/// </file>

/// <summary>测试类。</summary>
public class ConditionSimpleNull
{
    /// <summary>
    /// 简单 null 检查不应报。
    /// </summary>
    /// <param name="obj">待检查的对象。</param>
    public void SimpleNullCheck(object obj)
    {
        if (obj == null) return;
        if (obj != null)
        {
        }
        if (obj is string)
        {
        }
    }
}