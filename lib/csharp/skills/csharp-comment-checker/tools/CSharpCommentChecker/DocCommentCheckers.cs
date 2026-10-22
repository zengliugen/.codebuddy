using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Text.RegularExpressions;

/// <summary>
/// 文档注释检查器，提供 XML 文档注释（///）的合规性检查方法。
/// 包含注释存在性检测、标签完整性检查、语言检测和语义一致性校验。
/// </summary>
internal static class DocCommentCheckers
{
    /// <summary>
    /// 检查节点是否有文档注释，支持穿透属性列表和预处理器指令定位注释。
    /// </summary>
    /// <param name="node">要检查的语法节点。</param>
    /// <returns>是否有文档注释。</returns>
    public static bool HasDocComment(SyntaxNode node)
    {
        if (HasDocCommentInTrivia(node.GetLeadingTrivia()))
            return true;

        if (node is MemberDeclarationSyntax memberDecl && memberDecl.AttributeLists.Count > 0)
        {
            var firstAttr = memberDecl.AttributeLists[0];
            if (HasDocCommentInTrivia(firstAttr.GetLeadingTrivia()))
                return true;
        }

        return false;
    }

    /// <summary>
    /// 在 Trivia 列表中查找文档注释，支持递归穿透预处理器指令。
    /// 当遇到 #region、#if、#endif 等指令时，递归检查指令内部的前导 trivia。
    /// </summary>
    /// <param name="trivia">Trivia 列表。</param>
    /// <returns>是否包含文档注释。</returns>
    private static bool HasDocCommentInTrivia(SyntaxTriviaList trivia)
    {
        for (var i = 0; i < trivia.Count; i++)
        {
            var t = trivia[i];

            if (t.IsKind(SyntaxKind.WhitespaceTrivia) ||
                t.IsKind(SyntaxKind.EndOfLineTrivia) ||
                t.IsKind(SyntaxKind.SingleLineCommentTrivia) ||
                t.IsKind(SyntaxKind.MultiLineCommentTrivia))
            {
                continue;
            }

            // 递归穿透预处理器指令（#region、#if、#endif 等），处理注释在指令前的情况
            if (t.IsDirective)
            {
                var directive = t.GetStructure();
                if (directive != null && HasDocCommentInTrivia(directive.GetLeadingTrivia()))
                    return true;
                continue;
            }

            if (t.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) ||
                t.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
            {
                // 收集所有连续文档注释的完整文本，判断是否为纯文件头注释
                var sb = new System.Text.StringBuilder();
                var j = i;
                while (j < trivia.Count)
                {
                    var tt = trivia[j];
                    if (!tt.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) &&
                        !tt.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia) &&
                        !tt.IsKind(SyntaxKind.WhitespaceTrivia) &&
                        !tt.IsKind(SyntaxKind.EndOfLineTrivia))
                    {
                        break;
                    }
                    // 仅收集文档注释文本
                    if (tt.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) ||
                        tt.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
                    {
                        var text = tt.ToFullString().Trim();
                        sb.Append(text);
                    }
                    j++;
                }

                var fullDoc = sb.ToString();
                // 仅包含 <file> 而不含 <summary> 的是文件头注释，不视为成员的文档注释
                if (fullDoc.Contains("<file") && !fullDoc.Contains("<summary"))
                    continue;

                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// 获取节点的文档注释文本，支持穿透属性列表和预处理器指令。
    /// </summary>
    /// <param name="node">要检查的语法节点。</param>
    /// <returns>文档注释文本，若不存在则返回 null。</returns>
    public static string? GetDocCommentText(SyntaxNode node)
    {
        var text = GetDocCommentTextFromTrivia(node.GetLeadingTrivia());
        if (text != null)
            return text;

        if (node is MemberDeclarationSyntax memberDecl && memberDecl.AttributeLists.Count > 0)
        {
            var firstAttr = memberDecl.AttributeLists[0];
            return GetDocCommentTextFromTrivia(firstAttr.GetLeadingTrivia());
        }

        return null;
    }

    /// <summary>
    /// 从 Trivia 列表提取文档注释文本，支持递归穿透预处理器指令。
    /// 跳过普通行注释（//）和块注释（/* */），仅返回文档注释（///）。
    /// </summary>
    /// <param name="trivia">Trivia 列表。</param>
    /// <returns>文档注释文本，若不存在则返回 null。</returns>
    private static string? GetDocCommentTextFromTrivia(SyntaxTriviaList trivia)
    {
        for (var i = 0; i < trivia.Count; i++)
        {
            var t = trivia[i];

            if (t.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) ||
                t.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
            {
                // 收集所有连续文档注释的完整文本，判断是否为纯文件头注释
                var sb = new System.Text.StringBuilder();
                var j = i;
                while (j < trivia.Count)
                {
                    var tt = trivia[j];
                    if (!tt.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) &&
                        !tt.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia) &&
                        !tt.IsKind(SyntaxKind.WhitespaceTrivia) &&
                        !tt.IsKind(SyntaxKind.EndOfLineTrivia))
                    {
                        break;
                    }
                    if (tt.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) ||
                        tt.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
                    {
                        sb.Append(tt.ToFullString().Trim());
                    }
                    j++;
                }

                var fullDoc = sb.ToString();
                // 仅包含 <file> 而不含 <summary> 的是文件头注释，跳过
                if (fullDoc.Contains("<file") && !fullDoc.Contains("<summary"))
                    continue;

                return t.ToFullString().Trim();
            }

            // 递归穿透预处理器指令
            if (t.IsDirective)
            {
                var directive = t.GetStructure();
                if (directive != null)
                {
                    var text = GetDocCommentTextFromTrivia(directive.GetLeadingTrivia());
                    if (text != null) return text;
                }
            }

            // 跳过普通注释（// 或 /* */），继续查找文档注释
            if (t.IsKind(SyntaxKind.SingleLineCommentTrivia) ||
                t.IsKind(SyntaxKind.MultiLineCommentTrivia))
            {
                continue;
            }
        }
        return null;
    }

    /// <summary>
    /// 检查节点是否使用了禁止的 /** */ 块注释格式作为文档注释。
    /// 规范要求必须使用 /// 格式。
    /// </summary>
    /// <param name="node">要检查的语法节点。</param>
    /// <returns>是否使用了 /** */ 格式。</returns>
    public static bool HasBlockCommentFormat(SyntaxNode node)
    {
        if (HasBlockCommentInTrivia(node.GetLeadingTrivia()))
            return true;

        if (node is MemberDeclarationSyntax memberDecl && memberDecl.AttributeLists.Count > 0)
        {
            var firstAttr = memberDecl.AttributeLists[0];
            if (HasBlockCommentInTrivia(firstAttr.GetLeadingTrivia()))
                return true;
        }

        return false;
    }

    /// <summary>
    /// 在 Trivia 列表中查找 MultiLineDocumentationCommentTrivia（即 /** */ 格式），
    /// 支持递归穿透预处理器指令。
    /// </summary>
    /// <param name="trivia">Trivia 列表。</param>
    /// <returns>是否包含 /** */ 格式的文档注释。</returns>
    private static bool HasBlockCommentInTrivia(SyntaxTriviaList trivia)
    {
        foreach (var t in trivia)
        {
            if (t.IsKind(SyntaxKind.WhitespaceTrivia) ||
                t.IsKind(SyntaxKind.EndOfLineTrivia) ||
                t.IsKind(SyntaxKind.SingleLineCommentTrivia) ||
                t.IsKind(SyntaxKind.MultiLineCommentTrivia) ||
                t.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia))
            {
                continue;
            }

            // 递归穿透预处理器指令
            if (t.IsDirective)
            {
                var directive = t.GetStructure();
                if (directive != null && HasBlockCommentInTrivia(directive.GetLeadingTrivia()))
                    return true;
                continue;
            }

            // 检测到 /** */ 格式
            if (t.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
                return true;
        }

        return false;
    }

    /// <summary>
    /// 检查文件头注释，对应 file_header 规则。
    /// 检测文件开头是否有 &lt;file&gt; 标签或分隔线格式的文件头注释。
    /// </summary>
    /// <param name="root">编译单元根节点。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="rules">规则配置。</param>
    public static void CheckFileHeader(CompilationUnitSyntax root, string filePath, List<CommentIssue> results, CommentRules rules)
    {
        if (!rules.IsEnabled(RuleNames.FileHeader)) return;

        var firstTrivia = root.GetLeadingTrivia();
        var hasFileHeaderXml = false;
        var hasFileHeaderBlock = false;

        foreach (var trivia in firstTrivia)
        {
            var text = trivia.ToString();
            if (text.Contains("<file>")) hasFileHeaderXml = true;
            if (text.Contains("======") && text.Contains("文件名")) hasFileHeaderBlock = true;
        }

        if (!hasFileHeaderXml && !hasFileHeaderBlock)
        {
            results.Add(new CommentIssue
            {
                File = filePath,
                Line = 1,
                Severity = rules.GetIssueSeverity(RuleNames.FileHeader, IssueCategories.FileHeader),
                Category = IssueCategories.FileHeader,
                RuleName = RuleNames.FileHeader,
                CodeSnippet = "文件开头",
                Member = "",
                MemberType = "",
                Message = "缺少文件头注释（/// <file> 或 // ====== 格式）。"
            });
        }
    }

    /// <summary>
    /// 检查文档注释中的必要标签，基于可配置规则。
    /// 检查 &lt;summary&gt;、&lt;param&gt;、&lt;returns&gt;、&lt;typeparam&gt; 等标签的存在性和完整性。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <param name="docComment">文档注释文本。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="memberName">成员名称。</param>
    /// <param name="memberType">成员类型。</param>
    /// <param name="ruleName">规则名称。</param>
    /// <param name="rules">规则配置。</param>
    public static void CheckDocCommentTags(SyntaxNode node, string? docComment, List<CommentIssue> results, string filePath, string memberName, string memberType, string ruleName, CommentRules rules)
    {
        if (string.IsNullOrWhiteSpace(docComment)) return;

        var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

        // 检查 <summary>
        // 使用 <inheritdoc/> 继承基类注释的成员豁免此检查，与下方的 summary_no_period、param/returns 跳过逻辑保持一致
        if (rules.IsIssueEnabled(ruleName, IssueCategories.MissingSummary))
        {
            if (!docComment.Contains("<summary") && !docComment.Contains("<inheritdoc"))
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(ruleName, IssueCategories.MissingSummary),
                    Category = IssueCategories.MissingSummary,
                    RuleName = ruleName,
                    CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                    Member = memberName,
                    MemberType = memberType,
                    Message = "文档注释缺少 <summary> 标签。"
                });
            }
            else
            {
                if (rules.IsIssueEnabled(ruleName, IssueCategories.SummaryNoPeriod))
                {
                    var summaryMatch = Regex.Match(
                        docComment, @"<summary>\s*(.+?)\s*</summary>", RegexOptions.Singleline);
                    if (summaryMatch.Success)
                    {
                        var summaryText = summaryMatch.Groups[1].Value.Trim();
                        var cleanLines = summaryText
                            .Split('\n')
                            .Select(lineStr => { var t = lineStr.Trim(); return t.StartsWith("///") ? t.Substring(3).TrimStart() : t; })
                            .Where(lineStr => !string.IsNullOrEmpty(lineStr));
                        var cleanSummary = string.Join("", cleanLines).Trim();
                        if (!string.IsNullOrEmpty(cleanSummary) && !cleanSummary.Contains("<inheritdoc") && !cleanSummary.EndsWith("。"))
                        {
                            results.Add(new CommentIssue
                            {
                                File = filePath,
                                Line = line,
                                Severity = rules.GetIssueSeverity(ruleName, IssueCategories.SummaryNoPeriod),
                                Category = IssueCategories.SummaryNoPeriod,
                                RuleName = ruleName,
                                CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                                Member = memberName,
                                MemberType = memberType,
                                Message = "<summary> 标签内容未以句号（。）结尾。"
                            });
                        }
                    }
                }
            }
        }

        if (docComment.Contains("<inheritdoc")) return;

        // 对方法：检查 <param>
        if (node is BaseMethodDeclarationSyntax method)
        {
            if (rules.IsIssueEnabled(ruleName, IssueCategories.MissingParam))
            {
                foreach (var param in method.ParameterList.Parameters)
                {
                    // 取 ValueText 以剥离 @ 转义符：文档注释的 <param name> 须写不带 @ 的标识符（见注释规范 §3.3）
                    var paramName = param.Identifier.ValueText;
                    if (!docComment.Contains($"<param name=\"{paramName}\""))
                    {
                        results.Add(new CommentIssue
                        {
                            File = filePath,
                            Line = line,
                            Severity = rules.GetIssueSeverity(ruleName, IssueCategories.MissingParam),
                            Category = IssueCategories.MissingParam,
                            RuleName = ruleName,
                            CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                            Member = $"{memberName}({paramName})",
                            MemberType = memberType,
                            Message = $"参数 \"{paramName}\" 缺少 <param> 文档注释。"
                        });
                    }
                }
            }

            // 检查 <returns>
            if (method is MethodDeclarationSyntax mds && rules.IsIssueEnabled(ruleName, IssueCategories.MissingReturn))
            {
                if (mds.ReturnType.ToString() != "void" && mds.ReturnType.ToString() != "Void")
                {
                    if (!docComment.Contains("<returns>") && !docComment.Contains("<returns"))
                    {
                        results.Add(new CommentIssue
                        {
                            File = filePath,
                            Line = line,
                            Severity = rules.GetIssueSeverity(ruleName, IssueCategories.MissingReturn),
                            Category = IssueCategories.MissingReturn,
                            RuleName = ruleName,
                            CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                            Member = memberName,
                            MemberType = memberType,
                            Message = "有返回值的方法缺少 <returns> 文档注释。"
                        });
                    }
                }
            }
        }

        // 对泛型：检查 <typeparam>
        if (node is TypeDeclarationSyntax typeDecl && rules.IsIssueEnabled(ruleName, IssueCategories.MissingTypeparam))
        {
            foreach (var tp in typeDecl.TypeParameterList?.Parameters ?? [])
            {
                // 取 ValueText 以剥离 @ 转义符，与文档侧不含 @ 的字面值保持一致
                if (!docComment.Contains($"<typeparam name=\"{tp.Identifier.ValueText}\""))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath,
                        Line = line,
                        Severity = rules.GetIssueSeverity(ruleName, IssueCategories.MissingTypeparam),
                        Category = IssueCategories.MissingTypeparam,
                        RuleName = ruleName,
                        CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                        Member = typeDecl.Identifier.Text,
                        MemberType = memberType,
                        Message = $"类型参数 \"{tp.Identifier.ValueText}\" 缺少 <typeparam> 文档注释。"
                    });
                }
            }
        }
        if (node is MethodDeclarationSyntax methodGen && methodGen.TypeParameterList != null && rules.IsIssueEnabled(ruleName, IssueCategories.MissingTypeparam))
        {
            foreach (var tp in methodGen.TypeParameterList.Parameters)
            {
                // 取 ValueText 以剥离 @ 转义符，与文档侧不含 @ 的字面值保持一致
                if (!docComment.Contains($"<typeparam name=\"{tp.Identifier.ValueText}\""))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath,
                        Line = line,
                        Severity = rules.GetIssueSeverity(ruleName, IssueCategories.MissingTypeparam),
                        Category = IssueCategories.MissingTypeparam,
                        RuleName = ruleName,
                        CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                        Member = methodGen.Identifier.Text,
                        MemberType = memberType,
                        Message = $"类型参数 \"{tp.Identifier.ValueText}\" 缺少 <typeparam> 文档注释。"
                    });
                }
            }
        }
    }

    /// <summary>
    /// 检查注释语言，基于可配置规则。
    /// 注释内容应使用简体中文撰写，技术术语可保留英文。
    /// </summary>
    /// <param name="docComment">文档注释文本。</param>
    /// <param name="node">语法节点。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="memberName">成员名称。</param>
    /// <param name="memberType">成员类型。</param>
    /// <param name="ruleName">规则名称。</param>
    /// <param name="rules">规则配置。</param>
    public static void CheckCommentLanguage(string? docComment, SyntaxNode node, List<CommentIssue> results, string filePath, string memberName, string memberType, string ruleName, CommentRules rules)
    {
        if (string.IsNullOrWhiteSpace(docComment) || docComment.Contains("<inheritdoc")) return;

        if (!rules.IsIssueEnabled(ruleName, IssueCategories.Language)) return;

        var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

        var textOnly = Regex.Replace(
            docComment, @"</?[a-zA-Z][^>]*>", "").Trim();

        var hasChinese = textOnly.Any(ch => ch >= '\u4E00' && ch <= '\u9FFF');

        if (!hasChinese && !string.IsNullOrWhiteSpace(textOnly))
        {
            var remaining = textOnly;
            // 从可配置的规则中读取技术术语白名单（大小写不敏感剥离），
            // 术语表按目标项目常用技术术语维护，见 comment_config.json 的 knownTerms 字段。
            var knownTerms = rules.KnownTerms ?? new List<string>();
            if (knownTerms.Count > 0)
            {
                // 每个术语加左边界（(?<![A-Za-z0-9_])），避免短术语（如 UI、IL、Git）匹配英文单词内部，
                // 同时不约束右边界，保留 AssetBundles 等复数形式的剥离能力。
                var termPattern = string.Join("|",
                    knownTerms.Select(t => $"(?<![A-Za-z0-9_]){Regex.Escape(t)}"));
                remaining = Regex.Replace(remaining, termPattern, "", RegexOptions.IgnoreCase);
            }
            remaining = Regex.Replace(remaining, @"[.,;:!?\s]", "");

            if (remaining.Length > 5)
            {
                results.Add(new CommentIssue
                {
                    File = filePath,
                    Line = line,
                    Severity = rules.GetIssueSeverity(ruleName, IssueCategories.Language),
                    Category = IssueCategories.Language,
                    RuleName = ruleName,
                    CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
                    Member = memberName,
                    MemberType = memberType,
                    Message = "注释内容应使用简体中文撰写（技术术语除外）。"
                });
            }
        }
    }

    /// <summary>
    /// 执行文档注释与代码声明的语义一致性校验，包括参数不匹配、返回值不匹配和类型参数不匹配。
    /// 基于 Roslyn SemanticModel 验证文档注释标签与实际代码符号的一致性。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <param name="docComment">文档注释文本。</param>
    /// <param name="semanticModel">语义模型，用于获取编译期符号信息。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="memberName">成员名称。</param>
    /// <param name="memberType">成员类型。</param>
    /// <param name="ruleName">规则名称。</param>
    /// <param name="rules">规则配置。</param>
    public static void CheckDocCommentConsistency(
        SyntaxNode node, string? docComment,
        SemanticModel? semanticModel,
        List<CommentIssue> results,
        string filePath, string memberName, string memberType,
        string ruleName, CommentRules rules)
    {
        if (string.IsNullOrWhiteSpace(docComment) || semanticModel == null) return;
        var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

        // param_mismatch
        if (node is BaseMethodDeclarationSyntax method)
        {
            var paramMatches = Regex.Matches(docComment, @"<param\s+name=""([^""]+)""");
            var docParamNames = new HashSet<string>(paramMatches.Cast<Match>().Select(m => m.Groups[1].Value));
            // 代码侧取 ValueText 以剥离 @ 转义符，使两侧语义一致（文档侧为不含 @ 的字面值）
            var actualParamNames = new HashSet<string>(method.ParameterList.Parameters.Select(p => p.Identifier.ValueText));
            foreach (var docName in docParamNames)
            {
                if (!actualParamNames.Contains(docName) && rules.IsIssueEnabled(ruleName, IssueCategories.ParamMismatch))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath, Line = line,
                        Severity = rules.GetIssueSeverity(ruleName, IssueCategories.ParamMismatch),
                        Category = IssueCategories.ParamMismatch,
                        RuleName = ruleName,
                        Member = memberName, MemberType = memberType,
                        Message = $"文档注释中存在参数 \"{docName}\" 的 <param> 标签，但实际参数列表中无该参数。",
                        CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(node, "param_mismatch")
                    });
                }
            }

            // returns_mismatch
            if (method is MethodDeclarationSyntax mds)
            {
                var symbol = semanticModel.GetDeclaredSymbol(mds) as IMethodSymbol;
                if (symbol != null && symbol.ReturnsVoid && docComment.Contains("<returns") &&
                    rules.IsIssueEnabled(ruleName, IssueCategories.ReturnsMismatch))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath, Line = line,
                        Severity = rules.GetIssueSeverity(ruleName, IssueCategories.ReturnsMismatch),
                        Category = IssueCategories.ReturnsMismatch,
                        RuleName = ruleName,
                        Member = memberName, MemberType = memberType,
                        Message = "方法返回类型为 void，但文档注释中包含了 <returns> 标签。",
                        CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(node, "returns_mismatch")
                    });
                }
            }
        }

        // typeparam_mismatch
        var tpMatches = Regex.Matches(docComment, @"<typeparam\s+name=""([^""]+)""");
        if (tpMatches.Count > 0)
        {
            var docTpNames = new HashSet<string>(tpMatches.Cast<Match>().Select(m => m.Groups[1].Value));
            // 代码侧取 ValueText 以剥离 @ 转义符，使两侧语义一致（文档侧为不含 @ 的字面值）
            var actualTpNames = new HashSet<string>();
            if (node is TypeDeclarationSyntax typeDecl)
                foreach (var tp in typeDecl.TypeParameterList?.Parameters ?? [])
                    actualTpNames.Add(tp.Identifier.ValueText);
            if (node is MethodDeclarationSyntax methodGen && methodGen.TypeParameterList != null)
                foreach (var tp in methodGen.TypeParameterList.Parameters)
                    actualTpNames.Add(tp.Identifier.ValueText);

            foreach (var docName in docTpNames)
            {
                if (!actualTpNames.Contains(docName) && rules.IsIssueEnabled(ruleName, IssueCategories.TypeparamMismatch))
                {
                    results.Add(new CommentIssue
                    {
                        File = filePath, Line = line,
                        Severity = rules.GetIssueSeverity(ruleName, IssueCategories.TypeparamMismatch),
                        Category = IssueCategories.TypeparamMismatch,
                        RuleName = ruleName,
                        Member = memberName, MemberType = memberType,
                        Message = $"文档注释中存在类型参数 \"{docName}\" 的 <typeparam> 标签，但实际类型参数列表中无该参数。",
                        CodeSnippet = SnippetHelpers.GetInlineCodeSnippet(node, "typeparam_mismatch")
                    });
                }
            }
        }
    }
}
