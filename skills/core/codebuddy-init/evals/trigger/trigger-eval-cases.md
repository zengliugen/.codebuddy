# 触发评估用例（codebuddy-init）

依据 `SKILL.md` frontmatter 的 `description` 判断输入是否应触发本技能。

## 应触发（should_trigger）

| # | 输入 | 理由 |
|---|------|------|
| ST1 | 初始化一下项目配置 | 直接要求初始化 |
| ST2 | 新项目接入 .codebuddy，帮我生成配置 | 接入场景 + 生成配置 |
| ST3 | 生成 .codebuddy.project 的配置骨架 | 直呼产物路径 |
| ST4 | 我刚拉取了 codebuddy 引擎，需要创建项目侧配置 | submodule 接入后创建配置 |
| ST5 | 帮我把外置配置都建出来 | 外置配置创建 |
| ST6 | 初始化 codebuddy | 品牌词 + 初始化 |
| ST7 | 项目侧配置文件不存在，帮我建一下 | 缺失驱动创建 |
| ST8 | 按索引生成项目配置文件 | 索引驱动生成 |
| ST9 | 这个引擎装了哪些包 | 列出已安装可选包 |
| ST10 | 把 grilling 包卸了 | 移除可选包 |
| ST11 | 再加装 yao-meta-skill | 追加安装可选包 |
| ST12 | 看看 codebuddy 配置装好没 | 状态检测 |

## 不应触发（should_not_trigger）

| # | 输入 | 应路由至 |
|---|------|---------|
| SN1 | 提交代码 | git-commit / vcs-router |
| SN2 | 检查代码格式 | csharp-format-checker |
| SN3 | 给这个类补注释 | csharp-comment-generator |
| SN4 | 检查测试覆盖率 | csharp-test-coverage |
| SN5 | 审查这次变更 | csharp-code-review |
| SN6 | 打开 Unity 项目 | unity-pipeline |
| SN7 | 刷新 .codebuddy 里的规则文档 | 不适用（引擎维护，非项目初始化） |
| SN8 | 填写提交摘要的 type | git-commit 流程 |
| SN9 | 安装 Python 依赖 | 非引擎包管理 |
| SN10 | npm install lodash | 非引擎包管理 |

## 近邻用例（near_neighbor）

| # | 输入 | 判定 |
|---|------|------|
| NN1 | 初始化这个技能 | 不触发（技能工程，非项目配置；应走 yao-meta-skill） |
| NN2 | 初始化 git 仓库 | 不触发（git init，非本项目配置） |
| NN3 | 配置一下模型 | 不触发（机器级配置 models.json，不在本技能范围） |
| NN4 | 生成配置模板文档 | 边界：若指项目侧配置骨架则触发；若指说明文档则不触发（按语境判定） |
| NN5 | git 装了哪些包 / submodule 列表 | 不触发（版本控制，走 vcs-router） |

## 评估记录

| 日期 | 应触发 | 不应触发 | 近邻 | FP | FN |
|------|--------|---------|------|----|----|
| 2026-10-16 | 8/8 | 8/8 | 4/4（NN4 语境依赖） | 0 | 0 |
| 2026-10-22 | 12/12 | 10/10 | 5/5（NN4 语境依赖） | 0 | 0 |

> 说明：本用例集为内部基线，依据 frontmatter `description` 逐条判定，未引入独立评审者。
