# VCS 写操作互斥锁（SVN 场景）

## 锁机制本身：与 Git 完全一致

锁的定位、格式、stale 阈值、命令与容错匹配，全部由
`vcs-router/scripts/vcs_lock.py` 实现，**SVN 与 Git 共用同一个工具、同一把锁**。
完整机制说明见 `vcs-git-commit/references/vcs-lock.md`，本节不重复。

命令（与 Git 侧相同）：

```bash
python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py acquire --op "svn commit"
python .codebuddy/skills/vcs/vcs-router/scripts/vcs_lock.py release --session <LOCK_SESSION>
```

**为什么共用一把锁**：锁保护的是「项目内的工作副本状态」，与工作副本是 Git 还是 SVN 无关。
一个项目同时存在 Git 与 SVN 检出时，两套流程若各用一把锁，双方都无法察觉对方正在写——
这正是锁要防的场景。

## SVN 的持锁窗口

Git 的窗口是「`git add` → 暂存区校验 → `git commit`」。SVN 没有暂存区，
写操作是 `svn add`（新文件入库）与 `svn commit`（提交）。窗口因此是：

```
阶段一~六（变更收集、规划、H1、安全检查）      ← 锁外
  → 展示提交计划 → AskUserQuestion 授权        ← 锁外（授权后才加锁）
acquire（授权之后、svn add 之前）
  → svn add <本笔新文件…>（仅新增项需要）
  → 提交前清单校验（verify_targets.py --mode pre）
  → svn commit --targets <清单> -F <消息> --encoding UTF-8
  → 提交后修订复核（verify_targets.py --mode post）
release（无论成功/失败/中止都必须释放）
  → 下一笔重复 acquire~release；收尾报告
```

### 三条不可违反的约束

1. **锁必须覆盖 `svn add`**。`svn add` 会改变工作副本的版本化状态（把 `?` 变成 `A`），
   若在锁外执行，另一会话的规划阶段会看到错误的变更集（多出本会话刚 add 的项）。
2. **锁窗口不含用户交互**。全部检查、提交计划展示与授权在锁外完成，授权之后才 `acquire`。
   多笔提交**逐笔加锁**，不在锁内连续完成全部笔数。
3. **提交后复核也在锁内**。`svn log -r HEAD` 读的是刚提交的修订，若在锁外执行，
   另一会话此时提交了一笔，读到的就是别人的修订——复核结论会张冠李戴。
   复核完即释放，窗口仍然最短。

## SVN 的清单校验落在哪（与 Git 的关键差异）

Git 的暂存区校验夹在 `add` 与 `commit` 之间：先构造候选集，再比对，再提交。
SVN 没有候选集，`svn commit` 直接作用于目标路径，因此校验拆成**前后两次**，
两次的判据与失败处置完全不同：

| 时机 | 脚本 | 比对对象 | 发现的问题 | 处置 |
|---|---|---|---|---|
| 提交前 | `verify_targets.py --mode pre` | 目标清单 vs `svn status` 变更集 | ① 目标路径没有改动（提交会被拒或产生空提交）；② 有改动但没有任何目标覆盖（会被**静默漏提交**） | **中止**，修正清单后重验；锁可保持（尚未提交） |
| 提交后 | `verify_targets.py --mode post` | 目标清单 vs `svn log -r HEAD -v` 实际路径 | 清单里列了目录，目录内的计划外文件被一并带上 | **不可回退**，如实向用户报告差异，不得自行撤销或改写历史 |

**为什么两次都不能省**：pre 只能证明「清单与本地变更一致」，证明不了「实际提交了什么」；
post 只能事后发现，替代不了 pre 的事前拦截。只做 pre 会在提交后才发现多带了文件；
只做 post 则每次都要先提交再验证，风险已经发生。

## 路径口径（易误报）

全部按**相对 `svn commit` 执行目录**的路径比对，与目标清单的书写方式一致。两个具体坑：

| 坑 | 现象 | 正确做法 |
|---|---|---|
| `svn log -v` 输出仓库绝对路径（如 `/Test/trunk/a.txt`） | 直接与清单比对会把全部路径误报为「多出」 | 用 `svn info --show-item relative-url`（形如 `^/Test/trunk`）去掉前缀。**不要用 `url` 或 `repos-root-url`**：前者是完整 URL，后者是仓库根，都可能与 log 路径前缀不同 |
| `--targets` 按控制台 ANSI 码页解析路径 | UTF-8 清单里的中文路径被解成乱码，报「不在版本控制之下」 | 目标清单文件写成 **GBK/ANSI**；消息文件相反，写 UTF-8 并配 `--encoding UTF-8` |

两类文件编码方向相反，是 SVN 命令行在中文 Windows 下的固有行为，不是脚本缺陷。

## 对话层文本比对不可靠

不要用 Bash 返回的 stdout 在对话层逐行比对路径列表：传输层会在行尾附加伪影字符，
且中文路径在不同代码页下会显示为乱码（同一路径两种写法）。清单一致性校验一律用
`verify_targets.py` 在脚本进程内做集合比对。

## 边界与局限

- **锁只约束走技能流程的操作**：手动在终端执行 `svn commit` 不受锁约束，清单校验是这些场景的最后防线。
- **SVN 自身的文件锁（`svn lock`）与本锁无关**：前者是仓库级的版本化文件锁，用于防多人同时改；
  后者是本机会话间的写操作互斥。两者不能互相替代。
- **中断残留**：会话异常退出会残留锁，由 stale 机制（30 分钟）自动接管兜底。
