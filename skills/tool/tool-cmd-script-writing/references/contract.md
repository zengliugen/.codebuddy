# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

input:
  task:
    description: "脚本编写或修复任务；可提供脚本用途、目标平台（Windows CMD）、是否含中文输出、输入输出参数"
    type: "string"
    required: true
  script_path:
    description: "要修复的既有 .cmd/.bat 脚本路径；仅修复场景需要"
    type: "string"
    required: false
  output_encoding:
    description: "输出脚本的编码；默认 UTF-8 无 BOM（符合项目语言规范），行尾 CRLF"
    type: "string"
    required: false
    default: "utf-8-no-bom"
output:
  format: "batch-script"
  artifact:
    - "可运行的 .cmd/.bat 脚本，中文输出正常（行尾 ASCII 规避乱码）"
    - "修复场景：诊断报告 + 修复后的脚本代码"
    - "校验器扫描结果（check_cmd_trailing.py 输出，确认无行尾中文风险）"
  summary:
    - "脚本路径或修复内容"
    - "已应用的关键规范（UTF-8 行尾、goto 规避、路径处理）"
    - "验证结果（校验器通过 + 实际运行确认无 is not recognized 报错）"
exclusions:
  - "PowerShell 脚本（.ps1）"
  - "Python / Bash / Linux shell 脚本"
  - "业务逻辑设计（非脚本语法与编码问题）"
  - "已生成的 Generate/Gen 目录代码"
