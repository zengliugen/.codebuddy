@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

rem ============================================================
rem  项目侧一键配置（克隆后运行一次）。
rem
rem  本脚本是薄入口：实际逻辑由引擎侧 init_project_config.py
rem  （--setup 模式）承担，本脚本只负责定位 Python 并透传参数。
rem
rem  用法（也可双击直接运行）：
rem    setup.cmd                             按 configs/packs.json 重建全部链接
rem    setup.cmd --pack csharp,unity-pipeline 首次指定可选包并安装
rem    setup.cmd --minimal                   只保留默认包（core/vcs/tool）
rem    setup.cmd --force                     删除后全量重建
rem ============================================================

set "BASE=%~dp0"
if "%BASE:~-1%"=="\" set "BASE=%BASE:~0,-1%"

set "SETUP_TOOL=%BASE%\skills\core\codebuddy-init\scripts\init_project_config.py"
if not exist "%SETUP_TOOL%" (
    echo [错误] 未找到初始化脚本：%SETUP_TOOL%
    echo        请确认 .codebuddy 引擎包完整，且包含 core 默认包。
    pause
    exit /b 3
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
    exit /b 3
)

"%PYEXE%" "%SETUP_TOOL%" --setup %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo 配置完成，按任意键关闭窗口。
) else (
    echo 配置未成功，退出码 %RC% ，请查看上方提示，按任意键关闭窗口。
)
pause
exit /b %RC%
