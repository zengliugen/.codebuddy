# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: "Git 合并占位技能，用于保证 vcs-router 路由链路完整，不承载任何合并逻辑。"
input_contract:
  required:
    - trigger: 用户要求合并 Git 分支，或 vcs-router 路由到本技能
  optional:
    - source_branch: 源分支名（仅用于提示文案，不执行）
output_contract:
  required:
    - notice: 固定提示"当前未实现 git merge 流程"
exclusion_contract:
  - all_git_operations: 任何 Git 命令执行（merge / diff / status 等）
  - preflight_flow: 代码审查、安全检查等前置流程
  - rebase: git rebase
  - cherry_pick: git cherry-pick
  - revert: git revert
  - stash: git stash
  - branch: 分支操作
safety_constraints:
  - 禁止执行任何 Git 命令
  - 禁止触发审查或安全检查流程
  - 仅返回固定提示，不得越权
references:
  - merge-spec: ../../rules/vcs-router/git-merge-spec.mdc
