# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），
详细输入/输出/排除/安全/引用契约在此按需读取。

input:
  action:
    description: "操作类型：scan（只检测）或 fix（按规范修复）"
    type: "string"
    required: true
    enum: ["scan", "fix"]
  tree:
    description: "只处理某一棵树；缺省时两棵树都处理"
    type: "string"
    required: false
    enum: ["engine", "project"]
  json:
    description: "以 JSON 输出，供其他脚本消费"
    type: "boolean"
    required: false
    default: false

output:
  format: "text | json"
  artifact:
    - "问题清单，按类型分组（纯冗余 / 悬空分组 / 头注释漂移 / 通用项副本 / 树根兜底缺失）"
    - "每项含文件路径，必要时含行号与修复建议"
    - "统计：扫描的组件级文件数、纯冗余文件数、已豁免的 vendor 包名"
  summary:
    - "是否合规（退出码 0/1）"
    - "处理了哪些文件、删除了哪些文件"
    - "验证结果（git status 无意外变化、已跟踪文件未被新规则命中）"

exclusions:
  - "vendor 包（lib/packs.json 中 vendor: true）的 .gitignore"
  - "svn:ignore（属 SVN 专属机制，不是工作区文件）"
  - "业务产物该不该产生、该不该外置到 caches/（属 core-engine 的产物外置约定）"

safety:
  - "脚本不自动改写文件——分组注释里的人工说明无法机械生成，擅自重写会抹掉最有价值的部分"
  - "修复后必须复跑 scan 直到退出码 0"
  - "必须用 git ls-files -i -c --exclude-standard 确认没有已跟踪文件被新规则命中"
  - "vendor 包豁免依赖显式元数据，不靠 README 文本猜测"

references:
  - "references/spec.md：三层归属模型、格式契约、判定流程、正反例、自检清单"
  - "scripts/tool_gitignore.py：检测脚本（scan / fix / --json / --tree）"
