# 详细流程与规则

本文件由 `SKILL.md` 拆分而来，承载完整执行细节；主文件只保留触发、契约与流程骨架。

## 工作流程

当 vcs-router 路由到本技能（或用户直接要求提交 SVN 代码）时，按以下七个阶段执行规范化提交。

### 阶段一：收集变更信息

按以下优先级获取变更信息：

1. **从本次对话中提取修改信息**（优先）：
   - 回顾本次对话中所有文件编辑、新增、删除操作。
   - 提取每个修改的意图、涉及的模块和功能点。
   - 将对话中的修改按功能逻辑分组。

2. **回退至工作副本分析**（若对话中无修改信息）：

```bash
# 结构化收集：可提交 / 未版本化 / 已忽略 / 阻断 四类，并读取 svn:ignore
python .codebuddy/skills/vcs/vcs-svn-commit/scripts/collect_svn_changes.py --dir <工作副本目录>

# 需要同时看服务端是否有新版本时
python .codebuddy/skills/vcs/vcs-svn-commit/scripts/collect_svn_changes.py --show-updates
```

脚本退出码 1 表示存在**阻断项**（冲突 / 缺失 / 树冲突），必须先处理；
退出码 2 表示目标目录不是工作副本或 svn 不可用。

3. **处理未版本化项**（`?`）：它们**不会进入提交也不会报错**，是 SVN 最容易静默漏提交的地方。
   逐个确认后通过 `AskUserQuestion` 询问用户是否纳入本次提交：
   - 列出未版本化文件及其简要内容。
   - 确认用户是否要包含这些文件（需要 `svn add` 才会进提交）。
   - 若拒绝，仅处理已版本化改动；若接受，在阶段七统一 `svn add`。

4. **合并对话上下文与工作副本变更**（部分重叠时）：
   - 对话中涉及的文件：使用对话上下文中的意图信息生成摘要。
   - 对话外变更的文件：通过 `svn diff` 分析推断意图。
   - 合并后统一定义模块和规划提交粒度。

### 阶段二：确定修改模块

根据变更路径，按项目侧 `project-config.md`（索引 `svn_commit.project_config`）§1 定义的
优先级规则提取 scope。scope 的具体取值以项目侧配置为准；新增模块、无匹配路径等边界情况的
处理同样参见该节。

### 阶段三：规划提交粒度

- 单功能变更 → 一次提交。
- 多功能变更 → 按功能拆分为多次提交：
  - 新功能与 Bug 修复分开。
  - 重构与功能变更分开。
  - 文档变更与代码变更分开。
  - 不同模块变更尽量分开。

**SVN 特有限制：同一文件不能跨笔拆分**。提交粒度是路径，同一文件里有多个主题时只能合并为一笔，
正文分点说明。拆分规则与编排顺序详见 `references/commit-spec.md`。

### 阶段四：生成提交摘要

按**项目侧配置的 `commit_subject.pattern`** 生成摘要（格式不写死在引擎里）。**判定口径、授权方式遵循
`.codebuddy/rules/vcs/vcs-commit/commit-spec.mdc` 与 `submission-safety-spec.mdc` 公共子规则**（Git 与 SVN 共用同一份），
近似 type 的区分思路见 `references/commit-spec.md`。

**摘要格式与 type 枚举一律读取项目侧配置**（`.codebuddy.project/configs/skills/vcs/vcs-svn-commit/config.json`，
索引逻辑名 `svn_commit.config`），本文件与 SKILL.md **都不预置任何 type 清单或格式**：

| 从配置读什么 | 用来做什么 |
|---|---|
| `commit_subject.pattern` | 判定摘要是否合规的唯一依据（正则 + 命名组） |
| `commit_subject.format` | 展示给用户看的格式描述（与 pattern 不一致时以 pattern 为准） |
| `commit_subject.types` | type 枚举**及其含义**；**数组顺序即决策优先级** |
| `commit_subject.subject_max_len` / `scope_max_len` | 长度上限 |
| `commit_subject.subject_language` / `forbid_trailing` | 语言与禁用结尾字符 |

> **SVN 侧的格式与 Git 侧可能不同**：两份配置互不继承，**不能照搬 Git 侧的写法**。
> 生成前先读 `svn_commit.config` 的 `pattern`；选 type 时按 `types` 数组顺序
> 逐个比对 `description`，第一个命中即选它。

**生成后自动化校验**：每条提交摘要生成后，运行格式校验脚本确认合规。脚本的**格式判定完全由配置的
`pattern` 驱动**（不认引擎里任何写死的形态），配置缺失或字段非法时报错退出码 3。脚本位于 `vcs-router`
技能（Git 与 SVN 共用一份），**必须显式传 `--config-key svn_commit.config`**——该参数不设默认值，
漏传即参数错误，不存在「静默读了 Git 配置」的可能：

```bash
python .codebuddy/skills/vcs/vcs-router/scripts/validate_commit_subject.py --config-key svn_commit.config "<按本项目 pattern 生成的摘要>"
```

