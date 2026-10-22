# 项目配置指南（csharp-format-checker）

本技能为**通用技能 + 项目可配置**模式：技能脚本与 `SKILL.md` 通用，每个项目只通过**项目侧配置**
（索引逻辑名 `format_checker.config`，位于 `.codebuddy.project/configs/skills/csharp-format-checker/config.json`）
表达自己的格式范围与忽略目录。目标项目只改项目侧配置，无需改动技能代码。

## 配置项说明

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| `version` | int | 1 | 配置结构版本 |
| `workspace` | string | 空 | dotnet format 工作区（.slnx/.sln/.csproj，相对项目根）；留空则自动探测（`.slnx` → `.sln` → 根级 `.csproj`） |
| `groups` | string[] | `["whitespace","style"]` | 执行的 dotnet format 分组。`whitespace` 处理空格/换行/缩进，`style` 处理 .editorconfig 代码风格（using 排序、命名、var 等）。默认不包含 `analyzers`（第三方分析器），避免 Unity 自带分析器（UNT/UAC 等）的非格式类告警混入 |
| `severity` | string | `warn` | dotnet format `--severity`：只处理/报告等于或高于该级别的诊断（`error`/`warn`/`info`） |
| `no_restore` | bool | true | 免还原执行（Unity 工程 `Temp/obj` 已有还原产物时可提速）；失败且疑似还原问题时脚本会自动去掉该参数重试一次 |
| `changed_scope` | object | `{"max_projects": 3}` | **变更范围检查**（`--changed`）参数。见下节 |
| `exclude_dirs` | string[] | `[]` | **忽略目录**（相对项目根）。其中的文件**既不被检查也不被修改**（经 `--exclude` 传给 dotnet format）。**完全由本配置声明，脚本不内置任何排除项** |

### changed_scope（变更范围检查参数）

`--changed` 只检查**本次变更文件所属的工程**（`.csproj`），而非整个解决方案，可显著提速。

| 子键 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_projects` | int | 3 | 可串行检查的工程数上限。每个工程需独立重载一次工作区（固定开销数十秒，本项目实测约 40 秒/工程），超过该值即**回退整仓**（此时串行耗时已不低于整仓，无收益） |

**取值建议**：上限的临界点 = `整仓耗时 ÷ 单工程耗时`。本项目实测 162 秒 ÷ 41 秒 ≈ 3.9，故取 **3**
（3 个工程约 124 秒，仍有约 24% 收益）；设为 4 时约 165 秒，已与整仓持平。目标项目须按自身工程数
与单工程耗时重新测算后调整。可用命令行 `--max-projects <N>` 临时覆盖，便于调试。

> **回退行为**：无法定位变更工程时（非 git 环境、无变更 `.cs`、变更文件全在忽略目录内、文件不在任何
> 工程内、工程数超上限）脚本**回退整仓检查并输出告警**，不会静默跳过。

## 忽略目录配置（三方插件保护）

`exclude_dirs` 是本技能保护"不应被格式化代码"的唯一边界（脚本不内置任何排除项），请把以下内容加入：

- **三方插件源码目录**：如 `Assets/Plugins`（本项目包含 DOTween、Sirenix/Odin、XLua、Proxima、HybridCLR、TextMeshPro、StompyRobot 等插件源码）。
- **Package 缓存**：`Library/PackageCache`（Unity 官方与社区包源码，不归项目维护）。
- **生成代码目录**：如 `HybridCLRData`、各种 `Gen/` 与 `Generated/` 目录等。
- **自研包内嵌的三方代码**：如 `Packages/com.littlebaby.framework.core/Runtime/ThreadLib/UnityHook`（命名空间为 `MonoHook`，属三方挂钩库，虽位于自研包内仍需排除）。
- **审查范围外的配置目录**：`.codebuddy`（技能自带工具与测试夹具的 `.cs`，不属于项目源码）。

> **语义保证**：忽略目录内的文件不会出现在检查结果中，修复模式也绝不会改写其中任何文件。

**检查范围口径**：仅覆盖 `Assets/` 与 `Packages/` 下的自研代码（`Assets/Game`、`Assets/Battle`、`Packages/com.littlebaby.framework.*`），`Assets/`、`Packages/` 之外的目录（如 `.codebuddy/`）不在检查范围内。该口径同时体现在 `rules/csharp-code/RULE.mdc` 的范围声明中，**新增排除项时两处一并更新**。

本项目当前默认值（生成目录逐一显式声明，形成配置声明 + auto-generated 识别 + 范围限定的三重保护）：

```json
"exclude_dirs": [
  "Assets/Plugins",
  "Library/PackageCache",
  "HybridCLRData",
  ".codebuddy",
  "Assets/Battle/Runtime/Battle.Data/Generated",
  "Assets/Battle/Runtime/Battle.Logic/Generated",
  "Assets/Game/Runtime/Game/Gen",
  "Assets/Game/Runtime/Game/Generated",
  "Packages/com.littlebaby.framework.assetbundle/Runtime/Generated",
  "Packages/com.littlebaby.framework.core/Runtime/Generated",
  "Packages/com.littlebaby.framework.core/Tests/Runtime/Generated",
  "Packages/com.littlebaby.framework.fixedmathematics/Runtime/Gen",
  "Packages/com.littlebaby.framework.fixedmathematics/Tests/Editor/Gen",
  "Packages/com.littlebaby.framework.core/Runtime/ThreadLib/UnityHook"
]
```

自研代码（`Assets/Game`、`Assets/Battle`、`Packages/com.littlebaby.framework.*`）不在排除之列，正常参与检查。

## 迁移到目标项目

1. 复制技能目录与 `csharp-format-checker/config.json`。
2. 将 `workspace` 改为目标项目的解决方案/工程文件，或留空让其自动探测。
3. 将 `exclude_dirs` 改为目标项目的三方插件/生成代码目录清单。
4. 目标项目根目录必须存在 `.editorconfig`（技能的唯一格式标准，不属于技能本体）。

## 常见用法示例

```bash
# 只检查（默认，不修改文件）
python scripts/dotnet_format.py

# 只检查本次变更文件所属的工程（推荐用于提交门禁与代码审查）
python scripts/dotnet_format.py check --changed

# 变更工程检查 + 复用 5 分钟内范围一致的报告（避免重复执行完整检查）
python scripts/dotnet_format.py check --changed --reuse-report

# 变更工程检查，并调整工程数上限（超过则回退整仓）
python scripts/dotnet_format.py check --changed --max-projects 2

# 检查指定目录
python scripts/dotnet_format.py check --path <目标目录>

# 检查指定工程（快速验证某个程序集）
python scripts/dotnet_format.py check --project <工程文件>

# 修复落盘（会修改源码，需先与用户确认范围）
python scripts/dotnet_format.py fix

# 只修复变更工程内的文件
python scripts/dotnet_format.py fix --changed

# 指定忽略目录覆盖配置（一般不推荐，边界统一走配置）
python scripts/dotnet_format.py check --path <目标目录> --project <工程文件>
```

## 与 .editorconfig 的关系

- `.editorconfig`（项目根，`root = true`）是唯一格式标准；本技能不内置任何规范。
- 修改 `.editorconfig` 后重跑即可生效；新增/删除规则无需改动技能或配置。
- 若某目录需独立风格，可在该目录放下级 `.editorconfig`，dotnet format 会自动按最近者优先合并。
