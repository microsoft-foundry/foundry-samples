using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;
using Azure.Monitor.OpenTelemetry.Exporter;
using WorkstreamManager.Services;
using OpenTelemetry;
using OpenTelemetry.Trace;
using Xunit;

namespace WorkstreamManagerAgent.Tests;

[CollectionDefinition("Tracing", DisableParallelization = true)]
public class TracingCollection { }

[Collection("Tracing")]
public class AgentInvocationTracingTests : IDisposable
{
    private readonly ConcurrentQueue<Activity> _spans = new();
    private readonly TracerProvider _provider;
    private readonly Dictionary<string, string?> _environment;

    public AgentInvocationTracingTests()
    {
        _environment = new[]
        {
            "FOUNDRY_AGENT_NAME", "FOUNDRY_AGENT_VERSION", "FOUNDRY_PROJECT_ARM_ID",
            "FOUNDRY_AGENT_SESSION_ID", "FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
        }.ToDictionary(name => name, Environment.GetEnvironmentVariable);

        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_NAME", "test-agent");
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_VERSION", "7");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ARM_ID", "/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/test/projects/test");
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_SESSION_ID", "test-session");
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_DEFAULT_INSTANCE_CLIENT_ID", "test-instance");
        Environment.SetEnvironmentVariable("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", null);

