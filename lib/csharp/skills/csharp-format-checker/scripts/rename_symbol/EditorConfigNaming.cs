// 解析项目根 .editorconfig 的 dotnet_naming_* 命名规则，并按 Roslyn 的优先级为符号选出对应样式
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.CodeAnalysis;

namespace RenameSymbolTool
{
    /// <summary>
    /// 命名样式：对应 .editorconfig 的 dotnet_naming_style.*（前缀/后缀/大小写）
    /// </summary>
    internal sealed class NamingStyle
    {
        public string Prefix = string.Empty;
        public string Suffix = string.Empty;
        public string Capitalization = string.Empty;
    }

    /// <summary>
    /// 命名符号集合：对应 .editorconfig 的 dotnet_naming_symbols.*（种类/访问级别/必需修饰符）
    /// </summary>
    internal sealed class NamingSymbols
    {
        public readonly HashSet<string> Kinds = new HashSet<string>(StringComparer.Ordinal);
        public readonly HashSet<string> Accessibilities = new HashSet<string>(StringComparer.Ordinal);
        public readonly HashSet<string> RequiredModifiers = new HashSet<string>(StringComparer.Ordinal);
    }

    /// <summary>
    /// 命名规则：对应 .editorconfig 的 dotnet_naming_rule.*（符号集合 + 样式 + 触发级别 + 声明顺序）
    /// </summary>
    internal sealed class NamingRule
    {
        public string Severity;
        public NamingSymbols Symbols;
        public NamingStyle Style;
        public int Order;
    }

    /// <summary>
    /// 命名规则集：加载、匹配与按样式推导新名称
    /// </summary>
    internal sealed class NamingRuleSet
    {
        private readonly List<NamingRule> m_rules = new List<NamingRule>();

        // 字段类样式声明的前缀（如 s/m），用于清理成员名上残留的字段前缀
        private readonly List<string> m_fieldPrefixes = new List<string>();

        public int RuleCount
        {
            get { return m_rules.Count; }
        }

        // 实际参与改名的规则数（severity 为 warning/error 的规则）
        public int EnforcedCount
        {
            get { return m_rules.Count(rule => IsEnforced(rule.Severity)); }
        }

        /// <summary>
        /// 读取并解析 .editorconfig 中的命名规则
        /// </summary>
        public static NamingRuleSet Load(string editorConfigPath)
        {
            var styles = new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
            var symbolGroups = new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
            var ruleGroups = new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
            var ruleOrder = new List<string>();

            foreach (string rawLine in File.ReadAllLines(editorConfigPath))
            {
                string line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal) || line.StartsWith(";", StringComparison.Ordinal))
                {
                    continue;
                }

                int separator = line.IndexOf('=');
                if (separator <= 0)
                {
                    continue;
                }

                string key = line.Substring(0, separator).Trim();
                string value = line.Substring(separator + 1).Trim();

                if (key.StartsWith("dotnet_naming_style.", StringComparison.Ordinal))
                {
                    if (TrySplitKey(key, "dotnet_naming_style.", out string name, out string property))
                    {
                        GetOrAdd(styles, name)[property] = value;
                    }
                }
                else if (key.StartsWith("dotnet_naming_symbols.", StringComparison.Ordinal))
                {
                    if (TrySplitKey(key, "dotnet_naming_symbols.", out string name, out string property))
                    {
                        GetOrAdd(symbolGroups, name)[property] = value;
                    }
                }
                else if (key.StartsWith("dotnet_naming_rule.", StringComparison.Ordinal))
                {
                    if (TrySplitKey(key, "dotnet_naming_rule.", out string name, out string property))
                    {
                        if (!ruleGroups.ContainsKey(name))
                        {
                            ruleGroups[name] = new Dictionary<string, string>(StringComparer.Ordinal);
                            ruleOrder.Add(name);
                        }

                        ruleGroups[name][property] = value;
                    }
                }
            }

