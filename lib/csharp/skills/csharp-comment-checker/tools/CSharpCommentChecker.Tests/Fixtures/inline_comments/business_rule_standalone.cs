/// <file>
/// 业务规则注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试业务规则注释缺失的类。
/// </summary>
public class BusinessRuleTestClass
{
    /// <summary>
    /// 阈值检查但没有注释的方法。
    /// </summary>
    /// <param name="count">计数值。</param>
    public void ThresholdCheck(int count)
    {
        if (count > 15)
        {
            var result = count.ToString();
        }
    }
}
