using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Operations;

namespace CSharpTestCoverage;

/// <summary>
/// 测试引用采集器。
/// 从测试代码（Tests/）中采集全部符号引用，覆盖调用、成员访问、构造、索引器、
/// 运算符、转换、泛型、特性、反射、XML cref 等各类引用形式，
/// 统一以文档注释 ID（<see cref="ISymbol.GetDocumentationCommentId"/>）作为匹配键，
/// 从而与运行时成员采集器天然对齐（含泛型、重载、同名类型消歧）。
/// </summary>
public class TestReferenceCollector
{
    private readonly CoverageConfig _config;
    private readonly HashSet<string> _reflectionApis;

    /// <summary>
    /// 使用指定配置初始化采集器。
    /// </summary>
    /// <param name="config">覆盖率配置。</param>
    public TestReferenceCollector(CoverageConfig config)
    {
        _config = config;
        _reflectionApis = new HashSet<string>(
            config.ReferenceStrength.ReflectionApiNames, StringComparer.Ordinal);
    }

    /// <summary>
    /// 从测试语法树采集引用。
    /// </summary>
    /// <param name="compilation">包含测试源码的编译对象。</param>
    /// <param name="projectRoot">项目根目录（正斜杠归一化）。</param>
    /// <param name="testTrees">测试语法树清单。</param>
    /// <param name="warnings">告警收集器。</param>
    /// <returns>引用列表。</returns>
    public List<TestReference> Collect(
        Compilation compilation,
        string projectRoot,
        IEnumerable<SyntaxTree> testTrees,
        List<string> warnings)
    {
        var references = new List<TestReference>();

        foreach (var tree in testTrees)
        {
            var model = compilation.GetSemanticModel(tree);
            var root = tree.GetCompilationUnitRoot();
            var relativePath = RuntimeMemberCollector.MakeRelative(
                projectRoot, RuntimeMemberCollector.NormalizePath(tree.FilePath));

            foreach (var node in root.DescendantNodes())
            {
                CollectFromNode(node, model, relativePath, references);
            }

            CollectOperatorReferences(model, root, relativePath, references);
            CollectXmlCrefs(root, relativePath, references);
        }

        return references;
    }

    /// <summary>
    /// 采集运算符引用（二元、一元、自增自减、复合赋值、显式与隐式转换、条件真值）。
    ///
    /// **为何独立于语法节点分派**：运算符调用在语法树上的可绑定位置极不统一——
    ///   - 二元 / 一元 / 复合赋值 / 显式转换：`GetSymbolInfo(语法节点)` 可直接绑定；
    ///   - 条件真值 `operator true`：只在「外层语句的操作树」里可见，
    ///     直接对条件表达式取 Operation 会退化为 LocalReference（实测）；
    ///   - 隐式转换：语法节点上通常取不到（实测 `GetSymbolInfo` 仅对字面量节点生效），
    ///     且分布在变量初始化、赋值、实参、返回、数组元素等十多个位置。
    ///
    /// 因此统一改从**操作树**采集：`Operation.OperatorMethod` 对上述全部形式均能给出
    /// 用户定义运算符符号（实测覆盖 12/12）。
    ///
    /// **去重是必需的**：同一节点与其祖先节点的操作树互相包含同一子操作，
    /// 因此必须遍历后按站点去重（实测某样本原始 44 次命中，实为 8 个转换点）。
    /// 去重键取「运算符文档 ID + 语法位置」，保证同一站点的同一运算符只记一次，
    /// 同时保留不同站点的独立引用（引用计数反映真实调用点数量）。
    /// </summary>
    /// <param name="model">语义模型。</param>
    /// <param name="root">语法树根。</param>
    /// <param name="relativePath">测试文件相对路径。</param>
    /// <param name="references">引用收集器。</param>
    private void CollectOperatorReferences(
        SemanticModel model,
        CompilationUnitSyntax root,
        string relativePath,
        List<TestReference> references)
    {
        // 去重键：运算符文档 ID + 语法位置。同一运算符在不同站点的调用各记一次，
        // 同一站点的同一运算符（因父节点操作树重复包含）只记一次。
        var seenSites = new HashSet<string>(StringComparer.Ordinal);

        foreach (var node in root.DescendantNodes())
        {
            // 只从「语句」与「成员声明」两类节点出发：操作树按语法结构自顶向下构建，
            // 这两类节点已能覆盖方法体语句、字段/属性初始化、表达式体成员等全部发生位置。
            if (node is not (StatementSyntax or MemberDeclarationSyntax))
            {
                continue;
            }

            var operation = model.GetOperation(node);
            if (operation == null)
            {
                continue;
            }

            foreach (var descendant in operation.DescendantsAndSelf())
            {
                var operatorMethod = descendant switch
                {
                    IBinaryOperation binary => binary.OperatorMethod,
                    IUnaryOperation unary => unary.OperatorMethod,
                    ICompoundAssignmentOperation compound => compound.OperatorMethod,
                    IConversionOperation conversion => conversion.OperatorMethod,
                    IIncrementOrDecrementOperation increment => increment.OperatorMethod,
                    _ => null,
                };

                if (operatorMethod == null)
                {
                    continue;
                }

                var docId = operatorMethod.OriginalDefinition.GetDocumentationCommentId();
                if (string.IsNullOrEmpty(docId))
                {
                    continue;
                }

                var lineSpan = descendant.Syntax.GetLocation().GetLineSpan();
                var siteKey = docId + "@" + lineSpan.StartLinePosition.Line + ":" + lineSpan.StartLinePosition.Character;
                if (!seenSites.Add(siteKey))
                {
                    continue;
                }

                AddSymbol(operatorMethod, relativePath, descendant.Syntax, references, "operator", weak: false);
            }
        }
    }

