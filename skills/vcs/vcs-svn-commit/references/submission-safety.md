# 提交安全规范（SVN）

> **规范主源**：用户主动发起、授权要求、提交与更新的分离、敏感信息检查等强制条款以
> `.codebuddy/rules/vcs/vcs-commit/submission-safety-spec.mdc`（授权与安全规范子规则）为准。
> 本文件提供**SVN 场景的落地细节**：命令、检查流程、以及 SVN 没有暂存区带来的差异。

## 用户主动发起原则（按项目配置取值）

发起权由项目侧配置决定（机制见 `references/project-config.md` §1.5），参数为
`commit_initiation` 与 `push_initiation`（各取 `user_only` / `llm_allowed`）：

- **`user_only`**：该操作**必须**由用户主动发起，禁止因「便利」「自动保存」等理由自动执行；
  禁止根据对话上下文推断用户意图后自行决定。
- **`llm_allowed`**：允许自行发起（可在合适时机自主执行），不强制 `AskUserQuestion` 授权。
- SVN 侧的 `push_initiation` 语义对应「提交后是否可自行执行 `svn update` 等远端同步」：
  SVN 的 `svn commit` 直连远端，**提交本身即已写入远端**，不存在「本地已提交待推送」的中间态。
  因此该参数在 SVN 侧的取值按 `user_only` 从严处理：**提交后不自动执行任何远端同步动作**。

## 用户授权要求

- **`user_only` 模式**：提交前必须向用户展示即将提交的内容摘要（目标路径清单、提交消息），
  并通过 `AskUserQuestion` 工具获得明确授权后方可执行。
- **`llm_allowed` 模式**：本授权环节放开；但审查跳过、修复/忽略选择等交互仍照常。
- 授权必须**显式、主动**，禁止依赖隐含授权。
- **禁止**以纯文本提问方式替代 `AskUserQuestion`；工具超时**不构成豁免**，也**不等于授权**。
- **多笔提交需一次性给出完整计划**：一次操作涉及多笔时，必须在**一次**授权询问中给出全部笔数、
  每笔的摘要与目标路径清单，获得授权后再执行任何写操作。
- **授权先于写操作与加锁**：`svn add` / `svn commit` 与获取 VCS 锁都以授权为前置条件。

## SVN 的「提交与推送分离」是什么

Git 侧该约束是「commit 与 push 分两步」。SVN 没有 push，直接照搬会得到一条无法执行的条款。
实际等价物是下面三条（都必须在提交前后各守住）：

| 禁止动作 | 为什么 |
|---|---|
| 提交前隐式执行 `svn update` | update 会改写工作区（合并远端改动、可能产生冲突），属独立动作，须等待用户指令 |
| 提交前隐式执行 `svn revert` | 会丢弃用户改动，且 revert 不可恢复（除非有备份） |
| 提交后自动执行 `svn update` / `svn switch` | 提交已完成，后续动作与新提交无关，且会改变工作副本基线，干扰用户对「刚提交了什么」的核对 |

**禁止链式组合**：不得用 `&&` 把 `svn add`、`svn commit`、`svn update` 串成一条命令。

## 敏感信息检查

SVN 没有暂存区，因此不能像 Git 那样 `git diff --cached` 只看「准备提交的那部分」。
按**目标清单**逐项取 diff，才是与实际提交范围一致的口径：

```bash
# 逐个目标路径取其本地改动（新增文件直接读内容）
svn diff --targets <目标清单.txt>

# 新增文件 svn diff 为空（基线不存在），须直接读内容
while IFS= read -r p; do [ -f "$p" ] && grep -inE \
  '(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|credential|connection[_-]?string)' \
  "$p"; done < <(grep -vE '^\s*(#|$)' <目标清单.txt>)
```

若检测到匹配项：

1. 列出匹配的行及所在文件。
2. 警告用户提交内容可能包含敏感信息。
3. **阻止提交**，等待用户确认或移除敏感内容。

> **SVN 的额外风险**：`svn commit` 直连远端，敏感信息一旦提交就**已进入远端仓库历史**。
> 事后清理需要 `svnadmin dump/load` 重建仓库或修改修订属性，代价远高于 Git 的本地 amend。
> 因此本条在 SVN 侧按**最严**执行：命中即阻断，不接受「先提交再清理」。

## 忽略属性交叉比对

SVN 的忽略规则是**版本化属性** `svn:ignore`，不是工作区文件，必须用命令读取：

```bash
# 1. 递归列出当前工作副本的忽略规则（格式：<路径> - <规则>）
svn propget -R svn:ignore .

# 2. 列出被忽略项（确认目标清单里没有被误 add 的忽略项）
svn status --no-ignore

# 3. 核对目标清单中的每个路径是否已处于版本控制之下
svn status --targets <目标清单.txt>
```

若发现误将忽略项纳入版本控制：

| 状态 | 处理 |
|---|---|
| 尚未提交（第一列 `A`） | `svn revert -R <路径>` 撤销 add（仅撤回本地调度，不动仓库） |
| 已提交 | `svn delete <路径>` 单独一笔删除（保留本地文件用 `--keep-local`），不要改写历史 |

## 禁止行为汇总

1. **`commit_initiation=user_only`** 时禁止自动执行 `svn commit`。
2. 禁止提交后自动执行 `svn update` / `svn switch`（见上「提交与推送分离」）。
3. 禁止在用户未授权时执行任何会改写工作区的动作（`revert`、`update`、`cleanup --remove-unversioned`）。
4. 禁止把消息文件或目标清单文件放在工作副本内。
5. 禁止使用 `svn commit --force-log` 绕过日志校验。
6. 禁止提交 `svn:ignore` 已忽略的项（不得用 `svn add --force`）。
