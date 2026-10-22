/// <file>
/// 异常处理注释存在测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试异常处理注释存在的类。
/// </summary>
public class ExceptionWithTestClass
{
    /// <summary>
    /// catch 块带有注释的方法。
    /// </summary>
    public void ExceptionWith()
    {
        try
        {
            var result = "test";
        }
        // InvalidOperationException 在配置未初始化时抛出，记录后继续执行
        catch (InvalidOperationException)
        {
            var result = "error";
        }
    }
}
