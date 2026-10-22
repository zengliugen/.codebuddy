/// <file>
/// 测试 fixture - 运算符注释完整。
/// </file>

/// <summary>
/// 向量结构体。
/// </summary>
public struct Vector
{
    /// <summary>
    /// 向量加法运算符。
    /// </summary>
    /// <param name="a">向量a。</param>
    /// <param name="b">向量b。</param>
    /// <returns>相加结果。</returns>
    public static Vector operator +(Vector a, Vector b) { return a; }
}