            var ruleSet = new NamingRuleSet();
            for (int index = 0; index < ruleOrder.Count; index++)
            {
                string ruleName = ruleOrder[index];
                Dictionary<string, string> ruleProperties = ruleGroups[ruleName];
                if (!ruleProperties.TryGetValue("symbols", out string symbolsName)
                    || !ruleProperties.TryGetValue("style", out string styleName)
                    || !symbolGroups.TryGetValue(symbolsName, out Dictionary<string, string> symbolsProperties)
                    || !styles.TryGetValue(styleName, out Dictionary<string, string> styleProperties))
                {
                    continue;
                }

                var symbols = new NamingSymbols();
                AddAll(symbols.Kinds, GetValue(symbolsProperties, "applicable_kinds", "*"));
                AddAll(symbols.Accessibilities, GetValue(symbolsProperties, "applicable_accessibilities", "*"));
                AddAll(symbols.RequiredModifiers, GetValue(symbolsProperties, "required_modifiers", string.Empty));

                var style = new NamingStyle
                {
                    Prefix = GetValue(styleProperties, "required_prefix", string.Empty),
                    Suffix = GetValue(styleProperties, "required_suffix", string.Empty),
                    Capitalization = GetValue(styleProperties, "capitalization", string.Empty),
                };

                ruleSet.m_rules.Add(new NamingRule
                {
                    Severity = GetValue(ruleProperties, "severity", "warning"),
                    Symbols = symbols,
                    Style = style,
                    Order = index,
                });

                // 收集字段类样式前缀（field_* 样式），供成员名清理使用
                if (styleName.StartsWith("field", StringComparison.Ordinal)
                    && !string.IsNullOrEmpty(style.Prefix)
                    && !ruleSet.m_fieldPrefixes.Contains(style.Prefix))
                {
                    ruleSet.m_fieldPrefixes.Add(style.Prefix);
                }
            }

