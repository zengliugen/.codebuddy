# 门禁执行结果

本文件记录 2026-10-23 对 grilling 2.0.0 的**实际门禁执行结果**，逐项标注命令、退出码与结论。所有数值来自脚本输出，未做修饰。

## 一、执行环境

| 项 | 值 |
|----|-----|
| 执行日期 | 2026-10-23 |
| 技能目录 | `.codebuddy/lib/grilling/skills/grilling` |
| 工具链 | `yao-meta-skill 2.1.0` 的 `scripts/` |
| 技能版本 | 2.0.0（本地维护分支首版） |

## 二、脚本门禁结果

| 门禁 | 命令 | 退出码 | 结果 | 关键数值 |
|------|------|--------|------|---------|
| 结构校验 | `yao.py validate` | 0 | ✅ 通过 | `validate_skill` / `lint_skill` / `governance_check` / `resource_boundary_check` 四步全部 `ok: true`，`failures: []` |
| 治理检查 | `governance_check.py --require-manifest` | 0 | ✅ 通过 | 得分 **80/100**，档位 `production`，`warnings: []` |
| 触发评测 | `trigger_eval.py` × 6 组 | 0 | ⚠️ 部分达成 | 调参集全 1.000；**盲测 `post_freeze` 精确率 0.667 / 召回 0.400** |
| 信任报告 | `yao.py trust` | 0 | ✅ 通过 | 扫描 16 文件，脚本 0，密钥发现 0，网络脚本 0，权限缺口 0 |
| 一致性检查 | `yao.py conformance --target generic` | 0 | ✅ 通过 | 全部检查项 pass |
| Skill IR | `yao.py skill-ir` | 0 | ✅ 通过 | `schema_version 2.0.0`，`failures: []` |
| 资源边界 | `resource_boundary_check.py` | 0 | ✅ 通过 | 初始加载 868 tokens（上限 1000），全文 9656，延迟资源 4221 |

## 三、引擎一致性

| 检查 | 命令 | 退出码 | 结果 |
|------|------|--------|------|
| 包注册表一致性 | `python .codebuddy/scripts/check_manifest.py` | 0 | `[一致] 包 8 个，组件与索引路径均合规` |
| 安装状态一致性 | `python .codebuddy/scripts/pack_install.py status` | 0 | `一致：安装状态与实际链接完全匹配（已装 4 个可选包）` |

删除 `grill-me` 后，`lib/packs.json`、`README.md`、两处软链接均已同步，无悬空引用。

## 四、未通过 / 缺失项（必须如实列出）

| 项 | 状态 | 原因 |
|----|------|------|
| 触发准确率达标 | ❌ 未达成 | 盲测召回仅 0.400。属短语匹配方法性缺陷，非参数问题，调参不可消除 |
| 三份受控盲评 | ❌ `missing evidence` | 无第三方评审人，不虚构评审记录 |
| 真实输出样本 | ❌ `missing evidence` | 无留档的诘问会话 |
| 长期回归历史对比 | ❌ `missing evidence` | 本次为 2.0 首版，无上一版可对比 |
| Review Studio 页面 | ❌ 未生成 | 未执行 `yao.py review-studio` |
| Governed 档位 | ⚠️ 主动下调 | 治理脚本要求正文含英文边界标记才给 90 分，与项目语言底线冲突，经确认**保语言、降为 production** |

## 五、结论

**脚本门禁 7 项全部退出码 0，引擎一致性 2 项全部一致。**

但"退出码 0"不等于"质量达标"：

- 治理得分 80 对应 `production` 档，非 `governed`；
- 触发评测的真实泛化能力（召回 0.400）明显低于可称为"准确"的水平；
- 三项核心证据（人工盲评、真实样本、回归历史）明确缺失。

**本技能当前的可信陈述是**：工程结构完整、契约清晰、风险画像齐备、回归护栏已建立；触发准确性未达标，人工评审证据缺失。
