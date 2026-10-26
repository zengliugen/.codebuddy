# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: 会话经验固化技能。当用户要求把本次会话的经验沉淀下来，或会话中出现可复用经验信号（用户纠正做法、同类问题重复出现、发现技能/规则文档与实际不符、复杂任务收尾）时触发，从当前会话提取经验并写回本次会话实际使用过的技能与规则。
input_contract:
  required:
    - session_context: 当前会话上下文（执行过的命令、报错、用户纠正、得出的结论）
  optional:
    - write_back_whitelist: 用户显式指定的写回范围（默认由会话使用记录推断）
    - extra_lessons: 用户补充的经验条目
    - target_scope: 落点范围限定（skills / rules / both，默认 both）
    - skip_confirmation: 用户是否授权直接固化（默认需先出清单并确认）
output_contract:
  required:
    - distill_report: 固化报告（项目侧产物目录，经索引 artifacts.dirs.session_distill.reports 定位，文件名 <时间戳>_distill-report.md），含经验条目、落点映射、建议但未写入项、改动预览
    - target_updates: 经确认后的目标文件改动（限定 .codebuddy/skills/** 与 .codebuddy/rules/**）
    - change_summary: 改动文件清单与改动要点（回滚依据）
  optional:
    - entry_sync: 入口同步（技能 SKILL.md 参考文献表、规则 RULE.mdc 子规则路由表）
  evidence:
    - lesson_evidence: 每条经验对应的会话证据（命令输出、报错原文、用户明确纠正）
    - dedup_check: 目标文件查重结果（新增 / 补充 / 已存在跳过）
    - encoding_check: 写入文件为 UTF-8 无 BOM 且新增路径引用真实存在
exclusion_contract:
  - new_skill: 从零创建新技能（走 yao-meta-skill）
  - skill_audit: 技能结构审计与评估（走 yao-meta-skill）
  - rule_restructure: 规则文件的拆分与合并（走 rule-consolidation）
  - code_review: C# 代码审查（走 csharp-code-review）
  - version_control: 提交、推送等版本控制操作（走 vcs-router / git-commit）
  - unrelated_issues: 与本次会话无关的既有问题
  - code_files: 代码文件（.cs 等）的修改
safety_constraints:
  - 每条经验必须有会话证据，无证据不写入
  - 只写本次会话实际使用过的技能与规则（白名单），白名单之外仅列入报告
  - 默认先产出固化清单并经用户确认后写回；用户明确授权时可跳过确认
  - 不改变目标文件既有条款语义，不删除既有内容
  - 写入使用简体中文、UTF-8 无 BOM，并沿用目标文件既有排版风格
  - 不新建技能、不新建规则文件、不拆分合并规则
  - 不写入凭据、密钥、内网地址等敏感信息
references:
  - lesson-extraction: references/lesson-extraction.md
  - target-mapping: references/target-mapping.md
  - write-back-rules: references/write-back-rules.md
scripts:
  - list_targets: scripts/list_targets.py
evaluation:
  trigger_evals: evals/trigger/
