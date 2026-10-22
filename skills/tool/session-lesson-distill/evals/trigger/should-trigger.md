# Should Trigger Cases

## 用户主动调用

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "把这次的经验固化一下" | 触发 session-lesson-distill |
| 2 | "把这次会话的经验沉淀到技能里" | 触发 session-lesson-distill |
| 3 | "复盘一下这次踩的坑，沉淀下去" | 触发 session-lesson-distill |
| 4 | "这次会话有什么值得沉淀的，写回技能和规则" | 触发 session-lesson-distill |
| 5 | "/session-lesson-distill" | 触发 session-lesson-distill |
| 6 | "把刚才发现的问题固化到对应技能里" | 触发 session-lesson-distill |

## 主动触发信号：用户纠正做法

| # | 输入 | 预期行为 |
|---|------|---------|
| 7 | 用户指出"这个顺序不对，应该先出清单再改"，并要求把该约定记下来 | 触发 session-lesson-distill |
| 8 | 用户说"以后这类改动都要先编译验证，记到技能里" | 触发 session-lesson-distill |

## 主动触发信号：同类问题重复出现

| # | 输入 | 预期行为 |
|---|------|---------|
| 9 | 会话中同一类错误连续两次导致返工，用户要求沉淀 | 触发 session-lesson-distill |
| 10 | 用户说"这个坑今天踩了两次了，写进技能避免下次再犯" | 触发 session-lesson-distill |

## 主动触发信号：文档与实际不符

| # | 输入 | 预期行为 |
|---|------|---------|
| 11 | 用户说"技能里写的是这样，但实际不是，更新一下技能" | 触发 session-lesson-distill |
| 12 | 会话中发现规则条款与实际代码行为不一致，用户要求同步修正规则 | 触发 session-lesson-distill |

## 主动触发信号：复杂任务收尾

| # | 输入 | 预期行为 |
|---|------|---------|
| 13 | 一次多阶段任务完成后，用户说"这个流程值得沉淀成规范" | 触发 session-lesson-distill |
| 14 | 多技能协作的任务收尾时，用户要求把协作顺序沉淀下来 | 触发 session-lesson-distill |
