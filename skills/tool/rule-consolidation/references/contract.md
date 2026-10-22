# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: .codebuddy 规则文件整合拆分技能。当用户要求对规则文件进行拆分、合并、或评估规则结构是否合理时触发，按项目统一模式（入口 RULE.mdc 始终生效 + 子规则按需加载）评估并执行规则文件重组。
input_contract:
  required:
    - target_rule: 目标规则目录（.codebuddy/rules/<name>/）或规则文件列表
    - action: 操作意图（split / merge / evaluate，或用户描述中可推断）
  optional:
    - rule_scope: 规则范围限定（如"全部规则"或指定规则）
    - mode_limit: 评估模式限定（仅报告不修改）
    - reference_scope: 需同步引用的范围（技能/文档，默认自动检测）
output_contract:
  required:
    - restructure_plan: 重组方案（拆分/合并后的子规则清单、删除文件、路由表更新）
    - restructured_files: 重组后的规则文件（入口 + 子规则）
    - reference_updates: 引用同步变更（技能/文档中指向旧路径的引用）
  optional:
    - eval_report: 仅评估模式下的结构评估报告
  evidence:
    - pattern_check: 入口/子规则 frontmatter 与项目模式对比结果
    - size_metrics: 子规则内容行数统计（判断过小/过大）
    - grep_verification: 旧路径残留引用扫描结果
exclusion_contract:
  - skill_files: 技能文件（SKILL.md、agents/interface.yaml、scripts/）的**功能逻辑**修改
  - code_files: 代码文件修改
  - new_rule: 从零创建全新规则（不涉及重组已有规则）
  - rule_logic: 规则内容的实质语义变更（重组仅移动/合并内容，不改变条款含义）
  - non_codebuddy: .codebuddy 目录之外的规则文件
safety_constraints:
  - 删除文件前确认内容已并入合并后的子规则，不丢失条款
  - 仅评估模式下禁止擅自修改文件
  - 重组方案需向用户呈现并获确认后执行
  - 引用同步以 grep 验证收尾，避免遗留指向已删除文件的路径
  - 历史日志（check_logs/）内的旧路径引用不做修改
references:
  - split-criteria: references/split-criteria.md
  - merge-criteria: references/merge-criteria.md
  - pattern-spec: references/pattern-spec.md
evaluation:
  trigger_evals: evals/trigger/