    /// <summary>
    /// 依节点类型分派引用采集。
    /// </summary>
    private void CollectFromNode(
        SyntaxNode node,
        SemanticModel model,
        string relativePath,
        List<TestReference> references)
    {
        switch (node)
        {
            case ObjectCreationExpressionSyntax creation:
                AddSymbolInfo(model.GetSymbolInfo(creation), relativePath, node, references, "new");
                AddTypeInfo(model.GetTypeInfo(creation), relativePath, node, references, "new_type");
                break;

            case ImplicitObjectCreationExpressionSyntax implicitCreation:
                AddTypeInfo(model.GetTypeInfo(implicitCreation), relativePath, node, references, "new_implicit");
                break;

            case InvocationExpressionSyntax invocation:
                AddSymbolInfo(model.GetSymbolInfo(invocation), relativePath, node, references, "invoke");
                AddMethodGroupOperand(model, invocation, relativePath, references);
                AddGenericTypeArguments(model, invocation, relativePath, references, "invoke_generic_arg");
                AddReflectionStringArgument(model, invocation, relativePath, references);
                AddNameofOperand(model, invocation, relativePath, references);
                break;

            case MemberAccessExpressionSyntax memberAccess:
                AddSymbolInfo(model.GetSymbolInfo(memberAccess), relativePath, node, references, "member_access");
                break;

            case IdentifierNameSyntax identifier:
                AddSymbolInfo(model.GetSymbolInfo(identifier), relativePath, node, references, "identifier");
                break;

            case TypeOfExpressionSyntax typeOf:
                AddTypeInfo(model.GetTypeInfo(typeOf.Type), relativePath, node, references, "typeof");
                break;

            case DefaultExpressionSyntax defaultExpr:
                AddTypeInfo(model.GetTypeInfo(defaultExpr.Type), relativePath, node, references, "default");
                break;

            case CastExpressionSyntax cast:
                AddTypeInfo(model.GetTypeInfo(cast.Type), relativePath, node, references, "cast");
                break;

            case VariableDeclarationSyntax variableDecl:
                AddTypeInfo(model.GetTypeInfo(variableDecl.Type), relativePath, node, references, "variable_type");
                break;

            case ParameterSyntax parameter when parameter.Type != null:
                AddTypeInfo(model.GetTypeInfo(parameter.Type), relativePath, node, references, "parameter_type");
                break;

            case BaseTypeSyntax baseType:
                AddTypeInfo(model.GetTypeInfo(baseType.Type), relativePath, node, references, "base_type");
                break;

            case AttributeSyntax attribute:
                AddSymbolInfo(model.GetSymbolInfo(attribute), relativePath, node, references, "attribute");
                AddTypeInfo(model.GetTypeInfo(attribute), relativePath, node, references, "attribute_type");
                break;

            case GenericNameSyntax genericName:
                AddTypeInfo(model.GetTypeInfo(genericName), relativePath, node, references, "generic_name");
                break;

            case ElementAccessExpressionSyntax elementAccess:
                AddSymbolInfo(model.GetSymbolInfo(elementAccess), relativePath, node, references, "indexer");
                break;

            case ForEachStatementSyntax forEach:
                AddForEachEnumerator(model, forEach, relativePath, references);
                break;

            case IsPatternExpressionSyntax isPattern:
                AddTypeInfo(model.GetTypeInfo(isPattern.Pattern), relativePath, node, references, "pattern");
                break;
        }
    }

