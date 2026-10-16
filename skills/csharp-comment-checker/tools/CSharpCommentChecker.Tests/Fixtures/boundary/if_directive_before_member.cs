/// <file>
/// 测试 fixture - #if 指令边界情况。
/// </file>

/// <summary>
/// If 指令测试类。
/// </summary>
public class IfDirectiveTest
{
#if !UNITY_EDITOR
    /// <summary>
    /// 运行时初始化。
    /// </summary>
    public void RuntimeInit() { }
#endif
}
