# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: Git 提交执行技能。当用户要求提交 Git 代码（"git commit"、"提交到 git"，或由 vcs-router 技能路由）时触发，分析 Git 变更并生成标准化提交摘要，提交前按项目配置自动触发代码审查门禁（文件模式与阻塞级别均按项目配置，达阻塞级别问题则阻止提交）。不支持 amend、rebase、cherry-pick、revert、stash、分支操作。
input_contract:
  required:
    - trigger: 用户明确要求执行 git commit 操作（或 vcs-router 路由到本技能）；当项目配置 commit_initiation=llm_allowed 时，LLM 亦可自行发起
  optional:
    - conversation_context: 本次对话中的文件修改记录
    - user_preference_scope: 用户指定的 scope
    - user_preference_type: 用户指定的提交类型
    - skip_review: 用户指定跳过提交前审查（需明确授权）
  fallback:
    - git_diff: 对话无修改信息时分析本地 Git 变更
output_contract:
  required:
    - commit_plan: 提交计划（各组提交的摘要和涉及文件）
    - commit_hash: 每次提交的哈希值
    - commit_summary: 每次提交的标准化摘要
  optional:
    - push_plan: 推送计划（待推送的提交列表）
    - review_report: 提交前审查报告路径（触发审查步骤时）
  evidence:
    - gitignore_check: .gitignore 交叉比对结果
    - user_authorization: AskUserQuestion 授权记录
    - review_result: 提交前代码审查结果（error/warning/info 统计与报告路径）
exclusion_contract:
  - amend: git commit --amend 操作
  - rebase: git rebase 操作
  - cherry_pick: git cherry-pick 操作
  - revert: git revert 操作
  - stash: git stash 操作
  - branch: 分支创建/切换/删除操作
  - merge: git merge 操作
  - force_push: 未经用户明确指定的 git push --force
safety_constraints:
  - 所有确认必须通过 AskUserQuestion 工具
  - 禁止提交 .gitignore 中已忽略的文件
  - 提交与推送强制分离
  - 禁止使用 git add -f 强制添加忽略文件
  - 禁止在 hook 失败时使用 --no-verify（除非用户明确指定）
  - 提交前按项目配置执行 H1 暂存前钩子（步骤清单、文件模式、审查技能全部来自项目侧配置，引擎不提供默认值）
  - 存在 error 级别审查问题时必须修复或获用户明确授权忽略，禁止静默提交
  - 提交/推送发起权按项目配置（commit_initiation/push_initiation，user_only 或 llm_allowed）；user_only 时禁止 LLM 自动发起，llm_allowed 时放开授权但仍须提交推送分离
  - 获得用户授权后、暂存前必须获取 VCS 写操作锁（vcs-router/scripts/vcs_lock.py），锁内完成 add→暂存区校验→commit，提交后必须立即释放（含中止/失败路径）；逐笔加锁，锁窗口不跨越用户交互
  - 提交前必须校验暂存区文件列表与提交计划完全一致（防多会话暂存区污染）
  - 提交规范（摘要格式/授权/安全/Git 特定约束）遵循 rules/vcs/vcs-git-commit/ 下的分项规范（commit-spec / submission-safety-spec / git-commit-spec）；入口约束在 rules/vcs/vcs-router.entry/；审查门禁机制见 references/project-config.md §2（参数见项目侧 project-config.md）
references:
  - commit-spec: references/commit-spec.md
  - submission-safety: references/submission-safety.md
  - project-config: references/project-config.md（引擎侧机制）+ 项目侧 .codebuddy.project/configs/skills/vcs/vcs-git-commit/project-config.md（索引 git_commit.project_config）
  - vcs-config: 项目侧 .codebuddy.project/configs/skills/vcs/vcs-git-commit/config.json（索引 git_commit.config）
  - vcs-lock: references/vcs-lock.md
  - vcs-entry-rules: ../../../../rules/vcs/vcs-router.entry/vcs-router.entry.mdc
  - vcs-router-spec: ../../../../rules/vcs/vcs-router/RULE.mdc
  - vcs-commit-spec: ../../../../rules/vcs/vcs-git-commit/commit-spec.mdc
  - vcs-safety-spec: ../../../../rules/vcs/vcs-git-commit/submission-safety-spec.mdc
  - vcs-git-spec: ../../../../rules/vcs/vcs-git-commit/git-commit-spec.mdc
evaluation:
  trigger_evals: evals/trigger/
  output_risk_profile: reports/output-risk-profile.md