    /// <summary>
    /// 采集 nameof 表达式中引用的符号。
    /// nameof 在语法上是 InvocationExpressionSyntax，需单独判定以避免漏采。
    /// </summary>
    private void AddNameofOperand(
        SemanticModel model,
        InvocationExpressionSyntax invocation,
        string relativePath,
        List<TestReference> references)
    {
        if (invocation.Expression is not IdentifierNameSyntax { Identifier.ValueText: "nameof" })
        {
            return;
        }

        if (invocation.ArgumentList.Arguments.Count == 0)
        {
            return;
        }

        var argument = invocation.ArgumentList.Arguments[0].Expression;
        if (model.GetSymbolInfo(argument).Symbol is { } symbol)
        {
            AddTypeSymbol(symbol, relativePath, invocation, references, "nameof");
        }
    }

    /// <summary>
    /// 采集方法组形式的实参（如 lambda、方法组传递）。
    /// </summary>
    private void AddMethodGroupOperand(
        SemanticModel model,
        InvocationExpressionSyntax invocation,
        string relativePath,
        List<TestReference> references)
    {
        foreach (var argument in invocation.ArgumentList.Arguments)
        {
            var expression = argument.Expression;

            // 方法组：list.ForEach(this.Handle)
            if (expression is MemberAccessExpressionSyntax or IdentifierNameSyntax)
            {
                var symbol = model.GetSymbolInfo(expression).Symbol;
                if (symbol is IMethodSymbol)
                {
                    AddTypeSymbol(symbol, relativePath, expression, references, "method_group");
                }
            }

            // 委托实参：传递方法组给委托参数
            if (model.GetTypeInfo(expression).ConvertedType is INamedTypeSymbol convertedType &&
                convertedType.TypeKind == TypeKind.Delegate)
            {
                var symbol = model.GetSymbolInfo(expression).Symbol;
                if (symbol is IMethodSymbol)
                {
                    AddTypeSymbol(symbol, relativePath, expression, references, "delegate_arg");
                }
            }
        }
    }

    /// <summary>
    /// 采集调用表达式的泛型实参（如 Assert.Throws&lt;T&gt; 中的 T）。
    /// </summary>
    private void AddGenericTypeArguments(
        SemanticModel model,
        InvocationExpressionSyntax invocation,
        string relativePath,
        List<TestReference> references,
        string kind)
    {
        if (invocation.Expression is not GenericNameSyntax genericName)
        {
            return;
        }

        foreach (var typeArg in genericName.TypeArgumentList.Arguments)
        {
            AddTypeInfo(model.GetTypeInfo(typeArg), relativePath, typeArg, references, kind);
        }
    }

    /// <summary>
    /// 采集 foreach 的隐式 GetEnumerator 引用。
    /// foreach 不产生显式调用语法，必须在此补采，否则实现 IEnumerable 的类型
    /// 会因「只有 foreach 使用」而被误判为未覆盖。
    /// </summary>
    private void AddForEachEnumerator(
        SemanticModel model,
        ForEachStatementSyntax forEach,
        string relativePath,
        List<TestReference> references)
    {
        var collectionType = model.GetTypeInfo(forEach.Expression).Type;
        if (collectionType == null)
        {
            return;
        }

        // 集合类型本身
        AddTypeSymbol(collectionType, relativePath, forEach, references, "foreach_collection");

        // 路径 1：显式实现 IEnumerable / IEnumerable<T> 接口
        var enumerable = collectionType.AllInterfaces
            .FirstOrDefault(i => i.SpecialType == SpecialType.System_Collections_IEnumerable);
        if (enumerable != null)
        {
            var getEnumerator = enumerable.GetMembers("GetEnumerator").OfType<IMethodSymbol>().FirstOrDefault();
            if (getEnumerator != null)
            {
                AddSymbol(getEnumerator, relativePath, forEach, references, "foreach_getenumerator", weak: false);
            }
            AddSymbol(enumerable, relativePath, forEach, references, "foreach_enumerable", weak: false);
        }

        var genericEnumerable = collectionType.AllInterfaces
            .FirstOrDefault(i => i.OriginalDefinition.SpecialType == SpecialType.System_Collections_Generic_IEnumerable_T);
        if (genericEnumerable != null)
        {
            var method = genericEnumerable.GetMembers("GetEnumerator").OfType<IMethodSymbol>().FirstOrDefault();
            if (method != null)
            {
                AddSymbol(method, relativePath, forEach, references, "foreach_getenumerator_generic", weak: false);
            }
            AddSymbol(genericEnumerable, relativePath, forEach, references, "foreach_enumerable_generic", weak: false);
        }

        // 路径 2：未实现接口但提供公开 GetEnumerator（鸭子类型，编译期即被 foreach 绑定）
        // 此处直接按成员名在集合类型及其基类上查找，补采该 GetEnumerator。
        var duckEnumerator = FindPublicGetEnumerator(collectionType);
        if (duckEnumerator != null)
        {
            AddSymbol(duckEnumerator, relativePath, forEach, references, "foreach_getenumerator_duck", weak: false);
        }

        // 路径 3：补采涉及的 Current / MoveNext（结构体枚举器常以只读成员暴露）
        foreach (var candidate in collectionType.GetMembers("GetEnumerator").OfType<IMethodSymbol>())
        {
            var returnType = candidate.ReturnType as INamedTypeSymbol;
            if (returnType == null)
            {
                continue;
            }
            foreach (var member in returnType.GetMembers())
            {
                if (member.Name is "Current" or "MoveNext")
                {
                    AddSymbol(member, relativePath, forEach, references, "foreach_enumerator_member", weak: false);
                }
            }
        }
    }

