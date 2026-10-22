/// <file>
/// Workaround 注释存在测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试 workaround 注释存在的类。
/// </summary>
public class WorkaroundWithTestClass
{
    /// <summary>
    /// 吞掉异常并带有 HACK: 注释的方法。
    /// </summary>
    public void WorkaroundWith()
    {
        try
        {
            var result = "test";
        }
        // HACK: Unity 会在某些情况下抛出异常，暂时吞掉
        catch (Exception)
        {
        }
    }
}
