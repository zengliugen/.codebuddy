# 输出风险画像

## 风险矩阵

| 风险类别 | 严重度 | 概率 | 影响 | 缓解措施 |
|---------|--------|------|------|---------|
| `unity open` 阻塞挂起 | 高 | 高 | 智能体流程卡死，等待编辑器退出 | 明确"open 启动后不等待返回"，后台执行 + `pipeline list` 轮询 |
| 编辑器失焦节流/停滞 | 高 | 中 | recompile/run_tests 挂起或超时 | 强制先 `set_autotick --enable true`（SKILL.md 注意事项） |
| recompile 失败被误判为完成 | 高 | 中 | 编译错误流入后续测试 | 异步轮询 `recompile_status`，failed=true 时读 errors 数组 |
| run_tests 失败返回不透明 | 中 | 中 | 无法定位真实失败原因 | 已知警告 + 更窄 filter 重跑 / 查 Test Runner 日志 |
| 退出码误判导致无效重试 | 中 | 中 | 参数错误（2）原样重试、或真失败（6）改写命令行，浪费时间 | 明确退出码语义（SKILL.md §3）：2 改命令重试、6 读错误勿重试 |
| 代码重载打断运行态 | 中 | 低 | 游戏运行状态被意外修改 | 明确代码重载需游戏在运行；仅 public/void 方法约束 |
| `wait_for` 同步等待自死锁 | 中 | 低 | 条件依赖后续命令时占住 exec 队列，直到超时 | 明确同步仅用于 < 30 秒且不依赖后续命令的等待；否则 `--async true` |
| 多实例定位错误 | 中 | 低 | 操作作用于错误实例 | 编辑器用 `--project-path`、Player 用 `--runtime`/`--runtime-path` |
| CLI 未安装/不可执行 | 高 | 低 | 首次使用即失败 | check_unity_cli.py 检查 + 离线安装（离线优先 + 在线回退） |

## 输出质量维度

### 命令执行质量

可能的问题：
- 触发异步命令后假定"已返回即完成"
- 忽略 recompile_status 的 errors 数组
- playmode 测试用同步模式运行导致超时
- 把退出码 2（参数错误）的调用原样重试，或对退出码 6（已执行但失败）改写命令行

防护措施：
- 异步命令轮询约定（`SKILL.md` §3）
- playmode 必须 `--async_tests true` + `test_status` 轮询
- `--mode all` 不支持异步的边界说明
- 退出码语义表（2 = 改命令行重试；6 = 读错误勿重试）

### 环境就绪保障

可能的问题：
- CLI 未装时命令直接报错
- 国内网络直连 CDN 拿到缓存旧版

防护措施：
- `check_unity_cli.py` 前置检查 + 缓存（24h TTL）
- 代理参数（`-Proxy` / `--proxy`）与通道环境变量 `UNITY_CLI_CHANNEL`

### 编辑器状态管理

可能的问题：
- 编辑器打开但未 `-automated`，模态弹窗中断
- 未保活导致失焦停滞

防护措施：
- `unity open ... --args "-automated"` 标准方式
- `set_autotick` 前置（SKILL.md 注意事项首条）

## 已知局限性

1. **`run_tests` 失败时结果不透明**（上游包行为）：需要窄 filter 重跑或人工查日志定位。
2. **离线包二进制不随 git 分发**：clone 后需经导出包或手动拷贝，缺失时回退在线下载（依赖网络）。
3. **代码重载后端差异**：`reload_file`（`Assembly.Load`）仅支持 Mono——编辑器播放模式与 Mono 桌面
   开发构建，不支持 IL2CPP，且方法体只能访问宿主类型的 public 成员；如需 IL2CPP 或 private 成员，
   改用解释器后端 `reload_file_editor_interpreter` / `reload_file_player_interpreter`（受 C# 子集约束）。
4. **上游包升级会还原本地修复**：SKILL.md 头部 HTML 注释记录了本地改动清单与逐版本同步记录，
   包升级后需对照重放。当前基线为 `com.unity.pipeline@0.7.0-exp.1`。
5. **`wait_for` 同步模式占用命令队列**：条件依赖尚未发出的命令时会自死锁直到超时，长等待须用异步。
