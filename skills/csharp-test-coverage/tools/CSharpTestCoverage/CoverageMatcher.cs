namespace CSharpTestCoverage;

/// <summary>
/// 覆盖率匹配器。
/// 将测试侧引用（以文档注释 ID 为键）与运行时成员记录对齐，
/// 计算强引用覆盖、弱引用命中与骨架落地建议。
/// </summary>
public class CoverageMatcher
{
    private readonly CoverageConfig _config;

    /// <summary>
    /// 使用指定配置初始化匹配器。
    /// </summary>
    /// <param name="config">覆��率配置。</param>
    public CoverageMatcher(CoverageConfig config)
    {
        _config = config;
    }

    /// <summary>
    /// 执行匹配并填充覆盖率状态。
    /// </summary>
    /// <param name="records">运行时成员记录（将被就地修改）。</param>
    /// <param name="references">测试引用列表。</param>
    /// <param name="projectRoot">项目根目录（正斜杠归一化）。</param>
    /// <param name="testFileMap">测试文件存在性映射（相对路径 → 是否存在）。</param>
    /// <param name="warnings">告警收集器。</param>
    public void Match(
        List<CoverageRecord> records,
        List<TestReference> references,
        string projectRoot,
        IReadOnlySet<string> testFileMap,
        List<string> warnings)
    {
        // 建立文档 ID → 记录 的索引（文档 ID 天然消歧同名类型与重载）
        var byId = new Dictionary<string, List<CoverageRecord>>(StringComparer.Ordinal);
        foreach (var record in records)
        {
            if (!byId.TryGetValue(record.MemberId, out var list))
            {
                list = new List<CoverageRecord>();
                byId[record.MemberId] = list;
            }
            list.Add(record);
        }

        // 反射字符串引用单独收集：类型键 → 成员名集合
        var reflectionMembers = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
        var reflectionGlobal = new HashSet<string>(StringComparer.Ordinal);

        int matched = 0;
        int weakMatched = 0;

        foreach (var reference in references)
        {
            if (reference.Kind == "reflection_string")
            {
                // 反射字符串：记录成员名，稍后按成员名匹配
                if (!string.IsNullOrEmpty(reference.TypeFullName))
                {
                    if (!reflectionMembers.TryGetValue(reference.TypeFullName, out var set))
                    {
                        set = new HashSet<string>(StringComparer.Ordinal);
                        reflectionMembers[reference.TypeFullName] = set;
                    }
                    set.Add(reference.MemberName);
                }
                else
                {
                    reflectionGlobal.Add(reference.MemberName);
                }
                continue;
            }

            if (reference.Kind == "xml_cref")
            {
                // XML cref：按文档 ID 前缀或类型名松散匹配（弱引用）
                if (ApplyXmlCref(records, byId, reference))
                {
                    weakMatched++;
                }
                continue;
            }

            if (byId.TryGetValue(reference.TypeFullName, out var targets))
            {
                foreach (var target in targets)
                {
                    AddReferenceSite(target, reference, isWeak: reference.IsWeak);
                    matched++;
                }
            }
        }

        // 反射字符串按「类型键 + 成员名」优先，退化为全局成员名
        foreach (var record in records)
        {
            if (record.ReferenceCount > 0)
            {
                continue;
            }

            var typeKey = FindTypeKeyForRecord(byId, record);
            var hit = false;

            if (typeKey != null && reflectionMembers.TryGetValue(typeKey, out var members) &&
                members.Contains(record.Member))
            {
                hit = true;
            }
            else if (reflectionGlobal.Contains(record.Member))
            {
                hit = true;
            }

            if (hit)
            {
                record.WeakReferenceCount++;
                record.WeakReferenceSites.Add(new ReferenceSite
                {
                    File = "(reflection)",
                    Line = 0,
                    Kind = "reflection_string",
                });
            }
        }

        FinalizeState(records);
        AssignCounterpart(records, projectRoot, testFileMap);
        AssignSkeletonAction(records, testFileMap);
    }

