# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: C# 代码审查入口技能。只负责触发识别与 Agent 调度，审查逻辑委托给 csharp-code-review Agent。
input_contract:
  required:
    - target: 审查目标（文件路径 / 目录路径 / Git 变更范围 / 代码片段）
  optional:
    - dimension_filter: 用户指定的审查维度过滤（如"只查注释合规"）
    - severity_filter: 用户指定的严重级别过滤（如"只看 error"）
    - fix_request: 用户是否要求修复（默认 false，仅报告）
  fallback:
    - git_diff: 未指定目标时，分析本地未提交的 C# 变更
output_contract:
  required:
    - report_file: 审查报告文件（check_logs/{时间戳}_csharp-code_{目标}_{统计}_{GUID}.md）
    - summary: 对话内审查摘要（概览、问题统计、各维度分布、疑似问题）
  optional:
    - fix_verification: 修复模式的修复前后统计对比
  evidence:
    - rule_loaded: 已读取 .codebuddy/lib/csharp/rules/csharp-code-review/ 规则文件
    - comment_tool: 注释合规维度已调用 csharp-comment-checker Roslyn 工具（模式 D 除外）
    - format_tool: 格式合规维度已复用 5 分钟内 check_logs 报告或调用 csharp-format-checker dotnet format 工具（模式 D 除外）
exclusion_contract:
  - non_csharp: 非 C# 语言代码审查
  - auto_modify: 未经用户明确要求的自动修改代码
  - generated_code: Generated/、Gen/ 目录及 auto-generated 标记文件的审查
  - comment_generation: 注释生成与修正（应由 csharp-comment-generator 处理）
safety_constraints:
  - 默认只报告不修改代码
  - 修复必须经 AskUserQuestion 授权
  - 禁止臆测业务逻辑与无依据的判错
  - 禁止在技能层执行审查逻辑
references:
  - review-rules: .codebuddy/lib/csharp/rules/csharp-code-review/RULE.mdc
  - quality-spec: .codebuddy/lib/csharp/rules/csharp-code-review/quality-spec.mdc
  - comment-spec: .codebuddy/lib/csharp/rules/csharp-code-review/comment-spec.mdc
  - bug-boundary-spec: .codebuddy/lib/csharp/rules/csharp-code-review/bug-boundary-spec.mdc
  - architecture-spec: .codebuddy/lib/csharp/rules/csharp-code-review/architecture-spec.mdc
  - report-spec: .codebuddy/lib/csharp/rules/csharp-code-review/report-spec.mdc
  - agent: .codebuddy/lib/csharp/agents/csharp-code-review.md
