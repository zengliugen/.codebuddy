# Should NOT Trigger Cases

## 暂未纳入路由的 Git 独立操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "帮我 amend 一下上次提交" | 不触发 vcs-router |
| 2 | "修改上一次的 commit message" | 不触发 vcs-router |
| 3 | "git commit --amend" | 不触发 vcs-router |
| 4 | "rebase 到 main 分支" | 不触发 vcs-router |
| 5 | "git rebase main" | 不触发 vcs-router |
| 6 | "cherry-pick 这个 commit" | 不触发 vcs-router |
| 7 | "revert 最近的提交" | 不触发 vcs-router |
| 8 | "回滚上一次的改动" | 不触发 vcs-router |
| 9 | "stash 一下当前的改动" | 不触发 vcs-router |
| 10 | "创建一个新分支" | 不触发 vcs-router |
| 11 | "git push" | 不触发 vcs-router（推送非提交，由 git-commit 技能单独授权流程处理） |
| 12 | "查看 git log" | 不触发 vcs-router |

## 非版本控制上下文

| # | 输入 | 预期行为 |
|---|------|---------|
| 13 | "提交这个表单" | 不触发 vcs-router（非代码提交上下文） |
| 14 | "提交一个 bug report" | 不触发 vcs-router |
| 15 | "提交测试报告给领导" | 不触发 vcs-router |
| 16 | "合并这两个文档" | 不触发 vcs-router（非版本控制合并上下文） |
