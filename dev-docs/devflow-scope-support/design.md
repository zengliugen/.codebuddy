# devflow-scope-support 设计

| 字段 | 值 |
|---|---|
| 状态 | 已实施 |
| 关联能力 | devflow-scope-support |
| 创建日期 | 2026-11-10 |
| 更新日期 | 2026-11-10 |
| 生成器 | devflow-guard/new |

## 背景

> 需求已确认，探索记录见 explore/devflow-scope-support.md（含已排除方向与重新可行的前提）。

`devflow_guard.py` 的配置契约里 `docs_root` 是单值，`docs_dir(root, config)` 是全脚本唯一的
路径拼装入口，所有模式都假定「一个项目一套文档树」。因此引擎开发者在本仓库内开发引擎包时，
无法让「引擎包自身的过程文档」与「消费项目的过程文档」共存——而这两者的读者与入库归属本就不同。

同时，`.codebuddy/dev-design-docs/` 是一条只管纪律的 README，与 `devflow` 的能力文档体系
做同一件事，是后者出现前的过渡形态。两套并存会让「引擎开发文档该按哪套写」没有确定答案。

## 要解决的问题

- 一套脚本要同时管理两棵独立的文档树（引擎域 / 项目域），且两域的判定逻辑不得分叉。
- 引擎域文档改为入库，取消原「仅 README 入库」的忽略规则。
- 两域的能力名、总览表、探索记录、决策编号、归档区必须完全独立。

## 候选方案

| 方案 | 做法 | 代价 | 前提 |
|---|---|---|---|
| A：双域并存 | `scopes.<域>` 声明各自的 `base` 与 `docs_root`，`--scope` 选域；域是叠加在基础配置上的覆盖层 | 配置契约 v1→v2 破坏性变更；旧配置必须显式迁移 | 两域文档根能被同一套判定逻辑分别定位 |
| B：单根切换 | 仍只有一个 `docs_root`，按运行场景切换值 | 同一工作区不能同时管两域文档，`audit` 一次只能查一棵 | 引擎与项目文档永不共存于同一工作区 |
| C：废弃 `dev-design-docs` | 引擎文档并入项目域，靠子目录区分 | 引擎文档随分发进入每个消费项目，读者与入库归属都错位 | 引擎维护者与项目开发者共用同一棵树 |
| D：新增 `by-pack` 布局 | 引擎域按 `dev-docs/<包名>/<文档>.md` 组织 | 两种布局会让 `iter_capability_docs`/`archive`/`status` 每处都要分叉 | 包归属必须由目录结构表达 |
| 不做 | 维持现状，两套并存 | 引擎文档继续靠自律、不入库 | 无 |

选 A。B 与 C 在「两域必须共存」这一条上不成立；D 的代价（布局分叉）明显高于收益
（归属信息），而归属用能力名前缀表达即可，契约成本为零。

## 实现手段

- 选定哪一级：**框架内改动**（改本包自己的脚本与配置），不涉及外部框架符号，无需侵入手段分级。
- 唯一的「侵入性」取舍是把 `docs_dir()` 从拼 `root` 改为拼注入的 `base_root`。选这一处的理由：
  它已是全脚本唯一的文档根拼装入口，改这一处即覆盖 `init`/`new`/`status`/`archive`/`audit`/
  `explore`/`adr` 全部落点，不必给七个模式各写一遍域分支。

## 实测证据

```text
# 环境：Windows 10 / Python 3 / 项目根 Program/Client

# 1) 基线不回归（迁移配置后项目域体检结果与迁移前完全一致）
$ python .codebuddy/lib/devflow/skills/devflow-guard/scripts/devflow_guard.py audit
域：project（base=project，文档根：.codebuddy.project/docs/devflow）
结论：错误 0，警告 0，提示 0
exit=0

# 2) 旧 v1 配置必须失败（不静默回退）
$ <临时换回 v1 配置> python .../devflow_guard.py audit
配置不可用：配置缺少必需键：default_scope（项目侧：…）
顶层 docs_root 已改为按域声明——请在 scopes 中为每个域写 base 与 docs_root…
exit=3

# 3) 引擎域初始化与体检
$ python .../devflow_guard.py --scope engine init
已初始化文档结构（域 engine）：.codebuddy/dev-docs
  .codebuddy/dev-docs/README.md / explore/README.md / decisions/README.md / archive/README.md
exit=0
$ python .../devflow_guard.py --scope engine audit
域：engine（base=engine，文档根：.codebuddy/dev-docs）
结论：错误 0，警告 0，提示 0
exit=0

# 4) --scope 前置与后置等价（子命令侧 SUPPRESS 生效）
$ python .../devflow_guard.py audit --scope engine   # 同样输出「域：engine」
exit=0

# 5) 未知域
$ python .../devflow_guard.py --scope nope audit
配置不可用：未知的域：'nope'
可用域：engine、project
exit=3
```

## 结论

采用方案 A。域做「配置叠加」而非第二套结构，是这次最关键的一条：它让七个模式的判定逻辑
（保护条件、检查项、路径拼装）都保持单份，两域只可能在「文档根落在哪里」上不同。

引擎域文档根声明在引擎侧配置（`references/config.engine.json`），因为它是引擎事实——
写进项目配置会让每个消费项目重复同一常量，引擎改路径时还得逐项目同步。

## 未解问题

- 引擎域能力名前缀（`<包名>-<能力>`）不做机械校验：校验需要权威包清单，读 `lib/packs.json`
  会让脚本依赖安装形态，写进配置又成第三份副本。错前缀不报错，只让归属难查。
- `audit` 一次只查一个域。合查在配置层面可行（两域共享保留目录名与状态集合），但会让
  「某个域体检通过」这一信号变模糊。当前按「交付前两域各跑一次」处理。
