using System.Diagnostics;
using System.Text.Json;
using Azure.Monitor.OpenTelemetry.Exporter;
using Microsoft.Extensions.Hosting;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace WorkstreamManager.Services;

public static class AgentInvocationTracing
{
    public const string ActivitySourceName = "Foundry.Agent.Invocation";
    private static readonly ActivitySource Source = new(ActivitySourceName);

    public static TracerProviderBuilder ConfigureTracing(
        TracerProviderBuilder builder,
        Action<TracerProviderBuilder>? addExporters = null)
    {
        var instanceId = GetSetting("FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID");
        builder
            .ConfigureResource(resource => resource.AddService(
                serviceName: GetSetting("FOUNDRY_AGENT_NAME") ?? "autopilot",
                serviceVersion: GetSetting("FOUNDRY_AGENT_VERSION"),
                autoGenerateServiceInstanceId: instanceId is null,
                serviceInstanceId: instanceId))
            .AddSource(ActivitySourceName);
        addExporters?.Invoke(builder);

        // Set last: an exporter can install its own sampler, and an unsampled incoming
        // context must not silently suppress the invocation.
        return builder.SetSampler(new AlwaysOnSampler());
    }

    public static Activity? StartInvocation(string agentName, string agentId, string? mainAgentId = null)
    {
        var activity = Source.StartActivity($"invoke_agent {agentName}", ActivityKind.Internal);
        if (activity is null)
        {
            return null;
        }

        activity.SetTag("gen_ai.operation.name", "invoke_agent");
        activity.SetTag("gen_ai.agent.name", agentName);
        activity.SetTag("gen_ai.agent.id", agentId);
        activity.SetTag("microsoft.gen_ai.main_agent.id", mainAgentId ?? agentId);

        var projectId = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ARM_ID");
        if (!string.IsNullOrWhiteSpace(projectId))
        {
            activity.SetTag("microsoft.foundry.project.id", projectId);
        }

        var sessionId = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_SESSION_ID");
        if (!string.IsNullOrWhiteSpace(sessionId))
        {
            activity.SetTag("azure.ai.agentserver.session_id", sessionId);
        }

        return activity;
    }

    public static async Task<string> TraceAsync(string? input, Func<Activity?, Task<string>> invoke)
    {
        var agentName = GetSetting("FOUNDRY_AGENT_NAME") ?? "autopilot";
        var version = GetSetting("FOUNDRY_AGENT_VERSION") ?? "unknown";

        using var activity = StartInvocation(agentName, $"{agentName}:{version}");
        RecordMessages(activity, "gen_ai.input.messages", "user", input);
        try
        {
            var output = await invoke(activity);
            RecordMessages(activity, "gen_ai.output.messages", "assistant", output);
            return output;
        }
        catch (Exception ex)
        {
            RecordError(activity, ex.GetType().FullName ?? ex.GetType().Name);
            throw;
        }
    }

    public static void RecordResponseId(Activity? activity, string? responseId)
    {
        if (!string.IsNullOrWhiteSpace(responseId))
        {
            activity?.SetTag("gen_ai.response.id", responseId);
        }
    }

    public static void RecordResponse(Activity? activity, JsonElement response)
    {
        if (response.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String)
        {
            RecordResponseId(activity, id.GetString());
        }
        if ((response.TryGetProperty("error", out var error) && error.ValueKind != JsonValueKind.Null) ||
            (response.TryGetProperty("status", out var status) && status.ValueKind == JsonValueKind.String &&
                status.GetString() is "failed" or "cancelled"))
        {
            RecordError(activity, "responses_api_error");
        }
    }

    public static void RecordError(Activity? activity, string errorType)
    {
        activity?.SetStatus(ActivityStatusCode.Error);
        activity?.SetTag("error.type", errorType);
    }

    private static string? GetSetting(string name) =>
        Environment.GetEnvironmentVariable(name) is { } value && !string.IsNullOrWhiteSpace(value) ? value : null;

    private static void RecordMessages(Activity? activity, string attribute, string role, string? text)
    {
        if (activity is null)
        {
            return;
        }

        var parts = new List<Dictionary<string, string>>();
        if (!string.IsNullOrEmpty(text))
        {
            var part = new Dictionary<string, string> { ["type"] = "text" };
            if (string.Equals(
                Environment.GetEnvironmentVariable("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"),
                "true",
                StringComparison.OrdinalIgnoreCase))
            {
                part["content"] = text;
            }
            parts.Add(part);
        }

        activity.SetTag(attribute, JsonSerializer.Serialize(new[] { new { role, parts } }));
    }
}

internal sealed class AgentInvocationTracingService(string connectionString) : IHostedService, IDisposable
{
    private TracerProvider? _provider;

    public Task StartAsync(CancellationToken cancellationToken)
    {
        // Do not merge with another SDK's DI-managed provider and its HTTP sources.
        _provider = AgentInvocationTracing.ConfigureTracing(
                Sdk.CreateTracerProviderBuilder(),
                builder => builder.AddAzureMonitorTraceExporter(options => options.ConnectionString = connectionString))
            .Build();
        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    public void Dispose() => _provider?.Dispose();
}
