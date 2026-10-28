# 本地补丁记录（vendor）

本包来自上游 yao-meta-skill 2.1.0，随引擎分发。**不翻译正文**（触发评估与回归测试依赖原文措辞）。
本文件只记录本仓库对其所做的最小可行性补丁，便于上游升级时重放与比对。

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
