using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

/// <summary>
/// 行内注释检查器，提供方法体内部的 // 单行注释合规性检查方法。
/// 包含 14 个具体检查场景，对应 inline-comment-spec.md 规范中的触发场景。
/// </summary>
internal static class InlineCommentCheckers
{
    /// <summary>
    /// 调度所有行内注释检查，对方法体依次执行 14 项行内注释检查。
    /// </summary>
    /// <param name="method">方法声明。</param>
    /// <param name="body">方法体。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="sourceCode">源文件全文。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="rules">规则配置。</param>
    public static void CheckInlineComments(MethodDeclarationSyntax method, BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, CommentRules rules)
    {
        var methodName = method.Identifier.Text;
        var memberType = "method";

        CheckMagicNumbers(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckConditionBranches(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckLoopControl(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckResourceManagement(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckNullChecks(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckTypeCasts(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckExceptions(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckConcurrency(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckAlgorithmSelection(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckPerformanceOptimization(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckTodoFixme(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckWorkaround(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckBusinessRules(body, filePath, sourceCode, results, methodName, memberType, rules);
        CheckOrderDependency(body, filePath, sourceCode, results, methodName, memberType, rules);
    }

    /// <summary>
    /// 检测魔法数字（inline_magic_number，对应 inline-comment-spec.md §2 魔法数字）。
    /// 跳过 0/1/2/-1、循环条件中的数字、数组大小、case 标签和 const 字段初始化。
    /// </summary>
    private static void CheckMagicNumbers(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineMagicNumber)) return;

        var literals = body.DescendantNodes()
            .OfType<LiteralExpressionSyntax>()
            .Where(l => l.IsKind(SyntaxKind.NumericLiteralExpression))
            .Where(l =>
            {
                var value = l.Token.ValueText;
                if (value == "true" || value == "false" || value == "null")
                {
                    return false;
                }

                // 跳过 0-10 范围内的常见小数字（包括 -1），减少误报
                if (int.TryParse(value, out var intValue) && intValue >= -1 && intValue <= 10)
                {
                    return false;
                }

                // 跳过循环条件中的数字（如 for(int i=0; i<3; i++) 中的 3）
                if (l.Parent is BinaryExpressionSyntax binExpr)
                {
                    var ancestor = binExpr.Ancestors().FirstOrDefault(a =>
                        a is ForStatementSyntax || a is WhileStatementSyntax ||
                        a is DoStatementSyntax || a is ForEachStatementSyntax);
                    if (ancestor != null)
                    {
                        // 是循环条件中的比较数字，跳过
                        return false;
                    }
                }

                // 跳过数组创建中的大小
                if (l.Parent is ArrayCreationExpressionSyntax) return false;

                // 跳过 case 标签中的值
                if (l.Parent is CaseSwitchLabelSyntax) return false;

                // 跳过 switch 表达式中的常量模式
                if (l.Parent is ConstantPatternSyntax) return false;

                // 跳过属性赋值中的参数（如 [Range(0, 100)]）
                if (l.Parent is AttributeArgumentSyntax) return false;

                return true;
            });

        foreach (var literal in literals)
        {
            var line = literal.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

            if (!HasPrecedingComment(literal, sourceCode, line))
            {
                // 跳过 const 字段初始化
                if (literal.Parent is EqualsValueClauseSyntax evc &&
                    evc.Parent is VariableDeclaratorSyntax vds &&
                    vds.Parent is VariableDeclarationSyntax vd &&
                    vd.Parent is FieldDeclarationSyntax fieldDecl &&
                    fieldDecl.Modifiers.Any(m => m.IsKind(SyntaxKind.ConstKeyword)))
                {
                    continue;
                }

                // 跳过字段初始化（通常已有名称说明含义）
                if (literal.Parent is EqualsValueClauseSyntax evc2 &&
                    evc2.Parent is VariableDeclaratorSyntax vds2 &&
                    vds2.Parent is VariableDeclarationSyntax vd2 &&
                    vd2.Parent is FieldDeclarationSyntax)
                {
                    continue;
                }

                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineMagicNumber, IssueCategories.InlineMagicNumber),
                    Category = IssueCategories.InlineMagicNumber,
                    RuleName = RuleNames.InlineMagicNumber,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(literal, "magic_number"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = $"方法内存在魔法数字 {literal.Token.ValueText}，缺少行内注释解释含义。"
                });
            }
        }
    }

    /// <summary>
    /// 检查条件分支（inline_condition，对应 inline-comment-spec.md §2 条件分支）。
    /// 仅对非显而易见的 if/switch 判断报告，跳过 null 检查和简单单标识符判断。
    /// </summary>
    private static void CheckConditionBranches(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineCondition)) return;

        // 检查 if 语句
        var ifStatements = body.DescendantNodes().OfType<IfStatementSyntax>();
        foreach (var ifStmt in ifStatements)
        {
            CheckSingleCondition(ifStmt, body, filePath, sourceCode, results, methodName, memberType, rules);
        }

        // 检查 switch 语句
        var switchStatements = body.DescendantNodes().OfType<SwitchStatementSyntax>();
        foreach (var switchStmt in switchStatements)
        {
            var line = switchStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            // 跳过自明 switch（如 switch (state)、switch (value)），分支意图由 case 标签自述，避免误报
            if (IsSimpleExpression(switchStmt.Expression)) continue;
            if (!HasPrecedingComment(switchStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineCondition, IssueCategories.InlineCondition),
                    Category = IssueCategories.InlineCondition,
                    RuleName = RuleNames.InlineCondition,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(switchStmt, "condition"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "switch 语句缺少行内注释解释分支逻辑。"
                });
            }
        }
    }

    /// <summary>
    /// 检查单个 if 条件是否需要行内注释。
    /// </summary>
    private static void CheckSingleCondition(IfStatementSyntax ifStmt, BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        // 自明条件跳过：字面量比较、null 检查、单标识符判断、枚举/常量比较等，无需注释
        if (IsSelfEvident(ifStmt.Condition)) return;

        var line = ifStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

        if (!HasPrecedingComment(ifStmt, sourceCode, line))
        {
            results.Add(new CommentIssue
            {
                File = filePath,
                Line = line,
                Severity = rules.GetIssueSeverity(RuleNames.InlineCondition, IssueCategories.InlineCondition),
                Category = IssueCategories.InlineCondition,
                RuleName = RuleNames.InlineCondition,
                CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(ifStmt, "condition"),
                Member = methodName,
                MemberType = memberType,
                Message = "非显而易见的条件分支缺少行内注释解释判断意图。"
            });
        }
    }

    /// <summary>
    /// 检查循环提前退出（inline_loop_control，对应 inline-comment-spec.md §2 循环控制）。
    /// 检测循环中的 break、continue、return 提前退出语句是否缺少行内注释。
    /// </summary>
    private static void CheckLoopControl(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineLoopControl)) return;

        // 检测循环内的 break（向上查找祖先循环，处理 if 嵌套 break 的情况）
        var breaksInLoops = body.DescendantNodes()
            .OfType<BreakStatementSyntax>()
            .Where(b => b.Ancestors().Any(a =>
                a is ForStatementSyntax || a is WhileStatementSyntax ||
                a is ForEachStatementSyntax || a is DoStatementSyntax));

        foreach (var breakStmt in breaksInLoops)
        {
            // 跳过自明守卫的提前退出（如 if (x == null) break;），无需注释
            if (IsSelfEvidentGuardExit(breakStmt)) continue;

            var line = breakStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(breakStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineLoopControl, IssueCategories.InlineLoopControl),
                    Category = IssueCategories.InlineLoopControl,
                    RuleName = RuleNames.InlineLoopControl,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(breakStmt, "loop_control"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "循环中提前退出（break）缺少行内注释解释原因。"
                });
            }
        }

        // 检测循环内的 continue
        var continuesInLoops = body.DescendantNodes()
            .OfType<ContinueStatementSyntax>()
            .Where(c => c.Ancestors().Any(a =>
                a is ForStatementSyntax || a is WhileStatementSyntax ||
                a is ForEachStatementSyntax || a is DoStatementSyntax));

        foreach (var continueStmt in continuesInLoops)
        {
            // 跳过自明守卫的提前退出（如 if (item == null) continue;），无需注释
            if (IsSelfEvidentGuardExit(continueStmt)) continue;

            var line = continueStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(continueStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineLoopControl, IssueCategories.InlineLoopControl),
                    Category = IssueCategories.InlineLoopControl,
                    RuleName = RuleNames.InlineLoopControl,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(continueStmt, "loop_control"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "循环中提前退出（continue）缺少行内注释解释原因。"
                });
            }
        }

