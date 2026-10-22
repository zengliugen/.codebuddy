using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace CSharpTestCoverage;

/// <summary>
/// 运行时成员采集器。
/// 从配置声明的运行时源码根（<see cref="CoverageConfig.RuntimeRoots"/>）中采集 public + internal 成员，
/// 并按文档注释 ID（<see cref="ISymbol.GetDocumentationCommentId"/>）生成统一匹配键。
/// </summary>
public class RuntimeMemberCollector
{
    private readonly CoverageConfig _config;
    private readonly Dictionary<string, string> _assemblyCache = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// 使用指定配置初始化采集器。
    /// </summary>
    /// <param name="config">覆盖率配置。</param>
    public RuntimeMemberCollector(CoverageConfig config)
    {
        _config = config;
    }

    /// <summary>
    /// 采集运行时成员记录。
    /// </summary>
    /// <param name="compilation">包含运行时源码的编译对象。</param>
    /// <param name="projectRoot">项目根目录（正斜杠归一化）。</param>
    /// <param name="runtimeTrees">运行时语法树清单。</param>
    /// <param name="warnings">告警收集器。</param>
    /// <returns>覆盖率记录列表。</returns>
    public List<CoverageRecord> Collect(
        Compilation compilation,
        string projectRoot,
        IEnumerable<SyntaxTree> runtimeTrees,
        List<string> warnings)
    {
        var records = new List<CoverageRecord>();

        foreach (var tree in runtimeTrees)
        {
            var model = compilation.GetSemanticModel(tree);
            var root = tree.GetCompilationUnitRoot();
            var absolutePath = NormalizePath(tree.FilePath);
            var relativePath = MakeRelative(projectRoot, absolutePath);

            foreach (var node in root.DescendantNodes())
            {
                switch (node)
                {
                    case TypeDeclarationSyntax typeDecl:
                        AddTypeRecord(records, model, typeDecl, relativePath, absolutePath, projectRoot);
                        break;
                    case EnumDeclarationSyntax enumDecl:
                        AddEnumRecord(records, model, enumDecl, relativePath, absolutePath, projectRoot);
                        break;
                    case DelegateDeclarationSyntax delegateDecl:
                        AddDelegateRecord(records, model, delegateDecl, relativePath, absolutePath, projectRoot);
                        break;
                }
            }
        }

        return records;
    }

    /// <summary>
    /// 添加类型级记录（含其成员）。
    /// </summary>
    private void AddTypeRecord(
        List<CoverageRecord> records,
        SemanticModel model,
        TypeDeclarationSyntax typeDecl,
        string relativePath,
        string absolutePath,
        string projectRoot)
    {
        if (model.GetDeclaredSymbol(typeDecl) is not INamedTypeSymbol typeSymbol)
        {
            return;
        }

        var typeId = typeSymbol.GetDocumentationCommentId();
        if (string.IsNullOrEmpty(typeId))
        {
            return;
        }

        var typeLine = GetLine(typeDecl);
        records.Add(CreateRecord(
            typeSymbol, typeId, typeSymbol.Name, GetTypeKind(typeDecl),
            relativePath, absolutePath, projectRoot, typeLine));

        foreach (var member in typeDecl.Members)
        {
            AddMemberRecord(records, model, member, relativePath, absolutePath, projectRoot);
        }
    }

    /// <summary>
    /// 添加枚举类型记录及其枚举值。
    /// </summary>
    private void AddEnumRecord(
        List<CoverageRecord> records,
        SemanticModel model,
        EnumDeclarationSyntax enumDecl,
        string relativePath,
        string absolutePath,
        string projectRoot)
    {
        if (model.GetDeclaredSymbol(enumDecl) is not INamedTypeSymbol typeSymbol)
        {
            return;
        }

        var typeId = typeSymbol.GetDocumentationCommentId();
        if (string.IsNullOrEmpty(typeId))
        {
            return;
        }

        records.Add(CreateRecord(
            typeSymbol, typeId, typeSymbol.Name, "enum",
            relativePath, absolutePath, projectRoot, GetLine(enumDecl)));

        if (!_config.MemberScope.IncludeEnumValues)
        {
            return;
        }

        foreach (var member in enumDecl.Members)
        {
            if (model.GetDeclaredSymbol(member) is not IFieldSymbol fieldSymbol)
            {
                continue;
            }
            var memberId = fieldSymbol.GetDocumentationCommentId();
            if (string.IsNullOrEmpty(memberId))
            {
                continue;
            }
            records.Add(CreateRecord(
                fieldSymbol, memberId, fieldSymbol.Name, MemberKinds.EnumValue,
                relativePath, absolutePath, projectRoot, GetLine(member)));
        }
    }

