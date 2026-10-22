/// <file>
/// 并发注释存在测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试并发注释存在的类。
/// </summary>
public class ConcurrencyWithTestClass
{
    /// <summary>
    /// lock 语句带有注释的方法。
    /// </summary>
    public void ConcurrencyWith()
    {
        // 锁定以确保线程安全的字典写入
        lock (this)
        {
            var result = "test";
        }
    }
}