    /// <summary>
    /// 在类型及其基类上查找公开的无参 GetEnumerator（鸭子类型枚举）。
    /// </summary>
    private static IMethodSymbol? FindPublicGetEnumerator(ITypeSymbol type)
    {
        var current = type as INamedTypeSymbol;
        while (current != null)
        {
            var method = current.GetMembers("GetEnumerator")
                .OfType<IMethodSymbol>()
                .FirstOrDefault(m => m.Parameters.Length == 0 &&
                                     m.DeclaredAccessibility == Accessibility.Public);
            if (method != null)
            {
                return method;
            }
            current = current.BaseType;
        }
        return null;
    }

    /// <summary>
    /// 采集反射字符串实参（如 GetField("mSlotIndex")）作为弱引用。
    /// </summary>
    private void AddReflectionStringArgument(
        SemanticModel model,
        InvocationExpressionSyntax invocation,
        string relativePath,
        List<TestReference> references)
    {
        var methodName = invocation.Expression switch
        {
            MemberAccessExpressionSyntax ma => ma.Name.Identifier.ValueText,
            IdentifierNameSyntax id => id.Identifier.ValueText,
            GenericNameSyntax gn => gn.Identifier.ValueText,
            _ => null,
        };

        if (methodName == null || !_reflectionApis.Contains(methodName))
        {
            return;
        }

        var arguments = invocation.ArgumentList.Arguments;
        if (arguments.Count == 0)
        {
            return;
        }

        if (arguments[0].Expression is not LiteralExpressionSyntax literal ||
            !literal.IsKind(SyntaxKind.StringLiteralExpression))
        {
            return;
        }

        var memberName = literal.Token.ValueText;
        if (string.IsNullOrWhiteSpace(memberName))
        {
            return;
        }

        // 反射目标类型：优先取 member access 的 receiver 类型
        var receiverType = invocation.Expression is MemberAccessExpressionSyntax memberAccess
            ? model.GetTypeInfo(memberAccess.Expression).Type
            : null;

        references.Add(new TestReference
        {
            TypeFullName = receiverType != null ? BuildTypeKey(receiverType) : string.Empty,
            MemberName = memberName,
            ParameterCount = -1,
            IsWeak = true,
            Kind = "reflection_string",
            File = relativePath,
            Line = GetLine(invocation),
        });
    }

    /// <summary>
    /// 采集 XML 文档注释中的 cref 引用（弱引用）。
    /// </summary>
    private void CollectXmlCrefs(
        CompilationUnitSyntax root,
        string relativePath,
        List<TestReference> references)
    {
        foreach (var trivia in root.DescendantTrivia())
        {
            if (!trivia.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) &&
                !trivia.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
            {
                continue;
            }

            var structure = trivia.GetStructure();
            if (structure == null)
            {
                continue;
            }

            foreach (var cref in structure.DescendantNodes().OfType<NameMemberCrefSyntax>())
            {
                var text = cref.Name.ToString();
                if (string.IsNullOrWhiteSpace(text))
                {
                    continue;
                }
                references.Add(new TestReference
                {
                    TypeFullName = text,
                    MemberName = string.Empty,
                    ParameterCount = -1,
                    IsWeak = true,
                    Kind = "xml_cref",
                    File = relativePath,
                    Line = GetLine(cref),
                });
            }

            foreach (var cref in structure.DescendantNodes().OfType<QualifiedCrefSyntax>())
            {
                var text = cref.ToString();
                references.Add(new TestReference
                {
                    TypeFullName = text,
                    MemberName = string.Empty,
                    ParameterCount = -1,
                    IsWeak = true,
                    Kind = "xml_cref",
                    File = relativePath,
                    Line = GetLine(cref),
                });
            }
        }
    }

