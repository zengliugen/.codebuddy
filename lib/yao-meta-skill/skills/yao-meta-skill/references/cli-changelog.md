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
