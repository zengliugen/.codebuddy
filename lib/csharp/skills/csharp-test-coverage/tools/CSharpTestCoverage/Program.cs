using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
namespace CSharpTestCoverage;

/// <summary>
/// C# 测试覆盖率静态分析工具入口。
/// 用法：
///   CSharpTestCoverage &lt;路径...&gt; [--config &lt;配置路径&gt;] [--json] [--project-root &lt;项目根&gt;]
/// 输出：
///   默认输出人类可读汇总；--json 输出 CoverageReport 结构化 JSON（裸对象）。
/// </summary>
public static class Program
{
    /// <summary>
    /// 程序入口。
    /// </summary>
    /// <param name="args">命令行参数。</param>
    /// <returns>退出码：0 成功 / 1 参数或执行错误。</returns>
    public static int Main(string[] args)
    {
        // Windows 控制台默认非 UTF-8，中文输出会乱码；显式切换编码。
        try
        {
            Console.OutputEncoding = Encoding.UTF8;
        }
        catch
        {
            // 某些宿主环境不支持设置编码，忽略即可
        }

        if (args.Length == 0 || args.Contains("--help") || args.Contains("-h"))
        {
            PrintUsage();
            return args.Length == 0 ? 1 : 0;
        }

        var targetPaths = new List<string>();
        var configPath = GetArgValue(args, "--config");
        var projectRootArg = GetArgValue(args, "--project-root");
        var jsonOutput = args.Contains("--json");
        var debugReferences = args.Contains("--debug-references");

        for (int i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            if (arg is "--config" or "--project-root")
            {
                i++; // 跳过参数值
                continue;
            }
            if (arg.StartsWith("--", StringComparison.Ordinal))
            {
                continue;
            }
            targetPaths.Add(arg);
        }

        if (targetPaths.Count == 0)
        {
            Console.Error.WriteLine("错误：至少需要一个目标路径。");
            PrintUsage();
            return 1;
        }

        foreach (var path in targetPaths)
        {
            if (!File.Exists(path) && !Directory.Exists(path))
            {
                Console.Error.WriteLine($"错误：路径不存在 - {path}");
                return 1;
            }
        }

        var projectRoot = ResolveProjectRoot(projectRootArg, targetPaths[0]);
        if (projectRoot == null)
        {
            Console.Error.WriteLine("错误：无法定位项目根目录（未找到 .git 或 CODEBUDDY.md）。");
            return 1;
        }

        CoverageConfig config;
        try
        {
            // 配置分层：引擎侧通用配置 + 项目侧配置（经索引定位）深度合并，项目侧值覆盖引擎侧。
            // 配置缺失/损坏即报错退出，不使用内置默认配置继续分析。
            var effectiveConfigPath = ConfigResolver.Resolve(configPath);
            config = CoverageConfig.Load(effectiveConfigPath);
        }
        catch (CoverageConfigException ex)
        {
            Console.Error.WriteLine($"错误：{ex.Message}");
            return 3;
        }

        var warnings = new List<string>();

        try
        {
            var report = Analyze(targetPaths, projectRoot, config, warnings);
            if (debugReferences)
            {
                DumpReferenceDiagnostics(report, projectRoot);
                return 0;
            }
            if (jsonOutput)
            {
                var options = new JsonSerializerOptions
                {
                    WriteIndented = true,
                    DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
                    Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                };
                Console.WriteLine(JsonSerializer.Serialize(report, options));
            }
            else
            {
                PrintSummary(report, projectRoot);
            }
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"执行失败：{ex.Message}");
            Console.Error.WriteLine(ex.StackTrace);
            return 1;
        }
    }

    /// <summary>
    /// 打印引用诊断信息（用于排查匹配失败）。
    /// </summary>
    private static void DumpReferenceDiagnostics(CoverageReport report, string projectRoot)
    {
        Console.WriteLine("=== 引用诊断 ===");
        Console.WriteLine($"成员总数：{report.MemberCount}");
        Console.WriteLine($"已覆盖：{report.CoveredCount}");
        Console.WriteLine();

        Console.WriteLine("--- 抽查 Queue.cs 各成员（含引用位置）---");
        foreach (var record in report.Records
            .Where(r => r.RelativeFile.EndsWith("Managed/Normal/Queue.cs", StringComparison.OrdinalIgnoreCase))
            .Take(20))
        {
            Console.WriteLine(
                $"{record.MemberKind,-12} {record.Member,-24} {record.CoverageState,-14} " +
                $"id={record.MemberId}");
            foreach (var site in record.ReferenceSites.Take(3))
            {
                Console.WriteLine($"    引用 <- {site.File}:{site.Line} ({site.Kind})");
            }
        }

        Console.WriteLine();
        Console.WriteLine("--- 已覆盖成员样例（前 20）---");
        foreach (var record in report.Records
            .Where(r => r.CoverageState == CoverageStates.Covered)
            .Take(20))
        {
            Console.WriteLine(
                $"{record.Member,-30} {record.MemberId} " +
                $"<- {record.ReferenceSites.FirstOrDefault()?.File}");
        }
    }

    /// <summary>
    /// 执行静态分析主流程。
    /// </summary>
    private static CoverageReport Analyze(
        List<string> targetPaths,
        string projectRoot,
        CoverageConfig config,
        List<string> warnings)
    {
        var runtimeFiles = new List<string>();
        var testFiles = new List<string>();

        foreach (var target in targetPaths)
        {
            DiscoverFiles(target, projectRoot, config, runtimeFiles, testFiles, warnings);
        }

        runtimeFiles = runtimeFiles.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        testFiles = testFiles.Distinct(StringComparer.OrdinalIgnoreCase).ToList();

        if (runtimeFiles.Count == 0)
        {
            warnings.Add("未发现任何运行时源码文件，请检查目标路径与 runtimeRoots 配置。");
        }

        var allFiles = runtimeFiles.Concat(testFiles).ToList();
        if (allFiles.Count == 0)
        {
            return new CoverageReport { Warnings = warnings };
        }

        var parseOptions = new CSharpParseOptions(
            LanguageVersion.Latest,
            preprocessorSymbols: new[] { "UNITY_EDITOR", "UNITY_2022", "UNITY_6000", "UNITY_6000_5_OR_NEWER" });

        var trees = new List<SyntaxTree>();
        foreach (var file in allFiles)
        {
            try
            {
                var text = File.ReadAllText(file);
                trees.Add(CSharpSyntaxTree.ParseText(text, parseOptions, path: file));
            }
            catch (Exception ex)
            {
                warnings.Add($"解析失败 {file}：{ex.Message}");
            }
        }

        var references = LoadMetadataReferences(projectRoot, warnings);
        var compilation = CSharpCompilation.Create(
            "CoverageAnalysis",
            trees,
            references,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary)
                .WithAllowUnsafe(true)
                .WithNullableContextOptions(NullableContextOptions.Enable));

        var runtimePathSet = new HashSet<string>(runtimeFiles, StringComparer.OrdinalIgnoreCase);
        var runtimeTrees = trees.Where(t => runtimePathSet.Contains(t.FilePath)).ToList();
        var testTrees = trees.Where(t => !runtimePathSet.Contains(t.FilePath)).ToList();

        var memberCollector = new RuntimeMemberCollector(config);
        var records = memberCollector.Collect(compilation, projectRoot, runtimeTrees, warnings);

        var referenceCollector = new TestReferenceCollector(config);
        var testReferences = referenceCollector.Collect(compilation, projectRoot, testTrees, warnings);

        var testFileSet = new HashSet<string>(
            testFiles.Select(f => RuntimeMemberCollector.MakeRelative(projectRoot, f)),
            StringComparer.OrdinalIgnoreCase);

        var matcher = new CoverageMatcher(config);
        matcher.Match(records, testReferences, projectRoot, testFileSet, warnings);

        return BuildReport(records, runtimeFiles.Count, warnings);
    }

    /// <summary>
    /// 构建汇总报告。
    /// </summary>
    private static CoverageReport BuildReport(
        List<CoverageRecord> records,
        int runtimeFileCount,
        List<string> warnings)
    {
        var report = new CoverageReport
        {
            Records = records,
            RuntimeFileCount = runtimeFileCount,
            MemberCount = records.Count,
            CoveredCount = records.Count(r => r.CoverageState == CoverageStates.Covered),
            WeakOnlyCount = records.Count(r => r.CoverageState == CoverageStates.WeakReference),
            UncoveredCount = records.Count(r => r.CoverageState == CoverageStates.Uncovered),
            Warnings = warnings,
        };

        // 零测试文件：该文件下所有成员均未被强引用
        report.ZeroTestFiles = records
            .GroupBy(r => r.RelativeFile, StringComparer.OrdinalIgnoreCase)
            .Where(g => g.All(r => r.CoverageState != CoverageStates.Covered))
            .Select(g => g.Key)
            .OrderBy(x => x, StringComparer.OrdinalIgnoreCase)
            .ToList();

        return report;
    }

    /// <summary>
    /// 发现目标路径下的源码文件，按运行时/测试分类。
    /// </summary>
    private static void DiscoverFiles(
        string target,
        string projectRoot,
        CoverageConfig config,
        List<string> runtimeFiles,
        List<string> testFiles,
        List<string> warnings)
    {
        var full = Path.GetFullPath(target);
        var files = new List<string>();

        if (File.Exists(full))
        {
            if (full.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
            {
                files.Add(full);
            }
            else
            {
                warnings.Add($"跳过非 .cs 文件：{full}");
            }
        }
        else if (Directory.Exists(full))
        {
            try
            {
                files.AddRange(Directory.GetFiles(full, "*.cs", SearchOption.AllDirectories));
            }
            catch (Exception ex)
            {
                warnings.Add($"目录遍历失败 {full}：{ex.Message}");
                return;
            }
        }

        foreach (var file in files)
        {
            var normalized = RuntimeMemberCollector.NormalizePath(file);
            var relative = RuntimeMemberCollector.MakeRelative(projectRoot, normalized);
            var isTest = config.IsTestPath(normalized) || config.IsTestPath(relative);

            // 测试文件优先判定：生成的**测试**代码必须计入分子，
            // 不能因带 <auto-generated /> 标记而被豁免（否则会显著低估覆盖率）。
            // 实测该项目 fixedmathematics 包 54 个 Gen 测试文件均带该标记。
            if (isTest)
            {
                testFiles.Add(file);
                continue;
            }

            if (config.IsExcluded(normalized))
            {
                continue;
            }
            if (config.Exclude.AutoGenerated && IsAutoGenerated(file, config.Exclude.AutoGeneratedScanLines))
            {
                continue;
            }

            var isRuntime = config.IsRuntimePath(relative);
            if (isRuntime)
            {
                runtimeFiles.Add(file);
            }
            // 既非测试也非运行时（如 Assets/Plugins 已排除、其他目录）：忽略
        }
    }

    /// <summary>
    /// 判断文件是否为自动生成代码（只扫描文件头部若干行）。
    /// </summary>
    private static bool IsAutoGenerated(string filePath, int scanLines)
    {
        try
        {
            using var reader = new StreamReader(filePath);
            for (int i = 0; i < scanLines; i++)
            {
                var line = reader.ReadLine();
                if (line == null)
                {
                    break;
                }
                if (line.Contains("<auto-generated", StringComparison.OrdinalIgnoreCase) ||
                    line.Contains("<auto generated", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
        }
        catch
        {
            // 读取失败时保守地不判定为生成代码
        }
        return false;
    }

    /// <summary>
    /// 加载程序集引用（Unity Library/ScriptAssemblies 优先）。
    ///
    /// **为什么必须补入 Unity 参考程序集（corlib）**：
    /// `Library/ScriptAssemblies/*.dll` 是用 Unity 的 mscorlib 编译的，其中不含 corlib 本身。
    /// 若只加载 ScriptAssemblies + 宿主 .NET 的 System dll，编译会缺 `mscorlib` /
    /// `System.ValueType` / `System.Object` 等预定义类型，产生 CS0518 / CS0012 错误。
    /// 实测后果有两项，且都直接损害统计准确性：
    ///   1. `&lt;&lt;` / `&gt;&gt;` 与全部 `op_Explicit` / `op_Implicit` 转换运算符绑定失败
    ///      （用户定义运算符解析需要完整的类型系统）；
    ///   2. 特殊类型（Int32 / Boolean / String 等）无法解析，`GetDocumentationCommentId`
    ///      退化为短名（`Int32`），与测试侧解析出的全名（`System.Int32`）不一致，
    ///      导致运算符、含基元类型参数的方法两侧文档 ID 无法对齐。
    /// 补入 Unity 官方参考程序集后：编译错误 0、运算符绑定 12/12、两侧 ID 统一。
    /// </summary>
    private static List<MetadataReference> LoadMetadataReferences(string projectRoot, List<string> warnings)
    {
        var references = new List<MetadataReference>();
        // 去重键用文件全路径，避免同一程序集被重复加载（CS1704 重复程序集）。
        var loadedPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        var scriptAssemblies = Path.Combine(projectRoot, "Library", "ScriptAssemblies");
        int scriptCount = 0;
        if (Directory.Exists(scriptAssemblies))
        {
            foreach (var dll in Directory.GetFiles(scriptAssemblies, "*.dll"))
            {
                if (TryAddReference(references, loadedPaths, dll))
                {
                    scriptCount++;
                }
            }
        }

        if (scriptCount == 0)
        {
            warnings.Add("未找到 Library/ScriptAssemblies，符号解析精度将下降（纯语法模式）。");
        }

        // Unity 参考程序集（corlib 与门面程序集）：必须在 ScriptAssemblies 之后加载，
        // 用于补齐 mscorlib / System.ValueType 等预定义类型。
        var unityReferenceCount = LoadUnityReferenceAssemblies(
            projectRoot, references, loadedPaths);

        // 基础运行时引用：宿主 .NET 的 System dll，提供 ScriptAssemblies 之外的托管类型。
        var runtimeDir = Path.GetDirectoryName(typeof(object).Assembly.Location);
        if (runtimeDir != null)
        {
            foreach (var lib in new[] { "System.Runtime.dll", "System.Collections.dll", "System.Linq.dll", "System.Console.dll" })
            {
                TryAddReference(references, loadedPaths, Path.Combine(runtimeDir, lib));
            }
        }

        if (unityReferenceCount == 0 && scriptCount > 0)
        {
            warnings.Add(
                "未找到 Unity 参考程序集（corlib），运算符与转换运算符的引用采集可能不完整；" +
                "请确认 Library/EditorInstance.json 可读，或 Unity 安装目录下存在 UnityReferenceAssemblies。");
        }

        return references;
    }

    /// <summary>
    /// 加载 Unity 参考程序集（corlib 所在目录及其 Facades 门面目录）。
    ///
    /// 定位方式（按可靠性排序）：
    ///   1. `Library/EditorInstance.json` 的 `app_contents_path`，指向当前 Unity 安装的 Data 目录；
    ///   2. Unity 生成的 csproj 中 `mscorlib` 的 `HintPath`。
    /// 两种方式都拿不到时返回 0 并由调用方告警，不猜测硬编码路径。
    /// </summary>
    /// <param name="projectRoot">项目根目录。</param>
    /// <param name="references">引用列表（就地追加）。</param>
    /// <param name="loadedPaths">已加载文件路径集合（用于去重）。</param>
    /// <returns>成功加载的参考程序集数量。</returns>
    private static int LoadUnityReferenceAssemblies(
        string projectRoot,
        List<MetadataReference> references,
        HashSet<string> loadedPaths)
    {
        var profileDir = ResolveUnityReferenceProfileDir(projectRoot);
        if (profileDir == null)
        {
            return 0;
        }

        var count = 0;
        foreach (var dll in Directory.GetFiles(profileDir, "*.dll"))
        {
            if (TryAddReference(references, loadedPaths, dll))
            {
                count++;
            }
        }

        // Facades 提供 netstandard / System.Runtime 等门面程序集，
        // 缺失会导致面向 netstandard 编译的程序集无法解析引用。
        var facadesDir = Path.Combine(profileDir, "Facades");
        if (Directory.Exists(facadesDir))
        {
            foreach (var dll in Directory.GetFiles(facadesDir, "*.dll"))
            {
                if (TryAddReference(references, loadedPaths, dll))
                {
                    count++;
                }
            }
        }

        return count;
    }

    /// <summary>
    /// 解析 Unity 参考程序集 profile 目录（含 mscorlib.dll 的目录）。
    /// </summary>
    /// <param name="projectRoot">项目根目录。</param>
    /// <returns>profile 目录绝对路径；无法定位时返回 null。</returns>
    private static string? ResolveUnityReferenceProfileDir(string projectRoot)
    {
        var dataDirs = new List<string>();

        // 方式 1：Library/EditorInstance.json 的 app_contents_path
        var editorInstancePath = Path.Combine(projectRoot, "Library", "EditorInstance.json");
        if (File.Exists(editorInstancePath))
        {
            try
            {
                using var document = JsonDocument.Parse(File.ReadAllText(editorInstancePath));
                if (document.RootElement.TryGetProperty("app_contents_path", out var contentsPath))
                {
                    var value = contentsPath.GetString();
                    if (!string.IsNullOrWhiteSpace(value))
                    {
                        dataDirs.Add(value);
                    }
                }
            }
            catch
            {
                // EditorInstance.json 解析失败时走 csproj 兜底
            }
        }

        // 方式 2：Unity 生成的 csproj 中 mscorlib 的 HintPath（取其所属 Data 目录）
        foreach (var csproj in Directory.GetFiles(projectRoot, "Assembly-CSharp*.csproj"))
        {
            try
            {
                var text = File.ReadAllText(csproj);
                var match = System.Text.RegularExpressions.Regex.Match(
                    text,
                    @"<HintPath>([^<]*[\\/]UnityReferenceAssemblies[\\/][^<]*)</HintPath>",
                    System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                if (match.Success)
                {
                    // 由 .../Data/UnityReferenceAssemblies/<profile>/mscorlib.dll 回推 Data 目录
                    var hint = match.Groups[1].Value;
                    var markerIndex = hint.IndexOf("UnityReferenceAssemblies", StringComparison.OrdinalIgnoreCase);
                    if (markerIndex > 0)
                    {
                        var dataDir = hint[..markerIndex].TrimEnd('\\', '/');
                        if (Directory.Exists(dataDir))
                        {
                            dataDirs.Add(dataDir);
                        }
                    }
                }
            }
            catch
            {
                // 单个 csproj 读取失败时跳过
            }
        }

        foreach (var dataDir in dataDirs)
        {
            var root = Path.Combine(dataDir, "UnityReferenceAssemblies");
            if (!Directory.Exists(root))
            {
                continue;
            }
            // 选定含 mscorlib.dll 的 profile；多个时取版本号最高者（如 unity-4.8-api 优先于 unity-4.7.1-api）
            var profile = Directory.GetDirectories(root)
                .Where(d => File.Exists(Path.Combine(d, "mscorlib.dll")))
                .OrderByDescending(d => Path.GetFileName(d), StringComparer.OrdinalIgnoreCase)
                .FirstOrDefault();
            if (profile != null)
            {
                return profile;
            }
        }

        return null;
    }

    /// <summary>
    /// 尝试加载单个程序集引用，按文件路径去重。
    /// </summary>
    /// <param name="references">引用列表。</param>
    /// <param name="loadedPaths">已加载路径集合。</param>
    /// <param name="path">程序集文件路径。</param>
    /// <returns>是否成功新增。</returns>
    private static bool TryAddReference(
        List<MetadataReference> references,
        HashSet<string> loadedPaths,
        string path)
    {
        if (!File.Exists(path) || !loadedPaths.Add(path))
        {
            return false;
        }
        try
        {
            references.Add(MetadataReference.CreateFromFile(path));
            return true;
        }
        catch
        {
            // 个别 dll 无法加载时跳过
            return false;
        }
    }

    /// <summary>
    /// 定位项目根目录（含 .git 或 CODEBUDDY.md 的目录）。
    /// </summary>
    private static string? ResolveProjectRoot(string? explicitRoot, string samplePath)
    {
        if (!string.IsNullOrEmpty(explicitRoot))
        {
            var full = Path.GetFullPath(explicitRoot);
            return Directory.Exists(full) ? RuntimeMemberCollector.NormalizePath(full) : null;
        }

        var dir = File.Exists(samplePath)
            ? Path.GetDirectoryName(Path.GetFullPath(samplePath))
            : Path.GetFullPath(samplePath);

        while (!string.IsNullOrEmpty(dir))
        {
            if (Directory.Exists(Path.Combine(dir, ".git")) ||
                File.Exists(Path.Combine(dir, "CODEBUDDY.md")))
            {
                return RuntimeMemberCollector.NormalizePath(dir);
            }
            var parent = Path.GetDirectoryName(dir);
            if (parent == dir)
            {
                break;
            }
            dir = parent;
        }
        return null;
    }

    /// <summary>
    /// 获取 --name value 形式的参数值。
    /// </summary>
    private static string? GetArgValue(string[] args, string name)
    {
        var index = Array.IndexOf(args, name);
        if (index >= 0 && index + 1 < args.Length)
        {
            return args[index + 1];
        }
        return null;
    }

    /// <summary>
    /// 打印人类可读汇总。
    /// </summary>
    private static void PrintSummary(CoverageReport report, string projectRoot)
    {
        Console.WriteLine("=== C# 测试覆盖率静态分析 ===");
        Console.WriteLine($"运行时文件数：{report.RuntimeFileCount}");
        Console.WriteLine($"成员总数：{report.MemberCount}");
        Console.WriteLine($"已覆盖（强引用）：{report.CoveredCount}");
        Console.WriteLine($"仅弱引用：{report.WeakOnlyCount}");
        Console.WriteLine($"未覆盖：{report.UncoveredCount}");
        Console.WriteLine($"零测试文件数：{report.ZeroTestFiles.Count}");

        if (report.MemberCount > 0)
        {
            var rate = 100.0 * report.CoveredCount / report.MemberCount;
            Console.WriteLine($"成员覆盖率：{rate:F2}%");
        }

        Console.WriteLine();
        Console.WriteLine("提示：使用 --json 获取完整结构化记录。");

        if (report.Warnings.Count > 0)
        {
            Console.WriteLine();
            Console.WriteLine("告警：");
            foreach (var warning in report.Warnings.Take(20))
            {
                Console.WriteLine($"  - {warning}");
            }
        }
    }

    /// <summary>
    /// 打印用法说明。
    /// </summary>
    private static void PrintUsage()
    {
        Console.WriteLine("用法：CSharpTestCoverage <路径...> [--config <配置路径>] [--project-root <项目根>] [--json]");
        Console.WriteLine();
        Console.WriteLine("  <路径...>            目标包/目录/文件（可多个）");
        Console.WriteLine("  --config <路径>       覆盖率配置文件（默认取程序目录下的 coverage_config.json）");
        Console.WriteLine("  --project-root <路径> 项目根目录（默认自动向上查找 .git / CODEBUDDY.md）");
        Console.WriteLine("  --json               输出结构化 JSON（裸对象）");
    }
}
