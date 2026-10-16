/// <file>
/// 空值检查注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试空值检查注释缺失的类。
/// </summary>
public class NullCheckTestClass
{
    /// <summary>
    /// 深层空值检查但没有注释的方法。
    /// </summary>
    /// <param name="obj">测试对象。</param>
    public void DeepNullCheck(object obj)
    {
        var a = 1;
        var b = 2;
        var c = 3;
        var d = 4;
        var e = 5;
        var f = 6;
        if (GetTarget(obj) == null) return;
    }

    /// <summary>
    /// 获取目标对象（用于构造非显而易见的 null 检查，验证复杂表达式仍被报告）。
    /// </summary>
    /// <param name="obj">源对象。</param>
    /// <returns>目标对象。</returns>
    private static object? GetTarget(object obj) => obj;
}
