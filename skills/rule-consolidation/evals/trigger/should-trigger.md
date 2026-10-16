# Should Trigger Cases

## 拆分请求

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "vcs路由规则的内容太多了，拆分一下" | 触发 rule-consolidation，执行拆分 |
| 2 | "把这个规则按入口+子规则模式拆一下" | 触发 rule-consolidation，执行拆分 |
| 3 | "规则内容太多，按照其他规则的模式拆分子规则" | 触发 rule-consolidation，按项目模式拆分 |
| 4 | "主规则调整为入口规则，其他的动态触发加载" | 触发 rule-consolidation，拆分并按需加载 |

## 合并请求

| # | 输入 | 预期行为 |
|---|------|---------|
| 5 | "规则拆得太细了，合并一下" | 触发 rule-consolidation，执行合并 |
| 6 | "较小的规则其实可以放在一起" | 触发 rule-consolidation，评估并合并过小子规则 |
| 7 | "把 scope-spec 和 encoding-spec 合并成一个" | 触发 rule-consolidation，合并指定子规则 |

## 评估请求

| # | 输入 | 预期行为 |
|---|------|---------|
| 8 | "评估一下这些规则修改，是否有过度拆分的情况" | 触发 rule-consolidation，输出评估报告 |
| 9 | "检查规则结构是否合理" | 触发 rule-consolidation，评估模式合规 |
| 10 | "规则整合拆分做得怎么样，评价一下" | 触发 rule-consolidation，评估 |
