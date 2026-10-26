# 路径参数处理

## 场景

批处理脚本常需接收目标目录/文件路径，可能来自：
- 命令行参数（`%~1`）
- 交互输入（`set /p`）
- 脚本自身位置（`%~dp0`）

路径可能含**空格**（如 `D:\my folder`），也可能被用户**加了引号**（如 `"D:\my folder"`）。

## 一、脚本自身路径：%~dp0

- `%~dp0` 返回脚本所在目录，**以反斜杠结尾**（如 `D:\scripts\`）。
- `%~dp0` 本身已含引号包裹，拼接文件名安全：
  ```bat
  set "SOURCE=%~dp0Example.md"
  ```
- 取脚本上一级目录（脚本在子目录内）：
  ```bat
  for %%i in ("%~dp0..") do set "DEFAULT_TARGET=%%~fi"
  ```
  `%%~fi` 会展开为规范完整路径（去尾部反斜杠）。

## 二、命令行参数：%~1

- 用 `%~1`（带 `~`）会**自动去除外层引号**，得到干净路径。
- 但若参数含空格且未加引号，`%~1` 只能取第一段。因此调用方应给含空格路径加引号传参。

## 三、交互输入去引号

`set /p` 读入的路径**不会自动去引号**。用户可能输入 `"D:\my folder"`，引号会保留在变量中，导致后续 `if not exist` 判断和路径拼接出错。

处理方式——去掉路径两端成对的引号：

```bat
set /p "TARGET_ARG=目标目录: "
rem 去除输入路径两端可能带有的引号
if "!TARGET_ARG:~0,1!"=="""" if "!TARGET_ARG:~-1!"=="""" set "TARGET_ARG=!TARGET_ARG:~1,-1!"
```

判断逻辑：首字符和末字符**同时**是引号（`"`）时，用 `!TARGET_ARG:~1,-1!` 去掉首尾各一个字符。这样：
- 普通路径 `D:\my folder` 不受影响（首字符不是引号）。
- 带引号路径 `"D:\my folder"` 去掉引号 → `D:\my folder`。

## 四、去尾部反斜杠

参数或输入的目标目录末尾可能带 `\`（如 `D:\` 或 `D:\my folder\`），直接拼接文件名会产生 `D:\my folder\\file`（双反斜杠）。

处理方式：

```bat
if "%TARGET_ARG:~-1%"=="\" set "TARGET_ARG=%TARGET_ARG:~0,-1%"
```

注意：盘符根目录 `D:\` 去掉反斜杠后是 `D:`，拼接为 `D:\Example.md` 仍正确；但 `D:` 作为相对盘符有歧义，如有需要可单独处理。一般目录场景此判断足够。

## 五、拼接完整路径

```bat
set "LINK=%TARGET_ARG%\Example.md"
```

## 六、存在性判断

用引号包裹变量避免空格问题：

```bat
if not exist "%TARGET_ARG%" (
    echo 错误: 目标目录不存在: %TARGET_ARG% 
    pause
    exit /b 1
)
```

## 综合示例

```bat
set "TARGET_ARG=%~1"
if not defined TARGET_ARG (
    set "TARGET_ARG="
    echo 请输入目标项目根目录，直接回车使用默认: !DEFAULT_TARGET! 
    set /p "TARGET_ARG=目标目录: "
    if not defined TARGET_ARG set "TARGET_ARG=!DEFAULT_TARGET!"
    if "!TARGET_ARG:~0,1!"=="""" if "!TARGET_ARG:~-1!"=="""" set "TARGET_ARG=!TARGET_ARG:~1,-1!"
)
if not exist "%TARGET_ARG%" (
    echo 错误: 目标项目根目录不存在: %TARGET_ARG% 
    pause
    exit /b 1
)
if "%TARGET_ARG:~-1%"=="\" set "TARGET_ARG=%TARGET_ARG:~0,-1%"
set "LINK=%TARGET_ARG%\Example.md"
```
