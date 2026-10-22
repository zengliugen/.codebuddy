/// <file>
/// 测试 fixture - 算法/数据结构选择缺少行内注释。
/// </file>

/// <summary>
/// 测试类。
/// </summary>
public class AlgorithmTestClass
{
    /// <summary>
    /// 使用数据结构但无注释。
    /// </summary>
    public void MissingComment()
    {
        Dictionary<string, int> dict = new Dictionary<string, int>();
        dict["key"] = 1;
    }
}
