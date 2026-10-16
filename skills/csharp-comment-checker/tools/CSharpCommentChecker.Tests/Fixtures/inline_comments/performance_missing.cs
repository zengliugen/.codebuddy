/// <file>
/// 性能优化注释缺失测试用例。
/// </file>

using System;
using System.Collections.Generic;

/// <summary>
/// 用于测试性能优化注释缺失的类。
/// </summary>
public class PerformanceTestClass
{
    /// <summary>
    /// 预分配容量但没有注释的方法。
    /// </summary>
    public void UncommentedPreAlloc()
    {
        var list = new List<int>(100);
    }
}
