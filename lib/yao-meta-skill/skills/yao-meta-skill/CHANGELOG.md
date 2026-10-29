# yao-meta-skill 变更记录

> **本文件由引擎仓库维护，不是上游内容。** 本包为只读 vendor，**不翻译正文**
> （触发评估与回归测试依赖原文措辞）。

本包来自上游 yao-meta-skill 2.1.0，随引擎分发。**只允许最小可行性补丁**——这是本包与引擎内其它
**本地维护分支**包的根本差别。

## 与「本地维护分支」的区别

| 项 | 本包（只读 vendor） | 本地维护分支（引擎内另有若干） |
|---|---|---|
| 正文语言 | **保留上游原文**，不受语言规则约束 | 已中文化，受语言规则约束 |
| 可否改造 | 仅最小可行性补丁 | 允许本地改造 |
| 与上游关系 | 升级需逐项判断「上游修了没有」 | 正文以本仓库为准，无需逐字比对 |
| 为什么这样定 | 触发评估与回归测试依赖原文措辞（语义权重、测试快照），翻译会使工具链失效并导致上游拉取永久冲突 | 不产出需与上游逐字比对的评测快照，语义忠实度由本地评测保障 |

## 判断上游升级时该做什么

| 若上游…… | 则…… |
|---|---|
| 已修掉下述任一问题 | 采用上游实现，删除对应补丁，并从本文件删掉那一节 |
| 尚未修 | 保留补丁，按该节的「升级注意」重放 |
| 改动涉及新增文件（如 `rules/`） | 先比对职责再决定保留哪一份，避免同名规则重复注入 |

## 改动清单（按时间倒序）

| 日期 | 主题 | 涉及范围 | 详情 |
|---|---|---|---|
| 2026-10-29 | 文档归位：PATCHES.md 与 references/cli-changelog.md 合并到根目录 | 本文件 | 见下节 |
| 2026-10-29 | 规则正文补变更记录文档规范与提问超时分流 | `rules/yao-meta-skill/RULE.mdc` | 见下节 |
| 2026-10-29 | 治理脚本边界词补中文等价 | `scripts/governance_check.py` | 见下节 |
| 2026-10-28 | 报告路径去本机化 | 33 个脚本 | 见下节 |
| 2026-10-27 | 校验语义反转：禁止 path_scoped 激活 | `scripts/validate_skill.py` | 见下节 |
| 2026-10-22 | Windows 兼容：证据发布锁 | `scripts/evidence_store.py` | 见下节 |
| 2026-10-22 | 引擎侧新增 `rules/`（不改正文） | 新增 `rules/yao-meta-skill/` | 见下节 |

## 记录规范

- 一个变更一节，**按时间倒序**，标题为 `## YYYY-MM-DD 主题`。
- 每节写明文件、问题、补丁、边界、验证、升级注意六项——上游升级重放时缺任一项都会漏改。
- 纯错别字修订不单独成节。

## 一条必须知道的约束

**本包的 `requires` 为空**，因此正文不得出现任何其它包的组件名——包括引擎内自建的包。
写文档或说明时点名他包技能名会触发引擎的跨包引用校验（退出码 1）。需要举例时用泛化表述。

这条踩过一次：本文件的上一版在 changelog 里直接写了某个自建包的技能名，被校验拦下。

## 维护要求

1. **改本包任何文件后，必须在本文件追加一节**，写明文件、问题、补丁、边界、验证、升级注意。
2. 上方「改动清单」表同步补一行。
3. 改完跑 `python .codebuddy/scripts/check_manifest.py`，退出码必须为 0。
4. 纯文档修订（如修错别字）不需单独成节，但需在「改动清单」对应行体现。

## 为什么把改动记录放在根目录

本文件是**本仓库新增的文件**（上游无此文件），因此不构成「改上游正文」。把它放在技能根目录，
与其它技能保持同一位置约定；上游升级时能干净覆盖正文，所有本地差异集中在一份可查文件里。

## 2026-10-29 文档归位：PATCHES.md 与 references/cli-changelog.md 合并到根目录

| 项 | 内容 |
|---|---|
| 文件 | 新增根目录 `CHANGELOG.md`；删除 `PATCHES.md` 与 `references/cli-changelog.md` |
| 原因 | 同一类信息散在两处、文件名不一致（`PATCHES.md` / `cli-changelog.md` / `CHANGELOG.md` 三种并存），且各包放置位置各异，检索与维护都要先猜位置 |
| 补丁 | 维护档位、升级判据、改动清单、变更记录合并为单一 `CHANGELOG.md`，置于技能根目录 |
| 边界 | 只搬内容不改语义；引擎 `README.md` 的 vendor 表引用同步更新；`PATCHES.md` 原「维护要求」与「为什么」两节并入本文件 |

## 2026-10-29 规则正文补变更记录文档规范与提问超时分流

