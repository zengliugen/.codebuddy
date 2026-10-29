# tool-export-zipped-dir 变更记录

> **本文件由引擎仓库维护。** 本包为引擎内自建组件，正文与脚本均归本仓库所有。

## 记录规范

- 一个变更一节，**按时间倒序**，标题为 `## YYYY-MM-DD 主题`。
- 每节写明**为什么改**，而不只是改了什么——只记措辞调整的不写。
- 行为变更（脚本判定、退出码、文件产出）必须记录；纯文档润色不单独成节。

## 2026-10-29 项目根锚点去掉 .git（独立仓库形态下根定位错误）

| 项 | 内容 |
|---|---|
| 文件 | `scripts/export_zipped_dir.py` 的 `find_repo_root()` |
| 问题 | **反向缺陷**：用 `os.path.isdir()` 判断 `.git`，而 submodule / worktree 的 `.git` 是**文件**（gitfile），导致在 submodule 内的工作目录被误判为「不在 git 仓库中」，导出退化成全量模式，把被 gitignore 的产物一并打包 |
| 补丁 | 改用 `os.path.exists()`，目录与 gitfile 两种形态都认 |
| 边界 | 此函数判断的是「git 仓库根」，与项目根锚点无关——项目根仍只认 `.codebuddy` |
| 验证 | 在 submodule 形态的仓库内运行，能正确识别为 git 仓库 |