    /// <summary>
    /// 添加单个成员记录。
    /// </summary>
    private void AddMemberRecord(
        List<CoverageRecord> records,
        SemanticModel model,
        MemberDeclarationSyntax member,
        string relativePath,
        string absolutePath,
        string projectRoot)
    {
        ISymbol? symbol = member switch
        {
            MethodDeclarationSyntax m => model.GetDeclaredSymbol(m),
            ConstructorDeclarationSyntax c => model.GetDeclaredSymbol(c),
            PropertyDeclarationSyntax p => model.GetDeclaredSymbol(p),
            FieldDeclarationSyntax f => model.GetDeclaredSymbol(f.Declaration.Variables.FirstOrDefault()!),
            EventFieldDeclarationSyntax e => model.GetDeclaredSymbol(e.Declaration.Variables.FirstOrDefault()!),
            EventDeclarationSyntax ev => model.GetDeclaredSymbol(ev),
            IndexerDeclarationSyntax ix => model.GetDeclaredSymbol(ix),
            OperatorDeclarationSyntax op => model.GetDeclaredSymbol(op),
            ConversionOperatorDeclarationSyntax cv => model.GetDeclaredSymbol(cv),
            DestructorDeclarationSyntax dt => model.GetDeclaredSymbol(dt),
            _ => null,
        };

        if (symbol == null || !IsInScope(symbol))
        {
            return;
        }

        var kind = GetMemberKind(member);
        if (!ShouldIncludeKind(kind, member))
        {
            return;
        }

        var memberId = symbol.GetDocumentationCommentId();
        if (string.IsNullOrEmpty(memberId))
        {
            return;
        }

        var name = symbol is IMethodSymbol method && method.MethodKind == MethodKind.Constructor
            ? ".ctor"
            : symbol.Name;

        records.Add(CreateRecord(
            symbol, memberId, name, kind,
            relativePath, absolutePath, projectRoot, GetLine(member)));
    }

    /// <summary>
    /// 添加委托类型记录。
    /// </summary>
    private void AddDelegateRecord(
        List<CoverageRecord> records,
        SemanticModel model,
        DelegateDeclarationSyntax delegateDecl,
        string relativePath,
        string absolutePath,
        string projectRoot)
    {
        if (model.GetDeclaredSymbol(delegateDecl) is not INamedTypeSymbol symbol)
        {
            return;
        }

        var id = symbol.GetDocumentationCommentId();
        if (string.IsNullOrEmpty(id))
        {
            return;
        }

        records.Add(CreateRecord(
            symbol, id, symbol.Name, MemberKinds.Type,
            relativePath, absolutePath, projectRoot, GetLine(delegateDecl)));
    }

    /// <summary>
    /// 依据配置判断成员种类是否纳入统计。
    /// </summary>
    private bool ShouldIncludeKind(string kind, MemberDeclarationSyntax member)
    {
        if (kind == MemberKinds.Property && _config.MemberScope.SkipPropertyAccessors)
        {
            return false;
        }
        if (kind == MemberKinds.Event && _config.MemberScope.SkipEventAccessors)
        {
            return false;
        }
        if (kind == MemberKinds.Operator && _config.MemberScope.SkipOperators)
        {
            return false;
        }
        if (kind == MemberKinds.Destructor && _config.MemberScope.SkipDestructors)
        {
            return false;
        }
        return true;
    }

    /// <summary>
    /// 判断符号的访问级别是否在分母口径内。
    /// </summary>
    private bool IsInScope(ISymbol symbol)
    {
        if (_config.MemberScope.SkipCompilerGenerated &&
            symbol.GetAttributes().Any(a =>
                a.AttributeClass?.Name is "CompilerGeneratedAttribute" or "CompilerGenerated"))
        {
            return false;
        }

        var accessibility = symbol.DeclaredAccessibility;
        var allowed = _config.MemberScope.Accessibilities;

        if (accessibility == Accessibility.Public && allowed.Contains("public"))
        {
            return true;
        }
        if (accessibility == Accessibility.Internal && allowed.Contains("internal"))
        {
            return true;
        }
        if (accessibility == Accessibility.ProtectedOrInternal && allowed.Contains("internal"))
        {
            return true;
        }
        if (accessibility == Accessibility.Private && _config.MemberScope.IncludePrivateMembers)
        {
            return true;
        }
        if (accessibility == Accessibility.Protected && _config.MemberScope.IncludePrivateMembers)
        {
            return true;
        }

        return false;
    }

