# python-lint 执行细则

## 一、快速上手

```
# 检查（默认，只检查不修改）
python scripts/run_ruff.py check

# 提交门禁用（分级阻塞）
python scripts/run_ruff.py check --blocking

# 自动修可修的问题
python scripts/run_ruff.py fix

# 格式
python scripts/run_ruff.py format-check
python scripts/run_ruff.py format

# 只检查本次变更
python scripts/run_ruff.py check --changed

# 显式指定目标
python scripts/run_ruff.py check --target extensions/overrides.py

# 收集本次变更清单（供门禁或其他脚本使用）
python scripts/collect_targets.py
python scripts/collect_targets.py --json
```

## 二、配置项

路径：`.codebuddy.project/configs/skills/python/python-lint/config.json`
（索引逻辑名 `python_lint.config`）

| 键 | 必需 | 说明 |
|----|------|------|
| `version` | 是 | 配置版本 |
| `python_version` | 是 | 工具环境解释器版本（锁 minor） |
| `app_python` | 是 | 应用解释器路径；留空则走四级探测 |
| `line_length` | 是 | 行宽；中文注释按字符计数、显示占 2 格，120 较 88 合适 |
| `select` | 是 | 规则集；默认 `E`/`F`/`I`/`D` |
| `ignore` | 否 | 忽略规则；默认含 `E501`（长行由 formatter 兜住）与 `D400`/`D415`（只认 ASCII 标点，无法识别中文句号，见 §四注） |
| `pydocstyle_convention` | 否 | docstring 风格；默认 `google` |
| `target_version` | 是 | ruff 的目标版本，如 `py312` |
| `include_patterns` | 否 | 白名单；非空即启用白名单模式 |
| `exclude_patterns` | 是 | 黑名单 |

配置是规则与范围的**唯一来源**：脚本不内置任何默认值，缺失或缺少必需键即退出 3。

## 三、模式与退出码

| 模式 | 命令 | 阻塞 | 退出码 |
|------|------|------|--------|
| `check` | `ruff check` | 是 | 0 通过 / 1 有违规 |
| `check --blocking` | ①`check --fix --select I` ②`format --check` ③`check` | ②③ 阻塞，① 仅记录 | 0 / 1 |
| `fix` | `check --fix` | 是 | 0 / 1 |
| `format-check` | `format --check` | 是 | 0 / 1 |
| `format` | `format` | 是 | 0 / 1 |

配置或环境不可用一律退出 3（工具环境缺失、ruff 不存在、配置缺失或损坏）。

## 四、分级为何收在脚本内

单条命令的退出码只有 0 与非 0，表达不了「F/D 阻塞、I 自动修、E501 不阻塞」三档。
若拆成三条门禁命令，则「先修 import 再检查」的执行顺序成为隐式契约，配置膨胀且易错。
因此三档全部收在 `--blocking` 内：

| 档 | 规则 | 处理 |
|----|------|------|
| 自动修 | `I`（import 排序） | `--fix`，机械变换，不阻塞 |
| 阻塞 | `F`（未定义名等）、`D`（docstring） | 需人判断，阻塞 |
| 不检查 | `E501` | 进 `ignore`，长行由 `ruff format` 以改写方式消除 |
| 不检查 | `D400`/`D415` | 进 `ignore`：这两条只认 ASCII 后缀，无法识别中文 `。`。强行满足会让中文注释出现「半角点 + 全角句号」混排。首行标点由 `python-comment` 技能与人工自检保证 |

> **`D400`/`D415` 的取舍**：项目要求中文注释**全角标点**（与 `rules/core/language` 一致）。
> 这两条规则的判据是 ASCII 后缀匹配，`。` 会被判为「无标点」，与「完全没写标点」不可区分；
> `--fix` 的修复是**在全角句号后追加半角点**（`中断。` → `中断。.`）。
> 因此选择 ignore 这两条、把「首行必须有标点」交给 `python-comment` 技能保证。

**参数必须分开构造**：`ruff format` 只接受 `--target-version`/`--line-length`/`--config`，
**不接受** `--select` 与 `--ignore`。混用会让 format 永远报 `unexpected argument`。

## 五、检查范围

| 配置 | 模式 | 语义 |
|------|------|------|
| `include_patterns` 非空 | 白名单 | 默认拒绝，只收匹配的文件；黑名单继续生效 |
| `include_patterns` 缺失或为空 | 黑名单 | 默认放行，仅按 `exclude_patterns` 排除 |
| 两者都空 | — | 报错退出（范围无法确定，不静默全量或全空） |

过滤顺序：**扩展名（硬编码 `.py`）→ 白名单 → 黑名单**。扩展名属技能能力边界，不设配置键。

### 模式书写规则

模式一律按**项目根相对路径**书写。收集脚本会做一次换算：

```
git status 给的仓库相对路径  →  项目根相对路径  →  与模式匹配
```

因此**不需要**为抵销仓库前缀而补 `**/`：

| 写法 | 语义 | 适用 |
|------|------|------|
| `extensions/**/*.py` | 锚定项目根下的该目录 | 精确（推荐） |
| `**/extensions/**/*.py` | 匹配任意层级的同名目录 | 会误匹配 `src/extensions/`、`src/tasks/extensions/` |

实测：用引擎真实的 `glob_to_regex` 编译，不带前缀的写法命中 `extensions/bootstrap.py`
与 `extensions/core/x.py`，不命中 `src/extensions/b.py`；带前缀的写法会命中后者。

## 六、H1 门禁集成

在项目侧 `git-commit/project-config.md` §4 追加一行：

```
enabled  name              description                                   commands                          blocking
true     Python 静态检查    跑格式与规则检查，覆盖白名单内的改动文件；失败即中止   ["<工具环境>/Scripts/python.exe <技能>/scripts/run_ruff.py check --blocking"]   true
```

要点：

- 命令只写一条，模式与范围全由配置与脚本决定（避免两处事实来源）；
- 退出码 3（环境不可用）与 1（有违规）在输出里可区分，便于按情形处置；
- 环境缺失时提示跑 `python-env` 的 `ensure`，**不会自动安装**（安装必须显式可见）。

§3 审查门禁的 `collect_cmd` 指向 `collect_targets.py`，此时
`file_extensions`/`include_patterns`/`exclude_patterns` 全部置空——引擎规定
`collect_cmd` 非空时这三个参数不参与，范围口径只在 `python_lint.config` 一处维护。

## 七、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `工具环境未就绪` | 未跑过 `ensure` | 跑 `python-env` 的 `ensure` |
| `配置缺少必需键` | 项目侧配置未填 | 按 §二 补齐 |
| `白名单与黑名单均未配置` | 两个清单都空 | 至少配一个 |
| format 报 `unexpected argument '--select'` | 参数构造混用 | 本技能已分离；若为自定义调用，去掉 format 的 select/ignore |
| 清单为空但确有改动 | 改动不在白名单内 | 检查 `include_patterns` 与文件路径 |
