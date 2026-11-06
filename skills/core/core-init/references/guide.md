# 详细流程与规则

<!-- pack-ref-ok: grilling, yao-meta-skill —— 仅作为「追加安装」选项文案的示例出现，
实际选项按当前未安装的可选包动态生成，不构成硬依赖。 -->



本文件由 `SKILL.md` 拆分而来，承载完整执行细节；主文件只保留触发、契约与流程骨架。



## 与引擎和项目侧的边界
| 位置 | 归属 | 由谁维护 |
|------|------|---------|
| `.codebuddy/` | 引擎（可迁移、可 submodule 共享） | 引擎维护者；本技能**只读** |
| `.codebuddy/project.index.json` | 引擎侧配置注册表（入库共享，含路径与骨架） | 引擎维护者；本技能**只读** |
| `.codebuddy.project/` | 项目侧配置（随项目独立） | 本项目；本技能**据此生成** |
| `.codebuddy/models.json` 等 | 机器级/本机级（不入库） | 本机；本技能**不涉及** |

## 工作流程
### 阶段一：定位与索引校验

1. 自当前目录向上查找含 `.codebuddy` 子目录的目录，得项目根（`.codebuddy` 的父目录）。
2. 读取 `.codebuddy/project.index.json`。**索引缺失、JSON 损坏或缺少必需键（`project_config_root`、`files`）时报错退出（退出码 3）**，并提示"索引由引擎随包提供，请确认引擎包完整"。

### 阶段二：状态检测（进入正题前必做）

**无论用户说的是"初始化"还是笼统地"配置一下"，都先探测现状，再决定做什么**，禁止凭入口措辞直接跑生成：

```bash
python .codebuddy/skills/core/core-init/scripts/init_project_config.py --status
```

该命令**只读取磁盘现状、不创建也不修改任何文件**，输出：

| 检测项 | 含义 |
|--------|------|
| `initialized` | 项目配置目录（`.codebuddy.project/`）是否已存在 |
| `missing_configs` | 索引登记的 `files` / `rule_shells` 中缺失的配置项 |
| `missing_dirs` | 索引 `artifacts.dirs` 中缺失的运行时产物目录 |
| `packs.installed` | 已登记安装的可选包 |
| `packs.available` | 注册表存在但未安装的可选包 |
| `packs.unknown` | 安装状态中存在但注册表未登记的包（异常） |
| `links.consistent` | 调用 `pack_install.py status` 得到的链接与实际安装状态是否一致（`null` 表无法探测） |
| `actions` | 依据现状推导的**候选动作**清单，作为询问选项的依据 |

加 `--json` 得结构化结果，便于按 `actions` 精确构造选项。

### 阶段三：报告现状并按 `actions` 询问意图

1. 先用简洁文本向用户报告检测结论（已初始化/未初始化、缺失项数、已装与未装包、链接是否一致）。
2. 用 `AskUserQuestion` **按 `actions` 生成选项**询问要做什么，一问一答，不预设用户意图：

   | `actions` 取值 | 选项文案 | 后续动作 |
   |----------------|---------|---------|
   | `init_skeleton` | 生成配置骨架（首次接入） | 阶段四 A |
   | `fill_configs` | 按项目情况填写配置 | 阶段四 B |
   | `list_packs` | 查看已安装的可选包 | 阶段四 C |
   | `install_packs` | 追加安装可选包 | 阶段四 D |
   | `remove_packs` | 移除已安装的可选包 | 阶段四 E |
   | `verify_packs` | 修复安装状态与链接漂移 | 阶段四 F |

3. 选项文案须带上实际对象（如"追加安装：grilling、yao-meta-skill"），**不得罗列当前不可能的动作**；用户范围外的请求按其原话执行，不硬塞本技能职责。

### 阶段四：按选择执行

**A. 生成配置骨架**

```bash
python .codebuddy/skills/core/core-init/scripts/init_project_config.py
```

- **先确定生效包集合**：默认包 + 项目侧 `configs/packs.json` 记录的已装可选包。**后续所有条目都按此过滤**——
  未安装的包**不生成**配置骨架与产物目录（路径中的包层见 `index-spec.md` §3.3）。