    /// <summary>
    /// 应用 XML cref 弱引用（按文档 ID 前缀匹配类型，命中即记弱引用）。
    /// </summary>
    private bool ApplyXmlCref(
        List<CoverageRecord> records,
        Dictionary<string, List<CoverageRecord>> byId,
        TestReference reference)
    {
        var raw = reference.TypeFullName.Trim();
        // cref 文本形如 "CacheDictionary{TKey,TValue}.Remove" 或 "Queue.Enqueue"
        var typePart = raw.Split('(')[0];
        var lastDot = typePart.LastIndexOf('.');
        var typeName = lastDot > 0 ? typePart[..lastDot] : typePart;
        var memberName = lastDot > 0 ? typePart[(lastDot + 1)..] : string.Empty;
        typeName = typeName.Replace('{', '<').Replace('}', '>');

        var applied = false;
        foreach (var record in records)
        {
            var recordTypeName = string.IsNullOrEmpty(record.Namespace)
                ? record.TypeName
                : record.Namespace + "." + record.TypeName;

            if (!recordTypeName.EndsWith(typeName, StringComparison.Ordinal) &&
                !record.TypeName.Equals(typeName, StringComparison.Ordinal))
            {
                continue;
            }

            if (!string.IsNullOrEmpty(memberName) &&
                !record.Member.Equals(memberName, StringComparison.Ordinal) &&
                !record.MemberId.EndsWith("." + memberName, StringComparison.Ordinal))
            {
                continue;
            }

            record.WeakReferenceSites.Add(new ReferenceSite
            {
                File = reference.File,
                Line = reference.Line,
                Kind = reference.Kind,
            });
            applied = true;
        }

        if (applied)
        {
            foreach (var record in records)
            {
                if (record.WeakReferenceSites.Any(s => s.File == reference.File && s.Line == reference.Line))
                {
                    record.WeakReferenceCount = record.WeakReferenceSites.Count;
                }
            }
        }
        return applied;
    }

    /// <summary>
    /// 查找记录所属类型的文档 ID（用于反射字符串按类型匹配）。
    /// </summary>
    private static string? FindTypeKeyForRecord(
        Dictionary<string, List<CoverageRecord>> byId,
        CoverageRecord record)
    {
        var recordTypeName = string.IsNullOrEmpty(record.Namespace)
            ? record.TypeName
            : record.Namespace + "." + record.TypeName;

        foreach (var key in byId.Keys)
        {
            if (key.StartsWith("T:", StringComparison.Ordinal))
            {
                var typeFullName = key[2..];
                if (typeFullName.Equals(recordTypeName, StringComparison.Ordinal))
                {
                    return key;
                }
            }
        }
        return null;
    }

    /// <summary>
    /// 添加强引用或弱引用位置。
    /// </summary>
    private void AddReferenceSite(CoverageRecord record, TestReference reference, bool isWeak)
    {
        var site = new ReferenceSite
        {
            File = reference.File,
            Line = reference.Line,
            Kind = reference.Kind,
        };

        if (isWeak)
        {
            record.WeakReferenceSites.Add(site);
        }
        else
        {
            record.ReferenceSites.Add(site);
        }
    }

    /// <summary>
    /// 依据配置与引用计数确定覆盖率状态。
    /// </summary>
    private void FinalizeState(List<CoverageRecord> records)
    {
        foreach (var record in records)
        {
            record.ReferenceCount = record.ReferenceSites.Count;
            record.WeakReferenceCount = record.WeakReferenceSites.Count;

            if (record.ReferenceCount > 0)
            {
                record.CoverageState = CoverageStates.Covered;
            }
            else if (record.WeakReferenceCount > 0)
            {
                record.CoverageState = _config.ReferenceStrength.CountWeakAsCovered
                    ? CoverageStates.Covered
                    : CoverageStates.WeakReference;
            }
            else
            {
                record.CoverageState = CoverageStates.Uncovered;
            }
        }
    }

    /// <summary>
    /// 依据目录镜像规则为每条记录指定对应测试文件。
    /// </summary>
    private void AssignCounterpart(
        List<CoverageRecord> records,
        string projectRoot,
        IReadOnlySet<string> testFileMap)
    {
        // 索引测试文件：主干名 → 相对路径列表
        var testByStem = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var testPath in testFileMap)
        {
            var stem = GetTestStem(testPath);
            if (stem == null)
            {
                continue;
            }
            if (!testByStem.TryGetValue(stem, out var list))
            {
                list = new List<string>();
                testByStem[stem] = list;
            }
            list.Add(testPath);
        }