    /// <summary>
    /// 创建覆盖率记录。
    /// </summary>
    private CoverageRecord CreateRecord(
        ISymbol symbol,
        string memberId,
        string memberName,
        string memberKind,
        string relativePath,
        string absolutePath,
        string projectRoot,
        int line)
    {
        var containingType = symbol as INamedTypeSymbol ?? symbol.ContainingType;
        var typeName = containingType?.Name ?? string.Empty;
        var namespaceName = containingType?.ContainingNamespace?.ToDisplayString() ?? string.Empty;

        return new CoverageRecord
        {
            File = absolutePath,
            RelativeFile = relativePath,
            Assembly = ResolveAssembly(absolutePath, projectRoot),
            Namespace = namespaceName,
            TypeName = typeName,
            TypeKind = containingType != null ? GetTypeKindFromSymbol(containingType) : string.Empty,
            Member = memberName,
            MemberKind = memberKind,
            MemberSignature = symbol.ToDisplayString(SymbolDisplayFormat.MinimallyQualifiedFormat),
            MemberId = memberId,
            CoverageState = CoverageStates.Uncovered,
            Line = line,
        };
    }

    /// <summary>
    /// 从路径推断所属程序集：优先读取最近的 asmdef 的 name 字段。
    /// </summary>
    private string ResolveAssembly(string absolutePath, string projectRoot)
    {
        var dir = Path.GetDirectoryName(absolutePath);
        var visited = new List<string>();

        while (!string.IsNullOrEmpty(dir) && dir.Length >= projectRoot.Length)
        {
            visited.Add(dir);
            if (_assemblyCache.TryGetValue(dir, out var cached))
            {
                CacheAll(visited, cached);
                return cached;
            }

            var asmdef = Directory.Exists(dir)
                ? Directory.GetFiles(dir, "*.asmdef").FirstOrDefault()
                : null;
            if (asmdef != null)
            {
                var name = TryReadAsmdefName(asmdef) ?? Path.GetFileNameWithoutExtension(asmdef);
                CacheAll(visited, name);
                return name;
            }

            var parent = Path.GetDirectoryName(dir);
            if (parent == dir)
            {
                break;
            }
            dir = parent;
        }

        // 回退：由包路径推断。
        // 包名前缀 → 命名空间的映射从项目配置读取（`namespaceMapping.mappings`），
        // 不硬编码特定项目的包名；未配置映射时直接以包名作为命名空间。
        var relative = MakeRelative(projectRoot, absolutePath);
        var parts = relative.Split('/');
        if (parts.Length > 1 && parts[0].Equals("Packages", StringComparison.OrdinalIgnoreCase))
        {
            var packageName = parts[1];
            var mapped = TryMapPackageToNamespace(packageName);
            if (mapped != null)
            {
                CacheAll(visited, mapped);
                return mapped;
            }
            CacheAll(visited, packageName);
            return packageName;
        }

        var fallback = parts.Length > 0 ? parts[^1] : string.Empty;
        CacheAll(visited, fallback);
        return fallback;
    }

