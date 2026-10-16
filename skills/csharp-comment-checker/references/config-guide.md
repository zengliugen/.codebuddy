# 配置文件指南

## 配置文件位置

配置分两层，读取时**深度合并**（项目侧覆盖引擎侧，数组取并集）：

- **引擎侧**：`tools/CSharpCommentChecker/comment_config.json`（`rules` 规则与严重程度，随引擎共享）。
- **项目侧**：索引逻辑名 `comment.project_config`（`comment_config.project.json`，`exclude.paths` 排除目录与 `knownTerms` 项目术语）。

目标项目只改项目侧配置。

## 配置结构

每个规则包含 `enabled`（是否启用）、`description`（描述）、`issues`（Issue 字典）三个字段。`issues` 的 key 为 Issue Category，value 为 `IssueConfig`（含 `enabled`、`severity` 和 `description`）。**配置了什么就检查什么**——未在 `issues` 中显式列出的 Category 不会生成 Issue，`enabled` 设为 `false` 的 Issue 也会跳过。

```json
{
  "exclude": { "paths": ["/Generated/"] },
  "rules": {
    "doc_missing_method": {
      "enabled": true,
      "description": "方法缺少 XML 文档注释",
      "issues": {
        "missing_doc_comment": { "enabled": true, "severity": "error", "description": "方法缺少 XML 文档注释" },
        "missing_summary": { "enabled": true, "severity": "error", "description": "缺少 <summary> 标签" },
        "summary_no_period": { "enabled": true, "severity": "warning", "description": "<summary> 内容不以句号（。）结尾" },
        "missing_param": { "enabled": true, "severity": "warning", "description": "方法参数缺少 <param> 文档注释" }
      }
    }
  }
}
```

## 常见定制场景

- **关闭某规则**：将对应规则的 `"enabled"` 设为 `false`
- **关闭规则下某类检查**：将对应 Issue 的 `"enabled"` 设为 `false`（无需删除整个 key）
- **调整严重程度**：修改 `issues` 中对应 Category 的 `"severity"` 值（error/warning/info）
- **删除某类检查**：从 `issues` 字典中删除对应 Category key

## 技术术语白名单（knownTerms）

`language` 规则在判断注释是否使用简体中文时，会先剥离技术术语白名单中的英文术语（大小写不敏感），避免将 `AssetBundle`、`HybridCLR` 等术语误判为英文注释。该白名单可通过配置文件的顶层 `knownTerms` 数组按项目定制：

```json
{
  "exclude": { "paths": ["/Generated/"] },
  "knownTerms": ["AssetBundle", "HybridCLR", "Unity", "MVVM", "C#", "Git"],
  "rules": { }
}
```

说明：
- **配置为唯一来源**：术语表完全由 `knownTerms` 声明，工具不内置默认术语；该字段缺失会导致配置加载报错（退出码 3）。
- **按项目定制**：在数组中列出该项目需保留英文的技术术语，避免被 `language` 规则误报为英文注释。
- **大小写不敏感**：`Json` 可匹配注释中的 `JSON`/`json`，无需重复登记大小写变体。
- **清空即不剥离**：显式配置为空数组 `[]` 表示不剥离任何术语。

## 规则文件与配置的关系

项目的注释规范定义在 `.codebuddy/rules/csharp-comment/` 目录下的 `.mdc` 文件中。这些文件为人工维护的规范文档。本技能的检查逻辑由独立的运行时配置文件 `comment_config.json` 驱动，不直接读取 `.mdc` 文件。

> **注意：** 修改规范文件（`.mdc`）后，需要同步更新 `comment_config.json` 中的对应规则配置，否则检查行为不会自动变更。
