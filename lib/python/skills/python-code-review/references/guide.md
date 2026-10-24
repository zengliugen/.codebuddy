# python-code-review 执行细则

## 一、调度步骤

```
1. 判定模式（A git 变更 / B 单文件 / C 目录 / D 片段）
2. 确认规则文件齐备（4 个子规则）
3. 复制/引用报告落盘路径（不存在则创建）
4. 调度 python-code-review Agent，传入：模式、目标清单、报告路径
5. 回收 Agent 结论：error 计数 + 报告路径
6. 在对话中输出计数与路径（供门禁判定）
```

**技能不自己做审查判断**。若用户直接问「这段代码有什么问题」，应调度 Agent，
而不是凭记忆给结论——入口规则 `python-code/RULE.mdc` 的强制条款即为此设。

## 二、模式判定

| 用户表述 | 模式 | 输入获取 |
|---------|------|---------|
| 审查未提交的变更 / 这次的改动 / diff | A | `git status --porcelain` + `git diff` |
| 审查 `extensions/overrides.py` | B | 直接读取 |
| 审查 `extensions/` 目录 | C | Glob `**/*.py` |
| 粘贴一段代码 | D | 对话内容 |

**多文件时的顺序**：先按目录分层（同一目录的文件连续审查），再按文件名排序，
便于报告阅读。

## 三、范围过滤

模式 A 与 C 必须先过滤，否则会审到不该审的文件：

| 过滤项 | 依据 |
|--------|------|
| 非 `.py` | 技能只审 Python |
| `src/`、`tests/` | 项目侧约定：上游模板与上游基线测试不在审查范围 |
| `__pycache__`、`.venv`、`envs` | 运行产物 |
| 文件头含 `auto-generated` | 生成代码 |

过滤后为空时，输出「本次无 Python 代码需审查」，**不生成空报告**——
空报告会被误读为「已审查且无问题」。

## 四、复用 ruff 结果

审查前先跑一次轻量检查，避免人工重复报格式问题：

```bash
<工具环境>/Scripts/python.exe .codebuddy/lib/python/skills/python-lint/scripts/run_ruff.py check --changed
```

| 情形 | 处理 |
|------|------|
| 有输出 | 作为「格式/规则维度」既有结论，Agent 不重复报 |
| 退出码 3（环境不可用） | 报告注明「格式维度未检查」，不假装通过 |
| 清单为空 | 说明本次无变更，仍可按用户指定模式继续 |

## 五、报告落盘

```
.codebuddy.project/caches/skills/python/python-code-review/check_logs/
├── review-<YYYYMMDD-HHMMSS>.md
└── review-<YYYYMMDD-HHMMSS>.json
```

`.json` 结构：

```json
{
  "scope": "git-changed",
  "files": ["extensions/overrides.py"],
  "counts": {"error": 1, "warning": 2, "info": 0},
  "findings": [
    {"level": "error", "file": "extensions/overrides.py", "line": 42,
     "rule": "bug-spec §1", "message": "可变默认参数", "suggestion": "改用 None 哨兵"}
  ]
}
```

## 六、与门禁的衔接

| 门禁参数 | 取值 | 说明 |
|---------|------|------|
| `enabled` | 需项目侧配置为 `true` 才启用 | 未启用时本技能仅供人工调用 |
| `review_skill` | `python-code-review` | 门禁据此调度 |
| `blocking_level` | `error` | `error > 0` 即阻塞提交 |

门禁调用时，Agent 需在返回中明确给出 **error 计数**与**报告绝对路径**，
门禁据此判定；缺任一项视为未完成审查。

## 七、常见失败处置

| 现象 | 原因 | 处理 |
|------|------|------|
| Agent 未加载规则就出结论 | 跳过了阶段一 | 中止并要求重跑；入口规则禁止此行为 |
| 报告只有 `.md` 无 `.json` | 遗漏 | 补生成；门禁读不到 `.json` 视为失败 |
| 审查了 `src/` 的文件 | 未做范围过滤 | 剔除该部分结论并说明 |
| 大量存量问题涌入 | 未限定「只审本次变更」 | 报告改为只报变更引入的问题，存量单列 |
| 与 ruff 结论重复 | 未复用工具结果 | 删除重复项，保留 ruff 结论 |
