# 技能详细契约

<!-- pack-ref-ok: csharp, csharp-format-checker, csharp-test-coverage, csharp-comment-checker, git-commit —— references 指向可选包文档，仅在该包已安装且需要查阅时使用；未安装时该条目跳过。 -->

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: 项目配置初始化与可选包管理技能。当新项目需要接入本 .codebuddy 引擎，或需要查看/追加安装/移除引擎可选包时触发；运行先做只读状态检测，再据现状询问意图，可选动作为生成配置骨架、填写配置、列出已装包、追加安装、移除、修复链接漂移。不含任何项目专有值。
input_contract:
  required:
    - trigger: 用户要求初始化项目配置 / 接入 codebuddy 引擎 / 生成配置骨架
  optional:
    - status_only: 仅做状态检测（--status），不生成也不改包
    - fill_now: 是否在生成后立即按项目情况填写（默认由 AskUserQuestion 询问）
    - pack_action: 包管理动作（list / install / remove / verify），包名由用户勾选
    - force: 是否覆盖已存在文件（默认跳过不覆盖）
  fallback:
    - index: 索引与骨架均来自 .codebuddy/project.index.json，无需用户提供字段
output_contract:
  required:
    - status_report: 状态检测结论（是否已初始化、缺失配置与产物目录、已装/未装包、链接一致性、候选动作）
    - intent: 经 AskUserQuestion 确认的用户意图（生成 / 填写 / 列出 / 安装 / 移除 / 修复）
  conditional:
    - project_config_dir: 执行「生成配置骨架」时的项目侧配置目录路径（.codebuddy.project/）
    - created_list: 执行「生成配置骨架」时的创建清单（路径 + 类型 + 是否跳过）
    - pack_changes: 执行包管理动作时的装/卸/修复清单与复核结果
  optional:
    - fill_plan: 选择「立即填写」时的逐项填写计划与探测结果
    - verify_result: 填写后的冒烟验证结果
  evidence:
    - index_path: 使用的注册表路径
    - skip_list: 已存在而跳过的文件清单（幂等证据）
exclusion_contract:
  - modify_engine: 修改 .codebuddy 引擎侧文件（引擎只读）
  - overwrite_without_confirm: 未获用户确认时覆盖已存在且可能已填写的文件
  - skip_status: 未做状态检测就生成骨架或改动可选包
  - decide_packs_for_user: 替用户决定装/卸哪些包
  - remove_default_pack: 卸载默认包（core/vcs/tool/project）
  - guess_values: 填写项目值时猜测而非实际探测或询问用户
  - machine_level: 处理 models.json / settings.local.json 等机器级配置
safety_constraints:
  - 索引缺失、损坏或缺少必需键时报告并退出（退出码 3），不猜测字段
  - 默认幂等：已存在文件跳过不覆盖；--force 须先确认用户知晓将丢失已有内容
  - 索引路径必须为相对路径；拒绝绝对路径（防跨项目污染）
  - 「立即填写」阶段每项须实际探测项目，探测不到时询问用户而非套用经验值
  - 填写后向用户复述「键 → 值」供确认再写入
  - 包管理一律经 .codebuddy/scripts/pack_install.py，禁止手工增删链接；操作后以 status 复核
  - 卸载不可逆：执行前须向用户确认将删除的链接清单
<!-- pack-ref-ok: csharp-format-checker, csharp-test-coverage, csharp-comment-checker, git-commit
 下列 references 指向可选包技能文档，仅供「该包已安装时」查阅；未安装时对应条目跳过，不构成硬依赖。 -->
references:
  - index-spec: references/index-spec.md
  - fill-guide: references/fill-guide.md
  - format-config-guide: ../../../csharp/csharp-format-checker/references/config-guide.md
  - coverage-config-guide: ../../../csharp/csharp-test-coverage/references/config-guide.md
  - comment-config-guide: ../../../csharp/csharp-comment-checker/references/config-guide.md
  - git-commit-project-config: ../../../vcs/git-commit/references/project-config.md
evaluation:
  trigger_evals: evals/trigger/
  output_risk_profile: reports/output-risk-profile.md
