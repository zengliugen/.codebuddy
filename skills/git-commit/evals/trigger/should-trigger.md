# Should Trigger Cases

## Git 明确上下文

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "git commit" | 触发 git-commit |
| 2 | "提交到 git" | 触发 git-commit |
| 3 | "帮我 git 提交" | 触发 git-commit |
| 4 | "/git-commit" | 触发 git-commit |

## 斜杠命令触发词

| # | 输入 | 预期行为 |
|---|------|---------|
| 5 | `/commit` | 由 vcs-router 承接，检测为 Git 仓库后路由到 git-commit |

## 路由上下文（vcs-router 检测为 Git 仓库后）

| # | 输入 | 预期行为 |
|---|------|---------|
| 6 | "帮我提交代码"（当前目录为 Git 仓库） | 由 vcs-router 路由到 git-commit |
| 7 | "提交一下"（当前目录为 Git 仓库） | 由 vcs-router 路由到 git-commit |
| 8 | "刚才改了战斗模块，帮我提交一下"（当前目录为 Git 仓库） | 由 vcs-router 路由到 git-commit |
| 9 | "这些文件修改好了，提交吧"（当前目录为 Git 仓库） | 由 vcs-router 路由到 git-commit |
