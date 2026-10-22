# Should Trigger Cases

## 通用提交请求（需检测 VCS 类型后路由）

| # | 输入 | 预期行为 |
|---|------|---------|
| 1 | "帮我提交代码" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 2 | "提交一下" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 3 | "提交更改" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 4 | "帮我 commit" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 5 | "提交这些修改" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 6 | "把这些改动提交了" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 7 | "commit changes" | 触发 vcs-router，识别 commit，检测类型后路由 |
| 8 | `/commit` | 触发 vcs-router，识别 commit，检测类型后路由 |

## Git 明确上下文（commit 操作）

| # | 输入 | 预期行为 |
|---|------|---------|
| 9 | "git commit" | 触发 vcs-router，路由到 git-commit |
| 10 | "帮我提交到 git" | 触发 vcs-router，路由到 git-commit |
| 11 | "/git-commit" | 触发 vcs-router，路由到 git-commit |

## 带上下文的提交请求

| # | 输入 | 预期行为 |
|---|------|---------|
| 12 | "刚才改了战斗模块，帮我提交一下" | 触发 vcs-router，识别 commit，检测后路由 |
| 13 | "这些文件修改好了，提交吧" | 触发 vcs-router，识别 commit，检测后路由 |

## merge 操作（占位技能，提示暂未实现）

| # | 输入 | 预期行为 |
|---|------|---------|
| 14 | "合并 feature 分支到 main" | 触发 vcs-router，识别 merge，路由到占位技能 git-merge，提示暂未实现 |
| 15 | "git merge feature" | 触发 vcs-router，识别 merge，路由到占位技能 git-merge，提示暂未实现 |
| 16 | "帮我合并分支" | 触发 vcs-router，识别 merge，路由到占位技能 git-merge，提示暂未实现 |
