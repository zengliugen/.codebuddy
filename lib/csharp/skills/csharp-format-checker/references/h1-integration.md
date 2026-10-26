# 提交门禁集成（h1-integration）

> **归属**：本文件属于 `csharp-format-checker` 技能（`csharp` 包），说明本技能如何接入
> `vcs` 包 `vcs-git-commit` 技能的 **H1 暂存前**钩子。
> **依赖方向**：`csharp` → `vcs`（`csharp.requires` 含 `vcs`），合法；
> `vcs` 包**不反向引用**本文件，也不含任何 C# / dotnet 相关内容。

## 1. 在 H1 中的位置

`vcs-git-commit` 的 H1 步骤完全由**项目侧配置**声明（引擎侧机制见
`.codebuddy/skills/vcs/vcs-git-commit/references/project-config.md` §3 / §3.1）。
本技能对应的步骤行由项目侧 `project-config.md` §4 给出，典型形如：

```
python .codebuddy/skills/csharp/csharp-format-checker/scripts/dotnet_format.py check \
    --changed-from-file <本笔清单文件> --reuse-report
```

引擎侧只负责「执行命令、看退出码、按 `blocking` 判定」，不解释本条命令的参数语义——
参数语义由本文件与 `references/config-guide.md` 承担。

## 2. 退出码约定

| 退出码 | 含义 | H1 处理 |
|---|---|---|
| 0 | 格式合规 | 通过，进入下一 H1 步骤 |
| 2 | 存在待格式化文件 | 视为失败；按步骤 `blocking` 处理 |
| 1 | 执行错误（配置缺失、工程定位失败等） | 视为失败；按步骤 `blocking` 处理 |
| 3 | 配置缺失或字段非法 | 视为失败；须先修配置（见 `references/config-guide.md`） |

> **判定以进程退出码为准**，不可因报告「诊断统计」为空就判定通过——
> 该节只统计 `error`/`warning` 级诊断，与退出码不是一一对应关系。

## 3. 两个范围参数的语义区别（易混，勿用错）

| 参数 | 变更来源 | 适用场景 |
|------|---------|---------|
| `--changed-from-file <清单>` | **只取清单列出的文件** | **提交门禁 H1 必须用这个**（语义 = 本笔提交计划） |
| `--changed` | 工作区 `git status` 的**全部**变更 | 手动检查「当前工作区改了什么」；**不可用于提交门禁** |

二者互斥，同时指定会报错。

用 `--changed` 做提交门禁会把工作区里与本次提交无关的改动一并拉进来
（实测踩坑：只改 `.codebuddy` 时，因工作区另有 106 个 `Assets` 改动而回退整仓，
扫出 2133 处存量 `ENDOFLINE` 误判为失败）。

## 4. 为何位于暂存前（H1）而非暂存后

- **修复动作会改写源码文件**（`dotnet_format.py fix`）。置于暂存前时，修复结果随后
  随正常暂存流程进入提交，**无需「fix 后重新 `git add` 并重跑 `verify_staged.py`」的补偿流程**；
  置于暂存后则会破坏 `vcs-git-commit` 阶段七的暂存区一致性保证。
- 格式检查置于暂存前即落在 **VCS 锁窗口之外**，不占用互斥锁。

## 5. 检查范围口径

由**三重机制**共同保证，无需人工筛选：

| 机制 | 覆盖范围 |
|---|---|
| 变更文件所属工程（`.csproj`）定位 | 排除 `.codebuddy/` 下各工具的工程（不在 Unity 工程映射内） |
| 项目侧配置 `exclude_dirs` | 三方库、生成目录 |
| dotnet format 内置 auto-generated 识别 | 文件头含 auto-generated 标记的文件 |

配置项定义见 `references/config-guide.md`；项目侧取值索引逻辑名为 `format_checker.config`。

## 6. 报告复用（避免重复执行）

命令追加 `--reuse-report`：若 `check_logs/` 中存在 **5 分钟内且检查范围一致**的报告
（含 `csharp-code-review` Agent 阶段生成的那份），直接复用其退出码与报告，
**不再重复执行完整检查**；无可用报告时才实际执行。

范围一致性由报告 `.json` 中的 `scope_key` 与范围信息判定——
因此 `csharp-code-review` 在审查阶段生成报告时，须保证该字段完整写入，
否则 H1 无法复用，会造成同一次提交跑两遍格式检查。

## 7. 与审查门禁的分工

| 环节 | 维度 | 判定方式 |
|---|---|---|
| `vcs-git-commit` §2 审查门禁 | 代码质量 / Bug / 架构等**语义**维度 | Agent 参与，按 `blocking_level` 阻塞 |
| 本技能 H1 步骤 | 格式**合规**（确定性） | 命令退出码 |

两者并行，互不替代：格式合规不代表语义无问题，语义审查也不检查行尾、缩进等格式项。
