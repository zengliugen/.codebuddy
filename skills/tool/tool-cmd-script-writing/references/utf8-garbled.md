# UTF-8 中文乱码规避（chcp 65001）

## 问题现象

在 `chcp 65001`（UTF-8）环境下运行含中文的批处理脚本，会出现两类问题：

1. **乱码**：`echo` 输出的中文显示为 `锟斤拷` 之类的乱码。
2. **误判为命令**：某行中文被 CMD 截断，后续内容被当作命令执行，报：

   ```
   'xxx' is not recognized as an internal or external command,
   operable program or batch file.
   ```

## 根因

`chcp 65001` 是 Windows 的**历史遗留 bug**。CMD 以 UTF-8 逐字节读取批处理文件时，当一行**以汉字或全角标点结尾**（其 UTF-8 总字节数为奇数，或末字节恰好与 `\r\n` 换行符组合成被误读的双字节字符），会导致换行符丢失、行边界混乱，从而把 `echo` 内容误判为命令。

**关键特征**：该 bug 是**概率性的**——同一文本可能时好时坏，无规律可循。因此不能靠"碰运气"，必须从根本上规避。

## 铁律：行尾必须是 ASCII

**任何含中文的行（`echo`、`rem` 注释）末尾字符必须是 ASCII**（空格、英文标点、引号、`!` 等）。

### 正确写法（行尾补空格）

```bat
@echo off
chcp 65001 > nul
echo 错误: 创建硬链接失败。 
echo 请确认目标项目根与 .codebuddy 在同一磁盘卷，硬链接不支持跨卷。 
rem 创建硬链接。 
```

注意每行末尾都有一个**英文空格**。全角标点（`。`、`：`、`；`）用在句中没问题，但**不能作为行尾**。

### 错误写法（行尾是中文/全角标点）

```bat
echo 错误: 创建硬链接失败。
echo 请确认目标项目根与 .codebuddy 在同一磁盘卷，硬链接不支持跨卷。
rem 创建硬链接。
```

行尾的 `。`（全角句号）就是触发 bug 的元凶。

### 含变量的行

变量（`%VAR%` / `!VAR!`）展开后如果行尾是变量值（可能是中文路径），同样需要确保行尾补空格：

```bat
echo 提示: 目标目录: !TARGET_ARG! 
```

## 为什么不用双引号包裹？

`echo "中文"` 也能规避乱码（引号是 ASCII 行尾），但输出会**带引号**：`"中文"`。除非明确接受带引号的输出，否则不推荐。

## 编码要求

- 脚本文件必须是 **UTF-8 无 BOM**（符合本项目语言规范）。带 BOM 会导致首行 `@echo off` 前出现不可见字符，第一行命令失效。
- 行尾必须是 **CRLF**（`\r\n`）。LF（仅 `\n`）会导致 CMD 解析异常、乱码。
- 验证命令：
  ```bash
  file script.cmd          # 应显示 UTF-8 text, with CRLF
  head -c 3 script.cmd | xxd   # 开头应为 4065 63 (@ec)，无 BOM EF BB BF
  ```

## 批量修复

**推荐用本技能附带的校验器**，它能检测两类风险（全角标点结尾 + 中文单字结尾），比手写 perl 更全面：

```bash
# 扫描，检出所有含中文但行尾非 ASCII 的行
python .codebuddy/skills/tool/tool-cmd-script-writing/scripts/check_cmd_trailing.py script.cmd

# 加 --fix 自动给风险行行尾补英文空格（幂等）
python .codebuddy/skills/tool/tool-cmd-script-writing/scripts/check_cmd_trailing.py script.cmd --fix
```

> 注意：手写 perl 方案 `s/([。；：])\r\n/$1 \r\n/` 只能处理**全角标点**结尾的行，会漏掉以**中文单字**（如 `指向`、`目录`、`硬链接`）结尾的行——这类行同样是风险。校验器按"行尾字节是否为非 ASCII"判断，不会漏。

## 验证方法

修复后必须**实际运行**验证，不能只看代码。测试含中文输出的正常路径，确认无 `is not recognized` 报错。同时用校验器复扫，应输出"通过"。
