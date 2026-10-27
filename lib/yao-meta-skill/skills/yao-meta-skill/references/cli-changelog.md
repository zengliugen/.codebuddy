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
