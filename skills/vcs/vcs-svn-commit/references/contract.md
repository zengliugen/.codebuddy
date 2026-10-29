# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），
详细输入/输出/排除/安全/引用契约在此按需读取。

description: SVN 提交执行技能。当用户要求提交 SVN 代码（"svn commit"、"提交到 svn"，或由 vcs-router 技能检测为 SVN 工作副本后路由）时触发，分析工作副本变更并生成标准化提交摘要，提交前按项目配置自动触发代码审查门禁（达阻塞级别问题则阻止提交）。不支持 amend、revert、update、switch、分支与标签操作。
input_contract:
  required:
    - trigger: 用户明确要求执行 svn commit 操作（或 vcs-router 路由到本技能）；当项目配置 commit_initiation=llm_allowed 时，LLM 亦可自行发起
  optional:
    - conversation_context: 本次对话中的文件修改记录
    - user_preference_scope: 用户指定的 scope
    - user_preference_type: 用户指定的提交类型
    - target_paths: 用户显式指定的目标路径（默认由提交计划推导）
    - skip_review: 用户指定跳过提交前审查（需明确授权）
  fallback:
    - svn_status: 对话无修改信息时用 collect_svn_changes.py 分析工作副本变更
output_contract:
  required:
    - commit_plan: 提交计划（各笔的摘要与目标路径清单）
    - revision: 每次提交产生的修订号
    - commit_summary: 每次提交的标准化摘要
  optional:
    - review_report: 提交前审查报告路径（触发审查步骤时）
  evidence:
    - ignore_check: svn:ignore 交叉比对结果
    - user_authorization: AskUserQuestion 授权记录
    - review_result: 提交前代码审查结果（error/warning/info 统计与报告路径）
    - pre_check: 提交前目标清单校验结果（verify_targets.py --mode pre）
    - post_check: 提交后实际修订路径校验结果（verify_targets.py --mode post）
exclusion_contract:
  - amend: svn commit --force-log 或改写历史修订
  - revert: svn revert 操作
  - update: svn update 操作（提交前后均不自动执行）
  - switch: svn switch / relocate 操作
  - branch_tag: 分支与标签创建（svn copy 到 branches/ 与 tags/）
  - merge: svn merge 操作
  - lock: svn lock / unlock 操作
safety_constraints:
  - 所有确认必须通过 AskUserQuestion 工具
  - 禁止提交 svn:ignore 中已忽略的项（不得用 svn add --force）
  - 提交必须用 --targets 显式指定目标路径，禁止省略路径（等于提交整个工作副本）
  - 提交消息文件用 UTF-8 并配 --encoding UTF-8；目标清单文件用 GBK/ANSI（两条编码方向相反）
  - 提交消息文件与目标清单文件均不得位于工作副本内
  - 提交与远端同步强制分离：提交前不隐式 update/revert，提交后不自动 update/switch
  - 提交前按项目配置执行 H1 提交前钩子（步骤清单、审查技能全部来自项目侧配置，引擎不提供默认值）
  - 存在 blocking_level 级别审查问题时必须修复或获用户明确授权忽略，禁止静默提交
  - 提交发起权按项目配置（commit_initiation，user_only 或 llm_allowed）；user_only 时禁止 LLM 自动发起
  - 获得用户授权后、svn add 之前必须获取 VCS 写操作锁，锁覆盖 add → 提交前校验 → commit → 提交后复核，完成后立即释放
  - 提交前必须校验目标清单与变更集一致（verify_targets.py --mode pre），提交后必须核对实际修订路径（--mode post）
  - 提交规范遵循 rules/vcs/vcs-commit/（摘要、授权安全）与 rules/vcs/vcs-svn-commit/（SVN 专属约束）
references:
  - commit-spec: references/commit-spec.md
  - submission-safety: references/submission-safety.md
  - project-config: references/project-config.md（引擎侧机制）+ 项目侧 .codebuddy.project/configs/skills/vcs/vcs-svn-commit/project-config.md（索引 svn_commit.project_config）
  - vcs-config: 项目侧 .codebuddy.project/configs/skills/vcs/vcs-svn-commit/config.json（索引 svn_commit.config）
  - vcs-lock: references/vcs-lock.md
  - guide: references/guide.md
  - vcs-entry-rules: ../../../../rules/vcs/vcs-router.entry/vcs-router.entry.mdc
  - vcs-router-spec: ../../../../rules/vcs/vcs-router/RULE.mdc
  - vcs-commit-spec: ../../../../rules/vcs/vcs-commit/commit-spec.mdc
  - vcs-safety-spec: ../../../../rules/vcs/vcs-commit/submission-safety-spec.mdc
  - vcs-svn-spec: ../../../../rules/vcs/vcs-svn-commit/svn-commit-spec.mdc
evaluation:
  trigger_evals: evals/trigger_cases.json
