# 同步落实手册

按变更类型给出的执行步骤、验证方法与回滚边界。

## 通用原则

1. **保留用户已填内容**：迁移 = 移动文件，**不得重新生成覆盖**。只有"生成缺失骨架"才走 `init_project_config.py`，
   且它自带幂等保护（已存在即跳过）。
2. **删除前必须确认**：任何删除（残留清理、空目录）都要在 `AskUserQuestion` 中显式列出并获授权。
3. **落实后必验证**：三项验证全过才算完成（见文末）。
4. **不提交**：本技能只改文件；提交由 `vcs-router` 承接，且引擎仓库与父仓指针是**两笔**。

## 一、索引路径变更（迁移文件）

**场景**：`action_required` 且标注"需迁移项目侧文件（旧路径存在、新路径缺失）"。

```bash
# 1. 确认旧路径存在、新路径不存在
# 2. 建立新目录并移动（保留内容与 git 历史）
#    单条：手工 mv；多条：写一次性脚本批量处理
# 3. 清理因此变空的旧目录（自底向上，止于 configs/ 或 caches/）
```

**要点**：

- 优先用 `git mv`（在项目仓库内）以便 git 识别为重命名、保留历史；批量时可用脚本 + `git add -A`，
  提交时 git 通常仍能自动识别 rename。
- 迁移后**立即验证内容未变**（对比文件大小或哈希），再删空目录。
- 若新路径已存在内容（冲突），**停止并询问用户**，不得覆盖。

## 二、新增索引条目（生成骨架）

**场景**：`action_required` 且标注"需生成项目侧骨架"。

```bash
python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py --setup
```

- 该脚本按生效包集合过滤，只为已装包生成，幂等跳过已存在文件。
- 生成的是**占位骨架**，须提示用户：未填写前相关技能会报"配置缺失"。
- 若条目属于**未装包**，不生成；此时应提示"该配置属于包 X，需要时先装包"。

## 三、条目移除（清理残留）

**场景**：`suggest` 且标注"索引已移除但项目侧文件仍在"。

```bash
# 列出全部孤儿项（不删）
python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py --status

# 确认后清理（只删配置文件与空产物目录，非空目录不删）
python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py --prune-orphans
```

**要点**：

- `--prune-orphans` 只清理由索引判定的孤儿，不会误删已装包的文件。
- 非空的产物目录**不会**被删（防止误删用户手工放入的内容），会列在"未能删除"中。
- 若用户只想清理个别项，改为手工删除并在报告中记录。

## 四、包变更

### 新增包（可选包）

```bash
python .codebuddy/scripts/pack_install.py install <pack>
```

- **必须先询问用户**是否需要该包，不得自动安装。
- 安装后：项目侧配置与产物目录需再跑一次 `init_project_config.py --setup` 才会生成。
- 提示：**新增技能需重开会话**才会出现在技能目录。

### 包移除（已安装）

- 该包的扫描根链接将失效，技能/规则不可用。
- 执行 `pack_install.py remove <pack>`，再用 `--prune-orphans` 清理项目侧残留。
- 属破坏性操作，**必须明确告警**。

### 包内新增技能 / 规则

- 无需文件操作，仅**提示用户**：已装该包则重开会话后可用。
- 若新增的是规则（`.mdc`），说明其触发方式（`alwaysApply` 或 `paths`），便于用户预期。

## 五、根级软链接变更

```bash
# 重建（幂等，已正确则跳过）
python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py --setup
```

- 链接失败（Windows 未开开发者模式）时，脚本会告警并给出 `mklink` 命令，转告用户手工执行。
- 验证：`git -C .codebuddy status` 中该链接应为符号链接（`120000` 模式）。

## 六、验证（必做）

```bash
python .codebuddy/scripts/check_manifest.py                                        # 清单一致性
python .codebuddy/scripts/pack_install.py status                                   # 包链接一致性
python .codebuddy/skills/core/codebuddy-init/scripts/init_project_config.py --status  # 配置/孤儿/链接
```

三条全为退出码 0 且输出"一致"才算同步完成。任一失败：

- 回滚本次项目侧改动（`git checkout -- .codebuddy.project` 或反向迁移）；
- 报告中说明失败原因，不要留下半完成状态。

## 七、回滚边界

| 操作 | 可否回滚 | 方法 |
|---|---|---|
| 引擎 `pull` | 可 | 引擎仓库 `git reset --hard <旧HEAD>`（仅未推送时安全） |
| 项目侧文件迁移 | 可 | 项目仓库 `git checkout -- .codebuddy.project` |
| 骨架生成 | 可 | 删除新生成文件（未填写则无损失） |
| 残留清理 | **不可** | 内容已删；故清理前必须确认 |
| 包卸载 | 可 | 重新 `pack_install.py install`（配置文件若已清理需重新生成） |

> 迁移与生成都在项目仓库版本控制下，`git checkout` 即可恢复。
> **清理不可回滚**是唯一需要格外谨慎的操作。
