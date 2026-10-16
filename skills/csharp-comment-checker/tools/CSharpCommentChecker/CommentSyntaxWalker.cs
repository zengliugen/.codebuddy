using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

/// <summary>
/// 注释语法树遍历器，使用 Roslyn SyntaxWalker 遍历 C# 语法树并触发各类型成员的注释检查。
/// 同时负责文档注释检查和行内注释检查的调度。
/// </summary>
internal class CommentSyntaxWalker : CSharpSyntaxWalker
{
    private readonly CommentChecker _checker;
    private readonly List<CommentIssue> _results;
    private readonly string _filePath;
    private readonly string _sourceCode;
    private readonly CommentRules _rules;

    /// <summary>
    /// 初始化语法树遍历器。
    /// </summary>
    /// <param name="checker">关联的注释检查器实例。</param>
    /// <param name="results">Issue 结果列表。</param>
    /// <param name="filePath">文件路径。</param>
    /// <param name="sourceCode">源文件全文。</param>
    /// <param name="rules">规则配置。</param>
    public CommentSyntaxWalker(CommentChecker checker, List<CommentIssue> results, string filePath, string sourceCode, CommentRules rules)
        : base(SyntaxWalkerDepth.Trivia)
    {
        _checker = checker;
        _results = results;
        _filePath = filePath;
        _sourceCode = sourceCode;
        _rules = rules;
    }

