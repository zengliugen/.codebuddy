/// <file>
/// 资源管理注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试资源管理注释缺失的类。
/// </summary>
public class ResourceTestClass
{
    /// <summary>
    /// try-finally 释放资源但没有注释的方法。
    /// </summary>
    public void MissingResourceComment()
    {
        var handle = new ResourceHandle();
        try
        {
            handle.Use();
        }
        finally
        {
            handle.Dispose();
        }
    }
}

/// <summary>
/// 模拟资源句柄类。
/// </summary>
public class ResourceHandle
{
    /// <summary>
    /// 使用资源。
    /// </summary>
    public void Use() { }

    /// <summary>
    /// 释放资源。
    /// </summary>
    public void Dispose() { }
}
