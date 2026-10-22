# 触发评估摘要

## 测试范围

| 类别 | 案例数 | 预期通过率 |
|------|--------|-----------|
| Should Trigger | 8 | 100% |
| Should NOT Trigger | 5 | 100% |
| Near Neighbor | 3 | 100% |

## 关键路由边界

最容易被误路由的边界场景：

1. **check 与 fix 的意图区分**："检查格式"走只读 check；"把代码风格问题全部直接改掉"等明确修复请求走 fix（ST-08），但必须先经 AskUserQuestion 确认，禁止静默改写源码。
2. **注释规范归属**：涉及注释内容（缺失/语言/缩进引出的注释问题）应路由到 `csharp-comment-checker`，不属本技能；本技能只管 `.editorconfig` 格式规则。
3. **忽略目录保护**：`Assets/Plugins`、`Library/PackageCache` 等目录（由 `csharp-format-checker/config.json` 声明）内的文件不检查、不修改，请求者要求格式化它们时不能越权执行。
4. **非 C# 文件**：Lua/Shader/Markdown 等格式化请求不触发本技能。

## 评估方法

- 人工审查：逐个验证每个案例的描述是否被 `description` 正确路由。
- 盲测：随机打乱案例顺序（记录乱序种子），由独立评审者仅依据 frontmatter `description` 判断是否应触发，隐藏各案例所属桶。
- 对抗测试：构造边界模糊输入（如"格式化 Assets/Plugins"、"修一下注释对齐"、"全部直接改掉"），验证排除逻辑与门禁可靠。

## 盲测执行记录

- **2026-09-03（首轮内部盲测）**：ST 8/8、SN 5/5、NN 3/3 全部通过，FP=0、FN=0、Recall=1.000、Precision=1.000。乱序种子 `20260903`，明细见 [blind-run-report.md](blind-run-report.md)。局限：作者与盲判执行人为同一 LLM 实例，属内部基线；独立评审重跑入口为同一份 `trigger_cases.json`。
