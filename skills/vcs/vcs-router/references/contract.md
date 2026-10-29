# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: 版本控制操作统一入口（路由技能）。当用户要求提交代码或执行其他版本控制操作时触发，识别操作类型（commit/merge 等）并检测当前目录是 Git 仓库还是 SVN 工作副本，路由到对应 `vcs-<vcs>-<op>` 执行技能（两个 commit 已实现 / 两个 merge 当前为占位空实现）。仅负责识别与路由，不执行实际操作。
input_contract:
  required:
    - trigger: 用户明确要求执行版本控制操作（含"提交代码"、"git commit"、"svn commit"、"git merge"、"svn merge"等）
  optional:
    - operation: 用户指定的操作类型（commit / merge 等，默认 commit）
    - target_path: 用户指定的目标目录（默认当前工作目录）
    - vcs_hint: 用户显式指定的版本控制类型（"git commit" / "svn commit"），指定后跳过检测
  fallback:
    - vcs_detection: 通过 scripts/route_vcs.cmd 调用路由脚本（Git 优先、SVN 次之），脚本内置缓存读写
    - vcs_cache: 读取项目侧产物 .cache/vcs-route.json 缓存（目录路径一致且未超过 10 分钟时命中），命中则直接返回缓存结果
    - target_check: 脚本检查目标技能 <扫描根>/<pack>/<target>/SKILL.md 是否存在（逐包查找），输出 target_exists
output_contract:
  required:
    - vcs_type: 检测结果（git / svn / none）
    - operation: 操作类型（commit / merge 等）
    - route_target: 路由目标技能（vcs-<vcs>-<op>，如 vcs-git-commit / vcs-svn-commit）
    - target_exists: 目标技能是否存在（true / false）
  optional:
    - detection_evidence: 检测命令的输出证据
    - cache_hit: 是否命中检测结果缓存（true / false）
  evidence:
    - detection_result: git rev-parse 与 svn info 的执行结果（或缓存读取结果）
    - cache_record: 缓存文件内容（path / vcs_type / detected_at）
exclusion_contract:
  - actual_operation: 实际执行版本控制操作（提交、合并等）
  - operation_summary: 生成操作摘要
  - user_authorization: 操作前的授权确认
  - code_review: 提交前代码审查
  - amend: git commit --amend
  - rebase: git rebase 操作
  - cherry_pick: git cherry-pick 操作
  - revert: git revert 操作
  - stash: git stash 操作
  - branch_tag: 分支与标签创建/切换/删除操作
  - svn_update_revert_switch: svn update / revert / switch / relocate 操作
  - unsupported_operation: 目标技能不存在时的操作（未创建对应技能或占位技能之外的操作类型）
safety_constraints:
  - 仅负责路由，禁止执行实际操作命令
  - 既非 Git 仓库也非 SVN 工作副本时终止并提示，不猜测版本控制类型
  - 检测顺序固定为 Git 优先、SVN 次之（同时具备两者标记时按 Git 处理，避免提交目标落在外层仓库之外）
  - 用户显式指定类型时以用户指定为准
  - 目标技能不存在（target_exists 为 false）时提示操作暂未支持，禁止猜测执行
  - 缓存命中前必须校验目录路径与超时时间，禁止跨目录或过期缓存误导路由
  - 检测结果为 none 时不写入缓存
  - 缓存文件仅本机使用，不纳入版本控制
references:
  - vcs-git-commit: ../../vcs-git-commit/SKILL.md
  - vcs-svn-commit: ../../vcs-svn-commit/SKILL.md
  - vcs-git-merge: ../../vcs-git-merge/SKILL.md
  - vcs-svn-merge: ../../vcs-svn-merge/SKILL.md
evaluation:
  trigger_evals: evals/trigger/
