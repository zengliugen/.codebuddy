using System.Text.Json;
using System.Text.Json.Nodes;

/// <summary>
/// 配置文件定位与分层合并工具。
///
/// 注释检查配置分为两层：引擎侧通用配置（工具目录下的 comment_config.json，随引擎入库共享，
/// 承载 rules 规则与通用开关）与项目侧配置（项目根下的 .codebuddy.project/，经
/// .codebuddy/project.index.json 索引定位，承载 exclude.paths 与 knownTerms）。
/// 两层深度合并后使用，项目侧值覆盖引擎侧值，数组取并集。
///
/// 由 `check_comments.py` 调用时通常已通过 `--config` 传入合并结果，本类仅在其未传入时兜底，
/// 保证工具可独立运行（无需 Python 编排层）。
/// </summary>
public static class ConfigResolver
{
    /// <summary>索引中注释检查项目配置的逻辑名。</summary>
    private const string CommentCodeName = "comment.project_config";

    /// <summary>
    /// 解析合并后的配置路径：优先显式路径，其次经索引定位并合并，最后回退工具目录默认配置。
    /// </summary>
    /// <param name="explicitPath">命令行显式指定的配置路径；可为 null。</param>
    /// <returns>可直接加载的合并配置文件路径。</returns>
    /// <exception cref="CommentRulesConfigException">索引或配置缺失、损坏时抛出。</exception>
    public static string Resolve(string? explicitPath)
    {
        if (!string.IsNullOrWhiteSpace(explicitPath))
        {
            return explicitPath!;
        }

        var enginePath = Path.Combine(AppContext.BaseDirectory, "comment_config.json");
        var codebuddyDir = FindCodebuddyDir();
        if (codebuddyDir == null)
        {
            // 非引擎目录运行（如单元测试）：回退工具目录默认配置
            return enginePath;
        }

        var projectRoot = Path.GetDirectoryName(codebuddyDir)!;
        var projectPath = ResolveIndexPath(codebuddyDir, projectRoot, CommentCodeName);

        var merged = MergeFiles(enginePath, projectPath);
        var mergedPath = Path.Combine(AppContext.BaseDirectory, "comment_config.merged.json");
        File.WriteAllText(mergedPath, merged, new System.Text.UTF8Encoding(false));
        return mergedPath;
    }

    /// <summary>
    /// 自起始目录向上查找名为 `.codebuddy` 的目录。
    /// </summary>
    /// <returns>.codebuddy 目录绝对路径；找不到时返回 null。</returns>
    private static string? FindCodebuddyDir()
    {
        var current = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        while (!string.IsNullOrEmpty(current))
        {
            if (string.Equals(Path.GetFileName(current), ".codebuddy", StringComparison.Ordinal))
            {
                return current;
            }
            var parent = Path.GetDirectoryName(current);
            if (parent == current)
            {
                break;
            }
            current = parent;
        }
        return null;
    }

    /// <summary>
    /// 经索引注册表解析某逻辑名对应的项目侧配置绝对路径。
    /// </summary>
    /// <param name="codebuddyDir">.codebuddy 目录。</param>
    /// <param name="projectRoot">项目根（.codebuddy 的父目录）。</param>
    /// <param name="codeName">索引 files 下的逻辑名。</param>
    /// <returns>项目侧配置绝对路径。</returns>
    /// <exception cref="CommentRulesConfigException">索引缺失、损坏或路径非法时抛出。</exception>
    private static string ResolveIndexPath(string codebuddyDir, string projectRoot, string codeName)
    {
        var indexPath = Path.Combine(codebuddyDir, "project.index.json");
        if (!File.Exists(indexPath))
        {
            throw new CommentRulesConfigException(
                $"未找到项目配置索引：{indexPath}。该索引由 .codebuddy 引擎提供，请确认引擎包完整。");
        }

        JsonNode? root;
        try
        {
            root = JsonNode.Parse(File.ReadAllText(indexPath));
        }
        catch (Exception ex)
        {
            throw new CommentRulesConfigException($"项目配置索引解析失败（{ex.Message}）：{indexPath}");
        }

        var rel = root?["files"]?[codeName]?["path"]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(rel))
        {
            throw new CommentRulesConfigException($"索引缺少配置项 `files.{codeName}.path`：{indexPath}");
        }
        if (Path.IsPathRooted(rel!))
        {
            throw new CommentRulesConfigException(
                $"索引 `files.{codeName}.path` 必须为相对路径（当前为绝对路径）：{rel}");
        }
        return Path.GetFullPath(Path.Combine(projectRoot, rel!));
    }

    /// <summary>
    /// 深度合并引擎侧与项目侧配置，返回合并后的 JSON 文本。
    ///
    /// 字典递归合并（项目侧覆盖同名键）；数组取并集（引擎侧顺序在前，去重）；标量以项目侧为准。
    /// </summary>
    /// <param name="enginePath">引擎侧配置路径。</param>
    /// <param name="projectPath">项目侧配置路径。</param>
    /// <returns>合并后的 JSON 文本。</returns>
    /// <exception cref="CommentRulesConfigException">任一配置文件缺失或损坏时抛出。</exception>
    private static string MergeFiles(string enginePath, string projectPath)
    {
        var engine = ReadObject(enginePath, "引擎侧注释检查");
        var project = ReadObject(projectPath, "项目侧注释检查");
        var merged = MergeNodes(engine, project);
        return merged.ToJsonString(new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });
    }

    /// <summary>
    /// 读取 JSON 对象文件。
    /// </summary>
    /// <param name="path">文件路径。</param>
    /// <param name="label">错误消息中的配置名称。</param>
    /// <returns>JSON 对象节点。</returns>
    /// <exception cref="CommentRulesConfigException">文件缺失、损坏或顶层非对象时抛出。</exception>
    private static JsonObject ReadObject(string path, string label)
    {
        if (!File.Exists(path))
        {
            throw new CommentRulesConfigException(
                $"未找到{label}配置：{path}。请先按项目实际情况创建该配置（字段说明见 references/config-guide.md）。");
        }
        try
        {
            var node = JsonNode.Parse(File.ReadAllText(path));
            if (node is not JsonObject obj)
            {
                throw new CommentRulesConfigException($"{label}配置顶层必须是 JSON 对象：{path}");
            }
            return obj;
        }
        catch (CommentRulesConfigException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new CommentRulesConfigException($"{label}配置解析失败（{ex.Message}）：{path}");
        }
    }

    /// <summary>
    /// 深度合并两个 JSON 节点：项目侧（override）覆盖引擎侧（base）。
    /// </summary>
    private static JsonNode MergeNodes(JsonNode baseNode, JsonNode overrideNode)
    {
        if (baseNode is JsonObject baseObj && overrideNode is JsonObject overrideObj)
        {
            var result = (JsonObject)baseObj.DeepClone();
            foreach (var pair in overrideObj)
            {
                if (result.TryGetPropertyValue(pair.Key, out var existing) && existing != null && pair.Value != null)
                {
                    result[pair.Key] = MergeNodes(existing, pair.Value);
                }
                else
                {
                    result[pair.Key] = pair.Value?.DeepClone();
                }
            }
            return result;
        }

        if (baseNode is JsonArray baseArr && overrideNode is JsonArray overrideArr)
        {
            var result = (JsonArray)baseArr.DeepClone();
            foreach (var item in overrideArr)
            {
                var text = item?.ToJsonString();
                var duplicate = result.Any(existing => existing?.ToJsonString() == text);
                if (!duplicate)
                {
                    result.Add(item?.DeepClone());
                }
            }
            return result;
        }

        return overrideNode.DeepClone();
    }
}
