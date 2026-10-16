---
name: export-zipped-dir
description: 导出任意目录为 zip 压缩包。当用户要求"导出目录"、"打包目录"、"压缩目录"、"将 XXX 导出到下载目录"时触发。目录位于 git 仓库内时自动忽略被 gitignore 忽略的文件，可通过 --force 强制包含特定文件（如根目录配置 json）；目录不在任何 git 仓库内时（如 .codebuddy 被单独复制到其他位置）自动退化为全量导出，仅跳过通用构建产物。不处理单文件导出。
license: MIT
mode: Production
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式

`Production` —— 团队复用技能，将任意目录导出为 zip（git 仓库内遵循 gitignore 过滤，支持 `--force` 强制包含被忽略文件）。需通过触发评估和输出风险检查。

## 核心契约

| 维度 | 定义 |
|------|------|
| 拥有的任务 | 将任意目录导出为 zip：git 仓库内遵循 gitignore 过滤，支持强制包含被忽略文件；非 git 环境全量导出 |
| 输出 | 一个 zip 压缩包，含源目录内应导出的全部文件，保持相对路径结构 |
| 排除 | 单文件导出；git 模式下忽略被 gitignore 忽略的文件（除非通过 `--force` 强制）；非 git 模式跳过通用构建产物目录（`.git/`、`bin/`、`obj/`、`__pycache__/`、`node_modules/` 等） |
| 安全保证 | 仅读取与打包，不修改源目录；目标 zip 不存在时自动创建父目录 |

## 工作流程

### 阶段一：确认导出需求

1. 确认**源目录**：可以是当前 git 仓库内的路径，也可以是不在任何 git 仓库内的独立目录（如被单独复制的 `.codebuddy`）——非 git 环境下脚本会自动切换为全量导出。
2. 确认**输出位置**：若用户未指定，默认导出到用户下载目录（`$USERPROFILE/Downloads`），文件名带日期与时间（如 `codebuddy_20260803_143025.zip`）。
3. 确认**强制包含项**：询问是否需要强制包含某些被 gitignore 忽略的文件（典型场景：目录根目录下的配置 json，如 `models.json`、`settings.local.json`）。

### 阶段二：执行导出

运行脚本：

```bash
python .codebuddy/skills/export-zipped-dir/scripts/export_zipped_dir.py \
  --source <源目录> \
  --output <输出.zip> \
  [--force <被忽略但需导出的文件>]
```

示例（导出 .codebuddy 且强制包含根目录配置 json）：

```bash
python .codebuddy/skills/export-zipped-dir/scripts/export_zipped_dir.py \
  --source .codebuddy \
  --output "$USERPROFILE/Downloads/codebuddy_$(date +%Y%m%d_%H%M%S).zip" \
  --force .codebuddy/models.json \
  --force .codebuddy/settings.json \
  --force .codebuddy/settings.local.json
```

### 阶段三：验证输出

1. 脚本输出导出的文件总数与强制包含列表。
2. 抽查 zip 内容，确认排除规则生效（被忽略目录如 `bin/`、`obj/`、`__pycache__/` 不应出现）。
3. 报告 zip 的完整路径。

## 检查清单

- [ ] 源目录是在 git 仓库内（遵循 gitignore 过滤），还是非 git 环境（自动全量导出）？
- [ ] 是否确认了输出位置与文件名？
- [ ] 是否询问了需要强制包含的被忽略文件（如根目录配置 json）？
- [ ] 导出后是否验证了 zip 内容（排除规则生效、强制文件已包含）？
- [ ] 是否报告了 zip 的完整路径？
