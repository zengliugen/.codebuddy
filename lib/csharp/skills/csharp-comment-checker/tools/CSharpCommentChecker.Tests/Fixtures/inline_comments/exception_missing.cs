/// <file>
/// 异常处理注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试异常处理注释缺失的类。
/// </summary>
public class ExceptionTestClass
{
    /// <summary>
    /// catch 块有逻辑但没有注释的方法。
    /// </summary>
    public void CatchWithoutComment()
    {
        try
        {
            var result = "test";
        }
        catch (InvalidOperationException)
        {
            var result = "error";
        }
    }
}