        foreach (var record in records)
        {
            var mirror = BuildMirrorTestPath(record.RelativeFile);
            if (mirror != null)
            {
                // 目录镜像精确命中
                if (testFileMap.Contains(mirror))
                {
                    record.CounterpartTestFile = mirror;
                    continue;
                }

                // partial 专项：同目录下 <主干名>Tests.*.cs
                var dir = GetDirectory(mirror);
                var stem = GetStemFromMirror(mirror);
                var partial = testFileMap
                    .Where(p => GetDirectory(p).Equals(dir, StringComparison.OrdinalIgnoreCase) &&
                                GetStem(p).Equals(stem, StringComparison.OrdinalIgnoreCase))
                    .OrderBy(p => p.Length)
                    .FirstOrDefault();
                if (partial != null)
                {
                    record.CounterpartTestFile = partial;
                    continue;
                }
            }

            // 回退：命名空间 + 类型名
            if (_config.Matching.FallbackToNamespaceAndTypeName)
            {
                var recordTypeName = string.IsNullOrEmpty(record.Namespace)
                    ? record.TypeName
                    : record.Namespace + "." + record.TypeName;
                var byTypeName = testFileMap
                    .Where(p => GetStem(p).Equals(record.TypeName + "Tests", StringComparison.OrdinalIgnoreCase))
                    .ToList();
                if (byTypeName.Count == 1)
                {
                    record.CounterpartTestFile = byTypeName[0];
                }
                else if (byTypeName.Count > 1)
                {
                    // 同名类型：优先选择命名空间末段与记录一致的
                    var nsTail = record.Namespace.Split('.').LastOrDefault() ?? string.Empty;
                    var preferred = byTypeName
                        .FirstOrDefault(p => p.Contains("/" + nsTail + "/", StringComparison.OrdinalIgnoreCase));
                    record.CounterpartTestFile = preferred ?? byTypeName[0];
                }
            }
        }
    }

    /// <summary>
    /// 依据是否已有对应测试文件判定骨架落地方式。
    /// </summary>
    private void AssignSkeletonAction(List<CoverageRecord> records, IReadOnlySet<string> testFileMap)
    {
        foreach (var record in records)
        {
            if (record.CoverageState == CoverageStates.Covered)
            {
                record.SuggestedAction = SkeletonActions.None;
                continue;
            }

            if (!string.IsNullOrEmpty(record.CounterpartTestFile))
            {
                // 已有测试类 → 只能追加 partial 专项
                record.SuggestedAction = SkeletonActions.AppendPartial;
                record.SuggestedSkeletonFile = BuildPartialPath(record);
            }
            else
            {
                var mirror = BuildMirrorTestPath(record.RelativeFile);
                if (mirror != null)
                {
                    record.SuggestedAction = SkeletonActions.NewTestFile;
                    record.SuggestedSkeletonFile = mirror;
                }
                else
                {
                    record.SuggestedAction = SkeletonActions.None;
                }
            }
        }
    }

    /// <summary>
    /// 由运行时文件路径构建镜像测试文件路径。
    ///
    /// 本项目实测约定（core 包样板）：
    ///   <包>/Runtime/<相对路径>/Xxx.cs  →  <包>/Tests/Editor/<相对路径>/XxxTests.cs
    ///   <包>/Editor/<相对路径>/Xxx.cs   →  <包>/Tests/Editor/<相对路径>/XxxTests.cs
    /// 即：把 `Runtime/` 或 `Editor/` 段替换为 `Tests/Editor/`，其余相对路径原样保留。
    /// </summary>
    private string? BuildMirrorTestPath(string relativeRuntimeFile)
    {
        if (!relativeRuntimeFile.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        var normalized = relativeRuntimeFile.Replace('\\', '/');

        // 依次尝试 Runtime/ 与 Editor/ 两个根段
        foreach (var rootName in new[] { _config.Matching.RuntimeRootName, "Editor" })
        {
            var marker = "/" + rootName + "/";
            var index = normalized.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (index < 0)
            {
                continue;
            }

            var beforeRoot = normalized[..index];
            var afterRoot = normalized[(index + marker.Length)..];
            var innerDir = GetDirectory(afterRoot);
            var stem = GetStem(afterRoot);
            if (string.IsNullOrEmpty(stem))
            {
                return null;
            }

            // TestRootNames[0] 形如 "Tests/Editor"，已包含测试根段，直接拼接即可
            var testRoot = _config.Matching.TestRootNames[0];
            var testDir = string.IsNullOrEmpty(innerDir)
                ? beforeRoot + "/" + testRoot
                : beforeRoot + "/" + testRoot + "/" + innerDir;

            return testDir + "/" + stem + _config.Matching.TestFileSuffix + ".cs";
        }

        // 无 Runtime/ 与 Editor/ 段时，按包根直接镜像到测试根
        var dir = GetDirectory(normalized);
        var fileStem = GetStem(normalized);
        if (string.IsNullOrEmpty(dir) || string.IsNullOrEmpty(fileStem))
        {
            return null;
        }
        return dir + "/" + _config.Matching.TestRootNames[0] + "/" + fileStem
               + _config.Matching.TestFileSuffix + ".cs";
    }

    /// <summary>
    /// 构建 partial 专项文件路径（追加到已有测试类所在目录）。
    ///
    /// **按测试类聚合**：同一测试类的所有未覆盖成员共用一个骨架文件。
    /// 若按成员逐个拆分会产生大量碎片文件（如 `XxxTests.Zone.cs` / `XxxTests.Size.cs`），
    /// 违背 `naming-layout.mdc` 中「专项是语义主题而非单个成员」的约定。
    /// 主题名取成员种类的语义桶（Properties / Fields / Methods / Events / Coverage）。
    /// </summary>
    private string BuildPartialPath(CoverageRecord record)
    {
        var counterpart = record.CounterpartTestFile;
        var dir = GetDirectory(counterpart);
        var stem = GetStem(counterpart);          // 如 MemoryAllocatorTests
        var topic = InferCoverageTopic(record);
        return dir + "/" + stem + "." + topic + ".cs";
    }

    /// <summary>
    /// 由成员种类推断覆盖率专项主题名（按种类归并，避免每成员一个文件）。
    /// </summary>
    private static string InferCoverageTopic(CoverageRecord record)
    {
        return record.MemberKind switch
        {
            MemberKinds.Property => "Properties",
            MemberKinds.Field => "Fields",
            MemberKinds.Event => "Events",
            MemberKinds.EnumValue => "EnumValues",
            MemberKinds.Method => "Methods",
            MemberKinds.Constructor => "Construction",
            MemberKinds.Operator => "Operators",
            _ => "Coverage",
        };
    }

    /// <summary>
    /// 获取测试文件的类主干名（去掉 Tests 后缀与专项段）。
    /// </summary>
    private static string? GetTestStem(string testPath)
    {
        var stem = GetStem(testPath);
        if (string.IsNullOrEmpty(stem))
        {
            return null;
        }
        var dot = stem.IndexOf('.');
        return dot > 0 ? stem[..dot] : stem;
    }

    /// <summary>
    /// 由镜像路径取主干名。
    /// </summary>
    private static string GetStemFromMirror(string mirrorPath)
    {
        var stem = GetStem(mirrorPath);
        return stem;
    }

    /// <summary>
    /// 取路径的文件主干名（不含扩展名）。
    /// </summary>
    private static string GetStem(string path)
    {
        var name = path.Replace('\\', '/');
        var slash = name.LastIndexOf('/');
        if (slash >= 0)
        {
            name = name[(slash + 1)..];
        }
        var dot = name.LastIndexOf('.');
        return dot > 0 ? name[..dot] : name;
    }

    /// <summary>
    /// 取路径的目录部分。
    /// </summary>
    private static string GetDirectory(string path)
    {
        var normalized = path.Replace('\\', '/');
        var slash = normalized.LastIndexOf('/');
        return slash >= 0 ? normalized[..slash] : string.Empty;
    }
}
