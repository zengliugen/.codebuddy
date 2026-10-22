@echo off
goto :main

rem ============================================================
rem  vcs-router 技能：VCS 操作路由 + 缓存批处理入口。 
rem
rem  调用 scripts/route_vcs.py 完成以下工作： 
rem   - 检测当前目录是否为 Git 仓库（git / none） 
rem   - 接收操作类型（--op，默认 commit），组合路由目标 git-<op>
rem   - 读写技能目录 .cache/vcs-route.json 缓存（目录路径一致 
rem     且 10 分钟内有效时直接命中缓存，缓存仅本机使用不进行上传） 
rem   - 支持 --out 将完整路由 JSON 落文件、--quiet 让 stdout 仅输出一行 
rem
rem  用法： 
rem    route_vcs.cmd [--dir 目录] [--op 操作] [--refresh] [--timeout 秒] [--out 文件] [--quiet]
rem
rem  输出：stdout 输出 JSON 路由结果；退出码 0 表示成功。 
rem ============================================================

:main
chcp 65001 > nul
setlocal EnableDelayedExpansion

set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>&1
    if not errorlevel 1 set "PYEXE=py"
)
if not defined PYEXE (
    echo [错误] 未找到 Python，请先安装 Python 3 并加入 PATH。 
    exit /b 1
)

set "SCRIPT=%~dp0route_vcs.py"
if not exist "%SCRIPT%" (
    echo [错误] 未找到路由脚本：%SCRIPT%
    exit /b 1
)

"%PYEXE%" "%SCRIPT%" %*
exit /b %ERRORLEVEL%
