---
name: tool-cmd-script-writing
description: 编写与修复 Windows CMD 批处理脚本（.cmd/.bat）。当用户要求"写一个 cmd/bat 脚本"、"修复 cmd 乱码"、"cmd 脚本中文乱码"、"echo 报 is not recognized"、"批处理 goto 出错"、"写一个链接（mklink/硬链接）/构建/批处理脚本"时触发。核心能力：规避 chcp 65001 下的 UTF-8 中文乱码（行尾 ASCII 规则）、正确处理 goto 与括号块作用域、路径参数处理（去引号、尾部反斜杠、%~dp0）。覆盖 Windows 批处理脚本的规范编写与乱码/语法陷阱修复。
license: MIT
mode: Scaffold
metadata:
  author: zengliugen
  version: "1.0"
  skills_os: "2.0"
---

## 运行模式
`Scaffold` —— 个人/团队轻量复用技能，保持最小结构，重点放在正确性经验而非功能膨胀。

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 编写符合 Windows CMD 规范的批处理脚本；诊断并修复 UTF-8 中文乱码、`is not recognized` 误判、`goto` 作用域等脚本问题 |
| 输出 | 一个可运行、中文输出正常的 .cmd/.bat 脚本，或对既有脚本的诊断报告 + 修复后的代码 |
| 排除 | PowerShell、Python、Bash（非 CMD 系）；Linux/Unix shell；业务逻辑设计（非脚本语法与编码）；已生成的 `Generate/`/`Gen/` 目录代码 |
| 安全保证 | 不执行破坏性命令（删除/覆盖前需确认）；不读取敏感信息；路径含空格时正确加引号 |

## 关键铁律（违反必出问题）
1. **行尾必须是 ASCII**：在 `chcp 65001`（UTF-8）环境下，任何含中文的行（`echo`、`rem` 注释）**末尾字符必须是 ASCII**（空格、英文标点、引号）。若以中文/全角标点（`。`、`：`、`；`）结尾，会概率性触发 CMD 把后续内容误判为命令，报 `'xxx' is not recognized as an internal or external command`。
2. **不要在括号块内用 `goto`**：`if (...)`、`for (...)` 等括号块内使用 `goto` 会提前退出块并丢弃未执行的括号逻辑，破坏 `setlocal EnableDelayedExpansion` 的延迟展开作用域，导致变量取值为空或错误。
3. **中文输出不用引号包裹**：用 `echo 中文` + **行尾补空格**（而非双引号包裹），既规避乱码又不带引号。

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 工作流程
- 检查清单
- 参考文档

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（乱码、goto、路径处理、验证环境） | 4 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 1 |
| `evals/` | 触发评估用例与语义配置 | 2 |
| `reports/` | 质量与风险评估报告（信任报告等） | 2 |
| `agents/` | 接口契约 | 1 |
