# 检查范围详情

## 文档注释检查（///）

| 检查项 | 成员类型 | 默认严重程度（可配置） |
|--------|---------|----------------------|
| 缺少 XML 文档注释 | class / interface / struct | error |
| 缺少 XML 文档注释 | enum | error |
| 缺少 XML 文档注释 | enum value | error |
| 缺少 XML 文档注释 | delegate / event | error |
| 缺少 XML 文档注释 | method / constructor / operator | error |
| 缺少 XML 文档注释 | property (public) / field (public) | error |
| 缺少 `<summary>` 标签 | 所有（已有文档注释但缺 `<summary>`） | error |
| `<summary>` 不以句号结尾 | 所有 | warning |
| 缺少 `<param>` 标签 | method / constructor 的参数 | warning |
| 缺少 `<returns>` 标签 | 有返回值的方法 | warning |
| 缺少 `<typeparam>` 标签 | 泛型类型/方法 | warning |
| `<inheritdoc/>` 标记 | override/接口实现成员缺少注释 | info |
| 使用英文而非简体中文 | 注释文本 | warning |
| `<param>` 标签名与实际参数不一致 | method / constructor | warning |
| `<returns>` 存在但方法返回 void | method | warning |
| `<typeparam>` 标签名与实际类型参数不一致 | generic type / method | warning |

> 最后三项为语义一致性检查，基于 Roslyn `SemanticModel` 验证文档注释标签与实际代码的匹配。仅在语义分析可用时生效。

## 行内注释检查（//）

| 检查项 | 触发场景 | 默认严重程度（可配置） |
|--------|---------|----------------------|
| 魔法数字缺行内注释 | 方法体中的字面量常量 | warning |
| 条件分支缺行内注释 | 非显而易见的 if/switch 判断 | warning |
| 循环控制缺行内注释 | for/while 中的 break/continue | warning |
| 算法/数据结构选择缺行内注释 | 非显而易见的数据结构选择 | warning |
| 性能优化缺行内注释 | 对象池/缓存/预分配/位运算 | warning |
| Workaround 缺 HACK: 注释 | 临时方案/框架限制规避 | warning |
| 业务规则缺行内注释 | 硬编码阈值/特殊处理逻辑 | warning |
| 并发/线程安全缺行内注释 | 锁/原子操作/线程调度 | warning |
| 资源管理缺行内注释 | using/try-finally/显式 Dispose | warning |
| null 检查缺行内注释 | 非显而易见的防御性 null 检查 | info |
| 类型转换缺行内注释 | 强制类型转换/as/is 模式匹配 | info |
| 异常处理缺行内注释 | catch 特定异常/吞异常/重抛 | info |
| 代码顺序依赖缺行内注释 | 执行顺序有严格要求 | warning |
| TODO/FIXME 缺注释 | 未完成功能/待修复问题 | info |

> **注意：** 行内注释检查目前仅覆盖方法体（MethodDeclarationSyntax）。构造函数、属性访问器和运算符重载的方法体不会被检查行内注释。

## 文件级别检查

| 检查项 | 默认严重程度（可配置） |
|--------|----------------------|
| 缺少文件头注释 | warning |
| 文件解析错误 | error |
| 位于 Generated/ 或 Gen/ 目录 | 跳过（豁免） |