    /// <summary>
    /// 依据符号信息添加引用。
    /// </summary>
    private void AddSymbolInfo(
        SymbolInfo info,
        string relativePath,
        SyntaxNode node,
        List<TestReference> references,
        string kind)
    {
        if (info.Symbol != null)
        {
            AddTypeSymbol(info.Symbol, relativePath, node, references, kind);
            return;
        }

        // 重载候选（符号信息无法唯一确定时）
        foreach (var candidate in info.CandidateSymbols)
        {
            AddTypeSymbol(candidate, relativePath, node, references, kind + "_candidate");
        }
    }

    /// <summary>
    /// 依据类型信息添加引用。
    /// </summary>
    private void AddTypeInfo(
        TypeInfo info,
        string relativePath,
        SyntaxNode node,
        List<TestReference> references,
        string kind)
    {
        var type = info.Type ?? info.ConvertedType;
        if (type != null)
        {
            AddTypeSymbol(type, relativePath, node, references, kind);
        }
    }

    /// <summary>
    /// 将符号转换为引用记录。
    /// </summary>
    private void AddTypeSymbol(
        ISymbol symbol,
        string relativePath,
        SyntaxNode node,
        List<TestReference> references,
        string kind)
    {
        switch (symbol)
        {
            case INamedTypeSymbol named:
                AddSymbol(named, relativePath, node, references, kind, weak: false);
                break;
            case IMethodSymbol method:
                AddSymbol(method, relativePath, node, references, kind, weak: false);
                AddSymbol(method.ContainingType, relativePath, node, references, kind + "_containing", weak: false);
                break;
            case IPropertySymbol property:
                AddSymbol(property, relativePath, node, references, kind, weak: false);
                AddSymbol(property.ContainingType, relativePath, node, references, kind + "_containing", weak: false);
                break;
            case IFieldSymbol field:
                AddSymbol(field, relativePath, node, references, kind, weak: false);
                AddSymbol(field.ContainingType, relativePath, node, references, kind + "_containing", weak: false);
                break;
            case IEventSymbol eventSymbol:
                AddSymbol(eventSymbol, relativePath, node, references, kind, weak: false);
                AddSymbol(eventSymbol.ContainingType, relativePath, node, references, kind + "_containing", weak: false);
                break;
            case ITypeSymbol typeSymbol:
                AddSymbol(typeSymbol, relativePath, node, references, kind, weak: false);
                break;
        }
    }

    /// <summary>
    /// 由符号生成引用记录（以文档注释 ID 为匹配键）。
    /// </summary>
    private void AddSymbol(
        ISymbol? symbol,
        string relativePath,
        SyntaxNode node,
        List<TestReference> references,
        string kind,
        bool weak)
    {
        if (symbol == null)
        {
            return;
        }

        // 关键：测试侧符号常来自「构造泛型」（如 Queue<Int32>.Enqueue），
        // 其文档注释 ID 会带上类型实参（{System.Int32}），与运行时侧的
        // 泛型定义 ID（`1 / `0）不一致。统一取 OriginalDefinition 归一到定义形式。
        var normalized = symbol is INamedTypeSymbol or IMethodSymbol or IPropertySymbol
            or IFieldSymbol or IEventSymbol
            ? symbol.OriginalDefinition
            : symbol;

        var docId = normalized.GetDocumentationCommentId();
        if (string.IsNullOrEmpty(docId))
        {
            return;
        }

        references.Add(new TestReference
        {
            TypeFullName = docId,
            MemberName = string.Empty,
            ParameterCount = -1,
            IsWeak = weak,
            Kind = kind,
            File = relativePath,
            Line = GetLine(node),
        });
    }

    /// <summary>
    /// 构建类型匹配键（用于反射字符串引用，无法取得文档 ID 时的回退）。
    /// </summary>
    private static string BuildTypeKey(ITypeSymbol type)
    {
        return type.GetDocumentationCommentId() ?? type.ToDisplayString();
    }

    /// <summary>
    /// 获取节点行号（1 起）。
    /// </summary>
    private static int GetLine(SyntaxNode node)
    {
        return node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
    }
}
