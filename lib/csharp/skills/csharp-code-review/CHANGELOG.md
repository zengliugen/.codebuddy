# csharp-code-review 变更记录

> **本文件由引擎仓库维护。** 本包为引擎内自建组件，正文与脚本均归本仓库所有。

## 记录规范

- 一个变更一节，**按时间倒序**，标题为 `## YYYY-MM-DD 主题`。
- 每节写明**为什么改**，而不只是改了什么——只记措辞调整的不写。
- 行为变更（脚本判定、退出码、文件产出）必须记录；纯文档润色不单独成节。

## 2026-11-05 两个收集脚本的输出路径统一为项目根相对

| 项 | 内容 |
|---|---|
| 文件 | `scripts/collect_review_targets.py`、`scripts/collect_review_targets_svn.py` |
| 问题 | 两版脚本匹配时用的是**项目根相对路径**，但**输出**用的却是各自 VCS 的基准路径：Git 版输出仓库相对（`git status` 的原始形式），SVN 版输出 `--dir` 相对（`svn status` 的原始形式）。而项目根常不是仓库根 / 工作副本根——引擎以子目录接入宿主仓库是常见布局，实测本项目根为 `<仓库根>/Program/Client`，输出的清单是 `Program/Client/Assets/...`，审查方以项目根为基准去读 `Assets/...` 就全部落空。口径不一致还让 `targets` 与 `excluded` 里的路径写法不同，同一个文件在两边以不同形式出现 |
| 补丁 | 两版统一输出**项目根相对路径**：Git 版把 `git_root` 换算后输出 `project_rel`，SVN 版把 `workdir` 换算后输出 `project_rel`；`excluded` 同步改为同一口径。SVN 版另加 `--dir` 存在性前置校验（原先把「参数写错」误报成「svn status 执行失败」），并在「状态命中」后补一道**磁盘存在性**校验——删除式树冲突（`item="deleted"` + `tree-conflicted="true"`）与 `missing` 状态的文件在磁盘上已不存在，纳入目标会让审查方读文件失败 |
| 验证 | Git 版：子目录作项目根时输出由 `Program/Client/Assets/T.cs` 变为 `Assets/T.cs`；`--dir <子目录>` 输出 `Sub/S.cs` 可解析；白名单按项目根相对书写仍命中；`excluded` 路径口径与 `targets` 一致。SVN 版：嵌套目录、`--dir` 子目录、删除式树冲突（修复前收 `G.cs`、修复后为空）、`missing` 排除而 `modified` 保留、中文路径、`svn:ignore` 均符合预期。两版共用 `to_project_rel`，改动后互不影响 |

### 为什么输出口径必须与配置口径一致

配置里的 `include_patterns` / `exclude_patterns` 一律按项目根相对路径书写，这是**用户书写
配置时唯一的心智模型**。若输出改回仓库相对或 `--dir` 相对，同一个文件就有三种写法：
用户在配置里写 `Assets/Game/**`，脚本却吐出 `Program/Client/Assets/Game/X.cs`，
使用者必须自己记住「哪一处用哪种基准」——这类不一致不会报错，只会在审查方读不到文件时
表现为「目标清单是空的」或「文件不存在」，排查成本极高。

## 2026-11-05 新增 SVN 版审查目标收集脚本

| 项 | 内容 |
|---|---|
| 文件 | 新增 `scripts/collect_review_targets_svn.py`；同步 `references/guide.md`、`SKILL.md` 辅助脚本清单 |
| 问题 | 原脚本依赖 `git status`，在 SVN 工作副本中不可用。项目侧只能把 `collect_cmd` 留空、改由 LLM 按 `svn status \| grep -E '^[ADMR]'` 手工筛选——门禁无法全自动，且手工筛选在两个地方必然出错：① `?` 状态需另行收集，漏了就永远不审新文件；② `svn status` 对未版本化目录**只报目录本身、不递归**（`--depth infinity` 亦然），新建目录里的 `.cs` 即使收集了 `?` 也拿不到文件 |
| 补丁 | 复用 Git 版的配置定位、glob 匹配、文件头判定等函数（过滤语义单一来源），状态源改为 `svn status --xml`（结构化、带编码声明，中文路径无需猜代码页）；未版本化目录用 `os.walk` 自行展开；不传 `--no-ignore`，使 `svn:ignore` 覆盖项天然不入清单。两条 VCS 路线共用同一份 `code_review.config`，切换 VCS 只需改 `collect_cmd` |
| 验证 | 对真实测试工作副本实测：未版本化目录递归展开、中文路径、`svn:ignore`、删除项剔除、重命名（moved-to 侧为 `deleted` 已剔除、目标侧 `added` 保留）、白/黑名单两模式、`--no-header-check`、`--json` 均符合预期；另测四类失败路径（非工作副本、配置缺失、配置路径不存在、svn 不在 PATH）均以非 0 退出码明确报错 |

### 为什么状态源用 `--xml` 而不是 `-v` 或纯文本

纯文本输出会把路径按控制台代码页渲染，中文目录在 `GBK`/`UTF-8` 之间转换时机不同，
不同终端下拿到的字节不一致；`--xml` 的输出头部声明 `encoding="UTF-8"`，实测中文路径原样可读。

### 为什么必须显式识别「不是工作副本」

该情形下 `svn status` 的**退出码仍是 0**，只在 stderr 打一条 `W155007 ... is not a working copy`，
XML 是空的 `<target>`。只看退出码的门禁会得到「本次无审查目标」并顺利放行——
静默漏审比报错危险得多，故按 stderr 特征转为退出码 2。

## 2026-10-29 项目根锚点去掉 .git（独立仓库形态下根定位错误）

| 项 | 内容 |
|---|---|
| 文件 | `scripts/collect_review_targets.py` 的 `find_project_root()` |
| 问题 | 把 `.git` 与 `.codebuddy` 并列为项目根锚点。引擎以独立 git 检出形态挂载时，向上查找会先命中 `.codebuddy` 自身，项目根误判，配置路径拼成 `.codebuddy/.codebuddy.project/...` |
| 补丁 | 只认 `.codebuddy` 子目录作锚点，删除 `.git` 锚点判断 |
| 验证 | 模拟独立仓库形态下返回真实项目根；submodule 形态下行为不变 |