        _provider = AgentInvocationTracing.ConfigureTracing(Sdk.CreateTracerProviderBuilder())
            .AddProcessor(new SimpleActivityExportProcessor(new Collector(_spans)))
            .Build();
    }

    public void Dispose()
    {
        _provider.Dispose();
        foreach (var variable in _environment)
        {
            Environment.SetEnvironmentVariable(variable.Key, variable.Value);
        }
    }

    [Fact]
    public async Task InvocationExportsOnceWithRuntimeMetadataAndResponseId()
    {
        var result = await AgentInvocationTracing.TraceAsync("input", activity =>
        {
            Assert.Same(activity, Activity.Current);
            using var response = JsonDocument.Parse("""{"id":"resp_test","status":"completed","error":null}""");
            AgentInvocationTracing.RecordResponse(activity, response.RootElement);
            return Task.FromResult("output");
        });

        Assert.Equal("output", result);
        var span = Assert.Single(_spans);
        Assert.Equal("invoke_agent test-agent", span.DisplayName);
        Assert.Equal(ActivityKind.Internal, span.Kind);
        Assert.Equal("invoke_agent", span.GetTagItem("gen_ai.operation.name"));
        Assert.Equal("test-agent", span.GetTagItem("gen_ai.agent.name"));
        Assert.Equal("test-agent:7", span.GetTagItem("gen_ai.agent.id"));
        Assert.Equal("test-agent:7", span.GetTagItem("microsoft.gen_ai.main_agent.id"));
        Assert.Equal("resp_test", span.GetTagItem("gen_ai.response.id"));
        Assert.Equal("test-session", span.GetTagItem("azure.ai.agentserver.session_id"));
        Assert.Equal(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ARM_ID"), span.GetTagItem("microsoft.foundry.project.id"));
    }

    [Fact]
    public async Task ProductionSamplerRecordsAnUnsampledParentAndPreservesCorrelation()
    {
        using var parent = new Activity("incoming")
            .SetParentId(ActivityTraceId.CreateRandom(), ActivitySpanId.CreateRandom(), ActivityTraceFlags.None)
            .Start();
        Assert.False(parent.Recorded);

        await AgentInvocationTracing.TraceAsync("input", _ => Task.FromResult("output"));

        var span = Assert.Single(_spans);
        Assert.True(span.Recorded);
        Assert.Equal(parent.TraceId, span.TraceId);
        Assert.Equal(parent.SpanId, span.ParentSpanId);
        Assert.Same(parent, Activity.Current);
    }

    [Fact]
    public void ExporterSamplerDoesNotReplaceTheInvocationSampler()
    {
        _provider.Dispose();
        using var exporterProvider = AgentInvocationTracing.ConfigureTracing(
                Sdk.CreateTracerProviderBuilder(),
                builder => builder.AddAzureMonitorTraceExporter(options =>
                {
                    options.ConnectionString =
                        "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=http://127.0.0.1:9/";
                    options.DisableOfflineStorage = true;
                    // An exporter sampler that drops everything proves ours is applied last.
                    options.SamplingRatio = 0F;
                }))
            .Build();
        using var parent = new Activity("incoming")
            .SetParentId(ActivityTraceId.CreateRandom(), ActivitySpanId.CreateRandom(), ActivityTraceFlags.None)
            .Start();

        using var invocation = AgentInvocationTracing.StartInvocation("test-agent", "test-agent:7");

        Assert.NotNull(invocation);
        Assert.True(invocation.Recorded);
    }

    [Fact]
    public void ProviderIdentifiesTheHostedAgent()
    {
        var attributes = _provider.GetResource().Attributes.ToDictionary(attribute => attribute.Key, attribute => attribute.Value);
        Assert.Equal("test-agent", attributes["service.name"]);
        Assert.Equal("7", attributes["service.version"]);
        Assert.Equal("test-instance", attributes["service.instance.id"]);
    }

    [Fact]
    public void ProviderDoesNotCollectTheExistingHttpSource()
    {
        var httpSpans = new ConcurrentQueue<Activity>();
        using var existingProvider = Sdk.CreateTracerProviderBuilder()
            .SetSampler(new AlwaysOnSampler())
            .AddSource("System.Net.Http")
            .AddProcessor(new SimpleActivityExportProcessor(new Collector(httpSpans)))
            .Build();
        using var httpSource = new ActivitySource("System.Net.Http");
        using (httpSource.StartActivity("HTTP request")) { }
        Assert.Single(httpSpans);
        Assert.Empty(_spans);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("false")]
    public async Task ContentCaptureIsOffUnlessExplicitlyEnabled(string? setting)
    {
        Environment.SetEnvironmentVariable("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", setting);
        await AgentInvocationTracing.TraceAsync("private input", _ => Task.FromResult("private output"));

        var span = Assert.Single(_spans);
        foreach (var (attribute, role) in new[]
        {
            ("gen_ai.input.messages", "user"), ("gen_ai.output.messages", "assistant")
        })
        {
            var json = Assert.IsType<string>(span.GetTagItem(attribute));
            using var messages = JsonDocument.Parse(json);
            Assert.Equal(role, messages.RootElement[0].GetProperty("role").GetString());
            var part = messages.RootElement[0].GetProperty("parts")[0];
            Assert.Equal("text", part.GetProperty("type").GetString());
            Assert.False(part.TryGetProperty("content", out _));
            Assert.DoesNotContain("private", json);
        }
    }

    [Fact]
    public async Task EnabledCapturePreservesText()
    {
        Environment.SetEnvironmentVariable("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true");
        await AgentInvocationTracing.TraceAsync("input \"quoted\"", _ => Task.FromResult("output"));
        var span = Assert.Single(_spans);
        using var input = JsonDocument.Parse(Assert.IsType<string>(span.GetTagItem("gen_ai.input.messages")));
        using var output = JsonDocument.Parse(Assert.IsType<string>(span.GetTagItem("gen_ai.output.messages")));
        Assert.Equal("input \"quoted\"", input.RootElement[0].GetProperty("parts")[0].GetProperty("content").GetString());
        Assert.Equal("output", output.RootElement[0].GetProperty("parts")[0].GetProperty("content").GetString());
    }

    [Fact]
    public async Task ExceptionMarksFailureAndIsRethrownWithoutCapturingItsMessage()
    {
        var failure = new InvalidOperationException("private error text");
        var thrown = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            AgentInvocationTracing.TraceAsync("input", _ => Task.FromException<string>(failure)));
        Assert.Same(failure, thrown);
        var span = Assert.Single(_spans);
        Assert.Equal(ActivityStatusCode.Error, span.Status);
        Assert.Equal(typeof(InvalidOperationException).FullName, span.GetTagItem("error.type"));
        Assert.DoesNotContain(span.TagObjects, tag => tag.Value?.ToString()?.Contains("private error text") == true);
    }

    [Fact]
    public async Task HandledHttpFailureStaysFailedWhenTextIsReturned()
    {
        await AgentInvocationTracing.TraceAsync("input", activity =>
        {
            AgentInvocationTracing.RecordError(activity, "http_500");
            return Task.FromResult("The request failed.");
        });
        Assert.Equal(ActivityStatusCode.Error, Assert.Single(_spans).Status);
    }

    [Theory]
    [InlineData("""{"id":"resp_failed","status":"failed","error":null}""")]
    [InlineData("""{"id":"resp_failed","status":"cancelled","error":null}""")]
    [InlineData("""{"id":"resp_failed","error":{"code":"server_error"}}""")]
    public async Task FailedResponsePayloadIsNotReportedAsSuccess(string json)
    {
        await AgentInvocationTracing.TraceAsync("input", activity =>
        {
            using var response = JsonDocument.Parse(json);
            AgentInvocationTracing.RecordResponse(activity, response.RootElement);
            return Task.FromResult("");
        });
        var span = Assert.Single(_spans);
        Assert.Equal(ActivityStatusCode.Error, span.Status);
        Assert.Equal("resp_failed", span.GetTagItem("gen_ai.response.id"));
    }

    [Fact]
    public void ChildInvocationRetainsTheExplicitMainAgentAndParent()
    {
        using (var parent = AgentInvocationTracing.StartInvocation("parent", "parent:1"))
        {
            using var child = AgentInvocationTracing.StartInvocation("child", "child:2", "parent:1");
            Assert.NotNull(parent);
            Assert.NotNull(child);
            Assert.Equal(parent.TraceId, child.TraceId);
            Assert.Equal(parent.SpanId, child.ParentSpanId);
            Assert.Equal("child:2", child.GetTagItem("gen_ai.agent.id"));
            Assert.Equal("parent:1", child.GetTagItem("microsoft.gen_ai.main_agent.id"));
        }
        Assert.Equal(2, _spans.Count);
    }

    [Fact]
    public async Task ConcurrentInvocationsKeepTheirOwnResponseId()
    {
        await Task.WhenAll(Enumerable.Range(0, 4).Select(index =>
            AgentInvocationTracing.TraceAsync("input", async activity =>
            {
                await Task.Yield();
                AgentInvocationTracing.RecordResponseId(activity, $"resp_{index}");
                return $"output {index}";
            })));

        Assert.Equal(4, _spans.Count);
        Assert.Equal(4, _spans.Select(span => span.SpanId).Distinct().Count());
        Assert.Equal(4, _spans.Select(span => span.GetTagItem("gen_ai.response.id")).Distinct().Count());
        Assert.All(_spans, span => Assert.Equal("test-agent:7", span.GetTagItem("gen_ai.agent.id")));
    }

    [Fact]
    public async Task MissingOptionalMetadataDoesNotInventValues()
    {
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_VERSION", null);
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ARM_ID", null);
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_SESSION_ID", null);
        await AgentInvocationTracing.TraceAsync("", activity =>
        {
            AgentInvocationTracing.RecordResponseId(activity, null);
            return Task.FromResult("");
        });
        var span = Assert.Single(_spans);
        Assert.Equal("test-agent:unknown", span.GetTagItem("gen_ai.agent.id"));
        Assert.Null(span.GetTagItem("microsoft.foundry.project.id"));
        Assert.Null(span.GetTagItem("azure.ai.agentserver.session_id"));
        Assert.Null(span.GetTagItem("gen_ai.response.id"));
    }

    [Fact]
    public async Task NoListenerDoesNotBreakTheInvocationOrTagItsParent()
    {
        _provider.Dispose();
        using var parent = new Activity("incoming").Start();
        await AgentInvocationTracing.TraceAsync("input", activity =>
        {
            Assert.Null(activity);
            AgentInvocationTracing.RecordResponseId(activity, "resp_none");
            AgentInvocationTracing.RecordError(activity, "ignored");
            return Task.FromResult("output");
        });
        Assert.Empty(_spans);
        Assert.Null(parent.GetTagItem("gen_ai.response.id"));
        Assert.Equal(ActivityStatusCode.Unset, parent.Status);
    }

    private sealed class Collector(ConcurrentQueue<Activity> spans) : BaseExporter<Activity>
    {
        public override ExportResult Export(in Batch<Activity> batch)
        {
            foreach (var activity in batch)
            {
                spans.Enqueue(activity);
            }
            return ExportResult.Success;
        }
    }
}