- `files` 中 `format: json` 项 → 写入 `template`（占位值原样落盘，UTF-8 无 BOM、2 空格缩进）。
- `files` 中 `format: markdown` 项 → 按 `template_outline` 生成章节骨架，每节留 `<填写说明>`。
- `rule_shells` 项 → 生成规则项目事实正文骨架（Markdown 章节占位）。
- **`artifacts.dirs` 项 → 创建运行时产物空目录**（`caches/skills/<pack>/<技能>/` 下的 `check_logs/`、`.cache/` 等），供脚本落盘。
- 额外生成固定文件/骨架：
  - `.codebuddy.project/README.md`（目录用途与维护约定）；
  - `.codebuddy.project/.gitignore`（**整体忽略 `caches/` 运行时产物根目录**与**各组件目录下的 `<pack>` 桥接链接**，
    均不入库；并**反选 `configs/`、`docs/`** 恢复入库，见下方「configs 反选」提示）；
  - `.codebuddy.project/store/`（持久化项目结果目录骨架：`README.md` + `.gitkeep`，**入库**）；
  - `.codebuddy.project/cleanup-caches.cmd`（清理入口，薄入口调用引擎侧
    `.codebuddy/scripts/cleanup_artifacts.py`）；
  - `.codebuddy.project/skills/`（技能目录：`README.md` + `.gitkeep`）与
    `.codebuddy.project/{rules,skills,agents}/project/`（**项目专有包**骨架），
    并**建立桥接** `.codebuddy/<类型>/project` → `../../.codebuddy.project/<类型>/project`，
    使项目专有内容被 CodeBuddy 自动加载（失败则告警并给出手工命令，不阻断）。
  - **`root_symlinks.entries` 项** → 生成项目侧源文件骨架（如 `.codebuddy.project/configs/settings.json`）并
    **建立软链接**（如 `.codebuddy/settings.json` → `../.codebuddy.project/configs/settings.json`），使 CodeBuddy
    经软链接读取外置的根级文件（失败则告警并给出手工命令，不阻断）。
- **幂等保护**：目标文件/目录已存在时**跳过不覆盖**（列出"已存在，跳过"）；确需覆盖文件时用 `--force`（须先确认用户知晓将丢失已有内容）。

> **产物目录清单由索引驱动**：新增技能产物目录时，在索引 `artifacts.dirs` 登记（逻辑名 → 项目侧镜像路径，
> 路径含包层），初始化脚本与各技能脚本即自动适配，无需改脚本。

> **configs 反选（易踩坑，已固化到模板）**：仓库根 `.gitignore` 可能含泛化的 `configs/` 规则
> （典型如 Python 项目忽略运行时用户配置），它会**一并匹配** `.codebuddy.project/configs/`，
> 导致项目侧入库配置被静默忽略、不随项目共享。因此模板固定生成两行反选：
> ```
> !configs/
> !configs/**
> ```
> **两行缺一不可**：父级规则为目录级 `configs/` 时，仅写 `!configs/` 可能无法恢复嵌套文件，
> `!configs/**` 才能让 `configs/skills/<pack>/...` 等深层内容正常入库。
> 反选只作用于 `.codebuddy.project/` 范围，不影响其他目录的同名 `configs/`。
> **校验方法**：生成后执行 `git status --short`，确认 `.codebuddy.project/configs/` 下文件为
> `??`/`A` 而非被忽略；`caches/` 应仍被忽略。

> **卸载包后的残留**：从 `packs.json` 移除某包后，其配置与缓存目录会残留。`--status` 会把这些孤儿项
> 单列（候选动作含 `prune_orphans`）；**须经用户确认**后再执行 `--prune-orphans` 清理
> （只删配置文件与空产物目录，非空目录不删）。禁止未经确认自动清理。

**B. 按项目情况填写**

逐项读取该配置所属技能的 `references/config-guide.md`，并结合项目实际探测（构建清单、目录结构、依赖声明、模块/程序集清单、格式化配置等）填充占位值：

1. **每项填写前须实际读取项目，不得凭经验假设**；探测不到的值明确向用户询问，不猜测。
2. 填写后**向用户复述改动**（键 → 值）供确认；确认无误再写入。
3. 涉及口径一致性的配置（如多处的排除目录清单）必须同步，避免漂移。
4. 全部填写完成后，建议运行对应技能做一次冒烟验证（如格式检查 `--help`、覆盖率静态分析小目标）。

