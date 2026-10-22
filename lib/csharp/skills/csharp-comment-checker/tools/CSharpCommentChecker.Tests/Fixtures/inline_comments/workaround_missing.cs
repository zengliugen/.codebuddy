/// <file>
/// Workaround 注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试 workaround 注释缺失的类。
/// </summary>
public class WorkaroundTestClass
{
    /// <summary>
    /// 吞掉异常但没有 HACK: 注释的方法。
    /// </summary>
    public void MissingWorkaround()
    {
        try
        {
            var result = "test";
        }
        catch (Exception)
        {
        }
    }
}