| 项 | 内容 |
|---|---|
| 文件 | `lib/yao-meta-skill/rules/yao-meta-skill/RULE.mdc`（本包规则，新增约定）；引擎侧工具纪律规则与其提问细则（同类改动，随引擎入库） |
| 问题 | 一、各类技能把变更记录分散放在 `PATCHES.md` / `references/cli-changelog.md` / `references/CHANGELOG.md` 三种位置与命名，检索与维护都要先猜位置；二、提问超时后的处置未区分目标模式，导致无目标时也可能替用户选默认项 |
| 补丁 | 规则正文新增「变更记录文档（CHANGELOG.md）」小节：位置、命名、内容结构、变更小节写法、与 manifest/reports 三方分工、迁移步骤、写记录时的三个坑。工具纪律新增第 13 条：超时后按 `GetGoal()` 分两支——有活动目标则按推荐项推进，无目标则停住等回复 |
| 边界 | 规则侧改动，**未修改任何上游技能正文**；CHANGELOG 规范属引擎侧新增约定，上游若自行提供记录文件命名规范，需先比对职责 |
| 验证 | `check_manifest.py` 与 `pack_install.py status` 均退出码 0；全库 25 个技能 `validate` 全部通过 |
| 升级注意 | 上游若已规定变更记录的位置与命名，先比对再决定保留哪一份，避免重复约定 |

## 2026-10-29 治理脚本边界词补中文等价

| 项 | 内容 |
|---|---|
| 文件 | `scripts/governance_check.py` 的 `compute_score()` |
| 问题 | `boundary_and_eval` 维度只认英文标记（`do not` / `out of scope` / `should not trigger` / `do not use`）。本项目要求正文简体中文，导致所有中文技能都拿不到这 10 分，被系统性低估 10 分，并触发「声明 production 但得分不足 80」的误报 |
| 补丁 | 标记集合补入中文等价表述：`不适用` / `不在此范围` / `不应触发` / `不要用` / `禁止` / `排除` / `不支持` / `不处理` / `不负责` / `不在本技能` |
| 边界 | 只加词表，判定逻辑与分值权重未动；英文标记保留，多语言包不受影响 |
| 验证 | 全库 25 个技能复扫，得分整体上移 10 分；原先因缺英文标记而误报「声明 production 但得分不足 80」的三个自建技能，告警全部消除 |
| 升级注意 | 上游若已支持多语言边界词，直接采用上游实现并删除本补丁 |

## 2026-10-28 报告路径去本机化：display_path 兜底改为项目根相对

| 项 | 内容 |
|----|------|
| 文件 | **33 个脚本**，分三类（见下）；另加本记录文件（`references/cli-changelog.md`） |
| 问题 | `display_path()` 的兜底是 `return str(path.resolve())`：当目标不在基准 `ROOT`（即本技能目录）之下时，直接吐出本机绝对路径。用 yao 处理**本技能之外**的任何技能时必然命中该分支，于是报告里写满 `G:\Git\<用户>\...`。报告随技能入库后，即成为引擎明令禁止的「项目专有值」泄漏 |
| 补丁 A（30 个脚本） | 新增模块级 `_fallback_display(path)`，把兜底从「裸绝对路径」改为「以目标自身所在项目根为基准的相对路径」：向上找到第一个含 `.codebuddy` 或 `.git` 的目录，返回 `resolved.relative_to(该目录)`；仍失败时退化为「去掉盘符的尾部路径」。`display_path()` 的 `except` 分支改调该函数。受影响文件：`adjudicate_output_review` / `build_skill_atlas` / `compile_skill` / `cross_packager` / `evidence_consistency_core` / `import_output_review_decisions` / `prepare_world_class_submission_kit` / `probe_runtime_permissions` / `propose_adaptation` / `python_compat_check` / `registry_audit` / `render_adoption_drift_report` / `render_benchmark_reproducibility` / `render_review_annotations` / `render_review_studio` / `render_review_waivers` / `render_skill_os2_audit` / `render_skill_os2_coverage` / `render_world_class_claim_guard` / `render_world_class_evidence_plan` / `render_world_class_operator_runbook` / `render_world_class_submission_review` / `run_conformance_suite` / `run_output_eval` / `simulate_install` / `skill_ir_paths` / `trust_check` / `upgrade_check` / `verify_package` / `world_class_evidence_contract` |
| 补丁 B（2 个脚本） | `review_studio_actions.py` / `review_studio_gate_helpers.py` 的 `link_from()` 用 `os.path.relpath()` 生成 HTML 链接，**跨盘符**时抛 `ValueError`。改为捕获后返回空串——宁可没有链接，也不把本机绝对路径写进 HTML |
| 补丁 C（1 个脚本） | `review_studio_gates.py` 的发布路线 gate 用 `str(migration_path)` 直拼绝对路径（未走 `report_link`）。改为 `link_from(output_html, migration_path)`，并在 `review_studio_gate_helpers` 的导入清单中补 `link_from` |
| 例外 | `registry_audit.py` 未采用 `_fallback_display()`，而是在 `display_path` 内联 `try/except`（先求相对路径、跨盘符时退回去掉盘符的尾部路径），并将两处 `display_path(skill_dir)` 改为字面量 `.`——因为该命令的基准目录就是被处理的技能目录。行为与该模式等价，故未统一改写 |
| 边界 | 只改路径的**显示形式**，不改变任何路径的**解析与写入**行为；`relative_to` 成功时的原有返回值一字未改，因此同目录场景的输出与上游完全一致 |
| 验证 | 用本补丁后的 yao 对本引擎内另建的一个可选包技能跑完整十道 gate（validate / skill-ir / compile-skill / conformance / trust / runtime-permissions / package / package-verify / install-simulate / registry-audit），全部 `ok`；被处理技能的 `reports/` 下本机路径出现次数从 75 降为 **0**；33 个改动文件 `ast.parse` 全部通过，9 个关键脚本 `import` 全部通过 |
| 事故与回滚 | 首轮批量注入 `import os` 时，把 `skill_ir_paths.py` 的 `from __future__ import annotations` 挤到非首条语句，导致该模块 `SyntaxError`、`compile_skill` 等链式导入失败。已在该文件把 `import os` 移到 `from __future__` 之后修复。**升级重放时必须注意：`import os` 不能插在 `__future__` 之前** |
| 升级注意 | 上游若已修掉该兜底（判断依据：`display_path` 的 `except` 分支不再返回绝对路径），直接采用上游实现并删除本补丁。若上游仍未修，需保留——否则任何「用 yao 处理非 yao 目录下技能」的场景都会重新泄漏本机路径。重放时优先整段替换 `_fallback_display` 函数与 `display_path` 的 `except` 行，比逐行 apply 更稳 |
| 相关 | 该缺陷对任何消费本项目引擎、且用 yao 处理自建技能的项目都成立，属上游应修问题；引擎内另建的可选包是第一个暴露它的场景 |
## 2026-10-27 校验语义反转：禁止 path_scoped 激活

