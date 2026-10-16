/// <file>
/// 性能优化注释存在测试用例。
/// </file>

using System;
using System.Collections.Generic;

/// <summary>
/// 用于测试性能优化注释存在的类。
/// </summary>
public class PerformanceWithTestClass
{
    /// <summary>
    /// 预分配容量并带有注释的方法。
    /// </summary>
    public void PreAllocWith()
    {
        // 预分配容量避免扩容时的数组拷贝
        var list = new List<int>(100);
    }
}
