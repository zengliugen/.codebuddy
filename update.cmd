@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

rem ============================================================
rem  更新 CodeBuddy 引擎仓库到最新（双击可执行）。 
rem
rem  本脚本是薄入口：实际更新逻辑由引擎侧通用脚本 
rem  （scripts/update_repo.py）承担；脚本自动识别仓库形态 
rem  （普通仓库 / git 子模块）并采用对应的更新方式。 
rem
rem  默认更新本脚本所在的 .codebuddy 引擎仓库；如当前目录为 
rem  子模块，更新后会提示父仓库需提交子模块指针更新。 
rem
rem  用法（也可双击直接运行）： 
rem    update.cmd              更新 .codebuddy 引擎（默认） 
rem    update.cmd --fetch-only 只获取远程最新，不拉取 
rem    update.cmd --json       以 JSON 输出结果 
rem ============================================================

rem 定位引擎侧更新工具（相对本脚本：<...>/.codebuddy/ -> <...>/.codebuddy/scripts/） 
set "BASE=%~dp0"
if "%BASE:~-1%"=="\" set "BASE=%BASE:~0,-1%"
set "UPDATE_TOOL=%BASE%\scripts\update_repo.py"

if not exist "%UPDATE_TOOL%" (
    echo [错误] 未找到引擎侧更新脚本：%UPDATE_TOOL%
    echo        请确认 .codebuddy 引擎包完整。 
    pause
    exit /b 1
)

rem 查找可用的 Python（python 优先，回退 py）。 
set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>&1
    if not errorlevel 1 set "PYEXE=py"
)
if not defined PYEXE (
    echo [错误] 未找到 Python，请先安装 Python 3 并加入 PATH。 
    pause
    exit /b 1
)

rem 执行更新；透传全部参数（无参数时脚本默认更新 .codebuddy 引擎）。 
"%PYEXE%" "%UPDATE_TOOL%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo 更新流程结束，按任意键关闭窗口。 
) else (
    echo 更新未成功，退出码 %RC% ，请查看上方提示，按任意键关闭窗口。 
)
pause
exit /b %RC%