    /// <inheritdoc/>
    public override void VisitClassDeclaration(ClassDeclarationSyntax node) { CheckMember(node, node.Identifier.Text, MemberTypes.Class); base.VisitClassDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitInterfaceDeclaration(InterfaceDeclarationSyntax node) { CheckMember(node, node.Identifier.Text, MemberTypes.Interface); base.VisitInterfaceDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitStructDeclaration(StructDeclarationSyntax node) { CheckMember(node, node.Identifier.Text, MemberTypes.Struct); base.VisitStructDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitEnumDeclaration(EnumDeclarationSyntax node)
    {
        var hasDoc = DocCommentCheckers.HasDocComment(node);
        var docComment = DocCommentCheckers.GetDocCommentText(node);
        var name = node.Identifier.Text;
        var memberType = MemberTypes.Enum;
        var ruleName = CommentChecker.GetDocMissingRuleName(memberType);

        if (!hasDoc)
        {
            CheckDocMissing(node, name, memberType);
        }
        else
        {
            CheckBlockCommentFormat(node, name, memberType);
            DocCommentCheckers.CheckDocCommentTags(node, docComment, _results, _filePath, name, memberType, ruleName, _rules);
            DocCommentCheckers.CheckCommentLanguage(docComment, node, _results, _filePath, name, memberType, ruleName, _rules);
        }

        if (_checker.GetSemanticModel() != null)
        {
            DocCommentCheckers.CheckDocCommentConsistency(node, docComment,
                _checker.GetSemanticModel(), _results, _filePath, name,
                MemberTypes.Enum, RuleNames.DocMissingEnum, _rules);
        }

        foreach (var member in node.Members) CheckEnumMember(member, name);
    }

    /// <summary>
    /// 检查单个枚举成员的注释。
    /// </summary>
    private void CheckEnumMember(EnumMemberDeclarationSyntax member, string enumName)
    {
        var ruleName = CommentChecker.GetDocMissingRuleName(MemberTypes.EnumValue);
        if (!_rules.IsEnabled(ruleName)) return;

        var hasDoc = DocCommentCheckers.HasDocComment(member);
        if (!hasDoc)
        {
            var line = member.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            _results.Add(new CommentIssue
            {
                File = _filePath,
                Line = line,
                Severity = _rules.GetIssueSeverity(ruleName, IssueCategories.MissingDocComment),
                Category = IssueCategories.MissingDocComment,
                RuleName = ruleName,
                CodeSnippet = SnippetHelpers.GetDeclarationSnippet(member),
                Member = $"{enumName}.{member.Identifier.Text}",
                MemberType = MemberTypes.EnumValue,
                Message = "枚举值缺少 XML 文档注释。"
            });
        }
    }

    /// <inheritdoc/>
    public override void VisitDelegateDeclaration(DelegateDeclarationSyntax node) { CheckMember(node, node.Identifier.Text, MemberTypes.Delegate); base.VisitDelegateDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitEventDeclaration(EventDeclarationSyntax node) { CheckMember(node, node.Identifier.Text, MemberTypes.Event); base.VisitEventDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitEventFieldDeclaration(EventFieldDeclarationSyntax node) { foreach (var v in node.Declaration.Variables) CheckMember(node, v.Identifier.Text, MemberTypes.Event); base.VisitEventFieldDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitMethodDeclaration(MethodDeclarationSyntax node)
    {
        var name = node.Identifier.Text;
        // 跳过编译器生成的最小化 getter/setter
        if (name == "get_" || name == "set_") { base.VisitMethodDeclaration(node); return; }

        var hasDoc = DocCommentCheckers.HasDocComment(node);
        var docComment = DocCommentCheckers.GetDocCommentText(node);
        var memberType = MemberTypes.Method;
        var ruleName = CommentChecker.GetDocMissingRuleName(memberType);

        if (!hasDoc)
        {
            CheckDocMissing(node, name, memberType);
        }
        else
        {
            CheckBlockCommentFormat(node, name, memberType);
            DocCommentCheckers.CheckDocCommentTags(node, docComment, _results, _filePath, name, memberType, ruleName, _rules);
            DocCommentCheckers.CheckCommentLanguage(docComment, node, _results, _filePath, name, memberType, ruleName, _rules);
        }

        if (_checker.GetSemanticModel() != null)
        {
            DocCommentCheckers.CheckDocCommentConsistency(node, docComment,
                _checker.GetSemanticModel(), _results, _filePath, name,
                MemberTypes.Method, RuleNames.DocMissingMethod, _rules);
        }

        if (node.Body != null) InlineCommentCheckers.CheckInlineComments(node, node.Body, _filePath, _sourceCode, _results, _rules);

        base.VisitMethodDeclaration(node);
    }

    /// <inheritdoc/>
    public override void VisitConstructorDeclaration(ConstructorDeclarationSyntax node)
    {
        var name = node.Identifier.Text;
        var hasDoc = DocCommentCheckers.HasDocComment(node);
        var docComment = DocCommentCheckers.GetDocCommentText(node);
        var memberType = MemberTypes.Constructor;
        var ruleName = CommentChecker.GetDocMissingRuleName(memberType);

        if (!hasDoc)
        {
            CheckDocMissing(node, name, memberType);
        }
        else
        {
            CheckBlockCommentFormat(node, name, memberType);
            DocCommentCheckers.CheckDocCommentTags(node, docComment, _results, _filePath, name, memberType, ruleName, _rules);
            DocCommentCheckers.CheckCommentLanguage(docComment, node, _results, _filePath, name, memberType, ruleName, _rules);
        }

        if (_checker.GetSemanticModel() != null)
        {
            DocCommentCheckers.CheckDocCommentConsistency(node, docComment,
                _checker.GetSemanticModel(), _results, _filePath, name,
                MemberTypes.Constructor, RuleNames.DocMissingConstructor, _rules);
        }

        base.VisitConstructorDeclaration(node);
    }

    /// <inheritdoc/>
    public override void VisitOperatorDeclaration(OperatorDeclarationSyntax node) { CheckMember(node, $"operator {node.OperatorToken.Text}", MemberTypes.Operator); base.VisitOperatorDeclaration(node); }

    /// <inheritdoc/>
    public override void VisitPropertyDeclaration(PropertyDeclarationSyntax node)
    {
        var isPublic = node.Modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.InternalKeyword));
        if (isPublic) CheckMember(node, node.Identifier.Text, MemberTypes.Property);
        base.VisitPropertyDeclaration(node);
    }

    /// <inheritdoc/>
    public override void VisitFieldDeclaration(FieldDeclarationSyntax node)
    {
        var isPublic = node.Modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.InternalKeyword));
        if (isPublic)
        {
            foreach (var variable in node.Declaration.Variables) CheckMember(node, variable.Identifier.Text, MemberTypes.Field);
        }
        base.VisitFieldDeclaration(node);
    }

    /// <summary>
    /// 检查无文档注释的成员，若已有文档注释则检查是否使用了禁止的 /** */ 格式。
    /// 根据语义分析判断是否为 override 或接口实现。
    /// </summary>
    private void CheckMember(SyntaxNode node, string name, string memberType)
    {
        var hasDoc = DocCommentCheckers.HasDocComment(node);
        if (!hasDoc)
        {
            CheckDocMissing(node, name, memberType);
            return;
        }

        CheckBlockCommentFormat(node, name, memberType);
    }

    /// <summary>
    /// 报告成员缺少文档注释，对 override/接口实现降级为 info 并建议使用 &lt;inheritdoc/&gt;。
    /// </summary>
    private void CheckDocMissing(SyntaxNode node, string name, string memberType)
    {
        var ruleName = CommentChecker.GetDocMissingRuleName(memberType);
        if (!_rules.IsEnabled(ruleName)) return;

        var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
        var severity = _rules.GetIssueSeverity(ruleName, IssueCategories.MissingDocComment);

        var isOverrideOrImpl = _checker.GetSemanticModel() != null && IsOverrideOrInterfaceImplementation(node);

        if (isOverrideOrImpl && severity == SeverityDefaults.Error)
            severity = SeverityDefaults.Info;

        var message = isOverrideOrImpl
            ? $"{memberType} 缺少 XML 文档注释，建议使用 <inheritdoc/> 继承基类或接口的注释。"
            : $"{memberType} 缺少 XML 文档注释。";

        _results.Add(new CommentIssue
        {
            File = _filePath,
            Line = line,
            Severity = severity,
            Category = IssueCategories.MissingDocComment,
            RuleName = ruleName,
            CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
            Member = name,
            MemberType = memberType,
            Message = message
        });
    }

    /// <summary>
    /// 检查节点是否使用了禁止的 /** */ 块注释格式。
    /// 对应 compliance.mdc 禁止事项第 1 条：禁止使用 /** */ 块注释格式替代 /// 文档注释。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <param name="name">成员名称。</param>
    /// <param name="memberType">成员类型。</param>
    private void CheckBlockCommentFormat(SyntaxNode node, string name, string memberType)
    {
        if (!_rules.IsEnabled(RuleNames.DocBlockCommentFormat)) return;
        if (!DocCommentCheckers.HasBlockCommentFormat(node)) return;

        var line = node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
        _results.Add(new CommentIssue
        {
            File = _filePath,
            Line = line,
            Severity = _rules.GetIssueSeverity(RuleNames.DocBlockCommentFormat, IssueCategories.BlockCommentFormat),
            Category = IssueCategories.BlockCommentFormat,
            RuleName = RuleNames.DocBlockCommentFormat,
            CodeSnippet = SnippetHelpers.GetDeclarationSnippet(node),
            Member = name,
            MemberType = memberType,
            Message = "文档注释使用了禁止的 /** */ 块注释格式，应改用 /// 格式。"
        });
    }

    /// <summary>
    /// 判断节点是否为 override 成员或显式接口实现。
    /// </summary>
    private bool IsOverrideOrInterfaceImplementation(SyntaxNode node)
    {
        var semanticModel = _checker.GetSemanticModel();
        if (semanticModel == null) return false;

        var symbol = semanticModel.GetDeclaredSymbol(node);
        if (symbol == null) return false;

        if (symbol.IsOverride) return true;

        if (symbol is IMethodSymbol methodSymbol)
        {
            if (methodSymbol.OverriddenMethod != null) return true;
            foreach (var iface in methodSymbol.ContainingType.AllInterfaces)
            {
                foreach (var ifaceMember in iface.GetMembers())
                {
                    if (methodSymbol.Equals(
                        methodSymbol.ContainingType.FindImplementationForInterfaceMember(ifaceMember),
                        SymbolEqualityComparer.Default))
                    {
                        return true;
                    }
                }
            }
        }

        if (symbol is IPropertySymbol propertySymbol && propertySymbol.OverriddenProperty != null) return true;

        return false;
    }
}
