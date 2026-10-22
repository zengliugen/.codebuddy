/// <file>
/// 并发注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试并发注释缺失的类。
/// </summary>
public class ConcurrencyTestClass
{
    /// <summary>
    /// lock 语句但没有注释的方法。
    /// </summary>
    public void MissingLockComment()
    {
        lock (this)
        {
            var result = "test";
        }
    }
}
