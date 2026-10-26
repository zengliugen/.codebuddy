#!/usr/bin/env bash
# ============================================================
#  项目侧一键配置（克隆后运行一次）。
#
#  本脚本是薄入口：实际逻辑由引擎侧 init_project_config.py
#  （--setup 模式）承担，本脚本只负责定位 Python 并透传参数。
#
#  用法：
#    ./setup.sh                              按 configs/packs.json 重建全部链接
#    ./setup.sh --pack csharp,unity-pipeline  首次指定可选包并安装
#    ./setup.sh --minimal                    只保留默认包（core/vcs/tool）
#    ./setup.sh --force                      删除后全量重建
# ============================================================
set -u

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_TOOL="$BASE/skills/core/core-init/scripts/init_project_config.py"

if [ ! -f "$SETUP_TOOL" ]; then
    echo "[错误] 未找到初始化脚本：$SETUP_TOOL" >&2
    echo "       请确认 .codebuddy 引擎包完整，且包含 core 默认包。" >&2
    exit 3
fi

if command -v python3 >/dev/null 2>&1; then
    PYEXE=python3
elif command -v python >/dev/null 2>&1; then
    PYEXE=python
else
    echo "[错误] 未找到 Python 3，请先安装并加入 PATH。" >&2
    exit 3
fi

"$PYEXE" "$SETUP_TOOL" --setup "$@"
