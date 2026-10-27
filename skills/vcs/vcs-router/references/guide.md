# 详细流程与规则



本文件由 `SKILL.md` 拆分而来，承载完整执行细节；主文件只保留触发、契约与流程骨架。



## 通用基础技能说明
本技能为**通用基础技能**，无项目特定配置，迁移到其他项目后无需修改本文件（路由检测、缓存、互斥锁逻辑均通用）。项目可配置项位于：
- 提交摘要确定性参数（type/长度/语言）：项目侧 `.codebuddy.project/configs/skills/vcs/vcs-git-commit/config.json`（索引 `git_commit.config`）
- 流程级配置（scope 规则、审查门禁参数、钩子步骤取值）：项目侧 `.codebuddy.project/configs/skills/vcs/vcs-git-commit/project-config.md`（索引 `git_commit.project_config`）；机制见 `.codebuddy/skills/vcs/vcs-git-commit/references/project-config.md`

## 路由规则
路由采用**双维度**设计：`操作类型（operation）` + `版本控制类型（vcs type）`，组合出目标技能 `git-<op>`。commit 与 merge 操作已纳入路由，未来扩展新操作（如 revert、stash、branch）时沿用统一入口。

### 1. 识别操作类型

从用户请求中识别操作类型，默认 `commit`：

| 操作类型 | 关键词示例 | 目标技能（`git-<op>`） | 状态 |
|---------|-----------|----------------------|------|
| `commit` | 提交、commit、/commit | `vcs-git-commit` | 已实现 |
| `merge` | 合并、merge | `vcs-git-merge` | 占位（暂未实现，仅提示） |

- 用户未显式指定操作时，默认按 `commit` 处理。
- 未来扩展新操作（如 `revert`、`stash`、`branch`）时，只需新增目标技能目录 `skills/git-<op>/`，无需修改本技能。

### 2. 检测版本控制类型并组合路由

检测、缓存读写与目标存在性校验统一通过脚本完成（`scripts/route_vcs.cmd` 批处理入口 + `scripts/route_vcs.py` 核心逻辑）：

```bash
# 检测当前目录并输出 JSON 路由结果（缓存命中时直接返回缓存结果）
.codebuddy/skills/vcs/vcs-router/scripts/route_vcs.cmd --op <操作类型>

# 可选参数：
#   --dir 目录       指定检测目录（默认当前工作目录）
#   --op 操作        操作类型（默认 commit，如 commit/merge）
#   --refresh        忽略缓存，强制重新检测
#   --timeout 秒     缓存超时阈值（默认 600）
#   --out 文件       将完整路由 JSON 额外写入该文件
#   --quiet          stdout 仅输出一行 vcs_type/route_target 摘要（规避终端伪影污染 JSON 解析；
#                    未指定 --out 时完整 JSON 落到 .cache/vcs-route.result.json）
```

脚本输出 JSON（stdout），退出码 0 表示成功：

```json
{
  "vcs_type": "git | none",
  "operation": "commit | merge | ...",
  "route_target": "git-commit | git-merge | ... | 空",
  "target_exists": true,
  "cache_hit": true,
  "cache_file": "<缓存文件绝对路径>",
  "detected_at": 1234567890,
  "source": "cache | detection"
}
```

脚本底层执行的检测命令（与以下命令等价）：

```bash
# 1. 是否 Git 仓库（含 worktree）
git rev-parse --is-inside-work-tree 2>/dev/null

# 2. 辅助：显式查看目录标记
ls -d .git 2>/dev/null
```

#### 2.1 检测结果缓存

为减少重复检测开销，检测结果由脚本缓存到**技能目录**下的本地文件，**不纳入版本控制、不进行上传**：

- **缓存文件**：项目侧 `.codebuddy.project/caches/skills/vcs/vcs-router/.cache/vcs-route.json`（经索引 `artifacts.dirs.vcs_router.cache` 定位）
- **缓存格式**（JSON，仅存 VCS 类型，与操作类型无关）：
  ```json
  {
    "path": "<检测时目录的绝对路径>",
    "vcs_type": "git",
    "detected_at": "<Unix 时间戳>"
  }
  ```
- **读取时机**：路由前脚本先读取缓存，满足以下**全部**条件时直接返回缓存结果，跳过检测命令：
  1. 缓存文件存在且 JSON 可解析。
  2. 缓存 `path` 与当前目录绝对路径一致（目录切换立即失效）。
  3. 缓存 `detected_at` 距当前时间未超过 **10 分钟**（超时失效）。
