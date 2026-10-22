# Unity CLI 版本同步记录

本文件记录技能相对上游 `com.unity.pipeline` 的本地改动与同步要点。

来源：com.unity.pipeline 0.9.0-exp.1（上游已把 agent skill 移出包，正文以 `Documentation~/` 与
  `Runtime/Common/CommandNames.cs` 为准重建）。本文件为项目内可编辑副本。

  相对上游保留的本地改动：
    - 新增"打开 Unity 项目"章节（必须 `unity open`，禁止直接启动 Unity.exe）；
    - CLI 安装检查与离线自动安装（0.1 / 0.2 / 0.3）；
    - `--runtime` / `--runtime-path` 实例定位；`script eval` 在编辑器上同样可用；
    - 异步命令"按 JSON 字段判终态"，禁止关键字匹配；`unity_wait.py` 等辅助脚本；
    - 命令层超时的可覆盖写法（`unity command --timeout <秒>`）。

  2026-10-21 从 0.7.0-exp.1 同步到 0.9.0-exp.1（0.8 + 0.9 一并吸收）：
    1. **命令改为分组命名**：一律 `unity command "<分组> <名称>"`（**整体一个参数，必须加引号**），
       0.7 的扁平名全部失效。
       `recompile`→`script recompile`、`run_tests`→`test run`、`batch`→`job batch`、
       `wait_for`→`job wait`、`eval`→`script eval`、`run_script`→`script run`、
       `console`→`console get`、`audit`→`diagnostics run_audit`、`editor_status`→`editor status`、
       `set_autotick`→`editor set_auto_tick`、`screenshot`→`capture screenshot` 等。
    2. **代码重载改名为方法重载**：`[CodeReload]`→`[MethodReload]`、`[OnCodeReload]`→`[OnMethodReloaded]`、
       命名空间 `Unity.Pipeline.CodeReload`→`Unity.Pipeline.MethodReload`；
       `reload_file`→`script.methodreload reload`、`*_interpreter`→`reload_editor`/`reload_player`、
       `codereload_status`→`script.methodreload status`、`cleanup_codereload`→`script.methodreload cleanup`；
       新增 `script.methodreload generate_link_xml`（IL2CPP 裁剪用）。
    3. **超时改为按命令声明**（秒），默认 60 秒；CLI `--timeout <秒>` 可覆盖，不再有写死的 30 秒硬超时。
    4. 服务器只绑定 `127.0.0.1`，并用 Host 头校验挡住 DNS 重绑定；客户端不能用 `localhost`。
    5. 实例描述符统一列出所有连接方式（`endpoints`），心跳每 15 秒刷新；`-automated` 缺失改为
       描述符 `info` 字段提示（不再是控制台警告）。
    6. 新增探索类命令：`build list_platforms` / `create_profile` / `set_profile`、
       `editor.playmode set_run_in_background`、`console write`、`script.methodreload generate_link_xml`、
       `authoring get_root` / `set_root`、`editor search`、`runtime simulate_key` / `simulate_pointer`。
    7. 每个命令都接受 `--verbose` 与 `--omit-nulls`；`/api/commands` 支持按组过滤、分组与索引。
    8. 构建门控改为两个开关两条宏：`ENABLE_RUNTIME_PIPELINE_DEV`（开发/带插桩构建）与
       `ENABLE_RUNTIME_PIPELINE`（发布构建），旧版单条 `ENABLE_RUNTIME_PIPELINE` 语义已变。
    9. 样例迁到独立包 `com.unity.pipeline.samples`。
  之后若再升级包，以 `Library/PackageCache/com.unity.pipeline@<hash>/Documentation~/` 与
  `Runtime/Common/CommandNames.cs` 为准重放本同步。
