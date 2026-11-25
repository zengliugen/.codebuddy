// 按项目根 .editorconfig 的命名规则批量重命名 C# 符号（Roslyn Renamer + 自行写盘）
// 说明：Unity 工程的 MSBuildWorkspace 不支持 TryApplyChanges，故改为逐文档写回磁盘
using System.Text;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.MSBuild;
using Microsoft.CodeAnalysis.Rename;
using Microsoft.CodeAnalysis.Text;

namespace RenameSymbolTool
{
    internal static class Program
    {
        // 已处理符号（试运行模式不改变解决方案，必须自行去重防止死循环）
        private static readonly HashSet<string> s_handled = new HashSet<string>(StringComparer.Ordinal);

        // 程序集级 SuppressMessage 的 Target 集合（文档注释 ID，去掉 ~ 前缀），按需加载一次
        private static HashSet<string> s_assemblySuppressedTargets;

        private static async Task<int> Main(string[] args)
        {
            try
            {
                Console.OutputEncoding = new UTF8Encoding(false);
            }
            catch (IOException)
            {
                // 输出被重定向时设置编码可能失败，忽略即可
            }

            bool apply = false;
            string editorConfigPath = null;
            var projectPaths = new List<string>();
            var excludeDirs = new List<string>();

            for (int index = 0; index < args.Length; index++)
            {
                string arg = args[index];
                switch (arg)
                {
                    case "--apply":
                        apply = true;
                        break;
                    case "--dry-run":
                        apply = false;
                        break;
                    case "--editorconfig":
                        if (index + 1 >= args.Length)
                        {
                            Console.Error.WriteLine("[错误] --editorconfig 缺少路径参数");
                            return 2;
                        }

                        editorConfigPath = args[++index];
                        break;
                    case "--exclude":
                        if (index + 1 >= args.Length)
                        {
                            Console.Error.WriteLine("[错误] --exclude 缺少目录参数");
                            return 2;
                        }

                        excludeDirs.Add(args[++index]);
                        break;
                    default:
                        if (arg.StartsWith("--", StringComparison.Ordinal))
                        {
                            Console.Error.WriteLine($"[错误] 未知参数：{arg}");
                            return 2;
                        }

                        projectPaths.Add(arg);
                        break;
                }
            }

            if (projectPaths.Count == 0)
            {
                Console.Error.WriteLine("用法：RenameSymbolTool [--apply|--dry-run] [--editorconfig <路径>] [--exclude <目录>]… <csproj 路径…>");
                return 2;
            }

            editorConfigPath = editorConfigPath ?? FindEditorConfig(projectPaths[0]);
            if (editorConfigPath == null || !File.Exists(editorConfigPath))
            {
                Console.Error.WriteLine("[错误] 未找到项目根 .editorconfig，且未通过 --editorconfig 指定");
                return 3;
            }

            string projectRoot = Path.GetDirectoryName(Path.GetFullPath(editorConfigPath));
            if (excludeDirs.Count > 0)
            {
                Console.WriteLine($"[排除] {string.Join(", ", excludeDirs)}");
            }

            NamingRuleSet ruleSet = NamingRuleSet.Load(editorConfigPath);
            Console.WriteLine($"[配置] {editorConfigPath}（命名规则 {ruleSet.RuleCount} 条，生效 {ruleSet.EnforcedCount} 条）");
            if (ruleSet.RuleCount == 0)
            {
                Console.Error.WriteLine("[错误] .editorconfig 中未找到 dotnet_naming_rule 命名规则");
                return 3;
            }

            MSBuildLocator.RegisterDefaults();

            using var workspace = MSBuildWorkspace.Create();
            workspace.WorkspaceFailed += (sender, e) =>
            {
                if (e.Diagnostic.Kind == WorkspaceDiagnosticKind.Failure)
                {
                    Console.WriteLine($"[工作区失败] {e.Diagnostic.Message}");
                }
            };

            foreach (string path in projectPaths)
            {
                try
                {
                    Console.WriteLine($"[加载] {path}");
                    if (path.EndsWith(".sln", StringComparison.OrdinalIgnoreCase)
                        || path.EndsWith(".slnx", StringComparison.OrdinalIgnoreCase))
                    {
                        await workspace.OpenSolutionAsync(path);
                    }
                    else
                    {
                        await workspace.OpenProjectAsync(path);
                    }
                }
                catch (ArgumentException ex)
                {
                    // 工程已在引用闭包中加载时重复打开会抛此异常，属正常情况
                    Console.WriteLine($"[跳过] {ex.Message}");
                }
            }

            // 只分析传入的工程；其引用闭包中的其他工程仅作为引用方被同步改写
            var targetProjects = new HashSet<string>(projectPaths.Select(Path.GetFileNameWithoutExtension), StringComparer.Ordinal);
            Solution solution = workspace.CurrentSolution;

            int renamed = 0;
            int skipped = 0;
            while (true)
            {
                var found = await FindNextAsync(solution, targetProjects, ruleSet, projectRoot, excludeDirs);
                if (found == null)
                {
                    break;
                }

                ISymbol symbol = found.Value.Symbol;
                string newName = found.Value.NewName;
                Console.WriteLine($"{(apply ? "[改名]" : "[试运行]")} {symbol.ToDisplayString()} -> {newName}  ({found.Value.Location})");

                try
                {
                    Solution newSolution = await Renamer.RenameSymbolAsync(solution, symbol, new SymbolRenameOptions(), newName);
                    if (apply)
                    {
                        await WriteChangesAsync(solution, newSolution);
                    }

                    solution = newSolution;
                    renamed++;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"  [跳过] {ex.GetType().Name}: {ex.Message}");
                    skipped++;
                }
            }

