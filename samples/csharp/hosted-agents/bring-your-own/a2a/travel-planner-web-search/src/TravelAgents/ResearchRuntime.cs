// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.RegularExpressions;
using GitHub.Copilot;
using Microsoft.Extensions.AI;

namespace TravelAgents;

public sealed record SearchReceipt(string ToolCallId, bool Success, IReadOnlyList<string> SourceUrls);
public sealed record ResearchAnswer(string Answer, IReadOnlyList<SearchReceipt> Searches);
public sealed class ResearchException(string message, IReadOnlyList<SearchReceipt> searches, Exception? innerException = null) : Exception(message, innerException)
{
    public IReadOnlyList<SearchReceipt> Searches { get; } = searches;
}

public sealed class SearchBudget
{
    private int _attempts;
    public bool TryAcquire() => Interlocked.Increment(ref _attempts) <= 2;
}

public class ResearchRuntime(ILogger<ResearchRuntime> logger)
{
    public static string[] SourceUrls(string text) =>
        Regex.Matches(text, @"https?://[^\s<>""\\)]+").Select(match => match.Value.TrimEnd('.', ',', ';'))
            .Where(url => Uri.TryCreate(url, UriKind.Absolute, out _)).Distinct().Take(6).ToArray();

    public static void ValidateResearch(string answer, IReadOnlyList<SearchReceipt> searches)
    {
        if (searches.Count > 2 || !searches.Any(search => search.Success))
            throw new ResearchException("Research requires a successful cited web_search within the two-search budget.", searches);
        string[] cited = SourceUrls(answer);
        if (cited.Length == 0 || cited.Any(url => !searches.Any(search => search.Success && search.SourceUrls.Contains(url))))
            throw new ResearchException("The answer must cite URLs actually returned by successful searches.", searches);
    }

    public virtual async Task<string> AskAsync(
        string instructions, string prompt, ICollection<AIFunctionDeclaration> tools,
        string? callId, Activity? activity, CancellationToken cancellationToken)
    {
        await using var client = new CopilotClient(new CopilotClientOptions { UseLoggedInUser = false });
        await client.StartAsync(cancellationToken);
        await using var session = await client.CreateSessionAsync(await ConfigAsync(
            instructions, tools, callId, activity, cancellationToken), cancellationToken);
        var answer = await session.SendAndWaitAsync(prompt, TimeSpan.FromMinutes(10), cancellationToken);
        return answer?.Data.Content is { Length: > 0 } content
            ? content : throw new InvalidOperationException("Copilot returned no answer.");
    }

    public virtual async Task<ResearchAnswer> SearchAsync(
        string instructions, string prompt, string? callId, Activity? activity, CancellationToken cancellationToken)
    {
        string project = Settings.Required("FOUNDRY_PROJECT_ENDPOINT");
        Uri toolbox = Settings.ValidateToolboxUrl(Settings.Required("TOOLBOX_ENDPOINT"), project);
        var headers = Settings.Headers(callId, activity);
        var token = await Settings.Credential().GetTokenAsync(
            new Azure.Core.TokenRequestContext(["https://ai.azure.com/.default"]), cancellationToken);
        headers["Authorization"] = "Bearer " + token.Token;
        var budget = new SearchBudget();
        var receipts = new ConcurrentDictionary<string, SearchReceipt>();
        var config = await ConfigAsync(instructions, [], callId, activity, cancellationToken);
        config.AvailableTools = ["mcp:travel_web-web_search"];
        config.McpServers = new Dictionary<string, McpServerConfig>
        {
            ["travel_web"] = new McpHttpServerConfig
            {
                Url = toolbox.ToString(),
                Headers = headers,
                Tools = ["web_search"],
                Timeout = 60000
            }
        };
        config.Hooks = new SessionHooks
        {
            OnPreToolUse = (input, _) => Task.FromResult<PreToolUseHookOutput?>(new()
            {
                PermissionDecision = (input.ToolName is "travel_web-web_search" or "mcp:travel_web-web_search") && budget.TryAcquire() ? "allow" : "deny",
                PermissionDecisionReason = "Only web_search is allowed, at most twice per invocation. Finish with existing cited evidence."
            })
        };
        await using var client = new CopilotClient(new CopilotClientOptions { UseLoggedInUser = false });
        await client.StartAsync(cancellationToken);
        await using var session = await client.CreateSessionAsync(config, cancellationToken);
        using var subscription = session.On<SessionEvent>(evt =>
        {
            if (evt is ToolExecutionStartEvent start && start.Data.McpToolName == "web_search")
                receipts[start.Data.ToolCallId] = new(start.Data.ToolCallId, false, []);
            if (evt is ToolExecutionCompleteEvent complete && receipts.ContainsKey(complete.Data.ToolCallId))
            {
                string[] urls = SourceUrls(complete.Data.Result?.Content ?? "");
                receipts[complete.Data.ToolCallId] = new(complete.Data.ToolCallId, complete.Data.Success && urls.Length > 0, urls);
                logger.LogInformation("WEB_SEARCH_COMPLETED tool_call_id={ToolCallId} success={Success} source_count={Count}",
                    complete.Data.ToolCallId, complete.Data.Success, urls.Length);
            }
        });
        AssistantMessageEvent? response;
        try
        {
            response = await session.SendAndWaitAsync(prompt, TimeSpan.FromMinutes(3), cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            throw new ResearchException("Copilot web research failed; inspect the retained search receipts.", receipts.Values.ToArray(), error);
        }
        var searches = receipts.Values.ToArray();
        string answer = response?.Data.Content ?? "";
        ValidateResearch(answer, searches);
        return new(answer, searches);
    }

    private static async Task<SessionConfig> ConfigAsync(
        string instructions, ICollection<AIFunctionDeclaration> tools, string? callId,
        Activity? activity, CancellationToken cancellationToken)
    {
        var project = new Uri(Settings.Required("FOUNDRY_PROJECT_ENDPOINT"));
        if (project.Scheme != "https") throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT must use HTTPS.");
        var token = await Settings.Credential().GetTokenAsync(
            new Azure.Core.TokenRequestContext(["https://ai.azure.com/.default"]), cancellationToken);
        return new SessionConfig
        {
            Model = Settings.Required("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
            Provider = new ProviderConfig
            {
                Type = "azure",
                WireApi = "responses",
                BaseUrl = project.ToString().TrimEnd('/'),
                BearerToken = token.Token,
                Headers = Settings.Headers(callId, activity)
            },
            SystemMessage = new SystemMessageConfig { Mode = SystemMessageMode.Replace, Content = instructions },
            Tools = tools,
            AvailableTools = tools.Select(tool => tool.Name).ToList(),
            Streaming = false,
            EnableSessionStore = false,
            EnableConfigDiscovery = false,
            EnableSkills = false,
            SkipCustomInstructions = true,
            OnPermissionRequest = PermissionHandler.ApproveAll
        };
    }
}
