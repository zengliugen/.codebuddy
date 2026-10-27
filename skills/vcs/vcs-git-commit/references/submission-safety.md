# 提交安全规范

> **规范主源**：用户主动发起、授权要求、提交/推送分离、敏感信息检查等强制条款以 `.codebuddy/rules/vcs/vcs-git-commit/submission-safety-spec.mdc`（授权与安全规范子规则）为准。本文件提供**详细安全参考**（含 Git 命令与检查流程）。

## 用户主动发起原则（按项目配置取值）

发起权由项目侧配置决定（机制见 `references/project-config.md` §1.5），参数为
`commit_initiation` 与 `push_initiation`（各取 `user_only` / `llm_allowed`，默认 `user_only`）：

- **`user_only`**：该操作**必须**由用户主动发起，AI 助手**禁止**自动执行；**禁止**因"便利"或
  "自动保存"等理由自行执行；**禁止**根据对话上下文推断用户意图后自行决定。用户须通过明确指令
  （如输入 `/commit`、`git commit`、`git push` 等）发起。
- **`llm_allowed`**：允许 AI 助手自行发起该操作（可自主执行，不强制授权）。
- 两参数独立；`commit` 放开不蕴含 `push` 放开。

## 用户授权要求

- **`user_only` 模式**（对应操作）：提交/推送前必须向用户展示即将提交的内容摘要（暂存区文件列表、提交信息）
  或待推送的提交列表（如 `git log origin/<branch>..<branch>`），并通过 `AskUserQuestion` 工具获得用户明确授权后方可执行。
- **`llm_allowed` 模式**：本授权环节放开（LLM 可直接执行）；其余需用户确认的交互（如审查跳过、修复/忽略选择）仍照常。
- 授权必须是**显式的、主动的**，**禁止**依赖隐含授权（如"有变更就推了吧"等推断）。
- **禁止**以纯文本提问方式替代 `AskUserQuestion` 工具发起确认。
- **该工具超时不构成豁免**：超时表示用户当时不在场，属临时失败——当次改用纯文本提问，
  用户回话后恢复工具调用。把它读成「本会话不能用」并长期改用纯文本，等同违反上一条；
  超时返回的是错误对象而非用户同意，不得据此推进提交。详见 `core-tooling` 的 `ask-question-spec.mdc`。

## 提交与推送强制分离

- 提交（`git commit`）与推送（`git push`）必须严格分开执行，**禁止**在单次操作中同时完成。
- **`push_initiation=user_only`** 时，**禁止**在提交操作完成后自动执行推送，必须等待用户单独的推送指令；
  **`llm_allowed`** 时 LLM 可自行推送，但仍须与提交分两步执行。
- **禁止**使用 `git add`、`git commit`、`git push` 的链式组合命令（如 `git add -A && git commit -m "..." && git push`）。
- **禁止**使用 `git config alias` 或脚本将提交与推送合并为一步操作。

## 禁止推送的场景

| 场景 | 说明 |
|------|------|
| 暂存区未检查 | 未完成暂存区检查前，禁止推送 |
| 未获得授权 | 用户未明确授权推送操作前，禁止推送 |
| 包含敏感信息 | 提交内容包含密码、密钥、Token 等敏感信息时，禁止推送 |

### 敏感信息检查

每次提交前，扫描暂存区变更中的敏感信息模式：

```bash
# 扫描暂存区中的敏感信息（密码、密钥、Token、API Key 等）
git diff --cached | grep -iE '(password|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|credential|connection[_-]?string)'
```

若检测到匹配项：
1. 列出匹配的行及所在文件。
2. 警告用户提交内容可能包含敏感信息。
3. **阻止提交**，等待用户确认或移除敏感内容。

## 禁止行为汇总

1. **`commit_initiation=user_only`** 时**禁止**自动执行 `git commit`；`llm_allowed` 时允许 LLM 自行发起。
2. **`push_initiation=user_only`** 时**禁止**自动执行 `git push`；`llm_allowed` 时允许 LLM 自行发起（仍须与提交分离）。
3. **禁止**在提交后自动推送（`git commit && git push` 或等效行为）。
4. **禁止**使用 `git push --force` 或 `git push --force-with-lease` 除非用户明确指定。
5. **禁止**在用户未授权情况下修改或操作远程仓库。

## 禁止提交已忽略的文件

### 基本原则

- `.gitignore` 中已经忽略的文件和目录**严禁**通过 `git add -f` 或任何方式强制添加到版本控制中。
- 提交前必须确认暂存区中不包含任何应被忽略的文件。

### 以 `.gitignore` 为准

- 每次提交检查时，**必须从项目根目录的 `.gitignore` 文件中读取当前的忽略规则**，而非依赖记忆或硬编码列表。
- `.gitignore` 可能随时更新，仅以文件中的实际内容为唯一依据。

### 提交前检查

每次提交前，**按顺序**执行以下检查：

```bash
# 1. 读取当前的 .gitignore 规则（始终以文件内容为唯一依据）
cat .gitignore

# 2. 查看暂存区文件
git diff --cached --name-only

# 3. 检查暂存区中是否有文件匹配 .gitignore 的忽略规则
git ls-files --cached --ignored --exclude-standard

# 4. 查看被忽略但存在于工作区的文件（辅助排查）
git status --ignored --short
```

若发现误添加了已忽略文件，立即移除：

```bash
git rm --cached <file>    # 仅从暂存区移除，保留本地文件
```

### 禁止行为

1. **禁止**使用 `git add -f` 强制添加 `.gitignore` 中已忽略的文件。
2. **禁止**使用 `git add --all` 或 `git add .` 后不加检查直接提交。
3. **禁止**提交临时文件（`*.tmp`、`*.bak`、`*.cache` 等）。
4. **禁止**提交 IDE 或编辑器私有的配置文件（如 `.vscode/`、`.idea/`、`*.suo`）。
5. **禁止**在 `.gitignore` 中删除已有忽略规则以绕过检查。
