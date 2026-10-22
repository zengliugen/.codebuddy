# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: "C# 代码注释规范化技能，由 Agent 逐项分析代码上下文后生成或修正注释，禁止脚本批量处理。"
input_contract:
  required:
    - target: 待处理的 .cs 文件或目录
    - check_report: csharp-comment-checker 产出的 JSON 检查报告（全量生成场景可为空）
  optional:
    - member_filter: 仅处理指定成员
    - scope: 处理范围（file / directory）
  fallback:
    - scan_first: 目标为目录或请求含"扫描+修复"语义时，先调用 csharp-comment-checker 产出报告
output_contract:
  required:
    - modified_files: 已修改的 .cs 文件清单
    - change_summary: 每个文件的注释新增与修正条目数
  optional:
    - verify_report: 复扫验证报告（问题清零证据）
exclusion_contract:
  - scan_only: 仅检查不修改（走 csharp-comment-checker）
  - code_logic: 代码逻辑修改
  - non_csharp: 非 .cs 文件
  - generated_code: Generated/、Gen/ 目录及 auto-generated 标记文件
safety_constraints:
  - 注释必须由 LLM 逐项分析生成，禁止脚本、模板、正则批量生成
  - 禁止无报告的自由发挥修复（全量生成场景除外，且验证环节不可省略）
  - 修复完成后必须复扫验证，残留问题须明确说明
references:
  - examples: references/examples.md
  - checker: ../csharp-comment-checker/SKILL.md
