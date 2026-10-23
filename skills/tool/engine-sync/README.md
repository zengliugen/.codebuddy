# 引擎同步（engine-sync）

<!-- pack-ref-ok: vcs-router, git-commit, yao-meta-skill —— 「不做什么 / 交给谁」职责分流表，纯说明性，不调用这些组件。 -->

把引擎仓库（`.codebuddy/`）的更新**落实到项目侧**（`.codebuddy.project/`）。

## 解决什么问题

引擎以子模块分发，`git pull` 只更新引擎文件本身。但项目侧通过 `project.index.json`
与 `lib/packs.json` 与引擎耦合——索引路径变了、条目增删了、包结构变了，项目侧
**不会自动跟随**，表现为静默失效：

- 技能报「配置缺失」，但项目侧文件确实存在（索引路径已改，文件还在旧位置）
- 新技能不出现（包已装但未重启会话，或注册表变更未物化）
- 旧配置残留无人清理（索引条目已移除）
- 规则正文读不到（`rule_shells` 路径变更未迁移）

本技能把这类影响显性化，并在授权后落实。

## 怎么用

1. 触发：说「更新引擎并同步项目侧」或「/engine-sync」。
2. 技能执行六阶段：前置检查 → 更新引擎 → 分析影响 → 汇报授权 → 落实同步 → 报告。
3. 核心命令：

```bash
python .codebuddy/skills/tool/engine-sync/scripts/analyze_impact.py --from <旧HEAD> --to <新HEAD>
```

输出按三档严重度分组：`action_required`（必须处理）/ `suggest`（建议处理）/ `info`（仅告知）。

## 边界

| 不做 | 交给谁 |
|------|--------|
| 首次初始化项目侧 | `codebuddy-init` |
| 提交与推送 | `vcs-router` / `git-commit` |
| 创建或重构技能 | `yao-meta-skill` |
| 规则拆分合并 | `rule-consolidation` |

## 文档

| 文件 | 内容 |
|------|------|
| `references/guide.md` | 六阶段执行流程与检查清单 |
| `references/impact-model.md` | 影响模型：检测范围、三档严重度判定 |
| `references/sync-playbook.md` | 落实手册：各变更类型的步骤与回滚边界 |
| `scripts/analyze_impact.py` | 影响分析脚本（只读） |
| `security/permission_policy.json` | 权限声明（subprocess 仅限 git 只读） |
