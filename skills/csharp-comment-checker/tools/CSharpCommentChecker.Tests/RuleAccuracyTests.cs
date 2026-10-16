using System.Text.Json;
using Xunit;

namespace CSharpCommentChecker.Tests;

/// <summary>
/// 金标测试运行器，遍历 Fixtures/ 目录下的所有测试用例，
/// 对比 CommentChecker 的实际输出与期望输出。
/// </summary>
public class RuleAccuracyTests
{
    private static readonly string FixtureBaseDir = Path.Combine(AppContext.BaseDirectory, "Fixtures");
    private static readonly string ConfigPath = Path.Combine(
        AppContext.BaseDirectory, "test_comment_config.json");

    /// <summary>
    /// 自动发现所有 Fixtures 子目录中的测试用例。
    /// 每个 .cs 文件配对同名的 _expected.json 文件。
    /// </summary>
    public static IEnumerable<object[]> GetFixtureData()
    {
        if (!Directory.Exists(FixtureBaseDir))
            yield break;

        foreach (var subDir in Directory.GetDirectories(FixtureBaseDir))
        {
            foreach (var csFile in Directory.GetFiles(subDir, "*.cs"))
            {
                var expectedFile = csFile.Replace(".cs", "_expected.json");
                if (File.Exists(expectedFile))
                {
                    yield return new object[] { csFile, expectedFile };
                }
            }

            // 同时扫描 .cs_err 扩展名的 fixture（包含语法错误，避免被工具链编译）
            foreach (var csFile in Directory.GetFiles(subDir, "*.cs_err"))
            {
                var expectedFile = csFile.Replace(".cs_err", "_expected.json");
                if (File.Exists(expectedFile))
                {
                    yield return new object[] { csFile, expectedFile };
                }
            }
        }
    }

    [Theory]
    [MemberData(nameof(GetFixtureData))]
    public void VerifyCommentCheck(string csFile, string expectedJsonFile)
    {
        var expectedJson = File.ReadAllText(expectedJsonFile);
        var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
        var expected = JsonSerializer.Deserialize<List<ExpectedIssue>>(expectedJson, options) ?? new();
        var expectedIssues = expected
            .Select(e => new ExpectedIssue(e.Line, e.Severity, e.Category, e.Member, e.MemberType))
            .ToHashSet();

        var rules = CommentRules.Load(ConfigPath);
        var checker = new CommentChecker(rules);
        var actual = checker.CheckFile(csFile);
        var actualIssues = actual
            .Select(a => new ExpectedIssue(a.Line, a.Severity, a.Category, a.Member, a.MemberType))
            .ToHashSet();

        var missing = expectedIssues.Except(actualIssues).ToList();
        var unexpected = actualIssues.Except(expectedIssues).ToList();

        var errors = new List<string>();
        foreach (var m in missing)
            errors.Add($"MISSING: line={m.Line} severity={m.Severity} category={m.Category} member={m.Member}");
        foreach (var u in unexpected)
            errors.Add($"UNEXPECTED: line={u.Line} severity={u.Severity} category={u.Category} member={u.Member}");

        if (errors.Count > 0)
            Assert.Fail($"Fixture: {Path.GetFileName(csFile)}\n" + string.Join("\n", errors));
    }
}

/// <summary>
/// 金标测试中用于比对的 Issue 简化记录。
/// </summary>
public record ExpectedIssue(int Line, string Severity, string Category, string Member, string MemberType);
