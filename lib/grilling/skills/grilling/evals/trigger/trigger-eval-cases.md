# 触发评测用例

本文件是 `trigger_cases.json` 的人类可读版本，供评审时逐条核对语义边界。机器复跑以 JSON 为准（`yao.py test` 或 `trigger_eval.py`）。

## 一、应触发（should_trigger）

| 编号 | 输入 | 家族 | 命中理由 |
|------|------|------|---------|
| ST1 | 拷问一下这个方案，别放过任何漏洞 | cn_core | 直接命中「拷问」+「方案」 |
| ST2 | 帮我把这个架构决策想透，逐轮问我 | cn_core | 命中「想透」+「决策」，且明确要多轮 |
| ST3 | 我这个技术选型靠谱吗，压力测试一下 | cn_core | 命中「压测」语义 |
| ST4 | 盘问我关于这个设计的每一个假设 | cn_core | 命中「盘问」+「设计」 |
| ST5 | Grill me on this migration plan. | en_core | 英文显式触发短语 |
| ST6 | Stress-test this design decision before I commit to it. | en_core | 命中「stress-test」+「decision」 |
| ST7 | Interview me relentlessly about this proposal. | en_core | 命中「interview me」 |
| ST8 | 挑战一下我的想法，找出我没想到的地方 | cn_core | 命中「挑战」+「想法」 |

## 二、不应触发（should_not_trigger）

| 编号 | 输入 | 家族 | 不触发理由 |
|------|------|------|-----------|
| SN1 | 帮我把这段逻辑改成异步 | implementation | 直接实现诉求，不是诘问 |
| SN2 | 写个单元测试覆盖这个方法 | implementation | 产出代码，非认知检验 |
| SN3 | 解释一下什么是单调栈 | explain | 概念解释，无决策待定 |
| SN4 | 把这份 README 翻译成英文 | translate | 翻译类任务 |
| SN5 | 总结一下这次会议纪要 | summary | 总结类任务 |
| SN6 | Implement the login flow now. | implementation | 明确要求执行 |

## 三、近邻（near_neighbor，应判定为不触发）

| 编号 | 输入 | 家族 | 边界说明 |
|------|------|------|---------|
| NN1 | 帮我看看这个方案大致行不行 | light_review | 只是随口求个判断，不要求逐轮诘问；应走普通讨论 |
| NN2 | 先头脑风暴一下有哪些可能的方向 | brainstorm | 发散阶段，与诘问的收敛语义相反 |
| NN3 | 这个类和那个类的区别是什么 | explain | 纯知识问答 |
| NN4 | 帮我拆一下这个需求的任务清单 | planning | 拆任务是执行前准备，不涉及假设检验 |

## 四、阈值与判读

- 推荐阈值：`0.42`
- 判读：`should_trigger` 命中率应接近 100%；`should_not_trigger` 与 `near_neighbor` 应全部判为不触发。
- 若 NN1 被误判为触发，说明「方案」一词的权重过高，需下调 `grill_session` 中泛化短语的支撑作用。
- 若 ST2、ST8 漏判，说明「想透」「挑战」类隐式表达覆盖不足，需补入短语表。