校验失败（退出码 1）时按提示修正后重新校验；退出码 3 表示配置缺失或字段非法，须先补齐配置。
全部摘要校验通过后进入阶段五。

### 阶段五：执行项目专有钩子（H1 提交前）

H1 钩子步骤由**项目侧配置**声明（经索引 `svn_commit.project_config` 定位到
`.codebuddy.project/configs/skills/vcs/vcs-svn-commit/project-config.md`）。读取其 §4「H1 钩子步骤」
表格，**按表内顺序**执行 `enabled=true` 的步骤；`blocking=false` 失败仅告警，
`blocking=true` 失败即中止并询问用户。

**引擎不预设任何步骤** —— 步骤清单、顺序、启用状态与 `blocking` 取值全部由项目侧配置声明。
引擎只定义执行规则（见引擎侧 `references/project-config.md` §3）。

> **钩子点的位置**：SVN 没有暂存阶段，H1 落在「目标清单成型之后、清单校验之前」。
> 若某步骤会改写工作区文件，它必须在此处完成，后续的清单校验才会基于改写后的实际内容——
> 放到校验之后会让校验结论失效。

### 阶段六：安全检查

执行**忽略属性交叉比对**与**敏感信息扫描**（详见 `references/submission-safety.md` 与公共子规则
`submission-safety-spec.mdc`）：

```bash
# 1. 读取当前的忽略属性（版本化属性，不是工作区文件）
svn propget -R svn:ignore .

# 2. 列出被忽略项，确认目标清单里没有被误 add 的忽略项
svn status --no-ignore

# 3. 按目标清单扫描敏感信息（SVN 无暂存区，不能只看「准备提交的那部分」）
svn diff --targets <目标清单.txt>
```

若发现误将忽略项纳入版本控制：

- 尚未提交（`A` 状态）：`svn revert -R <路径>` 撤销 add。
- 已提交：单独一笔 `svn delete`（保留本地文件用 `--keep-local`），不改写历史。

同时扫描目标清单内变更的敏感信息（密码、密钥、Token、API Key 等），检测到则**阻止提交**并警告用户。
SVN 直连远端，敏感信息一旦提交即进入远端历史，事后清理代价极高，故按最严执行。

**计划外改动核对（全工作副本）**：仅按某个目录过滤核对容易漏看被工具自动改写的文件。
提交前必须执行**全工作副本** `svn status`，对本轮提交计划之外的文件：**显式排除**，
并在提交计划中**告知用户**这些计划外改动，由用户决定（保持 / 还原 / 单独提交），
禁止默认静默带入。

边界情况（无改动、冲突、锁定、混合修订、外链、hook 拒绝等）的处理参见
`rules/vcs/vcs-svn-commit/svn-commit-spec.mdc`「SVN 边界情况」。

### 阶段七：执行提交（含多会话互斥锁）

> **防冲突机制**：工作副本的版本化状态（哪些项已 `add`、哪些已删除）是目录级共享状态，
> 多会话并发 SVN 写操作会互相污染。本阶段用 VCS 互斥锁串行化写操作，并在提交前后校验清单。
> **锁机制与容错细节见 `references/vcs-lock.md`**。
>
> 三条不可违反的约束：
>
> 1. **逐笔加锁**：`acquire` 与 `release` 之间只完成**一笔**提交
>    （`svn add` → 提交前校验 → `svn commit` → 提交后复核），完成后立即释放。
> 2. **锁必须覆盖 `svn add` 与提交后复核**：`add` 会改变变更集，
>    复核读的是「刚提交的修订」，两者都必须在锁内。
> 3. **锁窗口不含用户交互**：全部检查与授权在锁外完成，授权之后才 `acquire`。

**逐笔执行以下步骤（每笔重复 1~8）：**

1. 展示提交计划（**全部笔数**的摘要与目标路径清单，以及审查报告路径/问题摘要）——
   多笔提交须在**一次**授权询问中给出完整计划（详见 `submission-safety-spec.mdc`）。
2. 通过 `AskUserQuestion` 发起确认询问，**一次性获得全部笔数的明确授权**。
3. **获取 VCS 锁**（**授权之后、`svn add` 之前**）：

   ```bash
   python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py acquire --op "svn commit"
   ```

   记录输出中的 `LOCK_SESSION=<id>`，本笔完成后用于释放。

4. **暂存本笔的新增项**：仅对本笔计划内的**未版本化**文件执行 `svn add`，显式列出路径：

   ```bash
   svn add -- <本笔新增路径…>
   ```

   - 新增目录默认 `--depth infinity`，会连子项一起加；**先确认目录内没有忽略项与临时文件**。
   - 父目录未版本化时 `svn add` 会失败，用 `svn add --parents` 补齐。
   - **禁止** `svn add --force`（会连忽略项一起加）。
   - 已版本化的改动**无需任何「暂存」动作**，`svn commit` 直接提交目标路径上的全部改动。

