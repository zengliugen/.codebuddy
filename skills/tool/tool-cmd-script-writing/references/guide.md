# 详细流程与规则



本文件由 `SKILL.md` 拆分而来，承载完整执行细节；主文件只保留触发、契约与流程骨架。



## 工作流程
### 阶段一：编写新脚本

按以下顺序产出脚本：

1. 确认脚本用途与是否含中文输出（本项目规范要求中文提示）。
2. 骨架：`@echo off` → `chcp 65001 > nul` → `setlocal EnableDelayedExpansion` → 逻辑 → `pause` → `exit /b 0`。
3. 每写一行含中文的 `echo`/`rem`，**立即在行尾补一个英文空格**。
4. 涉及用户输入路径时，处理去引号与尾部反斜杠（见 `references/`）。
5. 用参数化目标、默认值、备份/覆盖策略等完善健壮性。

### 阶段二：修复既有脚本

1. 先读脚本，定位问题类型（乱码 / `is not recognized` / `goto` 作用域 / 路径处理）。
2. **用校验器扫描行尾中文风险**（自动化，比人工逐行可靠）：
   ```bash
   python .codebuddy/skills/tool/tool-cmd-script-writing/scripts/check_cmd_trailing.py <脚本路径>
   # 检出风险后，加 --fix 自动给行尾补空格
   python .codebuddy/skills/tool/tool-cmd-script-writing/scripts/check_cmd_trailing.py <脚本路径> --fix
   ```
3. 按 `references/goto-pitfall.md` 检查括号块内的 `goto` 使用。
4. 修复后必须**实际运行验证**（跨卷/正常/覆盖等场景），不能只看代码。

### 阶段三：验证

- **运行前先人工检查脚本内容**：确认无未经确认的 `del`/`rd`/覆盖写等破坏性命令（与核心契约的安全保证呼应），再执行实际运行验证。
- 脚本文件编码必须是 **UTF-8 无 BOM**（可用 `file` 或 `head -c 3 | xxd` 验证，开头应为 `@ec` 而非 BOM）。
- 行尾应为 **CRLF**（`\r\n`），LF 会导致 CMD 解析异常。
- **运行校验器确认无行尾中文风险**（应输出"通过"）：
  ```bash
  python .codebuddy/skills/tool/tool-cmd-script-writing/scripts/check_cmd_trailing.py <脚本路径>
  ```
- 中文输出验证：`echo 中文` 行末尾有空格时，`is not recognized` 报错消失。
- 涉及硬链接/路径操作时，用真实场景测试（同卷、跨卷、目标已存在覆盖）。
- **验证环境要求**：必须在真实 Windows CMD 中运行验证（Git Bash / PowerShell / WSL 中运行会失真），详见 [`references/verification-env.md`](references/verification-env.md)。

## 检查清单
- [ ] 脚本是否为 UTF-8 无 BOM、CRLF 行尾？
- [ ] **校验器扫描是否通过**（`check_cmd_trailing.py` 输出"通过"，无行尾中文风险）？
- [ ] 括号块（`if`/`for`）内是否避免了 `goto`？
- [ ] 用户输入的路径是否做了去引号与尾部反斜杠处理？
- [ ] 中文输出是否已实际运行验证无 `is not recognized` 报错？

## 参考文档
- [UTF-8 乱码规避](references/utf8-garbled.md) —— `chcp 65001` 下中文乱码的根因与解法
- [goto 与括号块作用域](references/goto-pitfall.md) —— `goto` 在 `if`/`for` 块内的陷阱
- [路径参数处理](references/path-handling.md) —— 用户输入路径的去引号、尾部反斜杠、`%~dp0` 等
- [验证环境要求](references/verification-env.md) —— 必须在真实 Windows CMD 中运行验证，各替代环境的失真说明
- [行尾中文扫描校验器](scripts/check_cmd_trailing.py) —— 自动扫描含中文行是否为 ASCII 结尾，支持 `--fix` 补空格