**C. 查看已安装的可选包**

```bash
python .codebuddy/scripts/pack_install.py list
```

输出中每个包名下方可能出现 `可选搭配 xxx（未装不影响本包功能）` 一行。它来自注册表的
`optional_requires`，只是「装了本包后可考虑再装」的提示，**不随安装自动装上**，
也不代表本包缺它不可用。用户想装时按 D 走正常安装流程。

**D. 追加安装可选包**

1. 从 `--status` 的 `packs.available` 取值，用 `AskUserQuestion`（`multiSelect`）让用户勾选，不替用户决定。
2. 执行安装（依赖由安装器自动带出）：

```bash
python .codebuddy/scripts/pack_install.py install <包名...>
```

3. 安装后用 `pack_install.py status` 复核一致，并向用户说明**新技能需重启会话才会出现在技能目录**。

**E. 移除已安装的可选包**

1. 从 `--status` 的 `packs.installed` 取值让用户勾选；默认包（`core`/`vcs`/`tool`/`project`）不可卸载。
2. **移除是不可逆操作，须先向用户确认将删除的链接清单**；安装器报"被依赖"时，明确询问是否连带移除依赖方（`--force`）。

```bash
python .codebuddy/scripts/pack_install.py remove <包名...>
```

**F. 修复安装状态与链接漂移**

```bash
python .codebuddy/scripts/pack_install.py verify --repair
```

### 阶段五：报告

输出做了什么（创建/跳过的文件、装/卸的包、修复的链接）+ 下一步提示：

- 未填写的配置在首次运行对应技能时会报错（配置缺失即报错，不静默使用默认值）；
- 项目专有内容放 `.codebuddy.project/<类型>/project/` 下（经 `.codebuddy/<类型>/project` 链接自动加载）。

## 检查清单
- [ ] 是否先跑 `--status` 做只读检测（**未检测就不得生成或改包**）？
- [ ] 是否先向用户报告现状（已初始化/未初始化、缺失项、已装/未装包、链接一致性）？
- [ ] 是否按 `actions` 用 `AskUserQuestion` 询问意图，且选项只包含当前可行的动作？
- [ ] 是否先定位项目根并校验索引（缺失即报错退出 3）？
- [ ] 生成是否经过脚本（而非手工臆造字段）？
- [ ] 是否依据索引 `artifacts.dirs` 创建了 `caches/` 运行时产物空目录，并生成了 `.gitignore`、`cleanup-caches.cmd` 与 `store/` 骨架？
- [ ] `.codebuddy.project/.gitignore` 是否含 `!configs/` + `!configs/**` 两行反选？生成后用 `git status --short` 确认 `configs/` 下文件**未被忽略**、`caches/` **仍被忽略**？（仓库根若有 `configs/` 规则，缺反选会导致项目侧配置不入库）
- [ ] `.codebuddy.project/.gitignore` 是否含 `skills/*`、`rules/*`、`agents/*` 三条忽略，且以 `!*/project/` + `!*/project/**` 放行项目专有内容？生成后用 `git check-ignore -v` 确认 `<pack>/` 链接**被忽略**、`project/` 下文件**未被忽略**（桥接是派生结果，入库会与 `packs.json` 脱节并产生装包噪音）
- [ ] 是否生成了 `.codebuddy.project/{rules,skills,agents}/project/` 骨架并**建立了桥接** `.codebuddy/<类型>/project`（失败时是否已告警并给出命令）？
- [ ] 是否依据索引 `root_symlinks.entries` 生成了根级源文件骨架（如 `.codebuddy.project/configs/settings.json`）并**建立了软链接**（失败时是否已告警并给出命令）？
- [ ] 已存在文件是否跳过未覆盖（未获确认不使用 `--force`）？
- [ ] 装/卸包是否经 `pack_install.py`（而非手工增删链接），且操作后用 `status` 复核一致？
- [ ] 卸载前是否向用户确认将删除的链接清单（不可逆）？
- [ ] 追加安装后是否提示"新技能需重启会话才会出现在技能目录"？
- [ ] 是否输出了创建/装/卸/修复清单？
- [ ] 「填写配置」时，是否逐项**实际探测项目**而非套用经验值，并向用户复述确认？
- [ ] 是否提示了"未填写配置首次运行会报错"？