            Console.WriteLine($"完成：{(apply ? "已改名" : "待改名")} {renamed} 个，跳过 {skipped} 个");
            if (!apply)
            {
                Console.WriteLine("提示：当前为试运行模式，未修改任何文件；确认清单后加 --apply 落盘。");
            }

            return 0;
        }

        // 自 csproj 所在目录向上查找项目根 .editorconfig
        private static string FindEditorConfig(string projectPath)
        {
            string directory = Path.GetDirectoryName(Path.GetFullPath(projectPath));
            while (!string.IsNullOrEmpty(directory))
            {
                string candidate = Path.Combine(directory, ".editorconfig");
                if (File.Exists(candidate))
                {
                    return candidate;
                }

                string parent = Path.GetDirectoryName(directory);
                if (parent == directory)
                {
                    break;
                }

                directory = parent;
            }

            return null;
        }

        // 判断文件是否位于配置声明的忽略目录内（按项目根相对路径做前缀匹配）
        private static bool IsExcluded(string filePath, string projectRoot, List<string> excludeDirs)
        {
            if (excludeDirs.Count == 0)
            {
                return false;
            }

            string relative = Path.GetRelativePath(projectRoot, filePath).Replace('\\', '/');
            foreach (string dir in excludeDirs)
            {
                string normalized = dir.Replace('\\', '/').TrimEnd('/');
                if (normalized.Length == 0)
                {
                    continue;
                }

                if (relative.Equals(normalized, StringComparison.OrdinalIgnoreCase)
                    || relative.StartsWith(normalized + "/", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// 收集文件内 #pragma warning disable IDE1006 的生效行区间
        /// </summary>
        private static List<(int Start, int End)> BuildPragmaDisabledRanges(SyntaxNode root)
        {
            var ranges = new List<(int Start, int End)>();
            int lastLine = root.GetLocation().GetLineSpan().EndLinePosition.Line;
            int? openLine = null;

            foreach (PragmaWarningDirectiveTriviaSyntax directive in root.DescendantTrivia()
                .Where(item => item.IsKind(SyntaxKind.PragmaWarningDirectiveTrivia) && item.HasStructure)
                .Select(item => (PragmaWarningDirectiveTriviaSyntax)item.GetStructure())
                .OrderBy(item => item.SpanStart))
            {
                if (!AffectsIde1006(directive))
                {
                    continue;
                }

                int line = directive.GetLocation().GetLineSpan().StartLinePosition.Line;
                if (directive.DisableOrRestoreKeyword.IsKind(SyntaxKind.DisableKeyword))
                {
                    if (!openLine.HasValue)
                    {
                        openLine = line;
                    }
                }
                else if (openLine.HasValue)
                {
                    ranges.Add((openLine.Value, line));
                    openLine = null;
                }
            }

            if (openLine.HasValue)
            {
                ranges.Add((openLine.Value, lastLine));
            }

            return ranges;
        }

        /// <summary>
        /// 判断 pragma 指令是否影响 IDE1006（无错误码视为禁用全部）
        /// </summary>
        private static bool AffectsIde1006(PragmaWarningDirectiveTriviaSyntax directive)
        {
            if (directive.ErrorCodes.Count == 0)
            {
                return true;
            }

            foreach (ExpressionSyntax errorCode in directive.ErrorCodes)
            {
                if (string.Equals(errorCode.ToString().Trim(), "IDE1006", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// 判断行号是否落在被禁用的行区间内
        /// </summary>
        private static bool IsLineSuppressed(List<(int Start, int End)> ranges, int line)
        {
            foreach ((int start, int end) in ranges)
            {
                if (line >= start && line <= end)
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// 判断符号自身是否带 SuppressMessage("Style", "IDE1006…")
        /// </summary>
        private static bool HasSuppressMessageAttribute(ISymbol symbol)
        {
            foreach (AttributeData attribute in symbol.GetAttributes())
            {
                if (attribute.AttributeClass?.ToDisplayString() != "System.Diagnostics.CodeAnalysis.SuppressMessageAttribute")
                {
                    continue;
                }

                if (IsIde1006Suppression(attribute))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// 判断符号是否被程序集级 SuppressMessage 的 Target 命中（如 Target = "~E:Game.Excel.L10n.mOnValueChanged"）
        /// </summary>
        private static bool IsAssemblySuppressed(ISymbol symbol, Compilation compilation)
        {
            if (s_assemblySuppressedTargets == null)
            {
                s_assemblySuppressedTargets = new HashSet<string>(StringComparer.Ordinal);
                foreach (AttributeData attribute in compilation.Assembly.GetAttributes())
                {
                    if (attribute.AttributeClass?.ToDisplayString() != "System.Diagnostics.CodeAnalysis.SuppressMessageAttribute"
                        || !IsIde1006Suppression(attribute))
                    {
                        continue;
                    }

                    foreach (KeyValuePair<string, TypedConstant> pair in attribute.NamedArguments)
                    {
                        if (pair.Key == "Target" && pair.Value.Value is string target && target.Length > 0)
                        {
                            s_assemblySuppressedTargets.Add(target.TrimStart('~'));
                        }
                    }
                }
            }

            string documentId = symbol.GetDocumentationCommentId();
            return documentId != null && s_assemblySuppressedTargets.Contains(documentId);
        }

        /// <summary>
        /// 判断 SuppressMessage 是否针对 IDE1006（Category = Style，CheckId 形如 "IDE1006:命名样式"）
        /// </summary>
        private static bool IsIde1006Suppression(AttributeData attribute)
        {
            if (attribute.ConstructorArguments.Length < 2)
            {
                return false;
            }

            string category = attribute.ConstructorArguments[0].Value as string;
            string checkId = attribute.ConstructorArguments[1].Value as string;
            if (checkId == null || !string.Equals(category, "Style", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            int colon = checkId.IndexOf(':');
            string identifier = (colon >= 0 ? checkId.Substring(0, colon) : checkId).Trim();
            return string.Equals(identifier, "IDE1006", StringComparison.OrdinalIgnoreCase);
        }

        // 在目标工程中找出第一个待重命名的符号
        private static async Task<(ISymbol Symbol, string Location, string NewName)?> FindNextAsync(
            Solution solution,
            HashSet<string> targetProjects,
            NamingRuleSet ruleSet,
            string projectRoot,
            List<string> excludeDirs)
        {
            foreach (Project project in solution.Projects)
            {
                if (!targetProjects.Contains(project.Name))
                {
                    continue;
                }

                Compilation compilation = await project.GetCompilationAsync();

                foreach (Document document in project.Documents)
                {
                    if (document.FilePath == null)
                    {
                        continue;
                    }

                    // 跳过项目配置声明的忽略目录（三方库与生成代码）
                    if (IsExcluded(document.FilePath, projectRoot, excludeDirs))
                    {
                        continue;
                    }

                    // 跳过生成代码（<auto-generated> 标记），改名会被下次生成覆盖
                    SourceText sourceText = await document.GetTextAsync();
                    string fullText = sourceText.ToString();
                    string fileHead = fullText.Length > 512 ? fullText.Substring(0, 512) : fullText;
                    if (fileHead.Contains("<auto-generated>", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    SyntaxNode root = await document.GetSyntaxRootAsync();
                    SemanticModel model = await document.GetSemanticModelAsync();
                    if (root == null || model == null)
                    {
                        continue;
                    }

                    // 本文件内 #pragma warning disable IDE1006 的生效区间（被抑制的符号不参与改名）
                    List<(int Start, int End)> pragmaRanges = BuildPragmaDisabledRanges(root);

                    foreach (SyntaxNode node in root.DescendantNodes())
                    {
                        ISymbol symbol;
                        if (node is VariableDeclaratorSyntax variable
                            && variable.Parent is VariableDeclarationSyntax declaration
                            && declaration.Parent is BaseFieldDeclarationSyntax)
                        {
                            symbol = model.GetDeclaredSymbol(variable);
                        }
                        else if (node is MethodDeclarationSyntax || node is PropertyDeclarationSyntax || node is EventDeclarationSyntax)
                        {
                            symbol = model.GetDeclaredSymbol(node);
                        }
                        else if (node is ParameterSyntax || node is EnumDeclarationSyntax)
                        {
                            symbol = model.GetDeclaredSymbol(node);
                        }
                        else
                        {
                            continue;
                        }

                        if (symbol == null)
                        {
                            continue;
                        }

                        // 去重键必须带声明位置：不同方法中同名同类型的参数显示名相同，只按显示名会漏处理
                        FileLinePositionSpan span = node.GetLocation().GetLineSpan();
                        string location = $"{Path.GetFileName(document.FilePath)}:{span.StartLinePosition.Line + 1}";
                        string key = $"{symbol.ToDisplayString()}@{document.FilePath}:{span.StartLinePosition.Line}:{span.StartLinePosition.Character}";
                        if (s_handled.Contains(key))
                        {
                            continue;
                        }

                        string newName = TryGetNewName(symbol, ruleSet);
                        if (newName == null)
                        {
                            s_handled.Add(key);
                            continue;
                        }

                        // 抑制器豁免：被 #pragma / SuppressMessage 抑制的符号视为有意保留，不改名
                        int declarationLine = span.StartLinePosition.Line;
                        if (IsLineSuppressed(pragmaRanges, declarationLine)
                            || HasSuppressMessageAttribute(symbol)
                            || (compilation != null && IsAssemblySuppressed(symbol, compilation)))
                        {
                            s_handled.Add(key);
                            continue;
                        }

                        s_handled.Add(key);
                        return (symbol, location, newName);
                    }
                }
            }

            return null;
        }

        // 计算新名称；不合规、无法推导或存在重名冲突时返回 null
        private static string TryGetNewName(ISymbol symbol, NamingRuleSet ruleSet)
        {
            if (symbol.IsImplicitlyDeclared || symbol.Name.Length == 0)
            {
                return null;
            }

            // 字段的占位名（_ / s 等单字符）无法推导，跳过；参数与局部变量单字符可正常转小写
            if (symbol is IFieldSymbol && symbol.Name.Length <= 1)
            {
                return null;
            }

            if (!IsSupported(symbol))
            {
                return null;
            }

            if (!ruleSet.TryBuildName(symbol, out string newName) || newName == symbol.Name)
            {
                return null;
            }

            // 重名预检：参数查所属方法（含方法体局部变量），类型查所属命名空间，其余查所属类型
            if (symbol is IParameterSymbol parameter)
            {
                if (parameter.ContainingSymbol is IMethodSymbol method)
                {
                    if (method.Parameters.Any(item => item.Name == newName
                        && !SymbolEqualityComparer.Default.Equals(item, parameter)))
                    {
                        return null;
                    }

                    // 方法体内的局部变量/局部函数同名会被遮蔽，导致引用错位
                    if (HasLocalNameConflict(method, newName))
                    {
                        return null;
                    }
                }
            }
            else if (symbol is INamedTypeSymbol namedType)
            {
                if (namedType.ContainingNamespace != null
                    && namedType.ContainingNamespace.GetMembers(newName).Any())
                {
                    return null;
                }
            }
            else
            {
                INamedTypeSymbol containingType = symbol.ContainingType;
                if (containingType != null && containingType.GetMembers(newName).Length > 0)
                {
                    return null;
                }
            }

            return newName;
        }

        /// <summary>
        /// 判断方法体内是否已有同名局部变量或局部函数（参数改名会与其冲突）
        /// </summary>
        private static bool HasLocalNameConflict(IMethodSymbol method, string name)
        {
            foreach (SyntaxReference reference in method.DeclaringSyntaxReferences)
            {
                foreach (SyntaxNode node in reference.GetSyntax().DescendantNodes())
                {
                    if (node is VariableDeclaratorSyntax variable && variable.Identifier.ValueText == name)
                    {
                        return true;
                    }

                    if (node is LocalFunctionStatementSyntax localFunction && localFunction.Identifier.ValueText == name)
                    {
                        return true;
                    }
                }
            }

            return false;
        }

        // 只处理可安全改名的符号：字段、属性、普通方法、事件、参数与枚举类型；override 与显式接口实现跳过
        private static bool IsSupported(ISymbol symbol)
        {
            switch (symbol)
            {
                case IFieldSymbol:
                    return true;
                case IPropertySymbol property:
                    return !property.IsOverride && property.ExplicitInterfaceImplementations.Length == 0;
                case IEventSymbol evt:
                    return !evt.IsOverride && evt.ExplicitInterfaceImplementations.Length == 0;
                case IMethodSymbol method:
                    return method.MethodKind == MethodKind.Ordinary
                        && !method.IsOverride
                        && method.ExplicitInterfaceImplementations.Length == 0;
                case IParameterSymbol:
                    // 参数改名只影响方法体与 XML 注释，不影响调用方
                    return true;
                case INamedTypeSymbol type:
                    // 类型只处理枚举（当前 .editorconfig 仅对 enum 有前缀约束）
                    return type.TypeKind == TypeKind.Enum && !type.IsImplicitlyDeclared;
                default:
                    return false;
            }
        }

        // 把新解决方案中被改动的文档写回磁盘（保留原 BOM 状态与行尾）
        private static async Task WriteChangesAsync(Solution oldSolution, Solution newSolution)
        {
            foreach (ProjectChanges projectChanges in newSolution.GetChanges(oldSolution).GetProjectChanges())
            {
                foreach (DocumentId documentId in projectChanges.GetChangedDocuments())
                {
                    Document newDocument = newSolution.GetDocument(documentId);
                    if (newDocument?.FilePath == null)
                    {
                        continue;
                    }

                    SourceText text = await newDocument.GetTextAsync();
                    string content = text.ToString();
                    byte[] existing = File.Exists(newDocument.FilePath) ? await File.ReadAllBytesAsync(newDocument.FilePath) : Array.Empty<byte>();
                    bool hasBom = existing.Length >= 3 && existing[0] == 0xEF && existing[1] == 0xBB && existing[2] == 0xBF;
                    await File.WriteAllTextAsync(newDocument.FilePath, content, new UTF8Encoding(hasBom));
                    Console.WriteLine($"  写入 {Path.GetFileName(newDocument.FilePath)}");
                }
            }
        }
    }
}
