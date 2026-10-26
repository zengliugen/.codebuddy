# 详细流程与规则

## 工作流程

当用户要求更新引擎并同步项目侧时，按以下六阶段执行。

### 阶段一：前置检查（只读）

1. 定位引擎根与项目根：脚本经 `project.index.json` 标记文件自动定位，无需手填。
2. 确认引擎仓库状态：当前分支、是否有未提交改动、是否有进行中的合并/变基。
   - 工作区**脏**时：`update_repo.py` 只报告不拉取。此时**先问用户**是提交、暂存还是放弃，
     不得擅自丢弃改动。
3. 记录当前子模块指针（`git rev-parse HEAD`），供后续对比与回滚。

### 阶段二：执行引擎更新

```bash
python .codebuddy/scripts/update_repo.py
```

- 该脚本负责：`fetch --prune` → 差异统计 → `pull --ff-only` → 重建包链接（`pack_install verify --repair`）。
- **不可快进**（本地与远程分叉）时脚本会报错中止。此时向用户说明分叉情况，
  由用户决定 rebase / merge / 放弃，**不得自行处理分叉**。
- 更新完成后记录新的 HEAD，作为影响分析的 `--to`，旧的 HEAD 作为 `--from`。

### 阶段三：分析项目侧影响

```bash
python .codebuddy/skills/tool/tool-engine-sync/scripts/analyze_impact.py --from <旧HEAD> --to <新HEAD>
```

脚本对比两个版本的**项目侧契约**，按三档严重度输出：

| 档位 | 含义 | 处理原则 |
|------|------|---------|
| `action_required` | 契约已变且**不处理会缺失或失效** | 必须处理；用户拒绝时须明确告知后果 |
| `suggest` | 残留或可选优化 | 列出清单，由用户决定是否清理 |
| `info` | 仅告知，无需动作 | 简略汇报即可 |

检测范围见 `references/impact-model.md`。**必须实际运行脚本**，不得凭 `git log` 摘要臆测。

### 阶段四：汇报影响并请求授权

用 `AskUserQuestion` 呈现影响清单，选项须具体：

- `action_required` 逐项列出（名称、旧/新路径、将要执行的动作）。
- `suggest` 列出摘要，说明"可跳过"。
- **明确告知**哪些操作会**删除**文件（如清理残留），获得确认后才执行。

### 阶段五：落实同步

按变更类型执行标准动作，详见 `references/sync-playbook.md`：

| 变更类型 | 标准动作 |
|---|---|
| 索引路径变更（旧路径有文件、新路径无） | 迁移文件（保留内容），清理空目录 |
| 新增索引条目 | `init_project_config.py --setup` 生成缺失骨架 |
| 条目移除 | 确认后清理残留（`--prune-orphans` 或手工） |
| 包新增 | 说明可选包，询问是否安装 |
| 包内新增技能/规则 | 提示重开会话后生效 |
| 包移除（已安装） | 提示链接将失效，需卸载 |
| 根级软链接变更 | 重建链接 |

落实后**必须验证**：

```bash
python .codebuddy/scripts/check_manifest.py
python .codebuddy/scripts/pack_install.py status
python .codebuddy/skills/core/core-init/scripts/init_project_config.py --status
```

### 阶段六：报告与后续

- 汇报：更新了多少提交、处理了哪些项、跳过了哪些项、验证结果。
- **提示子模块指针**：若引擎为子模块，更新后父仓仍锁定旧提交，需提交指针才会对他人生效。
- **提示提交**：本技能不提交；如需提交，走 `vcs-router`（引擎仓库与父仓指针为两笔）。

## 三档严重度与处理原则

**action_required 不可静默跳过**。若用户选择跳过，须记录在报告中并说明后果
（如"该配置项将持续缺失，相关技能首次运行会报错"）。

**suggest 不默认执行**。典型如清理旧缓存目录——内容是运行时产物，删了也无损失，
但仍需确认，避免误删用户手工放入的文件。

**info 不必逐条罗列**。汇总数量 + 一句结论即可，避免淹没关键信息。

## 检查清单

- [ ] 更新前是否记录了旧 HEAD，供 `--from` 使用？
- [ ] 工作区脏时是否先询问用户，未擅自丢弃改动？
- [ ] 不可快进时是否交由用户决策，未自行 rebase/merge？
- [ ] 是否**实际运行** `analyze_impact.py`，而非凭提交摘要臆测？
- [ ] `action_required` 项是否逐项汇报并取得授权？
- [ ] 涉及删除的操作是否明确告警并获确认？
- [ ] 文件迁移是否**保留原内容**（不得重新生成覆盖用户已填值）？
- [ ] 落实后是否跑了三项验证（check_manifest / pack status / init --status）？
- [ ] 是否提示了子模块指针需另行提交？
- [ ] 是否说明了本次未提交、提交需走 `vcs-router`？
