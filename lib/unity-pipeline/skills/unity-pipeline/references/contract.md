# 技能详细契约

本文件由 `agents/interface.yaml` 拆分而来：接口文件只保留机器可读最小集（界面元信息与兼容性声明），详细输入/输出/排除/安全/引用契约在此按需读取。

description: "驱动 Unity Editor 或开发版 Player 的管线技能，来源 com.unity.pipeline，属第三方来源（lib/unity-pipeline）。"
input_contract:
  required:
    - action: 目标动作（打开项目 / 命令执行 / 测试 / 重编译 / 代码重载）
  optional:
    - runtime: 目标实例类型（editor / player）
    - runtime_path: 实例描述符路径（多实例定位）
    - timeout: 命令层超时秒数（--timeout）
    - command_args: 具体命令参数
output_contract:
  required:
    - command_result: 命令返回的 JSON（按字段判定终态）
  optional:
    - instance_info: 实例描述符信息
    - log_path: 命令日志路径
exclusion_contract:
  - direct_exe: 直接启动 Unity.exe（必须走 unity open）
  - keyword_matching: 以关键字匹配判定异步命令终态
  - non_pipeline: 与 Unity 实例无关的纯 C# 编辑操作
safety_constraints:
  - 必须使用 unity open 打开项目，禁止直接启动 Unity.exe
  - 异步命令一律按 JSON 字段判定终态，禁止关键字匹配
  - 编译检查不可跳过；异步命令须轮询而非阻塞等待
  - 服务器仅绑定 127.0.0.1，客户端不得使用 localhost
references:
  - commands: references/commands.md
  - rule: ../../../rules/unity-pipeline/RULE.mdc
