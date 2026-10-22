# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

input:
  project_path:
    description: "项目绝对路径（环境检查默认取当前工作目录）"
    type: "string"
    required: false
  target_file:
    description: "目标 .cs 文件绝对路径（LSP 操作对象）"
    type: "string"
    required: false
    validation: "must exist on filesystem"
output:
  format:
    - type: "env_report"
      description: "环境检查结果：csharp-ls 安装状态 + csharp-lsp 插件安装/启用/加载状态，含修复指引"
    - type: "lsp_result"
      description: "LSP 操作返回的符号/定义/引用/悬停信息"
boundary:
  inclusions:
    - "csharp-ls 语言服务器安装检查"
    - "csharp-lsp 插件安装/开启检查"
    - "LSP 代码智能操作（goToDefinition、findReferences、hover、goToImplementation、documentSymbol、workspaceSymbol、prepareCallHierarchy、incomingCalls、outgoingCalls）"
  exclusions:
    - "不修改源代码（本技能只查询，不编辑）"
    - "不替代 csharp-code / csharp-comment / unity-pipeline"
    - "不检查 Unity 编译错误（由 unity-pipeline 的 recompile 负责）"
  constraints:
    - "仅支持 .cs 文件（插件 extensionToLanguage 仅映射 .cs）"
    - "LSP 操作需先经 ToolSearch 加载 LSP 工具"
    - "line 与 character 使用 1-based 索引；所有操作均须传这两个参数，无位置概念的操作（documentSymbol、workspaceSymbol）传 1"
    - "环境检查结果带本地缓存（技能目录 .cache/，按项目隔离）：24 小时内且环境指纹未变化时复用上次通过结论；环境变化自动失效，强制重查加 --no-cache"
  limitations:
    - "csharp-ls 首次冷启动索引大型工程较慢"
    - "LSP 结果为空时需回退 Grep/Read 手动查找"