| 项 | 内容 |
|----|------|
| 文件 | `scripts/validate_skill.py`（第 63—69 行） |
| 问题 | 原逻辑为「`activation.mode == path_scoped` 时**要求** `paths` 非空」，即**鼓励**路径触发并强制配路径。本项目已全库弃用路径触发（`paths` 是文件命中后才注入的事后触发，赶不上「未动手就该走技能」的决策点），原逻辑方向相反，且会产出被引擎侧清单校验判为非法的技能，形成两个校验脚本互相矛盾 |
| 补丁 | 删除原「path_scoped 需 paths 非空」判定；改为两条独立拒绝：`mode == path_scoped` 报错并提示改用 `manual` + `triggers`；`paths` 非空报错。`paths: []` 与字段缺省均放行（模板默认值即此形态） |
| 边界 | 只改这一处判定，`mode` 缺失的既有检查与其余字段校验均未动；错误文案不含任何他包组件路径（本包 `requires` 为空，不得引用包外组件） |
| 验证 | 跑自身目录 `ok: true`、退出码 0；两个反例（`path_scoped` + 非空 `paths`、`manual` + 非空 `paths`）均 `ok: false`、退出码 2；引擎侧清单校验与包状态校验均退出码 0 |
| 文档未同步（已知差异） | `references/platform-capability-matrix.md` 的 Portable Semantics 仍写「activation mode and optional path filters」，那是上游原文，本补丁**未改正文**；实际行为已收紧为「路径过滤器必须为空」。升级比对时以本表为准，勿按该句恢复路径触发 |
| 升级注意 | 上游若已自行禁止 `path_scoped`，直接采用上游实现并删除本补丁；若上游仍要求「path_scoped 必须带 paths」，需保留本补丁（否则与本项目触发策略冲突） |

## 2026-10-22 引擎侧新增 rules/（不改正文）

| 项 | 内容 |
|----|------|
| 文件 | 新增 `rules/yao-meta-skill/RULE.mdc`（引擎侧新写，非上游内容） |
| 原因 | 上游只提供技能，无「技能创建必须走该技能」的强制入口；缺该层时是否调用技能完全依赖 `description` 触发，易被绕过 |
| 边界 | **未修改任何上游文件**，仅在包根新增同级 `rules/` 目录（与 `lib/unity-pipeline/rules/` 同一布局约定）；`lib/packs.json` 的 `comps.rules` 由 `[]` 改为 `["yao-meta-skill"]` |
| 升级注意 | 上游若自行提供规则目录，先比对职责再决定保留哪一份，避免同名规则重复注入 |

## 2026-10-22 Windows 兼容：证据发布锁

| 项 | 内容 |
|----|------|
| 文件 | `scripts/evidence_store.py` |
| 问题 | 顶层 `import fcntl` 在 Windows 不存在，导致 `yao.py`、`registry_audit.py` 等凡引入 evidence 链的命令直接 ImportError |
| 补丁 | 改为条件导入：POSIX 用 `fcntl.flock`；Windows 回退 `msvcrt.locking`（对首字节非阻塞独占锁）。锁语义等价，锁被占用时立即抛 `OSError` |
| 新增 | 模块级 `_acquire_lock()` / `_release_lock()`，把平台差异收敛到一处；`publish_lock()` 改为调用二者 |
| 验证 | `python scripts/yao.py --help` 正常输出全部子命令；`import evidence_store` 通过 |
| 升级注意 | 上游若自行加入跨平台锁，直接采用上游实现并删除本补丁 |

