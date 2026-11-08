# python-env 执行细则

## 一、快速上手

```
# 判断是否就绪（只读，不安装）
python scripts/env.py check

# 创建或更新工具环境（数秒，可离线）
python scripts/env.py ensure

# 强制重建（环境损坏或需要回到锁定版本时）
python scripts/env.py ensure --force

# 取应用解释器路径（供覆盖率等需要"在项目环境中执行"的场景）
python scripts/env.py python
```

## 二、应用解释器探测

按四级顺序尝试，**每级都校验目标解释器能 `import ok`**：

| 级 | 来源 | 说明 |
|----|------|------|
| 1 | 配置 `app_python` | 非空时优先；相对路径按项目根解析 |
| 2 | 环境变量 `VIRTUAL_ENV` | 当前已激活虚拟环境 |
| 3 | 项目根 `{.venv, venv, env}` | 标准布局的 `Scripts/python.exe` 或 `bin/python` |
| 4 | `py -3.12`（Windows）或 PATH 上的 `python` | 覆盖 CI 场景（CI 不建 `.venv`，解释器在 PATH） |

**为什么每级都校验 `import ok`**：只判断文件存在不够。用一个没装运行依赖的解释器跑
测试，用例会全部跳过，而 `unittest` 对全跳过仍返回退出码 0（实测输出
`OK (skipped=7)`），覆盖率则报 `0%`——看起来像「代码确实没被覆盖」，比报错更难发现。

全失败时的输出会逐级列出失败原因与路径，供后续分析并向用户询问。

## 三、工具环境的构成

| 项 | 取值 | 依据 |
|----|------|------|
| 位置 | `.codebuddy.project/envs/python` | 项目侧、不入库、可重建；与 `.codebuddy/` 分离（引擎可能只读） |
| 解释器版本 | 3.12（锁 minor） | ruff 是独立二进制；coverage 的 cp312 ABI 在 3.12.x 内稳定 |
| 依赖 | ruff、coverage（见锁文件） | 均无传递依赖 |
| 体积 | 约 28MB | 冷缓存创建约 3.6 秒 |

**「不入库」由哪条规则保证**：`.codebuddy.project/envs/.gitignore`（由 `core-init` 生成，
内容 `*` 加 `!/.gitignore`、`!/README.md` 两条反选）。它写在 `envs/` 这一层，
**不依赖**本目录内部那个 `.gitignore`——后者由 uv 自动生成（内容只有 `*`），
属工具产物，删了会在 `ensure --force` 重建时重新出现。

因此修改忽略配置时**只需动 `envs/.gitignore`**，不要去改 `envs/python/.gitignore`，
也不要给它补 `#  目录:` 头注释（`tool-gitignore-layout` 的扫描已按 `pyvenv.cfg`
整枝跳过虚拟环境，不会再报这个问题）。

依赖的**定义与锁定**在引擎包内 `lib/python/envs/`：
`pyproject.toml` 声明、`uv.lock` 锁定（含各平台产物哈希）。本技能只负责物化。

## 四、一致性判定：为什么用 `--locked` 而不是 `--frozen`

| 模式 | 锁与 `pyproject.toml` 不一致时 | 是否可用 |
|------|-------------------------------|---------|
| `--frozen` | **静默退出 0**，不更新也不报错 | 不可用：改了依赖声明却不生效 |
| `--locked` | 退出 1，提示 `the lockfile needs to be updated` | 采用 |
| `--check` | 退出 1 表示环境过期（干跑，不写入） | `check` 子命令使用 |

`check` 子命令即用 `uv sync --check --locked`，因此它验证的是**环境与锁一致**，
而不只是「ruff 文件存在」——装了旧版 ruff 这种情况也能被发现。

## 五、修改依赖的流程

1. 改包内 `lib/python/envs/pyproject.toml`
2. 在该目录执行 `uv lock`（重新生成锁）
3. 提交这两个文件
4. 各项目跑 `env.py ensure` 更新本地实例

**不要**只改锁文件或只改声明——`--locked` 会直接报错拦下。

## 六、环境变量

`ensure` / `check` 内部设置 `UV_PROJECT_ENVIRONMENT` 指向项目侧实例，因此 uv 不会在
引擎包目录内创建 `.venv`（否则会在共享的 submodule 里留下产物）。

## 七、与相邻技能的分工

| 场景 | 用哪个 |
|------|--------|
| 建/更新工具环境、查应用解释器 | 本技能 |
| 跑代码检查 | `python-lint` |
| 跑测试与覆盖率 | `python-test-coverage` |

本技能**不做**安装项目运行依赖——那属项目负责人按上游流程完成。

## 八、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `未找到 uv` | PATH 中无 uv | 安装 uv（单文件可执行） |
| `工具环境与 uv.lock 不一致` | 包内锁文件更新了，或本地被改动 | 跑 `ensure`（必要时 `--force`） |
| `未找到可用的应用解释器` | 项目未建虚拟环境，或环境缺运行依赖 | 按上游流程建环境；或填 `app_python` |
| uv 提示 `Failed to hardlink files` | 缓存与目标在不同磁盘 | 无害（改用复制），可设 `UV_LINK_MODE=copy` 消除提示 |
