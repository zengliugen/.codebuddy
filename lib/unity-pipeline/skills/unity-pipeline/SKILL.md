---
name: unity-pipeline
description: 通过命令行打开 Unity 项目并驱动正在运行的 Unity Editor 或开发版 Player。项目启动使用 Unity CLI 内置的 `unity open` 命令（非 pipeline 包提供）；实例控制依赖 unity-pipeline 包（`unity pipeline` / `unity command`）。当智能体需要打开/启动 Unity 项目、控制实时 Unity 实例、自动化 Unity 测试（运行/列出/重编译）、无头重编译脚本、评估 C# 代码，或应用运行时代码重载（`script.methodreload reload` / `reload_editor` / `reload_player`）时使用。前提：`unity` CLI 未安装时，技能通过内置离线安装包自动安装（`tools/unity-cli-offline/install.ps1`，离线优先 + 在线回退）。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "2.0"
---

# Unity Pipeline（智能体控制）

命令一律按 **`unity command "<分组> <名称>" [参数]`** 调用（0.9 起强制分组，旧扁平名已失效）。
**分组与名称必须作为同一参数传入**——不加引号会被当成"执行名为 editor 的命令"而失败。
不带参数执行 `unity command` 列出全部命令。两个服务器：**编辑器**（`7800-7849`，随编辑器启动）
与**运行时**（`7900-7949`，仅存于启用 Pipeline 的 Player 构建）。

> 详细资料按需读：[commands.md](references/commands.md) 命令速查 ·
> [advanced-commands.md](references/advanced-commands.md) 安装/方法重载/批处理/求值/审计 ·
> [contract.md](references/contract.md) 契约

## 0. CLI 检查与安装

```bash
python .codebuddy/skills/unity-pipeline/unity-pipeline/scripts/check_unity_cli.py
```

通过后缓存 24 小时（按 `unity` 路径与版本指纹失效，失败不缓存；`--no-cache` 强制重查）。
未安装时执行离线优先安装（缺二进制则在线回退）。

## 1. 打开 Unity 项目

**必须使用 `unity open`，禁止直接启动 Unity.exe**（后者绕过 Hub 版本匹配，无法与 Pipeline 衔接）。

```bash
unity open <项目路径> --args "-automated"    # -automated 阻止模态弹窗中断连续命令
```

`open` 会**一直挂起直到编辑器退出**，必须后台执行，再用 `unity pipeline list` 与
`unity command "editor status"` 轮询确认就绪，**不要等待 `open` 返回**。

## 2. 安装与校验

```bash
unity pipeline install      # 安装到当前项目
unity pipeline list         # 确认实例 + 服务器可达 + 包版本
```

升级包后**必须重启编辑器**：命令注册是编译期特性，旧进程不会出现新分组。

## 3. 自主编辑循环（核心工作流）

```bash
unity command "editor set_auto_tick" --enable true   # 失焦仍持续 tick，无头工作前必需
# 在磁盘上编辑 C# 源文件
unity command "script recompile"                     # 异步触发域重载
unity command "script recompile_status"              # 轮询至终态
unity command "test run" --mode editor --filter MyFixture.MyTest
```

关键判定规则：

- **终态必须按 JSON 字段判定，禁止关键字匹配**——`"failed":false` 会被 `failed` 命中而误判成功。
  取 `status` 值与终态集合比较；`scripts/unity_wait.py` 已内置该逻辑。
- `compilationFailed=true` 表示编译失败抑制域重载，**不要据 `up_to_date` 判通过**。
- playmode 测试**必须加 `--async_tests true`**（会域重载并丢弃同步请求），再轮询 `test status`。
- **超时可被 CLI `--timeout <秒>` 覆盖**（默认 30 秒，覆盖命令默认值）。
- **退出码**：`2` = 参数错误（改命令行重试）；`6` = 已执行但失败（重试无意义）。
- **卡住的命令可能是模态弹窗**：查 `editor status`，`blocked_by_dialog` 需人工关闭。
- **只走环回**：服务器只绑 `127.0.0.1` 并校验 Host 头，`localhost` 会被拒绝。

## 技能包结构

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 命令速查、进阶命令、版本同步、契约 | 4 |
| `scripts/` | 轮询、结果解析、版本检查、CLI 检查 | 4 |
| `evals/` | 触发评估用例与语义配置 | 3 |
| `reports/` | 质量与风险评估报告 | 1 |
| `agents/` | 接口契约 | 1 |
