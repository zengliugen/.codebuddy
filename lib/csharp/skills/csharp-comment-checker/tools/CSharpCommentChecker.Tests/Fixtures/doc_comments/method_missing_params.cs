// ====== 文件名: method_missing_params.cs ======
/// <summary>
/// 测试类，包含缺少参数注释的方法。
/// </summary>
public class MethodMissingParamsTest
{
    /// <summary>
    /// 缺参数注释的方法。
    /// </summary>
    /// <returns>计算值。</returns>
    public int MissingParamMethod(int x, int y)
    {
        return x + y;
    }
}
