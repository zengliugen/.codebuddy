using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

/// <summary>
/// 代码摘要提取工具方法，提供从语法节点生成人类可读摘要的辅助函数。
/// </summary>
internal static class SnippetHelpers
{
    /// <summary>
    /// 从语法节点提取声明摘要字符串。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <returns>声明摘要字符串。</returns>
    public static string GetDeclarationSnippet(SyntaxNode node)
    {
        return node switch
        {
            MethodDeclarationSyntax m => ExtractSignature(m),
            ClassDeclarationSyntax c => $"class {c.Identifier.Text}",
            InterfaceDeclarationSyntax i => $"interface {i.Identifier.Text}",
            StructDeclarationSyntax s => $"struct {s.Identifier.Text}",
            EnumDeclarationSyntax e => $"enum {e.Identifier.Text}",
            PropertyDeclarationSyntax p => p.ToString().Split('\n')[0].Trim(),
            FieldDeclarationSyntax f => f.ToString().Split('\n')[0].Trim(),
            DelegateDeclarationSyntax d => $"delegate {d.Identifier.Text}",
            EventFieldDeclarationSyntax ef => $"event {ef.Declaration.Variables.First().Identifier.Text}",
            EventDeclarationSyntax ev => $"event {ev.Identifier.Text}",
            ConstructorDeclarationSyntax ctor => ExtractSignature(ctor),
            _ => node.ToString().Split('\n')[0].Trim()
        };
    }

    /// <summary>
    /// 提取行内代码摘要（关联代码行的文本）。
    /// </summary>
    /// <param name="node">语法节点。</param>
    /// <param name="contextType">上下文类型（仅用于调用方语义区分）。</param>
    /// <returns>代码行文本。</returns>
    public static string GetInlineCodeSnippet(SyntaxNode node, string contextType)
    {
        var location = node.GetLocation();
        if (location == null) return "";
        var lineSpan = location.GetLineSpan().StartLinePosition;
        var sourceText = node.SyntaxTree.GetText();
        var lineText = sourceText.Lines[lineSpan.Line].ToString().Trim();
        return lineText;
    }

    /// <summary>
    /// 提取方法/构造函数签名字符串。
    /// </summary>
    /// <param name="method">方法或构造函数声明。</param>
    /// <returns>签名字符串。</returns>
    private static string ExtractSignature(BaseMethodDeclarationSyntax method)
    {
        var parameters = string.Join(", ",
            method.ParameterList.Parameters.Select(p => $"{p.Type} {p.Identifier}"));
        var returnType = method is MethodDeclarationSyntax m
            ? m.ReturnType.ToString()
            : "";
        var name = method is MethodDeclarationSyntax md
            ? md.Identifier.Text
            : (method as ConstructorDeclarationSyntax)?.Identifier.Text ?? "";
        return returnType.Length > 0
            ? $"{returnType} {name}({parameters})"
            : $"{name}({parameters})";
    }
}
