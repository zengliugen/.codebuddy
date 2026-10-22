# csharp-comment-checker 触发评估记录

- **技能**：`csharp-comment-checker`（v1.2）
- **评估时间**：2026-08-26
- **评估方式**：脚本评估（`scripts/trigger_eval.py`，基于 `SKILL.md` frontmatter `description` 关键词匹配）
- **评估集**：`scripts/trigger_cases.json`（应触发 8 条 / 不应触发 9 条 / 近邻 4 条）

## 一、评估结果

| 指标 | 结果 |
|------|------|
| 应触发用例 | 8 个 |
| 不应触发用例 | 9 个 |
| 误报（FP） | 0 |
| 漏报（FN） | 0 |
| 精确率 | 1.0 |
| 召回率 | 1.0 |
| 匹配阈值 | 0.3 |
| Description 长度 | 331 字符 |

## 二、结论

**全部通过。** 当前 `description` 对注释检查/扫描/验证类请求召回完整，且不会误触发功能开发、编译、翻译等无关请求。

## 三、说明与局限

1. **评估为静态关键词匹配**，非模型级语义验证。`score_match` 通过"注释关键词 + 操作关键词"组合打分（`trigger_eval.py:60-81`），验证的是 description 的关键词覆盖度，不验证语义理解能力。
2. **中文触发词覆盖**：`score_match` 的 `has_action and "c#" in prompt_norm` 分支依赖 prompt 中出现 "c#"，对未含 "c#" 的纯中文请求覆盖有限；该分支仅作为降级匹配，主路径（注释 + 操作关键词）已覆盖主要场景。
3. 若需更强的发布证据，可接入 `scripts/yao.py output-exec` 运行模型级 A/B 验证（需配置 provider-runner），本报告不包含该证据，标记为 `missing evidence`。

## 四、修复关联

| 问题 | 处理 |
|------|------|
| Production 缺触发评估证据 | 本评估记录 + `scripts/trigger_cases.json` 落盘 |
