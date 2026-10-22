/// <file>
/// 测试 fixture - 自明条件分支不应报告 inline_condition。
/// </file>

/// <summary>测试类。</summary>
public class ConditionSelfEvident
{
    /// <summary>
    /// 自明条件分支（字面量比较、字符串比较、枚举比较、switch）不应报告 inline_condition。
    /// </summary>
    /// <param name="count">数量。</param>
    /// <param name="name">名称。</param>
    /// <param name="state">状态。</param>
    public void SelfEvidentConditions(int count, string name, EState state)
    {
        // 各分支意图由条件自身表达，无需额外注释
        if (count == 0) { }
        if (name == "config") { }
        if (state == EState.Ready) { }
        switch (state) { }
    }
}

/// <summary>状态枚举。</summary>
public enum EState
{
    /// <summary>就绪状态。</summary>
    Ready = 0,
}
