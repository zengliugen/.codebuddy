# Should NOT Trigger Cases

## Amend 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "帮我 amend 一下上次提交" | 不触发 git-commit |
| 2 | "修改上一次的 commit message" | 不触发 git-commit |
| 3 | "git commit --amend" | 不触发 git-commit |

## Rebase 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 4 | "rebase 到 main 分支" | 不触发 git-commit |
| 5 | "把当前分支 rebase 上去" | 不触发 git-commit |
| 6 | "git rebase main" | 不触发 git-commit |

## Cherry-Pick 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 7 | "cherry-pick 这个 commit" | 不触发 git-commit |
| 8 | "把那个提交拣选过来" | 不触发 git-commit |

## Revert 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 9 | "revert 最近的提交" | 不触发 git-commit |
| 10 | "回滚上一次的改动" | 不触发 git-commit |

## 其他 Git 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 11 | "stash 一下当前的改动" | 不触发 git-commit |
| 12 | "创建一个新分支" | 不触发 git-commit |
| 13 | "切换到 dev 分支" | 不触发 git-commit |
| 14 | "合并 feature 分支到 main" | 不触发 git-commit |

## 非 Git 操作

| # | 输入 | 预期行为 |
|---|------|---------|
| 15 | "提交这个表单" | 不触发 git-commit（非代码提交上下文） |
| 16 | "提交一个 bug report" | 不触发 git-commit |
