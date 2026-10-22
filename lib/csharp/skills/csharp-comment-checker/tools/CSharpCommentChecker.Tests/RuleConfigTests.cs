using Xunit;

namespace CSharpCommentChecker.Tests;

/// <summary>
/// 规则配置单元测试，验证 Issue 级别的 enabled 开关逻辑。
/// </summary>
public class RuleConfigTests
{
    [Fact]
    public void IsIssueEnabled_IssueLevelEnabledTrue_ReturnsTrue()
    {
        var rules = new CommentRules
        {
            Rules = new Dictionary<string, RuleConfig>
            {
                ["test_rule"] = new()
                {
                    Enabled = true,
                    Issues = new()
                    {
                        ["test_category"] = new IssueConfig { Enabled = true, Severity = "warning" }
                    }
                }
            }
        };

        Assert.True(rules.IsIssueEnabled("test_rule", "test_category"));
    }

    [Fact]
    public void IsIssueEnabled_IssueLevelEnabledFalse_ReturnsFalse()
    {
        var rules = new CommentRules
        {
            Rules = new Dictionary<string, RuleConfig>
            {
                ["test_rule"] = new()
                {
                    Enabled = true,
                    Issues = new()
                    {
                        ["test_category"] = new IssueConfig { Enabled = false, Severity = "warning" }
                    }
                }
            }
        };

        Assert.False(rules.IsIssueEnabled("test_rule", "test_category"));
    }

    [Fact]
    public void IsIssueEnabled_IssueLevelEnabledDefault_ReturnsTrue()
    {
        // IssueConfig.Enabled 默认为 true
        var rules = new CommentRules
        {
            Rules = new Dictionary<string, RuleConfig>
            {
                ["test_rule"] = new()
                {
                    Enabled = true,
                    Issues = new()
                    {
                        ["test_category"] = new IssueConfig { Severity = "warning" }
                    }
                }
            }
        };

        Assert.True(rules.IsIssueEnabled("test_rule", "test_category"));
    }

    [Fact]
    public void IsIssueEnabled_RuleLevelDisabled_ReturnsFalse()
    {
        var rules = new CommentRules
        {
            Rules = new Dictionary<string, RuleConfig>
            {
                ["test_rule"] = new()
                {
                    Enabled = false,
                    Issues = new()
                    {
                        ["test_category"] = new IssueConfig { Enabled = true, Severity = "warning" }
                    }
                }
            }
        };

        Assert.False(rules.IsIssueEnabled("test_rule", "test_category"));
    }

    [Fact]
    public void IsIssueEnabled_CategoryNotInIssues_ReturnsFalse()
    {
        var rules = new CommentRules
        {
            Rules = new Dictionary<string, RuleConfig>
            {
                ["test_rule"] = new()
                {
                    Enabled = true,
                    Issues = new()
                    {
                        ["other_category"] = new IssueConfig { Enabled = true, Severity = "warning" }
                    }
                }
            }
        };

        Assert.False(rules.IsIssueEnabled("test_rule", "test_category"));
    }
}
