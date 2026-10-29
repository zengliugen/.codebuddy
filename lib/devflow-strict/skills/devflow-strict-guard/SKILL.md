---
name: devflow-strict-guard
description: 说明本项目的开发流程档位 —— 回答「本项目是否强制走开发流程」「能不能跳过流程」「强制档装在哪」这类档位问题。能力开发的具体动作（生成骨架、体检、初始化）一律由 devflow 包的技能执行，本技能不做也不应被那些请求唤起。
license: 内部项目使用
mode: manual
metadata:
  category: 开发流程
  version: 1.0.0
---

# 强制开发流程引导

本项目安装了 `devflow-strict` 包，即**要求**新增能力走开发流程。
本技能只做一件事：把请求转交给 `devflow` 包的技能，并提醒当前处于强制档位。

## 为什么单独存在

引擎的入口规则要求「有本包同名或同前缀技能」才能登记，因此本包需要一个技能。
但流程逻辑（脚本、模板、判据）**只有一份**，在 `devflow` 包里。这里不复制任何实现——
若复制，日后改一处就要记得改两处，这是本项目反复避免的形态。

## 该做什么

能力开发的全部动作（`init` / `new` / `audit`）由 `devflow` 包的 `devflow-guard` 技能执行。
遇到这类请求时，**转交给它**，不要自己应答。judgement 与实施细则读 `devflow` 规则族。

## 本档位与可选档位的区别

| 项 | 本包（强制） | `devflow` 包（可选） |
|---|---|---|
| 入口规则 | 常驻注入，要求必须走流程 | 无常驻入口 |
| 触发方式 | 常驻提示 + 技能描述 | 仅技能描述，用户主动唤起 |
| 规范内容 | 完全相同（都在 `devflow` 包） | 同左 |

**不要在本技能里重复规范内容**。用户需要判据时，读 `devflow` 规则族。

## 不适用范围

本技能只回答档位问题并转发请求。下列请求**都不该由本技能应答**，应直接交 `devflow-guard`：

| 请求 | 去向 |
|---|---|
| 生成能力文档骨架、初始化文档目录 | `devflow-guard` 的 `new` / `init` |
| 体检文档契约、报缺口 | `devflow-guard` 的 `audit` |
| 判断某次改动算不算新增能力 | `devflow` 规则族 `design-spec.mdc` |
| 决定实现手段 | `devflow` 规则族 `implementation-spec.mdc` |
| 提交代码 | 版本控制路由技能 |

**不负责**：校验能力、复制规范内容、维护流程脚本。

## 已知局限

1. 本技能是薄转发层，自身不含任何校验能力；实际检查全部由 `devflow` 包的脚本完成。
2. `requires` 保证安装本包时会一并装 `devflow`；若因手工操作导致 `devflow` 缺失，
   本技能无可用动作，应报错而不是静默降级。

## 技能包结构

| 目录 | 用途 | 文件数 |
|------|------|--------|
| `references/` | 档位说明与判据（[guide.md](references/guide.md)） | 1 |
| `evals/` | 触发评估用例与语义配置（[trigger_cases.json](evals/trigger_cases.json)、[semantic_config.json](evals/semantic_config.json)） | 2 |
| `reports/` | 质量与风险评估报告 | 1 |
| `agents/` | 接口契约 | 1 |