    /// <summary>
    /// 按配置的包名 → 命名空间映射推断命名空间。
    ///
    /// 映射项来自 `coverage_config.json` 的 `namespaceMapping.mappings`；
    /// 未命中任何映射时返回 null（由调用方回退为包名本身）。
    /// </summary>
    /// <param name="packageName">UPM 包名，如 `com.example.core`。</param>
    /// <returns>推断出的命名空间；无匹配映射时为 null。</returns>
    private string? TryMapPackageToNamespace(string packageName)
    {
        foreach (var item in _config.NamespaceMapping.Mappings)
        {
            var prefix = item.PackagePrefix;
            if (string.IsNullOrEmpty(prefix) || string.IsNullOrEmpty(item.Namespace))
            {
                continue;
            }
            if (!packageName.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var suffix = packageName[prefix.Length..];
            if (suffix.Length == 0)
            {
                return item.Namespace;
            }

            // 后缀按 `.` 分片，每片首字母大写后拼到根命名空间之后
            var segments = suffix.Split('.', StringSplitOptions.RemoveEmptyEntries);
            var mappedParts = new List<string> { item.Namespace };
            foreach (var segment in segments)
            {
                mappedParts.Add(char.ToUpperInvariant(segment[0]) + segment[1..]);
            }
            return string.Join(".", mappedParts);
        }
        return null;
    }

    /// <summary>
    /// 读取 asmdef 的 name 字段（不引入 JSON 依赖，简单提取）。
    /// </summary>
    private static string? TryReadAsmdefName(string path)
    {
        try
        {
            var text = File.ReadAllText(path);
            var match = System.Text.RegularExpressions.Regex.Match(
                text, "\"name\"\\s*:\\s*\"([^\"]+)\"");
            return match.Success ? match.Groups[1].Value : null;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// 批量写入程序集缓存。
    /// </summary>
    private void CacheAll(List<string> dirs, string assemblyName)
    {
        foreach (var d in dirs)
        {
            _assemblyCache[d] = assemblyName;
        }
    }

    /// <summary>
    /// 获取节点所在行号（1 起）。
    /// </summary>
    private static int GetLine(SyntaxNode node)
    {
        return node.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
    }

    /// <summary>
    /// 获取类型种类标识。
    /// </summary>
    private static string GetTypeKind(BaseTypeDeclarationSyntax decl)
    {
        return decl switch
        {
            ClassDeclarationSyntax => "class",
            StructDeclarationSyntax => "struct",
            InterfaceDeclarationSyntax => "interface",
            EnumDeclarationSyntax => "enum",
            RecordDeclarationSyntax => "record",
            _ => "type",
        };
    }
    /// <summary>
    /// 由符号获取类型种类标识。
    /// </summary>
    private static string GetTypeKindFromSymbol(INamedTypeSymbol symbol)
    {
        return symbol.TypeKind switch
        {
            TypeKind.Class => symbol.IsRecord ? "record" : "class",
            TypeKind.Struct => symbol.IsRecord ? "record" : "struct",
            TypeKind.Interface => "interface",
            TypeKind.Enum => "enum",
            TypeKind.Delegate => "delegate",
            _ => "type",
        };
    }

    /// <summary>
    /// 获取成员种类标识。
    /// </summary>
    private static string GetMemberKind(MemberDeclarationSyntax member)
    {
        return member switch
        {
            MethodDeclarationSyntax => MemberKinds.Method,
            ConstructorDeclarationSyntax => MemberKinds.Constructor,
            PropertyDeclarationSyntax => MemberKinds.Property,
            FieldDeclarationSyntax => MemberKinds.Field,
            EventFieldDeclarationSyntax => MemberKinds.Event,
            EventDeclarationSyntax => MemberKinds.Event,
            IndexerDeclarationSyntax => MemberKinds.Indexer,
            OperatorDeclarationSyntax => MemberKinds.Operator,
            ConversionOperatorDeclarationSyntax => MemberKinds.Operator,
            DestructorDeclarationSyntax => MemberKinds.Destructor,
            _ => MemberKinds.Other,
        };
    }

    /// <summary>
    /// 路径归一化为正斜杠。
    /// </summary>
    internal static string NormalizePath(string path)
    {
        return path.Replace('\\', '/');
    }

    /// <summary>
    /// 计算相对项目根的路径。
    /// </summary>
    internal static string MakeRelative(string projectRoot, string absolutePath)
    {
        var normalizedRoot = NormalizePath(projectRoot).TrimEnd('/') + "/";
        var normalizedPath = NormalizePath(absolutePath);
        if (normalizedPath.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase))
        {
            return normalizedPath[normalizedRoot.Length..];
        }
        return normalizedPath;
    }
}

/// <summary>
/// 成员种类常量。
/// </summary>
public static class MemberKinds
{
    /// <summary>类型本身。</summary>
    public const string Type = "type";

    /// <summary>方法。</summary>
    public const string Method = "method";

    /// <summary>构造函数。</summary>
    public const string Constructor = "constructor";

    /// <summary>属性。</summary>
    public const string Property = "property";

    /// <summary>字段。</summary>
    public const string Field = "field";

    /// <summary>事件。</summary>
    public const string Event = "event";

    /// <summary>索引器。</summary>
    public const string Indexer = "indexer";

    /// <summary>运算符。</summary>
    public const string Operator = "operator";

    /// <summary>析构函数。</summary>
    public const string Destructor = "destructor";

    /// <summary>枚举值。</summary>
    public const string EnumValue = "enumvalue";

    /// <summary>其他。</summary>
    public const string Other = "other";
}
