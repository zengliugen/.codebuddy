/// <file>
/// 类型转换注释存在测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试类型转换注释存在的类。
/// </summary>
public class TypeCastWithTestClass
{
    /// <summary>
    /// 强制类型转换并带有注释的方法。
    /// </summary>
    /// <param name="obj">待转换的对象。</param>
    public void CastWith(object obj)
    {
        // obj 在构造函数中已保证为 string 类型
        var result = (string)obj;
    }
}
