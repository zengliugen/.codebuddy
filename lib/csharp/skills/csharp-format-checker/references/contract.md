# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: C# 代码格式检查与修复技能。当用户要求检查/扫描 C# 代码格式、执行 dotnet format、格式化 C# 代码、把格式检查作为提交前步骤时触发，使用 dotnet format 按项目根 .editorconfig 检查（默认只读 verify）或修复（fix 需确认）C# 代码格式；忽略目录由项目侧配置（索引 `format_checker.config`）指定（排除三方插件与生成代码，既不被检查也不被修改）。
input_contract:
  required:
    - trigger: 用户明确要求检查/修复 C# 代码格式（含"检查代码格式"、"格式化代码"、"跑 dotnet format"、"代码风格是否合规"等）
  optional:
    - mode: 执行模式（check 默认只检查不修改 / fix 落盘修改）
    - target_path: 用户指定的目标目录或文件（相对项目根）
    - project: 用户指定的工作区文件（.slnx/.sln/.csproj）
    - changed: 只检查本次变更文件所属的工程（--changed，与 target_path/project 互斥）
    - max_projects: 变更工程数上限（--max-projects，仅 --changed 生效，超过则回退整仓）
    - reuse_report: 复用 5 分钟内范围一致的报告（--reuse-report，仅 check 模式）
    - config: 配置文件路径（默认经索引 format_checker.config 定位到项目侧）
  fallback:
    - project_root: 脚本从当前目录向上查找含 .editorconfig 的目录作为项目根
    - config_file: 读取项目侧配置（索引 format_checker.config 定位），缺失时报错退出（不生成模板）
    - workspace: 配置 workspace 为空时自动探测（*.slnx → *.sln → *.csproj）
    - exclude_dirs: 忽略目录来自配置，脚本通过 --exclude 传给 dotnet format
    - changed_scope: --changed 无法定位变更工程时回退整仓并告警（非 git 环境、无变更 .cs、文件全在忽略目录内、文件不在任何工程内、工程数超上限）
output_contract:
  required:
    - exit_code: dotnet format 退出码（0 合规或修复完成 / 2 check 存在待格式化文件 / 1 执行出错）
    - log_file: check_logs/ 下 .log 完整原始输出
    - report_file: check_logs/ 下 .md 摘要报告（工作区/检查范围/分组/退出码/诊断统计）
    - json_file: check_logs/ 下 .json 结构化报告（含 scope_key 与 scope 范围信息，供 --reuse-report 严格匹配复用）
  optional:
    - formatted_count: 需格式化（check）或已格式化（fix）的统计信息
  evidence:
    - editorconfig: 项目根 .editorconfig 路径（唯一格式标准）
    - workspace: 实际使用的解决方案/工程文件
    - exclude_dirs: 本次实际生效的忽略目录
    - raw_output: dotnet format 完整输出
exclusion_contract:
  - comment_check: XML 文档注释/行内注释内容合规性检查（csharp-comment-checker）
  - non_csharp: 非 .cs / .editorconfig 未覆盖文件
  - ignored_dirs: 配置 exclude_dirs 内的目录与文件（不检查、不修改）
  - code_review: 代码审查（csharp-code-review）
  - auto_confirm_fix: 未获用户确认的大范围 fix（禁止静默改写源码）
safety_constraints:
  - check 模式禁止修改任何源码文件（使用 --verify-no-changes）
  - 忽略目录内的文件既不被检查也不被修改，禁止绕过
  - fix 模式整仓执行前必须经 AskUserQuestion 确认
  - fix 后必须用 git 状态核对变更，确认三方插件目录无改动
  - 禁止预扫描文件列表，发现/过滤全部由脚本与 dotnet format 完成
  - 结果文件必须落盘到 check_logs/（除非用户 --no-save）
references:
  - guide: references/guide.md
  - config-guide: references/config-guide.md
  - h1-integration: references/h1-integration.md（提交门禁 H1 集成说明）
  - output-risk: reports/output-risk-profile.md
evaluation:
  trigger_evals: evals/trigger/
