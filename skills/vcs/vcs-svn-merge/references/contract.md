# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来，承载完整契约细节。

description: "SVN 合并占位技能，用于保证 vcs-router 路由链路完整，不承载任何合并逻辑。"
input_contract:
  required:
    - trigger: 用户要求合并 SVN 分支/标签，或 vcs-router 路由到本技能
  optional:
    - source_url: 源分支/标签 URL（仅用于提示文案，不执行）
    - target_path: 目标工作副本路径（仅用于提示文案，不执行）
output_contract:
  required:
    - notice: 固定提示"当前未实现 svn merge 流程"
exclusion_contract:
  - all_svn_operations: 任何 SVN 命令执行（merge / switch / info / status 等）
  - preflight_flow: 代码审查、安全检查等前置流程
  - switch: svn switch
  - relocate: svn relocate
  - update: svn update
  - branch_tag: 分支与标签创建（svn copy）
safety_constraints:
  - 禁止执行任何 SVN 命令
  - 禁止触发审查或安全检查流程
  - 仅返回固定提示，不得越权
references:
  - merge-spec: ../../../../rules/vcs/vcs-svn-merge/svn-merge-spec.mdc
