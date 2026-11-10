# devflow-scope-support 实施计划

| 字段 | 值 |
|---|---|
| 状态 | 已实施 |
| 关联能力 | devflow-scope-support |
| 创建日期 | 2026-11-10 |
| 更新日期 | 2026-11-10 |
| 生成器 | devflow-guard/new |

## 目标

`devflow_guard.py` 一台脚本可同时管理引擎域与项目域两棵文档树；两域判定逻辑单份、
路径来源单处；引擎域文档入库；v1 配置显式失败而非静默错解。
对应设计文档：`devflow-scope-support/design.md`。

## 分批任务

| 批次 | 内容 | 涉及文件 | 验收标准 |
|---|---|---|---|
| 一 | 脚本改造：配置契约 v2、分层合并、`resolve_scope`、`docs_dir` 改锚点、`--scope` CLI | `scripts/devflow_guard.py` | 七个模式在 `--scope engine` 下行为与项目域一致 |
| 二 | 引擎域目录、引擎侧配置、引擎域总览模板、取消忽略规则 | `references/config.engine.json`、`references/templates/skeletons/README.engine.md`、`.codebuddy/.gitignore`、`.codebuddy/dev-docs/` | `--scope engine init` 产出四份说明；`dev-docs/` 未被忽略 |
| 三 | 索引与项目侧配置迁移 v2 | `project.index.json`、`.codebuddy.project/.../devflow-guard/config.json` | 项目域 `audit` 结果与迁移前完全一致 |
| 四 | 文档与规则同步 | `SKILL.md`、`references/{guide,intake}.md`、`rules/devflow/RULE.mdc`、`devflow-strict` 入口、`DESIGN.md`、`CHANGELOG.md`、引擎 `README.md`、`core-init/references/index-spec.md`、`manifest.json`、`agents/interface.yaml` | 无遗留的顶层 `docs_root` 表述；`check_manifest.py` 通过 |
| 五 | 验收 | — | 计划中九步验收全部通过 |

## 文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `lib/devflow/skills/devflow-guard/scripts/devflow_guard.py` | 修改 | 配置 v2、分层合并、`resolve_scope`、`--scope`、`docs_dir` 改锚点 |
| `lib/devflow/skills/devflow-guard/references/config.engine.json` | 新增 | 引擎侧配置，只声明 `engine` 域 |
| `lib/devflow/skills/devflow-guard/references/templates/skeletons/README.engine.md` | 新增 | 引擎域总览模板（说明入库、包前缀、与项目域的区别） |
| `lib/devflow/skills/devflow-guard/SKILL.md` | 修改 | 新增「两个文档域」小节；配置契约改分层 |
| `lib/devflow/skills/devflow-guard/references/guide.md` | 修改 | 配置契约换 v2；新增「从 v1 迁移到 v2」 |
| `lib/devflow/skills/devflow-guard/references/intake.md` | 修改 | 新增「第二问：在哪个域做」 |
| `lib/devflow/skills/devflow-guard/{CHANGELOG.md,manifest.json,agents/interface.yaml}` | 修改 | 记录本次变更、版本号、输入文件与默认提示 |
| `lib/devflow/DESIGN.md` | 修改 | 新增双域决策、入库决策与被否决选项 |
| `lib/devflow/rules/devflow/RULE.mdc` | 修改 | 执行入口补域与 `--scope` |
| `lib/devflow-strict/rules/devflow-strict-guard.entry/*.mdc` | 修改 | 强制条款补 `--scope` 与两域 |
| `dev-docs/`（原 `dev-design-docs/`） | 改名 + 改写 | README 由 `--scope engine init` 生成；其余入库 |
| `.codebuddy/.gitignore` | 修改 | 删除 `/dev-design-docs/*` 与放行 README 两行及其注释 |
| `.codebuddy/README.md` | 修改 | 目录树与「引擎开发文档」整节重写；边界表补引擎侧配置与 `dev-docs/` |
| `.codebuddy/project.index.json` | 修改 | `devflow.docs.config.template` 换 v2 |
| `.codebuddy/skills/core/core-init/references/index-spec.md` | 修改 | §3.6.2 补引擎域例外 |
| `.codebuddy.project/configs/skills/devflow/devflow-guard/config.json` | 修改 | 迁移为 v2（`scopes.project` + `default_scope` + `overview.template`） |

## 验收标准

- 功能：`init`/`new`/`explore`/`adr`/`status`/`archive`/`audit` 在 `--scope engine` 与
  `--scope project` 下均可工作，且两域文档根、总览表、归档区互不影响。
- 测试：项目域 `audit` 迁移前后结果一致（0/0/0）；引擎域 `audit` 为 0/0/0；
  v1 配置返回退出码 3；未知域返回退出码 3；`new` 的三条保护（缺探索记录、重名、保留目录名）在新域上仍生效。
- 落位：未改动任何非本仓库文件；引擎域文档根由引擎侧配置声明，未写进项目侧。

## 实施进度

开工后逐批更新，**只记结论不记过程**（过程进偏差记录）。

| 批次 | 状态 | 完成日期 | 备注 |
|---|---|---|---|
| 一 | 已完成 | 2026-11-10 | — |
| 二 | 已完成 | 2026-11-10 | — |
| 三 | 已完成 | 2026-11-10 | — |
| 四 | 已完成 | 2026-11-10 | — |
| 五 | 已完成 | 2026-11-10 | — |

## 计划外事项

实施中出现但未纳入原计划的内容，确认是否单独立项。

- `references/config.engine.json` 初版重复声明了 `overview.header`。深度合并对数组取并集，
  重复声明会让总览表出现重复列。已改为只覆盖 `template` 一个键，并把这条陷阱写进该文件的
  `_comment`。属同一批次内的修正，不单独立项。
- `_validate_shapes` 原把 `docs_root` 的类型校验与路径校验写在一起。拆分后顶层不再有
  `docs_root`，该项校验移到 `_validate_scope_docs_root`（按域校验，并额外要求解析后不等于
  且不跳出锚点）。属批次一的实现细节，不单独立项。
