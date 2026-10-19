// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace BrowserAutomation;

/// <summary>
/// Redaction utilities for sensitive values in logs and tool output.
/// </summary>
public static class Redaction
{
    private static readonly Regex TokenPattern = new(@"\beyJ[a-zA-Z0-9._-]{20,}\b", RegexOptions.Compiled);
    private static readonly Regex AccessKeyPattern = new(@"(accessKey=)[^&\s""']+", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex PrivateSections = new(
        @"^###[ \t]+(Snapshot|Page snapshot|Ran Playwright code)[ \t]*\r?\n.*?(?=^###[ \t]|\z)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase | RegexOptions.Multiline | RegexOptions.Singleline);

    public static string Redact(string text)
    {
        text = TokenPattern.Replace(text, "<token>");
        text = AccessKeyPattern.Replace(text, "$1<redacted>");
        return text;
    }

    public static string PublicToolOutput(
        string name, string output, bool isError, IReadOnlyList<string> liveViewUrls)
    {
        if (name == "load_skill")
            return output;
        if (name.Split("___")[^1] is "browser_snapshot" or "browser_take_screenshot"
            or "browser_evaluate" or "browser_run_code")
        {
            var status = isError ? "failed" : "returned";
            return $"Browser tool {status}; result omitted for privacy.";
        }
        return SanitizeText(output, liveViewUrls);
    }

    private static string SanitizeText(string text, IReadOnlyList<string> liveViewUrls)
    {
        var prefix = text.StartsWith("Tool error: ", StringComparison.Ordinal)
            ? "Tool error: "
            : text.StartsWith("Tool call failed: ", StringComparison.Ordinal)
                ? "Tool call failed: " : "";
        text = text[prefix.Length..];
        JsonNode? value;
        try
        {
            value = JsonNode.Parse(text);
        }
        catch (JsonException)
        {
            value = null;
        }
        if (value is JsonObject or JsonArray)
        {
            var original = value.ToJsonString();
            SanitizeJson(value, liveViewUrls);
            var sanitized = value.ToJsonString();
            if (sanitized != original)
                return prefix + sanitized;
        }
        foreach (var url in liveViewUrls)
        {
            if (string.IsNullOrEmpty(url))
                continue;
            text = text.Replace(url, "[live-view URL omitted]", StringComparison.Ordinal);
            text = text.Replace(
                JsonSerializer.Serialize(url)[1..^1],
                "[live-view URL omitted]",
                StringComparison.Ordinal);
        }
        text = PrivateSections.Replace(
            text, match => $"### {match.Groups[1].Value}\nContent omitted for privacy.\n");
        return prefix + Redact(text);
    }

    private static void SanitizeJson(JsonNode node, IReadOnlyList<string> liveViewUrls)
    {
        if (node is JsonObject obj)
        {
            if (obj["type"] is JsonValue type
                && type.TryGetValue<string>(out var contentType) && contentType == "image")
            {
                obj.Clear();
                obj["type"] = "text";
                obj["text"] = "Screenshot omitted for privacy.";
                return;
            }
            foreach (var property in obj.ToList())
            {
                var key = property.Key.Replace("_", "").Replace(" ", "").ToLowerInvariant();
                if (key == "liveviewurl")
                    obj.Remove(property.Key);
                else if (key is "snapshot" or "pagesnapshot" or "screenshot" or "ranplaywrightcode")
                    obj[property.Key] = "Content omitted for privacy.";
                else if (property.Value is JsonValue item && item.TryGetValue<string>(out var text))
                    obj[property.Key] = SanitizeText(text, liveViewUrls);
                else if (property.Value is { } child)
                    SanitizeJson(child, liveViewUrls);
            }
        }
        else if (node is JsonArray array)
        {
            for (var index = 0; index < array.Count; index++)
            {
                if (array[index] is JsonValue item && item.TryGetValue<string>(out var text))
                    array[index] = SanitizeText(text, liveViewUrls);
                else if (array[index] is { } child)
                    SanitizeJson(child, liveViewUrls);
            }
        }
    }
}