- **写入时机**：检测完成后由脚本写入缓存（项目侧产物 `.cache/` 不存在时自动创建）。
- **边界处理**：
  - 检测结果为 `none`（非 Git 仓库）**不写入缓存**，避免目录初始化后旧缓存误导路由。
  - 用户显式指定 Git 上下文时，跳过检测与缓存读写，直接以用户指定为准。
- **缓存清理**：缓存仅本机本地使用，如需强制重新检测，删除项目侧产物 `.cache/vcs-route.json` 或调用脚本加 `--refresh` 参数。`--quiet` 未指定 `--out` 时产出的结果文件 `.cache/vcs-route.result.json` 同为本地运行期产物，可随时删除。
- **不进行上传**：项目侧 `.codebuddy.project/.gitignore` 已整体忽略 `caches/`，缓存文件不会进入版本控制，不会被提交或推送。

### 3. 判定与路由

| 检测结果 | 路由目标 | 说明 |
|---------|---------|------|
| Git 仓库 | `git-<op>`（如 `vcs-git-commit`） | 常规 Git 仓库（含子目录，`git rev-parse` 在仓库任意子目录返回 true） |
| 非 Git 仓库 | 终止并提示 | 告知用户当前目录不是 Git 仓库，不执行任何操作 |

- 脚本输出的 `target_exists` 为 `true` → 目标技能存在，路由过去。占位技能（`vcs-git-merge`）被路由后，由目标技能返回"未实现占位"提示。
- 脚本输出的 `target_exists` 为 `false` → 目标技能尚未实现，告知用户该操作暂未支持，不执行任何操作。

### 4. 路由确认

- 将识别的操作类型、检测结果（是否 Git 仓库）与目标技能告知用户。
- 若用户请求中已显式指定类型（如"git commit"），以用户指定为准，不再重复检测。
- 路由完成后，将控制权移交给目标技能（如 `vcs-git-commit`），本技能不参与后续执行流程。

## VCS 写操作互斥锁（多会话防冲突）
本技能目录下提供 VCS 写操作通用基础设施——互斥锁工具（`scripts/vcs_lock.py`），供 git-commit
及未来 git-merge / git-revert 等写操作技能复用：

- **用途**：git 的暂存区/HEAD 是仓库级共享状态，多会话并发提交、回滚会互相污染。锁保证同一项目
  同一时刻只有一个会话持有写操作权。
- **机制**：锁文件 `.codebuddy.project/caches/.vcs-lock/codebuddy-vcs.lock`（项目侧通用锁目录，
  运行时生成，不依赖 git 目录，已加入 `.gitignore` 不入库），O_EXCL 原子创建，
  锁内容记录会话标识/操作/开始时间；30 分钟 stale 自动接管，`--force` 可强制覆盖；释放时按 session 校验归属，
  校验支持容错匹配（归一化 + 安全前缀），可容忍终端输出伪影附加的尾部字符。
- **用法**：`python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py acquire|release|status`。
- **集成**：git-commit 在阶段七**逐笔加锁**——**获用户授权后获取锁**，锁内完成本笔
  `git add` → 暂存区校验 → `git commit`，提交完成**立即释放**（锁窗口不跨越用户交互）；
  详见 `.codebuddy/skills/vcs/vcs-git-commit/references/vcs-lock.md`。

## 排除边界
以下请求不路由到执行技能，直接拒绝或说明：

- `git commit --amend`、`git rebase`、`git cherry-pick`、`git revert`、`git stash`、分支操作（暂未纳入路由的独立操作）
- 目标技能不存在时的操作（未创建对应占位技能的操作类型）
- 非版本控制上下文（"提交表单"、"提交报告"等）

## 检查清单
- [ ] 是否已识别操作类型（commit 默认，merge 等从关键词识别）？
- [ ] 是否已校验项目侧产物 `.cache/vcs-route.json` 缓存（目录路径一致且未超过 10 分钟）？
- [ ] 缓存命中时，是否直接使用脚本返回的缓存结果并跳过检测命令？
- [ ] 缓存失效时，是否已通过脚本重新检测并更新缓存？
- [ ] 检测结果为 `none` 时，是否确认未写入缓存？
- [ ] 是否已确认当前目录是否为 Git 仓库与路由目标 `git-<op>`？
- [ ] 目标技能不存在（`target_exists` 为 `false`）时，是否已提示该操作暂未支持？
- [ ] 用户显式指定类型时，是否以用户指定为准（跳过缓存）？
- [ ] 是否已将控制权完整移交给目标技能，未越权执行操作？
- [ ] 缓存文件是否未进入版本控制（项目侧 `.codebuddy.project/.gitignore` 已整体忽略 `caches/`）？
- [ ] 写操作（commit/reset 等）技能是否已集成 VCS 互斥锁（`vcs_lock.py`）？
