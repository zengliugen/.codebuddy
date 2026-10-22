/// <file>
/// 测试 fixture - 算法/数据结构选择有行内注释。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class AlgorithmWithTestClass
{
    /// <summary>
    /// 使用数据结构且有注释。
    /// </summary>
    public void WithComment()
    {
        // 使用字典实现 O(1) 键查找
        var dict = new Dictionary<string, int>();
        dict["key"] = 1;
    }
}
