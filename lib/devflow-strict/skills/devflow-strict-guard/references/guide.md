# devflow-strict-guard 说明

本技能是**薄转发层**，不含实现。它的存在只为一件事：满足引擎对入口规则的配套要求。

## 先读设计记录

拆包的理由、为什么本技能只做转发、以及设计中被否决的选项，都在
`lib/devflow/DESIGN.md`。本文只讲怎么用。

## 为什么需要它

引擎校验项 9 规定：入口规则目录必须有**本包同名或同前缀的技能**。
`devflow-strict` 包承载「强制入口」，因此必须自带一个技能。

但流程逻辑（脚本、模板、判据）只有一份，在 `devflow` 包里。这里刻意**不复制**——
复制会导致改一处忘另一处，正是本项目反复强调要避免的形态。

## 两个包的关系

```text
devflow            规范 devflow（RULE + 3 子）+ 技能 devflow-guard
                   无常驻入口 → 可选使用
     ↑ requires
devflow-strict     入口规则 devflow-strict-guard.entry + 转发技能 devflow-strict-guard
                   常驻入口 → 强制使用
```

装 `devflow-strict` 时 `requires` 单向闭包会自动带上 `devflow`，用户不需要装两次。

## 转交规则

能力开发的全部动作由 `devflow` 包的 `devflow-guard` 技能执行（`init` / `new` / `audit`），
本技能只负责回答「本项目档位是什么、能不能跳过」。转交表只维护在 `SKILL.md` 一处。

## 不要做的事

1. **不要在本技能里重复规范内容**——判据只写在 `devflow` 规则族。
2. **不要把脚本或模板复制过来**——两份必然分叉。
3. **不要在 `devflow` 缺失时静默降级**——应报错说明安装异常。
