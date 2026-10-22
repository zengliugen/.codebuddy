/// <file>
/// 测试 fixture - 运算符注释缺失。
/// </file>

/// <summary>
/// 向量结构体。
/// </summary>
public struct Vector
{
    public static Vector operator +(Vector a, Vector b) { return a; }
}