5. **写出本笔目标清单**，并用脚本做**提交前校验**：

   ```bash
   # 清单文件写成 GBK/ANSI（Windows 中文环境），否则中文路径会被 svn 解成乱码
   python .codebuddy/skills/vcs/vcs-svn-commit/scripts/verify_targets.py \
     --mode pre --targets <本笔目标清单.txt> --dir <提交执行目录>
   ```

   退出码 1 时必须中止并释放锁，修正清单后重新规划。校验内容详见 `references/vcs-lock.md`。

6. **执行 `svn commit`**（已获授权，直接提交本笔）：

   ```bash
   svn commit --targets <本笔目标清单.txt> -F <提交消息.txt> --encoding UTF-8
   ```

   - **消息文件必须是 UTF-8 且配 `--encoding UTF-8`**：不传该参数时中文消息会按
     控制台码页解释并落盘为乱码（实测过，不可改）。
   - **消息文件与清单文件都不得放在工作副本内**（会污染变更集）。放系统临时目录，用完删除。
   - 目标路径**必须经清单文件传入**，禁止省略路径（那等于提交整个工作副本）。

7. **提交后复核实际修订**：

   ```bash
   python .codebuddy/skills/vcs/vcs-svn-commit/scripts/verify_targets.py \
     --mode post --targets <本笔目标清单.txt> --dir <提交执行目录>
   ```

   退出码 1 表示实际修订路径与清单不一致（典型成因：清单里列了目录，目录内的计划外文件
   被一并带上）。**修订已提交不可回退**，须如实报告差异，禁止自行尝试撤销或改写历史。
   同时用 `svn log -r HEAD -v` 人工核对摘要与路径列表。

8. **立即释放 VCS 锁**（无论成功、失败或中止都必须释放，释放后才能开始下一笔）：

   ```bash
   python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py release --session <LOCK_SESSION>
   ```

   **禁止**在未释放锁的情况下开始下一笔（会让锁窗口跨越用户交互）。

**每笔提交完成后的收尾：**

9. 报告该笔**修订号**、摘要与实际提交的路径数量。
10. **提交与远端同步分离**：提交完成后不自动执行 `svn update` / `svn switch`，
    需等待用户单独指令（详见 `references/submission-safety.md`）。

---

## 检查清单

提交前逐项检查：

- [ ] 本次提交是否由 vcs-router 路由（或用户直接指定 SVN 上下文）？
- [ ] 提交发起权是否合规（`commit_initiation`：`user_only` 时需用户主动发起）？
- [ ] 是否已读取 `svn_commit.config` 的 `pattern` 与 `types`，并按**配置的格式**生成摘要（未照搬 Git 写法）？
- [ ] 是否已用 `collect_svn_changes.py` 收集变更，并确认退出码不是 1（无阻断项）？
- [ ] 未版本化项（`?`）是否已逐个确认——纳入本笔（`svn add`）或明确判为不入库？
- [ ] H1 步骤是否已按**项目侧配置**的表内顺序执行（`enabled` / `blocking` 语义见引擎侧 `references/project-config.md` §3）？
- [ ] H1「提交前审查」步骤：是否已取到审查清单（**且含未版本化新文件**）？
- [ ] 用户指示跳过审查时，是否已通过 `AskUserQuestion` 确认跳过理由？
- [ ] 审查是否存在配置的 `blocking_level` 级别问题？若是，是否已修复或获得用户明确授权忽略？
- [ ] 审查报告路径是否已记录进提交计划？
- [ ] 提交摘要是否已用 `--config-key svn_commit.config` 校验通过？
- [ ] 是否已读取 `svn:ignore` 并与目标清单交叉比对（无已忽略项被纳入）？
- [ ] 是否已按**目标清单**扫描敏感信息（不只扫已暂存或部分文件）？
- [ ] 提交/同步前是否通过 `AskUserQuestion` 获得明确授权？
- [ ] 是否在**获得授权之后**才获取 VCS 锁？每笔完成后是否**立即释放**（含中止/失败路径）？
- [ ] 锁是否**覆盖 `svn add` 与提交后复核**？
- [ ] 目标清单是否只含本笔路径，且每个路径都确有改动（`verify_targets.py --mode pre` 通过）？
- [ ] **目标清单是否写成 GBK/ANSI、提交消息是否写成 UTF-8 并配 `--encoding UTF-8`**？
- [ ] 两个临时文件是否都在工作副本之外？
- [ ] 是否已用 `verify_targets.py --mode post` 与 `svn log -r HEAD -v` 复核实际修订？
- [ ] 是否已用全工作副本 `svn status` 核对**计划外改动**，并在计划中告知用户由其决定？
- [ ] 提交完成后是否**未**自动执行 `svn update` / `svn switch`？
- [ ] 边界情况（冲突、锁定、混合修订、外链、hook 拒绝）是否已检查？