        // 检测循环内的 return
        var returnsInLoops = body.DescendantNodes()
            .OfType<ReturnStatementSyntax>()
            .Where(r => r.Expression != null &&
                        r.Ancestors().Any(a =>
                            a is ForStatementSyntax || a is WhileStatementSyntax ||
                            a is ForEachStatementSyntax || a is DoStatementSyntax) &&
                        !r.Ancestors().TakeWhile(a => !(a is ForStatementSyntax || a is WhileStatementSyntax ||
                                                         a is ForEachStatementSyntax || a is DoStatementSyntax))
                            .Any(a => a is AnonymousFunctionExpressionSyntax || a is LocalFunctionStatementSyntax));

        foreach (var returnStmt in returnsInLoops)
        {
            // 跳过自明守卫的提前退出（如 if (x != null) return x;），无需注释
            if (IsSelfEvidentGuardExit(returnStmt)) continue;

            var line = returnStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(returnStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineLoopControl, IssueCategories.InlineLoopControl),
                    Category = IssueCategories.InlineLoopControl,
                    RuleName = RuleNames.InlineLoopControl,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(returnStmt, "loop_control"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "循环中提前退出（return）缺少行内注释解释原因。"
                });
            }
        }
    }

    /// <summary>
    /// 检查资源管理（inline_resource，对应 inline-comment-spec.md §2 资源管理）。
    /// 仅检测 try-finally 中的显式 Dispose() 调用，忽略标准 using 语句。
    /// </summary>
    private static void CheckResourceManagement(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineResource)) return;

        // 仅检测 try-finally 中的显式 Dispose 调用（非标准 using 包装的资源释放）
        var tryFinallyBlocks = body.DescendantNodes()
            .OfType<TryStatementSyntax>()
            .Where(t => t.Finally != null);

        foreach (var tryStmt in tryFinallyBlocks)
        {
            // 检查 finally 块中是否有 Dispose 调用
            if (tryStmt.Finally == null) continue;
            var hasDispose = tryStmt.Finally.Block.DescendantNodes()
                .OfType<InvocationExpressionSyntax>()
                .Any(i => i.Expression.ToString().EndsWith(".Dispose"));
            if (!hasDispose) continue;

            var line = tryStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(tryStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineResource, IssueCategories.InlineResource),
                    Category = IssueCategories.InlineResource,
                    RuleName = RuleNames.InlineResource,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(tryStmt, "resource"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "try-finally 中的资源释放（Dispose）缺少行内注释解释为何需要显式释放。"
                });
            }
        }
    }

    /// <summary>
    /// 检测非显而易见的 null 检查（inline_null_check，对应 inline-comment-spec.md §2 空值检查）。
    /// 跳过方法体前几行的参数校验代码。
    /// </summary>
    private static void CheckNullChecks(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineNullCheck)) return;

        var bodyStartLine = body.GetLocation().GetLineSpan().StartLinePosition.Line;

        var nullCheckNodes = body.DescendantNodes().OfType<BinaryExpressionSyntax>()
            .Where(b => b.IsKind(SyntaxKind.EqualsExpression) || b.IsKind(SyntaxKind.NotEqualsExpression))
            .Where(b =>
            {
                // 仅检测一侧为 null 字面量的比较
                ExpressionSyntax? operand = null;
                if (b.Left.IsKind(SyntaxKind.NullLiteralExpression)) operand = b.Right;
                else if (b.Right.IsKind(SyntaxKind.NullLiteralExpression)) operand = b.Left;
                if (operand == null) return false;

                var line = b.GetLocation().GetLineSpan().StartLinePosition.Line;
                // 跳过方法体前 5 行（通常是参数校验）
                if (line - bodyStartLine <= 5) return false;

                // 跳过简单表达式的 null 检查（如 obj == null / this.data != null），属显而易见的防御性判空
                return !IsSimpleExpression(operand);
            });

        foreach (var node in nullCheckNodes)
        {
            var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(node, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineNullCheck, IssueCategories.InlineNullCheck),
                    Category = IssueCategories.InlineNullCheck,
                    RuleName = RuleNames.InlineNullCheck,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(node, "null_check"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "非显而易见的 null 检查缺少行内注释解释防御原因。"
                });
            }
        }
    }

    /// <summary>
    /// 检测强制类型转换（inline_type_cast，对应 inline-comment-spec.md §2 类型转换）。
    /// 同时检查 as 转换和显式 (Type) 强制转换。
    /// </summary>
    private static void CheckTypeCasts(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineTypeCast)) return;

        // 检测 as 转换：仅当 as 结果未在下一行进行 null 检查时才报告
        var asExpressions = body.DescendantNodes().OfType<BinaryExpressionSyntax>()
            .Where(b => b.IsKind(SyntaxKind.AsExpression));
        foreach (var asExpr in asExpressions)
        {
            var line = asExpr.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            var lines = sourceCode.Split('\n');
            var idx = line;
            if (idx < lines.Length)
            {
                var nextLine = lines[idx].Trim();
                if (nextLine.Contains("== null") || nextLine.Contains("!= null") || nextLine.Contains("is "))
                    continue;
            }

            if (!HasPrecedingComment(asExpr, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineTypeCast, IssueCategories.InlineTypeCast),
                    Category = IssueCategories.InlineTypeCast,
                    RuleName = RuleNames.InlineTypeCast,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(asExpr, "type_cast"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "强制类型转换（as）缺少行内注释解释转换的安全性。"
                });
            }
        }

        // 检测显式 (Type) 强制转换
        var castExpressions = body.DescendantNodes().OfType<CastExpressionSyntax>();
        foreach (var castExpr in castExpressions)
        {
            var line = castExpr.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(castExpr, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineTypeCast, IssueCategories.InlineTypeCast),
                    Category = IssueCategories.InlineTypeCast,
                    RuleName = RuleNames.InlineTypeCast,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(castExpr, "type_cast"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "强制类型转换（显式转换）缺少行内注释解释转换的安全性。"
                });
            }
        }
    }

    /// <summary>
    /// 检测异常处理（inline_exception，对应 inline-comment-spec.md §2 异常处理）。
    /// 跳过空 catch 块和简单重抛。
    /// </summary>
    private static void CheckExceptions(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineException)) return;

        var catchClauses = body.DescendantNodes().OfType<CatchClauseSyntax>();
        foreach (var catchClause in catchClauses)
        {
            var line = catchClause.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

            if (catchClause.Block == null) continue;
            var catchStatements = catchClause.Block.Statements;
            if (catchStatements.Count == 0) continue;
            if (catchStatements.Count == 1 && catchStatements[0] is ThrowStatementSyntax) continue;

            if (!HasPrecedingComment(catchClause, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineException, IssueCategories.InlineException),
                    Category = IssueCategories.InlineException,
                    RuleName = RuleNames.InlineException,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(catchClause, "exception"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "异常处理（catch 块）缺少行内注释解释为何捕获此异常。"
                });
            }
        }
    }

    /// <summary>
    /// 检测并发/线程安全（inline_concurrency，对应 inline-comment-spec.md §2 并发/线程安全）。
    /// 检测 lock 语句和 Interlocked 操作。
    /// </summary>
    private static void CheckConcurrency(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineConcurrency)) return;

        // 检测 lock 语句
        var lockStatements = body.DescendantNodes().OfType<LockStatementSyntax>();
        foreach (var lockStmt in lockStatements)
        {
            var line = lockStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(lockStmt, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineConcurrency, IssueCategories.InlineConcurrency),
                    Category = IssueCategories.InlineConcurrency,
                    RuleName = RuleNames.InlineConcurrency,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(lockStmt, "concurrency"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "并发同步（lock 语句）缺少行内注释解释为何需要同步。"
                });
            }
        }

        // 检测 Interlocked 操作
        var interlockedCalls = body.DescendantNodes().OfType<InvocationExpressionSyntax>()
            .Where(i => i.Expression.ToString().StartsWith("Interlocked."));
        foreach (var call in interlockedCalls)
        {
            var line = call.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(call, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineConcurrency, IssueCategories.InlineConcurrency),
                    Category = IssueCategories.InlineConcurrency,
                    RuleName = RuleNames.InlineConcurrency,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(call, "concurrency"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "线程安全操作（Interlocked）缺少行内注释解释同步原因。"
                });
            }
        }
    }

    /// <summary>
    /// 检测算法/数据结构选择（inline_algorithm，对应 inline-comment-spec.md §2 算法选择）。
    /// 默认禁用，因为启发式难以准确判断数据结构选择意图。
    /// </summary>
    private static void CheckAlgorithmSelection(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineAlgorithm)) return;

        var algorithmTypes = new[] { "Dictionary<", "HashSet<", "SortedDictionary<", "SortedSet<",
            "Queue<", "Stack<", "ConcurrentDictionary<", "LinkedList<" };

        var variableDecls = body.DescendantNodes().OfType<LocalDeclarationStatementSyntax>();
        foreach (var decl in variableDecls)
        {
            var declText = decl.Declaration.Type.ToString();
            if (!algorithmTypes.Any(t => declText.Contains(t))) continue;

            var line = decl.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(decl, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineAlgorithm, IssueCategories.InlineAlgorithm),
                    Category = IssueCategories.InlineAlgorithm,
                    RuleName = RuleNames.InlineAlgorithm,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(decl, "algorithm"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = $"使用特定数据结构（{declText}）缺少行内注释解释选择原因。"
                });
            }
        }
    }

    /// <summary>
    /// 检测性能优化（inline_performance，对应 inline-comment-spec.md §2 性能优化）。
    /// 检测循环内 StringBuilder 使用和集合预分配（capacity >= 64）。
    /// </summary>
    private static void CheckPerformanceOptimization(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlinePerformance)) return;

        // 检测循环内的 StringBuilder 使用
        var loops = body.DescendantNodes()
            .Where(n => n is ForStatementSyntax || n is WhileStatementSyntax || n is ForEachStatementSyntax || n is DoStatementSyntax);
        foreach (var loop in loops)
        {
            var sbNodes = loop.DescendantNodes().OfType<ObjectCreationExpressionSyntax>()
                .Where(o => o.Type.ToString().Contains("StringBuilder"));
            foreach (var sb in sbNodes)
            {
                var line = sb.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
                if (!HasPrecedingComment(sb, sourceCode, line))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath,
                        Line = line,
                        Severity = rules.GetIssueSeverity(RuleNames.InlinePerformance, IssueCategories.InlinePerformance),
                        Category = IssueCategories.InlinePerformance,
                        RuleName = RuleNames.InlinePerformance,
                        CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(sb, "performance"),
                        Member = methodName,
                        MemberType = memberType,
                        Message = "循环中使用 StringBuilder 缺少行内注释解释为何不用字符串拼接。"
                    });
                }
            }
        }

        // 检测带 capacity 的集合预分配（仅当 capacity 为字面量 >= 64 时报告）
        var objectCreations = body.DescendantNodes().OfType<ObjectCreationExpressionSyntax>()
            .Where(o => o.ArgumentList != null && o.ArgumentList.Arguments.Count > 0)
            .Where(o => o.Type.ToString().Contains("List<") || o.Type.ToString().Contains("Dictionary<"))
            .Where(o =>
            {
                var args = o.ArgumentList!.Arguments;
                var firstArg = args[0].Expression;
                if (firstArg is LiteralExpressionSyntax literal &&
                    literal.IsKind(SyntaxKind.NumericLiteralExpression) &&
                    int.TryParse(literal.Token.ValueText, out var capacity))
                {
                    // 仅当 capacity >= 64 时才报告
                    return capacity >= 64;
                }
                return false;
            });

        foreach (var creation in objectCreations)
        {
            var line = creation.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(creation, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlinePerformance, IssueCategories.InlinePerformance),
                    Category = IssueCategories.InlinePerformance,
                    RuleName = RuleNames.InlinePerformance,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(creation, "performance"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "集合预分配容量缺少行内注释解释优化原因。"
                });
            }
        }
    }

    /// <summary>
    /// 检测 TODO/FIXME（inline_todo_fixme，对应 inline-comment-spec.md §2 TODO/FIXME）。
    /// 检测 throw new NotImplementedException 且无 TODO:/FIXME: 注释的情况。
    /// </summary>
    private static void CheckTodoFixme(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineTodoFixme)) return;

        var throwStmts = body.DescendantNodes().OfType<ThrowStatementSyntax>()
            .Where(t => t.Expression != null && t.Expression.ToString().Contains("NotImplementedException"));
        foreach (var throwStmt in throwStmts)
        {
            var line = throwStmt.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            var lines = sourceCode.Split('\n');
            var idx = line - 1;
            var hasTodoComment = false;
            for (int i = Math.Max(0, idx - 3); i < idx; i++)
            {
                if (lines[i].Trim().StartsWith("//") &&
                    (lines[i].Contains("TODO:") || lines[i].Contains("TODO") ||
                     lines[i].Contains("FIXME:") || lines[i].Contains("FIXME")))
                {
                    hasTodoComment = true;
                    break;
                }
            }

            if (!hasTodoComment)
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineTodoFixme, IssueCategories.InlineTodoFixme),
                    Category = IssueCategories.InlineTodoFixme,
                    RuleName = RuleNames.InlineTodoFixme,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(throwStmt, "todo_fixme"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "抛出 NotImplementedException 处缺少 TODO: 或 FIXME: 注释说明待办内容。"
                });
            }
        }
    }

    /// <summary>
    /// 检测 Workaround（inline_workaround，对应 inline-comment-spec.md §2 Workaround）。
    /// 检测 catch(Exception) 吞异常和 #if 条件编译块未标注 HACK: 注释。
    /// </summary>
    private static void CheckWorkaround(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineWorkaround)) return;

        // 检测 catch(Exception) 吞异常：catch 所有异常但无重抛，且无 HACK: 注释
        var catchAllClauses = body.DescendantNodes().OfType<CatchClauseSyntax>()
            .Where(c => c.Declaration == null || c.Declaration.Type.ToString() == "Exception");
        foreach (var catchClause in catchAllClauses)
        {
            if (catchClause.Block == null) continue;
            var hasRethrow = catchClause.Block.Statements.Any(s => s is ThrowStatementSyntax);
            if (hasRethrow) continue;

            var line = catchClause.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            var lines = sourceCode.Split('\n');
            var idx = line - 1;
            var hasHackComment = false;
            for (int i = Math.Max(0, idx - 3); i <= idx; i++)
            {
                if (i < lines.Length && lines[i].Trim().StartsWith("//") && lines[i].Contains("HACK:"))
                {
                    hasHackComment = true;
                    break;
                }
            }

            if (!hasHackComment)
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineWorkaround, IssueCategories.InlineWorkaround),
                    Category = IssueCategories.InlineWorkaround,
                    RuleName = RuleNames.InlineWorkaround,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(catchClause, "workaround"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = "捕获所有异常（catch Exception）未标注 HACK: 注释说明规避原因。"
                });
            }
        }

        // 检测 #if 条件编译块：无 HACK: 注释
        var bodyStartLine = body.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
        var bodyEndLine = body.GetLocation().GetLineSpan().EndLinePosition.Line + 1;
        var sourceLines = sourceCode.Split('\n');
        for (int i = bodyStartLine - 1; i < bodyEndLine && i < sourceLines.Length; i++)
        {
            var trimmed = sourceLines[i].Trim();
            if (trimmed.StartsWith("#if ") && !trimmed.StartsWith("#if UNITY_EDITOR") && !trimmed.StartsWith("#if UNITY"))
            {
                var hasHackNearby = false;
                for (int j = Math.Max(0, i - 2); j <= Math.Min(sourceLines.Length - 1, i + 1); j++)
                {
                    if (sourceLines[j].Trim().StartsWith("//") && sourceLines[j].Contains("HACK:"))
                    {
                        hasHackNearby = true;
                        break;
                    }
                }
                if (!hasHackNearby)
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath,
                        Line = i + 1,
                        Severity = rules.GetIssueSeverity(RuleNames.InlineWorkaround, IssueCategories.InlineWorkaround),
                        Category = IssueCategories.InlineWorkaround,
                        RuleName = RuleNames.InlineWorkaround,
                        CodeSnippet = sourceLines[i].Trim(),
                        Member = methodName,
                        MemberType = memberType,
                        Message = "条件编译块（#if）未标注 HACK: 注释说明规避原因。"
                    });
                }
            }
        }
    }

    /// <summary>
    /// 检测业务规则（inline_business_rule，对应 inline-comment-spec.md §2 业务规则）。
    /// 专注于比较表达式中的阈值字面量，与 CheckMagicNumbers 互补（后者处理独立字面量）。
    /// </summary>
    private static void CheckBusinessRules(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineBusinessRule)) return;

        var numericNodes = body.DescendantNodes().OfType<LiteralExpressionSyntax>()
            .Where(l => l.IsKind(SyntaxKind.NumericLiteralExpression))
            .Where(l =>
            {
                var parent = l.Parent;
                // 检测出现在比较表达式中的数字（如 if (count > 10)）
                return parent is BinaryExpressionSyntax &&
                       (parent.IsKind(SyntaxKind.GreaterThanExpression) ||
                        parent.IsKind(SyntaxKind.GreaterThanOrEqualExpression) ||
                        parent.IsKind(SyntaxKind.LessThanExpression) ||
                        parent.IsKind(SyntaxKind.LessThanOrEqualExpression));
            })
            .Where(l =>
            {
                var value = l.Token.ValueText;
                return value != "0" && value != "1" && value != "2" && value != "-1";
            });

        foreach (var literal in numericNodes)
        {
            var line = literal.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            if (!HasPrecedingComment(literal, sourceCode, line))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(RuleNames.InlineBusinessRule, IssueCategories.InlineBusinessRule),
                    Category = IssueCategories.InlineBusinessRule,
                    RuleName = RuleNames.InlineBusinessRule,
                    CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(literal, "business_rule"),
                    Member = methodName,
                    MemberType = memberType,
                    Message = $"比较中的阈值 {literal.Token.ValueText} 缺少行内注释解释业务含义。"
                });
            }
        }
    }

    /// <summary>
    /// 检测顺序依赖（inline_order，对应 inline-comment-spec.md §2 顺序依赖）。
    /// 默认禁用，因为静态分析无法准确判断代码顺序依赖关系。
    /// </summary>
    private static void CheckOrderDependency(BlockSyntax body, string filePath, string sourceCode, List<CommentIssue> results, string methodName, string memberType, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.InlineOrder)) return;

        var statements = body.Statements;
        var consecutiveCount = 0;
        var consecutiveStartLine = 0;
        var hasCommentInGroup = false;
        var lineMap = new Dictionary<int, bool>();

        foreach (var stmt in statements)
        {
            var line = stmt.GetLocation().GetLineSpan().StartLinePosition.Line;
            var text = stmt.GetLeadingTrivia().ToString();
            var hasComment = text.Contains("//");

            if (lineMap.Count > 0)
            {
                var lastLine = lineMap.Keys.Max();
                if (line == lastLine + 1 || line == lastLine + 2)
                {
                    if (consecutiveCount == 0) consecutiveStartLine = line;
                    consecutiveCount++;
                    if (hasComment) hasCommentInGroup = true;
                }
                else
                {
                    if (consecutiveCount >= 3 && !hasCommentInGroup)
                    {
                        results.Add(new CommentIssue
                        {
                            File = filePath,
                            Line = consecutiveStartLine + 1,
                            Severity = rules.GetIssueSeverity(RuleNames.InlineOrder, IssueCategories.InlineOrder),
                            Category = IssueCategories.InlineOrder,
                            RuleName = RuleNames.InlineOrder,
                            CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(stmt, "order"),
                            Member = methodName,
                            MemberType = memberType,
                            Message = "连续多行密集语句缺少行内注释说明执行顺序逻辑。"
                        });
                    }
                    consecutiveCount = 1;
                    consecutiveStartLine = line;
                    hasCommentInGroup = hasComment;
                }
            }
            else
            {
                consecutiveCount = 1;
                consecutiveStartLine = line;
                hasCommentInGroup = hasComment;
            }
            lineMap[line] = hasComment;
        }

        if (consecutiveCount >= 3 && !hasCommentInGroup)
        {
            results.Add(new CommentIssue
            {
                File = filePath,
                Line = consecutiveStartLine + 1,
                Severity = rules.GetIssueSeverity(RuleNames.InlineOrder, IssueCategories.InlineOrder),
                Category = IssueCategories.InlineOrder,
                RuleName = RuleNames.InlineOrder,
                CodeSnippet = "",
                Member = methodName,
                MemberType = memberType,
                Message = "连续多行密集语句缺少行内注释说明执行顺序逻辑。"
            });
        }
    }

    /// <summary>
    /// 检查节点前是否有注释（上方一行或同级前导）。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <param name="sourceCode">源文件全文。</param>
    /// <param name="line">行号（1-based）。</param>
    /// <returns>是否有前导注释。</returns>
    private static bool HasPrecedingComment(SyntaxNode node, string sourceCode, int line)
    {
        // 检查前导语法中的单行注释
        var prevTrivia = node.GetLeadingTrivia();
        if (prevTrivia.Any(t => t.IsKind(SyntaxKind.SingleLineCommentTrivia) || t.IsKind(SyntaxKind.MultiLineCommentTrivia)))
            return true;

        // 检查源码中前一行
        var lines = sourceCode.Split('\n');
        var idx = line - 1;
        if (idx > 0 && lines[idx - 1].Trim().StartsWith("//"))
            return true;

        return false;
    }

    /// <summary>
    /// 判断条件表达式是否"自明"，即无需行内注释也能理解判断意图。
    /// 自明条件包括：字面量/null/字符串比较、0-10 小数字大小比较、单标识符判断、
    /// 单层成员访问、枚举/常量比较、is 模式匹配、方法调用（方法名自述判断意图）、
    /// 以及由上述自明判断组成的逻辑组合（不含数值大小比较）。
    /// 用于降低 inline_condition 等启发式规则的误报率。
    /// </summary>
    /// <param name="condition">条件表达式。</param>
    /// <returns>条件是否自明。</returns>
    private static bool IsSelfEvident(ExpressionSyntax condition)
    {
        // 括号包裹的表达式：剥掉括号后递归判断（如 excludeGenerated && (A || B)）
        if (condition is ParenthesizedExpressionSyntax paren)
        {
            return IsSelfEvident(paren.Expression);
        }

        // 逻辑非：!x → 递归判断操作数
        if (condition is PrefixUnaryExpressionSyntax pre && pre.IsKind(SyntaxKind.LogicalNotExpression))
        {
            return IsSelfEvident(pre.Operand);
        }

        // 二元表达式
        if (condition is BinaryExpressionSyntax bin)
        {
            var kind = bin.Kind();
            // is 类型检查（obj is string）：意图由表达式本身表达，视为自明
            if (kind == SyntaxKind.IsExpression) return true;
            // 相等/不等比较：任一侧为字面量（null、数字、字符串、bool），或两侧均为自明操作数
            if (kind == SyntaxKind.EqualsExpression || kind == SyntaxKind.NotEqualsExpression)
            {
                if (IsLiteralOrNull(bin.Left) || IsLiteralOrNull(bin.Right)) return true;
                return IsSelfEvidentOperand(bin.Left) && IsSelfEvidentOperand(bin.Right);
            }
            // 大小比较：仅任一侧为 0-10 范围内的小数字（如 count > 0、x < 5）时才自明，
            // 较大阈值（如 hp &gt; 100）可能蕴含业务含义，仍报告
            if (kind == SyntaxKind.GreaterThanExpression || kind == SyntaxKind.GreaterThanOrEqualExpression ||
                kind == SyntaxKind.LessThanExpression || kind == SyntaxKind.LessThanOrEqualExpression)
            {
                return IsSmallNumericLiteral(bin.Left) || IsSmallNumericLiteral(bin.Right);
            }
            // 逻辑与/或：所有分支均为非数值比较的自明判断时才自明
            // （如 arg == "--json" || arg == "--config"；但 x > 10 && y < 5 仍报告）
            if (kind == SyntaxKind.LogicalAndExpression || kind == SyntaxKind.LogicalOrExpression)
            {
                return IsSelfEvidentLogic(bin.Left) && IsSelfEvidentLogic(bin.Right);
            }
            return false;
        }

        // is 模式匹配（x is not null、e is T v 等），意图由模式本身表达
        if (condition is IsPatternExpressionSyntax) return true;

        // 方法调用：方法名自述判断意图（如 File.Exists、string.IsNullOrWhiteSpace、list.Any）
        if (condition is InvocationExpressionSyntax) return true;

        // 简单表达式：单标识符 / this 引用 / 单层成员访问（bool 标志直接判断等）
        return IsSimpleExpression(condition);
    }

    /// <summary>
    /// 判断逻辑组合（&amp;&amp;/||）的分支是否为自明判断。
    /// 数值大小比较分支：任一侧为 0-10 小数字（如 Count &gt; 0、idx &lt; 5）视为自明；
    /// 大数字阈值（如 x &gt; 100）仍可能蕴含业务含义，使组合条件不自明。
    /// 其余自明判断（字面量比较、null 检查、方法调用、标识符等）组合时仍视为自明。
    /// </summary>
    /// <param name="expr">逻辑分支表达式。</param>
    /// <returns>分支是否为自明判断。</returns>
    private static bool IsSelfEvidentLogic(ExpressionSyntax expr)
    {
        // 剥掉括号后判断数值大小比较，防止括号包裹的阈值比较被误判
        var unparenthesized = expr;
        while (unparenthesized is ParenthesizedExpressionSyntax p) unparenthesized = p.Expression;
        if (unparenthesized is BinaryExpressionSyntax bin &&
            (bin.IsKind(SyntaxKind.GreaterThanExpression) ||
             bin.IsKind(SyntaxKind.GreaterThanOrEqualExpression) ||
             bin.IsKind(SyntaxKind.LessThanExpression) ||
             bin.IsKind(SyntaxKind.LessThanOrEqualExpression)))
        {
            return IsSmallNumericLiteral(bin.Left) || IsSmallNumericLiteral(bin.Right);
        }
        return IsSelfEvident(expr);
    }

    /// <summary>
    /// 判断表达式是否为自明的比较操作数：简单表达式、字面量或方法调用。
    /// </summary>
    /// <param name="expr">操作数表达式。</param>
    /// <returns>是否为自明操作数。</returns>
    private static bool IsSelfEvidentOperand(ExpressionSyntax expr)
    {
        return IsSimpleExpression(expr) ||
               expr is LiteralExpressionSyntax ||
               expr is InvocationExpressionSyntax;
    }

    /// <summary>
    /// 判断表达式是否为简单表达式：单标识符、this 引用或单层成员访问（不深入多级链）。
    /// 如 flag、this.isReady、results.Count 为简单表达式；a.b.c、GetValue() 为非简单表达式。
    /// </summary>
    /// <param name="expr">表达式。</param>
    /// <returns>是否为简单表达式。</returns>
    private static bool IsSimpleExpression(ExpressionSyntax expr)
    {
        // 单标识符（局部变量、参数、字段名）
        if (expr is IdentifierNameSyntax) return true;
        // this 引用
        if (expr is ThisExpressionSyntax) return true;
        // 单层成员访问：this.flag / obj.flag（不深入 obj.A.B 多级链）
        if (expr is MemberAccessExpressionSyntax member)
        {
            return member.Expression is IdentifierNameSyntax || member.Expression is ThisExpressionSyntax;
        }
        return false;
    }

    /// <summary>
    /// 判断表达式是否为字面量或 null 关键字（数字、字符串、字符、bool、null）。
    /// </summary>
    /// <param name="expr">表达式。</param>
    /// <returns>是否为字面量或 null。</returns>
    private static bool IsLiteralOrNull(ExpressionSyntax expr)
    {
        return expr is LiteralExpressionSyntax literal &&
               (literal.IsKind(SyntaxKind.NullLiteralExpression) ||
                literal.IsKind(SyntaxKind.TrueLiteralExpression) ||
                literal.IsKind(SyntaxKind.FalseLiteralExpression) ||
                literal.IsKind(SyntaxKind.StringLiteralExpression) ||
                literal.IsKind(SyntaxKind.CharacterLiteralExpression) ||
                literal.IsKind(SyntaxKind.NumericLiteralExpression));
    }

    /// <summary>
    /// 判断表达式是否为 0-10 范围内（含 -1）的数字字面量。
    /// 与魔法数字规则"跳过 0-10 小数字"的约定保持一致。
    /// </summary>
    /// <param name="expr">表达式。</param>
    /// <returns>是否为 0-10 范围内的小数字字面量。</returns>
    private static bool IsSmallNumericLiteral(ExpressionSyntax expr)
    {
        return expr is LiteralExpressionSyntax literal &&
               literal.IsKind(SyntaxKind.NumericLiteralExpression) &&
               int.TryParse(literal.Token.ValueText, out var value) &&
               value >= -1 && value <= 10;
    }

    /// <summary>
    /// 判断退出语句（break/continue/return）是否位于"自明守卫 if"的单语句体中。
    /// 如 if (item == null) continue;、if (x != null) return x; 这类无需注释的防御性退出。
    /// </summary>
    /// <param name="exitStmt">循环退出语句。</param>
    /// <returns>是否为自明守卫的提前退出。</returns>
    private static bool IsSelfEvidentGuardExit(StatementSyntax exitStmt)
    {
        // 向上查找最近的 if 祖先；若先遇到循环/switch/else 边界则说明不是简单守卫
        IfStatementSyntax? guardIf = null;
        foreach (var ancestor in exitStmt.Ancestors())
        {
            if (ancestor is IfStatementSyntax ifStmt)
            {
                guardIf = ifStmt;
                break;
            }
            if (ancestor is ForStatementSyntax || ancestor is WhileStatementSyntax ||
                ancestor is DoStatementSyntax || ancestor is ForEachStatementSyntax ||
                ancestor is SwitchStatementSyntax || ancestor is SwitchSectionSyntax ||
                ancestor is ElseClauseSyntax)
            {
                return false;
            }
        }
        if (guardIf == null) return false;

        // if 体必须仅包含这一个退出语句（简单守卫，如 if (x == null) continue;）
        if (guardIf.Statement is BlockSyntax block)
        {
            if (block.Statements.Count != 1 || block.Statements[0] != exitStmt) return false;
        }
        else if (guardIf.Statement != exitStmt)
        {
            return false;
        }

        // 守卫条件必须自明（字面量比较、null 检查、单标识符判断等）
        return IsSelfEvident(guardIf.Condition);
    }
}
