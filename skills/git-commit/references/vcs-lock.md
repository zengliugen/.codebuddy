# VCS 写操作互斥锁（多会话防冲突）

## 为什么需要锁

git 的暂存区（index）与 HEAD 是**仓库级共享状态**。多个 CodeBuddy 会话并发执行 git 写操作
（提交、回滚、合并、stash 等）时会出现两类典型冲突：

1. **暂存区污染**：会话 A 执行 `git add` 暂存自己的文件后，会话 B 也执行 `git add` 暂存了自己的文件，
   会话 A 随后 `git commit` 会把 B 的文件一并提交。
2. **提交被回滚**：会话 B 执行 `git reset` 时，会把会话 A 刚创建的提交一起回滚。

锁的目标是保证：**同一仓库同一时刻只有一个会话持有 git 写操作权**。

## 锁机制

### 锁文件

- 位置：`.codebuddy.project/.vcs-lock/codebuddy-vcs.lock`（项目 `.codebuddy` 下的通用锁目录，运行时生成，不入库）。
- 通过从当前工作目录向上查找 `.codebuddy` 目录定位（回退到脚本自身位置推导），不依赖 git 目录。
- 采用 **O_CREAT|O_EXCL 原子创建**获取锁，杜绝两个进程同时拿锁的竞态。

### 锁内容（JSON）

```json
{
  "session_id": "18840-1787076950712-yoxcza",
  "operation": "git commit",
  "started_at": 1787076950.123,
  "started_at_readable": "2026-08-19T02:15:50",
  "pid": 18840,
  "host": "DESKTOP-XXX"
}
```

`socket` 会话标识（PID-毫秒时间戳-随机串）用于：
- 向冲突方展示"谁在操作、在做什么、何时开始"；
- 释放时校验会话归属，防止误删已被其他会话接管的锁。

> **释放容错**：终端捕获 `acquire` 输出时，`LOCK_SESSION=<id>` 行尾**偶发附加伪影字符**
> （Windows 下多为 `X`，是 CRLF 换行的控制字符被渲染所致）。因此 `release` 的 session 校验
> 支持**容错匹配**：先归一化（去除尾部非字母数字字符），再做安全前缀匹配（前缀 ≥ 12 字符），
> 带伪影的 session 也能正确放行；完全不匹配时才拒绝，并输出锁中真实 session 供人工核对。

### stale（过期）判定

锁从 `started_at` 起超过 **30 分钟**（`--timeout` 可调）视为残留锁：
- 残留锁通常来自会话中断未释放，获取时可**自动接管**；
- 用户也可主动 `--force` 无条件接管（会打断对方操作，慎用）。

## 命令

统一入口：`python .codebuddy/skills/vcs-router/scripts/vcs_lock.py <子命令>`

| 子命令 | 说明 |
|--------|------|
| `acquire --op "<操作描述>" [--wait 秒] [--timeout 秒] [--force]` | 获取锁。被占用时输出占用摘要并自动轮询等待（默认 120 秒）；仍失败退出码 1。成功时输出 `LOCK_SESSION=<id>` |
| `release --session <session_id>` | 释放锁。session 校验支持**容错匹配**（归一化去尾部伪影 + 安全前缀匹配），可容忍终端输出伪影（如行尾附加 `X`）导致的 session 偏差；仍不匹配时输出锁中真实 session 供核对 |
| `status [--timeout 秒]` | 查看锁状态与占用详情 |

退出码：`0` 成功；`1` 失败（等待超时/会话不匹配/未找到 `.codebuddy` 目录）。

## 集成到 git-commit 技能

### 持锁窗口（逐笔加锁，最短窗口）

**锁只覆盖一笔提交的三个 git 写操作**：`git add` → 暂存区校验 → `git commit`。

```
阶段一~六（全部检查，含审查门禁与 H1 钩子）   ← 锁外
  → 展示提交计划 → AskUserQuestion 授权       ← 锁外（授权后才加锁）
acquire（授权之后、暂存之前）
  → git add -- <本笔路径>
  → 暂存区校验（git diff --cached --name-only 与提交计划比对）
  → git commit
release（无论成功/失败/中止都必须释放）
  → 下一笔重复上述 acquire~release；收尾报告 → 推送分离
```

### 两条设计约束（不可违反）

1. **锁必须覆盖 `git add`**。锁要防的首要场景就是暂存区污染：若他会话在本次持锁前已
   `git add` 过文件，本次 `git commit` 会把它的文件一并带走。因此**暂存与提交不可拆到锁外**
   ——只锁 `git commit` 无法防住这一类冲突。
2. **锁窗口必须排除用户交互**。检查、提交计划展示与 `AskUserQuestion` 授权全部在锁外完成，
   避免用户思考/确认的等待时间占用互斥锁（原设计在授权前加锁，会导致锁窗口跨越用户交互）。
   同理，多笔提交**逐笔加锁**，不在锁内连续完成全部笔数。

> **授权与写操作的顺序**：本流程遵循 `common-submission-safety-spec.mdc`「获得授权后再执行
> 任何写操作（暂存/提交）」——授权是 `acquire` 的前置条件，即授权在前、暂存在后。

