---
name: csharp-test-coverage
description: C# 测试覆盖率检查技能。对指定目录/文件/包做测试覆盖率分析：静态分析（Roslyn 解析运行时成员与 Tests/ 引用的映射，识别零引用成员）为主，Unity Code Coverage 真实采集为辅，双路可合并并标出分歧项。当用户要求"检查测试覆盖率"、"看看哪些代码没有测试"、"找出未覆盖的成员/文件"、"零测试代码"、"跑一次覆盖率"、"未覆盖清单"，或要求为缺失测试生成骨架时，应主动调用此技能。扫描完成后必须询问是否生成 Test 骨架（默认不生成）；骨架需编译验证（已安装可选包 unity-pipeline 时经其 recompile，未安装时用 dotnet build）。真实采集全程不关闭编辑器，状态读取一律走 unity command "script eval" 读内存值，禁止读 Settings.json 判断开关。
license: MIT
compatibility: 需要 .NET 10.0+ SDK 与 Python 3.8+（静态分析工具首次运行自动 dotnet publish）。真实采集需 unity CLI 可用且已安装可选包 unity-pipeline（未安装时该路不可用，退化为静态分析单路）。无需额外 Agent，由 CodeBuddy Code 直接执行。
metadata:
  author: zengliugen
  version: "0.1"
  skills_os: "2.0"
---

## 运行模式
`Production` —— 团队复用技能，需通过触发评估和输出风险检查。

## 快速上手
```bash
# 静态分析（默认，不写任何文件到 Tests/）
python scripts/check_coverage.py <框架包目录>

# 全仓扫描（框架包 + 各业务领域目录，按配置 scanScopes.all）
python scripts/check_coverage.py --scope all

# 真实覆盖率采集（需显式确认；全程不关闭编辑器）
python scripts/collect_real_coverage.py --dry-run
python scripts/collect_real_coverage.py --confirm

# 仅解析已有覆盖率产物
python scripts/parse_unity_coverage.py
```

运行后自动在技能目录 `check_logs/` 下生成：
- `.md` 报告：概览、模块分布、未覆盖成员清单、零测试文件、弱引用、与真实覆盖率的分歧
- `.json` 数据：完整结构化记录

---

## 核心契约
| 维度 | 定义 |
|------|------|
| 拥有的任务 | 给定目录/文件/包，输出测试覆盖率分析：零引用成员清单、零测试文件清单、弱引用清单；可选真实采集与骨架生成 |
| 输出 | `check_logs/` 下 `.md` + `.json`；真实采集时附 Unity 报告路径 |
| 排除 | 不做代码修复（骨架是待补完的脚手架，非成品测试）；不做注释/格式检查（见 `csharp-comment-checker` / `csharp-format-checker`） |
| 前提 | .NET 10.0+ SDK（静态分析）；Unity 编辑器 + Coverage 包（真实采集） |

## 检查口径
### 成员与引用

| 维度 | 口径 |
|------|------|
| 分母 | `public` + `internal` 成员（可经配置加入 `private`） |
| 强引用 | 方法调用、`new`、属性读、字段读、泛型实例化、索引器、`foreach`、`typeof`、`default`、`Assert.Throws<T>`、扩展方法、lambda、继承、特性等 |
| 弱引用 | XML `cref`、反射字符串成员名（如 `GetField("mSlotIndex")`）——**单列，不计入强引用覆盖** |
| 豁免 | `Generated/`、`Gen/`、文件头 auto-generated 标记的**运行时**代码不计入分母；**生成的测试代码计入分子** |

### 覆盖率层级

报告以**成员级**为底，向上汇总到类型级、文件级、程序集级。

## 详细流程

完整执行细节见 [references/guide.md](references/guide.md)，小节索引：

- 前置规则：直接传递目标路径，禁止预分析
- 强制规则
- 双路数据来源
- 目录镜像映射
- 骨架生成规则
- 真实采集要点
- 边界排除（不触发/不支持）
- 已知限制
- 检查清单

## 技能包结构

本技能目录下各子目录的用途如下，均在 SKILL.md 之外按需读取：

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 按需加载的详细参考文档（含契约、指南与示例） | 6 |
| `scripts/` | 确定性执行脚本，供本技能直接调用 | 9 |
| `evals/` | 触发评估用例与语义配置，供 trigger_eval 复跑 | 2 |
| `reports/` | 质量与风险评估报告（输出风险画像、信任报告等） | 3 |
| `agents/` | 接口契约与子代理定义 | 1 |
