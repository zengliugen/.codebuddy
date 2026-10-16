/// <file>
/// 资源管理注释存在测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试资源管理注释存在的类。
/// </summary>
public class ResourceWithTestClass
{
    /// <summary>
    /// try-finally 释放资源并带有注释的方法。
    /// </summary>
    public void ResourceWith()
    {
        var handle = new ResourceHandle();
        // 需要显式释放以确保文件句柄及时关闭
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
