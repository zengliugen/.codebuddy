# devflow-strict 包

> 本包只含**强制档入口**与一个薄转发技能，实现全部在 `lib/devflow/` 包。

## 先读这里

设计记录（为什么拆包、为什么本技能只做转发、被否决的选项）：
**`lib/devflow/DESIGN.md`**

## 本包提供什么

| 组件 | 作用 |
|---|---|
| `rules/devflow-strict-guard.entry/` | 常驻入口：要求新增能力必须走开发流程 |
| `skills/devflow-strict-guard/` | 薄转发技能：只回答档位问题，动作一律转交 `devflow` 包的技能 |

`requires: [devflow]`——装本包时依赖闭包会自动带上 `devflow`，不需要装两次。

## 改之前先确认

1. **不要往本包加实现**。脚本、模板、判据都只在 `devflow` 包；复制过来必然分叉。
2. **不要改成本包独立实现**。曾经尝试让本包「只登记 devflow 包的入口规则」，
   `check_manifest.py` 报「组件缺失」「组件命名不合规」——四个引擎机制约束决定了必须自带组件，
   详见 `lib/devflow/DESIGN.md`。
3. 本包正文不得点名其它包组件，会触发跨包引用校验（`requires` 闭包外的组件名一律报错）。