            // 长前缀优先匹配，避免短前缀误伤
            ruleSet.m_fieldPrefixes.Sort((left, right) => right.Length.CompareTo(left.Length));
            return ruleSet;
        }

        /// <summary>
        /// 按优先级为符号选出命名规则：必需修饰符多者优先，const 优先于 static，
        /// 其次访问级别更具体者优先，最后按声明顺序
        /// </summary>
        public bool TryBuildName(ISymbol symbol, out string newName)
        {
            newName = null;
            NamingRule matched = m_rules
                .Where(rule => IsEnforced(rule.Severity) && Matches(rule.Symbols, symbol))
                .OrderByDescending(rule => rule.Symbols.RequiredModifiers.Count)
                .ThenByDescending(rule => rule.Symbols.RequiredModifiers.Contains("const") ? 1 : 0)
                .ThenByDescending(rule => rule.Symbols.Accessibilities.Contains("*") ? 0 : 1)
                .ThenBy(rule => rule.Order)
                .FirstOrDefault();
            if (matched == null)
            {
                return false;
            }

            // 成员（方法/属性/事件）在目标样式无前缀时，清理名字上残留的字段前缀（如 mOnValueChanged）
            bool stripFieldPrefix = symbol is not IFieldSymbol;
            return TryBuildName(symbol.Name, matched.Style, stripFieldPrefix, out newName);
        }

        /// <summary>
        /// 按样式把原名称转换为合规新名称；无法推导时返回 false
        /// </summary>
        private bool TryBuildName(string original, NamingStyle style, bool stripFieldPrefix, out string newName)
        {
            newName = null;
            string name = original;

            bool hasPrefix = !string.IsNullOrEmpty(style.Prefix)
                && name.Length > style.Prefix.Length
                && name.StartsWith(style.Prefix, StringComparison.Ordinal)
                && char.IsUpper(name[style.Prefix.Length]);

            if (hasPrefix)
            {
                name = name.Substring(style.Prefix.Length);
            }
            else
            {
                // 去掉分组下划线，并迁移字段前缀（静态字段要求 s、实例字段要求 m）
                name = name.TrimStart('_');
                if (!string.IsNullOrEmpty(style.Prefix))
                {
                    foreach (string fieldPrefix in m_fieldPrefixes)
                    {
                        if (fieldPrefix != style.Prefix && IsLegacyPrefixed(name, fieldPrefix))
                        {
                            name = name.Substring(fieldPrefix.Length);
                            break;
                        }
                    }
                }
                else if (stripFieldPrefix)
                {
                    foreach (string fieldPrefix in m_fieldPrefixes)
                    {
                        if (IsLegacyPrefixed(name, fieldPrefix))
                        {
                            name = name.Substring(fieldPrefix.Length);
                            break;
                        }
                    }
                }
            }

            if (name.Length == 0)
            {
                return false;
            }

            name = ApplyCapitalization(name, style.Capitalization);
            if (!string.IsNullOrEmpty(style.Suffix) && !name.EndsWith(style.Suffix, StringComparison.Ordinal))
            {
                name += style.Suffix;
            }

            newName = style.Prefix + name;
            return true;
        }

        /// <summary>
        /// 是否参与改名：只有 warning / error 级别的规则生效；none 与 silent 不驱动改名
        /// </summary>
        private static bool IsEnforced(string severity)
        {
            return string.Equals(severity, "warning", StringComparison.OrdinalIgnoreCase)
                || string.Equals(severity, "error", StringComparison.OrdinalIgnoreCase);
        }

        private static bool Matches(NamingSymbols symbols, ISymbol symbol)
        {
            string kind = GetKind(symbol);
            if (kind == null && !symbols.Kinds.Contains("*"))
            {
                return false;
            }

            if (kind != null && !symbols.Kinds.Contains("*") && !symbols.Kinds.Contains(kind))
            {
                return false;
            }

            if (!symbols.Accessibilities.Contains("*"))
            {
                string accessibility = GetAccessibility(symbol);
                if (accessibility == null || !symbols.Accessibilities.Contains(accessibility))
                {
                    return false;
                }
            }

            foreach (string modifier in symbols.RequiredModifiers)
            {
                if (!HasModifier(symbol, modifier))
                {
                    return false;
                }
            }

            return true;
        }

        private static string GetKind(ISymbol symbol)
        {
            switch (symbol)
            {
                case IFieldSymbol:
                    return "field";
                case IPropertySymbol:
                    return "property";
                case IMethodSymbol method:
                    return method.MethodKind == MethodKind.LocalFunction ? "local_function" : "method";
                case IEventSymbol:
                    return "event";
                case IParameterSymbol:
                    return "parameter";
                case ITypeParameterSymbol:
                    return "type_parameter";
                case ILocalSymbol:
                    return "local";
                case INamespaceSymbol:
                    return "namespace";
                case INamedTypeSymbol type:
                    switch (type.TypeKind)
                    {
                        case TypeKind.Class:
                            return "class";
                        case TypeKind.Struct:
                            return "struct";
                        case TypeKind.Interface:
                            return "interface";
                        case TypeKind.Enum:
                            return "enum";
                        case TypeKind.Delegate:
                            return "delegate";
                    }

                    return null;
                default:
                    return null;
            }
        }

        private static string GetAccessibility(ISymbol symbol)
        {
            if (symbol is ILocalSymbol || (symbol is IMethodSymbol method && method.MethodKind == MethodKind.LocalFunction))
            {
                return "local";
            }

            switch (symbol.DeclaredAccessibility)
            {
                case Accessibility.Public:
                    return "public";
                case Accessibility.Private:
                    return "private";
                case Accessibility.Protected:
                    return "protected";
                case Accessibility.Internal:
                    return "internal";
                case Accessibility.ProtectedOrInternal:
                    return "protected_internal";
                case Accessibility.ProtectedAndInternal:
                    return "private_protected";
                default:
                    return null;
            }
        }

        private static bool HasModifier(ISymbol symbol, string modifier)
        {
            switch (modifier)
            {
                case "static":
                    switch (symbol)
                    {
                        case IFieldSymbol field:
                            return field.IsStatic;
                        case IMethodSymbol method:
                            return method.IsStatic;
                        case IPropertySymbol property:
                            return property.IsStatic;
                        case IEventSymbol evt:
                            return evt.IsStatic;
                        default:
                            return false;
                    }
                case "const":
                    return symbol is IFieldSymbol constField && constField.IsConst;
                case "readonly":
                    return symbol is IFieldSymbol readonlyField && readonlyField.IsReadOnly;
                case "async":
                    return symbol is IMethodSymbol asyncMethod && asyncMethod.IsAsync;
                case "abstract":
                    switch (symbol)
                    {
                        case IMethodSymbol method:
                            return method.IsAbstract;
                        case IPropertySymbol property:
                            return property.IsAbstract;
                        case IEventSymbol evt:
                            return evt.IsAbstract;
                        default:
                            return false;
                    }
                case "virtual":
                    switch (symbol)
                    {
                        case IMethodSymbol method:
                            return method.IsVirtual;
                        case IPropertySymbol property:
                            return property.IsVirtual;
                        case IEventSymbol evt:
                            return evt.IsVirtual;
                        default:
                            return false;
                    }
                case "override":
                    switch (symbol)
                    {
                        case IMethodSymbol method:
                            return method.IsOverride;
                        case IPropertySymbol property:
                            return property.IsOverride;
                        case IEventSymbol evt:
                            return evt.IsOverride;
                        default:
                            return false;
                    }
                case "sealed":
                    switch (symbol)
                    {
                        case IMethodSymbol method:
                            return method.IsSealed;
                        case IPropertySymbol property:
                            return property.IsSealed;
                        case IEventSymbol evt:
                            return evt.IsSealed;
                        default:
                            return false;
                    }
                case "extern":
                    return symbol is IMethodSymbol externMethod && externMethod.IsExtern;
                case "unsafe":
                    // IMethodSymbol 不暴露 unsafe（属语法层修饰符），此处不参与匹配；未配置该修饰符时无影响
                    return false;
                case "required":
                    return symbol is IPropertySymbol { IsRequired: true };
                default:
                    return false;
            }
        }

        private static string ApplyCapitalization(string name, string capitalization)
        {
            if (name.Length == 0)
            {
                return name;
            }

            switch (capitalization)
            {
                case "pascal_case":
                case "first_word_upper":
                    return char.ToUpperInvariant(name[0]) + name.Substring(1);
                case "camel_case":
                    return char.ToLowerInvariant(name[0]) + name.Substring(1);
                case "all_upper":
                    return name.ToUpperInvariant();
                case "all_lower":
                    return name.ToLowerInvariant();
                default:
                    return name;
            }
        }

        private static bool IsLegacyPrefixed(string name, string prefix)
        {
            return prefix.Length > 0
                && name.Length > prefix.Length
                && name.StartsWith(prefix, StringComparison.Ordinal)
                && char.IsUpper(name[prefix.Length]);
        }

        private static bool TrySplitKey(string key, string prefix, out string name, out string property)
        {
            name = null;
            property = null;
            string remainder = key.Substring(prefix.Length);
            int separator = remainder.IndexOf('.');
            if (separator <= 0 || separator == remainder.Length - 1)
            {
                return false;
            }

            name = remainder.Substring(0, separator);
            property = remainder.Substring(separator + 1);
            return true;
        }

        private static Dictionary<string, string> GetOrAdd(Dictionary<string, Dictionary<string, string>> groups, string name)
        {
            if (!groups.TryGetValue(name, out Dictionary<string, string> properties))
            {
                properties = new Dictionary<string, string>(StringComparer.Ordinal);
                groups[name] = properties;
            }

            return properties;
        }

        private static string GetValue(Dictionary<string, string> properties, string key, string fallback)
        {
            return properties.TryGetValue(key, out string value) ? value : fallback;
        }

        private static void AddAll(HashSet<string> target, string rawValue)
        {
            foreach (string item in rawValue.Split(','))
            {
                string value = item.Trim();
                if (value.Length > 0)
                {
                    target.Add(value);
                }
            }
        }
    }
}
