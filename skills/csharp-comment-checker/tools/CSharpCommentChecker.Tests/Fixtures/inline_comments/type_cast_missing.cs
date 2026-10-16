/// <file>
/// 类型转换注释缺失测试用例。
/// </file>

using System;

/// <summary>
/// 用于测试类型转换注释缺失的类。
/// </summary>
public class TypeCastTestClass
{
    /// <summary>
    /// 强制类型转换但没有注释的方法。
    /// </summary>
    /// <param name="obj">待转换的对象。</param>
    public void CastWithoutComment(object obj)
    {
        var result = (string)obj;
    }
}
