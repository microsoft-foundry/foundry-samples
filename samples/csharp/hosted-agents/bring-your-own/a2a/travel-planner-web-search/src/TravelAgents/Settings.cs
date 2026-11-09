// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Azure.AI.AgentServer.Core;
using Azure.Core;
using Azure.Identity;

namespace TravelAgents;

public static class Settings
{
    public static string Required(string name) =>
        Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
            ? value : throw new InvalidOperationException($"Set {name} before starting this sample.");

    public static bool IsHosted => !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));

    public static TokenCredential Credential() => IsHosted
        ? new ManagedIdentityCredential(ManagedIdentityId.FromUserAssignedClientId(Required("FOUNDRY_AGENT_INSTANCE_CLIENT_ID")))
        : new DefaultAzureCredential();

    public static Uri ValidateAgentUrl(string url, string project, bool hosted)
    {
        var target = new Uri(url, UriKind.Absolute);
        var origin = new Uri(project, UriKind.Absolute);
        if (target.UserInfo.Length > 0 || target.Fragment.Length > 0 ||
            url.Contains('%') || url.Split('/').Any(segment => segment is "." or ".."))
            throw new ArgumentException("Agent URL contains credentials, encoded paths or traversal.", nameof(url));
        bool inProject = target.Scheme == "https" && target.Authority == origin.Authority &&
            target.AbsolutePath.StartsWith(origin.AbsolutePath.TrimEnd('/') + "/agents/", StringComparison.Ordinal);
        bool local = !hosted && target.Scheme == "http" && target.Host is "localhost" or "127.0.0.1";
        if (!inProject && !local)
            throw new ArgumentException("Agent URL must be inside the configured Foundry project, or loopback locally.", nameof(url));
        return target;
    }

    public static Uri ValidateToolboxUrl(string url, string project)
    {
        var target = new Uri(url, UriKind.Absolute);
        var origin = new Uri(project, UriKind.Absolute);
        if (target.Scheme != "https" || target.Authority != origin.Authority || target.UserInfo.Length > 0 ||
            target.Fragment.Length > 0 || url.Contains('%') || url.Split('/').Any(segment => segment is "." or "..") ||
            !target.AbsolutePath.StartsWith(origin.AbsolutePath.TrimEnd('/') + "/toolboxes/", StringComparison.Ordinal) ||
            !target.AbsolutePath.EndsWith("/mcp", StringComparison.Ordinal) || target.Query != "?api-version=v1")
            throw new ArgumentException("TOOLBOX_ENDPOINT must be an HTTPS MCP endpoint in this Foundry project.", nameof(url));
        return target;
    }

    public static Dictionary<string, string> Headers(string? callId, Activity? activity)
    {
        var headers = new Dictionary<string, string>();
        if (!string.IsNullOrEmpty(callId)) headers["x-agent-foundry-call-id"] = callId;
        if (activity?.Id is { } id) headers["traceparent"] = id;
        if (!string.IsNullOrEmpty(activity?.TraceStateString)) headers["tracestate"] = activity.TraceStateString;
        return headers;
    }
}