配套的第二道防线——**提交前暂存区校验**：
即使有锁，若另一会话在本次持锁前已 `git add` 过文件，本次 `git commit` 仍可能把它的文件一并提交。
因此 `git commit` 前必须执行 `git diff --cached --name-only`，确认暂存区文件列表与提交计划
**完全一致**（无多出、无缺失）；不一致立即中止并释放锁，向用户说明差异。

### 校验脚本的路径前缀（易误报）

`verify_staged.py --expect-file` 期望**仓库相对路径**（如 `Packages/...`），而
`git diff --cached --name-only` 在子目录中执行时输出带当前目录前缀（本仓库为 `<仓库前缀>/`，按 `git rev-parse --show-prefix` 实测值替换）。
直接把输出喂给脚本会**误报「多出（暂存区有、计划没有）」并逐条列出全部文件**（实为同一批文件）。

生成计划清单前先归一化：

```bash
# 先确认当前目录相对仓库根的前缀（本仓库为 <仓库前缀>/，按实测值替换）
git rev-parse --show-prefix

# 生成计划清单时去掉该前缀
git diff --cached --name-only | sed 's|^<仓库前缀>/||' > <本笔计划清单.txt>
python .codebuddy/skills/git-commit/scripts/verify_staged.py --expect-file <本笔计划清单.txt>
```

### 文件计数对不上时的排查

用 `git status --porcelain | wc -l` 统计的**行数**与暂存后 `git diff --cached --name-only | wc -l`
统计的**文件数**可能不一致，属正常现象，**不是文件遗漏**：

- `git status --porcelain` 对**未跟踪的新目录只输出一行**（折叠整个目录，不展开其中的文件）；
- 目录被暂存后，`git diff --cached --name-only` 会逐文件列出，数字因此变大。

**实测**：某次提交前统计 72 行，暂存后为 71 个文件——差异来自新目录（含 2 个文件）在 porcelain
输出中只占 1 行。

**排查方式**：计数不符时，用 `git diff --cached --name-status | grep '^A'` 列出新增文件，
确认每个新目录内的文件都已暂存即可，不要据此判定「计划外多出文件」。

**另一类：重命名被拆成 `D` + `??`（索引状态问题）**

与上述 porcelain 输出行为不同，**目录整体重命名后**若索引状态被外部操作重置
（例如会话期间的历史修正、`git reset` 等），`git status` 会显示为**大量 `D`（旧路径）+ `??`（新目录）**，
而不是 `R`（重命名）。此时并非文件被删除，也无需逐个 `git add`：

```bash
git add -A                       # 让 git 重建重命名识别
git diff --cached --name-status -M   # 复核：应恢复为 R（R0xx 表示重命名 + 内容修改）
```

**要点**：`git add -A` 会保留重命名伴随的内容修改（显示为 `R0xx` 而非 `R100`），
不会把「重命名 + 修改」误拆成删除与新增；提交统计也会恢复为 `R`。
仅加 `--untracked-files=all` 无法解决此类问题——那是让未跟踪文件**展开显示**，
而此处需要的是**重建索引中的重命名映射**。

**实测**：某次目录层级重构后 `git status` 为 `1062 D + 29 ?? + 6 M`；执行 `git add -A` 后
变为 `1062 R + 6 M`，其中 84 个为 `R0xx`（重命名 + 内容修改），内容修正完整保留。

## 与既有基础设施的关系

- 锁工具放在 `vcs-router` 技能目录下，作为 VCS 写操作的通用基础设施，供 git-commit 及未来
  git-merge / git-revert 等写操作技能复用。
- `vcs-router` 的路由缓存（`.cache/vcs-route.json`）只做 VCS 类型检测结果缓存，与写操作锁无关。
- 锁文件位于 `.codebuddy.project/.vcs-lock/`（运行时生成），已被 `.codebuddy/.gitignore` 与项目根 `.gitignore` 忽略，不入库。

## 边界与局限

- **锁只约束走技能流程的操作**：手动在终端执行 `git add`/`git reset` 不受锁约束，暂存区校验
  是这些场景的最后防线。
- **同一会话的后台命令同样会争用 `.git/index.lock`**：这不是多会话问题，而是**自身**并发。
  用 `run_in_background` 发起的大范围 git 命令（如全仓 `git status`、`git ls-files
  --cached --ignored --exclude-standard` 遍历）会在执行期间持有 `.git/index.lock`，
  此时前台 `git add` / `git commit` 会失败并提示
  `Unable to create '.../.git/index.lock': File exists`。
  处置：确认无其它 git 进程后**等待后台任务结束**（lock 会自行消失）再重试；
  **不要**贸然删除 lock 文件——若确有进程在写，删除会破坏其状态。
  提交阶段的全仓核对尽量放在获取锁之前的阶段六完成，避免与暂存/提交窗口重叠。
- **多 worktree / 多仓库共享配置**：锁定位的是项目 `.codebuddy` 目录，属**项目级互斥**。
  多 worktree 共享同一项目时天然共用一把锁（比仓库级锁更严格，串行化更彻底）；
  若多个项目通过目录链接共享同一份 `.codebuddy` 配置，锁也会被这些项目共享。
- **中断残留**：会话异常退出会残留锁，由 stale 机制（30 分钟）自动接管兜底。
