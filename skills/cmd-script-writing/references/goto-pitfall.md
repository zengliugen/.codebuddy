# goto 与括号块作用域

## 问题现象

在 `if (...)`、`for (...)` 等括号块**内部**使用 `goto` 跳转，会导致：
- 块内 `goto` 之后本应继续执行的括号内语句被跳过。
- 破坏 `setlocal EnableDelayedExpansion` 的延迟展开作用域，使 `!VAR!` 取到空值或旧值。
- 跳转到的标签之后的逻辑顺序错乱。

## 根因

CMD 批处理的括号块（`if (...)` / `for (...)`）是**一次预解析的整体**。在块内执行 `goto` 会立即终止当前块的解析流程并跳转，导致：
1. 块内 `goto` 之后的剩余语句不执行（即使它们在同一个括号块内）。
2. 标签后的执行从新位置继续，但 `setlocal` 的变量作用域、延迟展开状态可能与预期不符。

## 铁律：避免在括号块内用 goto

**不要在 `if (...)` 或 `for (...)` 括号块内部使用 `goto`。** 若需要在条件分支中跳转，改用以下方式之一：

### 方案 A：用 `if` 嵌套替代

把跳转逻辑改为嵌套 `if`/`else`，避免 `goto`：

```bat
if exist "%LINK%" (
    del /f "%LINK%" > nul 2> nul
    if errorlevel 1 (
        echo 删除失败。 
        pause
        exit /b 1
    )
    echo 已删除。 
)
```

### 方案 B：在块外跳转

把 `goto` 放在括号块**外面**（先判断、再跳转）：

```bat
if exist "%LINK%" goto :exist
goto :create

:exist
echo 目标已存在。 
...

:create
echo 创建中。 
...
```

### 方案 C：用标签配合条件，但不在块内 goto

需要循环或跳转时，把判断放在标签与 `goto` 之间，不要包在 `if (...)` 块里：

```bat
:wait_loop
set /a "i+=1"
if %i% lss 4 goto :wait_loop
```

注意这里 `if` 只有单条命令（`goto`），**没有用括号块**，所以 `goto` 是安全的。

## 判断准则

- **`if 条件 ( 多行 )` 是括号块**，块内禁止 `goto`。
- **`if 条件 单条命令` 不是块**（如 `if %i% lss 4 goto :loop`），`goto` 安全。
- 无法避免在块内跳转时，重构为"块外判断 + 标签"结构。

## 与延迟展开的关系

`setlocal EnableDelayedExpansion` 启用后：
- `%VAR%`：在块**解析时**展开（整块一次性读取，取的是进入块前的值）。
- `!VAR!`：在块**执行时**展开（每行执行时取当前值）。

块内用 `set` 赋值后又想立即读取，**必须用 `!VAR!`**（延迟展开），用 `%VAR%` 会取到旧值：

```bat
if exist "%LINK%" (
    set "MSG=已删除" 
    echo 状态: !MSG!   rem 用 !MSG! 而非 %MSG%
)
```

如果配合 `goto` 跳出块，`!VAR!` 的作用域可能被破坏，因此更要避免块内 goto。
