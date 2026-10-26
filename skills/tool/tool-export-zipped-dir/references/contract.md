# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

input:
  source:
    description: "要导出的目录路径（当前 git 仓库内的相对路径，如 .codebuddy）"
    type: "string"
    required: true
    validation: "must exist on filesystem and be inside current git repo"
  output:
    description: "输出的 zip 文件路径；未指定时默认导出到用户下载目录，文件名带日期"
    type: "string"
    required: false
    validation: "must be writable path"
  force:
    description: "强制包含的被 gitignore 忽略文件列表（仓库相对路径），如根目录配置 json"
    type: "array"
    items:
      type: "string"
    required: false
    default: []
output:
  format: "zip"
  artifact:
    - "包含源目录内未被忽略文件的 zip 压缩包，保持相对路径结构"
  summary:
    - "导出的文件总数"
    - "强制包含的文件列表"
    - "zip 的完整路径"
exclusions:
  - "非 git 仓库内的路径"
  - "单文件导出（不属于本技能职责，建议直接复制）"
  - "被 gitignore 忽略的文件，除非通过 force 明确指定"
