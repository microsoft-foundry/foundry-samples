using Azure.Identity;
using HelloWorldA365.AgentLogic;
using HelloWorldA365.AgentLogic.AuthCache;
using HelloWorldA365.AgentLogic.SemanticKernel;
using HelloWorldA365.Mcp;
using HelloWorldA365.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;

using Microsoft.ApplicationInsights.Extensibility;
using System.Text;
using Microsoft.Agents.A365.Tooling.Extensions.SemanticKernel.Services;
using Microsoft.Agents.A365.Tooling.Services;
using Microsoft.Agents.A365.Observability.Runtime;
using Microsoft.Agents.A365.Observability.Extensions.SemanticKernel;
using Microsoft.Agents.A365.Observability.Runtime.Tracing.Exporters;

var builder = WebApplication.CreateBuilder(args);

// Add Azure Key Vault as configuration provider when running in production (not locally)
var keyVaultName = builder.Configuration["KeyVaultName"];
if (!string.IsNullOrEmpty(keyVaultName))
{
    var keyVaultUri = $"https://{keyVaultName}.vault.azure.net/";

    // Use DefaultAzureCredential which will use Managed Service Identity in production
    builder.Configuration.AddAzureKeyVault(
        new Uri(keyVaultUri),
        new DefaultAzureCredential());

    Console.WriteLine($"Azure Key Vault configured: {keyVaultUri}");
}
else
{
    Console.WriteLine("KeyVaultName not configured. Key Vault integration skipped.");
}

// Add controllers support
builder.Services.AddControllers();

// ===================================
// These are needed for Agent SDK
// ===================================
builder.Services.AddHttpClient();
builder.Services.AddSingleton<IStorage, MemoryStorage>();
builder.AddAgentApplicationOptions();

builder.AddAgent<A365AgentApplication>();
// Uncomment this so you can get logs of activities.
// builder.Services.AddSingleton<Microsoft.Agents.Builder.IMiddleware[]>([new TranscriptLoggerMiddleware(new FileTranscriptLogger())]);
// Register Agent Logic Service Factory as singleton
builder.Services.AddSingleton<AgentLogicServiceFactory>();


builder.Services
    .AddSingleton<SemanticKernelAgentLogicServiceFactory>()
    .AddSingleton<McpToolDiscovery>();

// Register Tooling services
builder.Services.AddSingleton<IMcpToolRegistrationService, McpToolRegistrationService>();
builder.Services.AddSingleton<IMcpToolServerConfigurationService, McpToolServerConfigurationService>();

// Register auth helper
builder.Services.AddSingleton<AgentTokenHelper>();
builder.Services.AddSingleton<IAgentTokenCache, AgentTokenCache>();

// Register OpenAPI for external agents
builder.Services.AddOpenApi();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddLogging();

#region Setup A365


AppContext.SetSwitch("Azure.Experimental.TraceGenAIMessageContent", true);
AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);

if (Environment.GetEnvironmentVariable("EnableKairoTracing") == "true")
{
    builder.Services.AddSingleton(sp =>
    {
        var cache = sp.GetRequiredService<IAgentTokenCache>();
        return new Agent365ExporterOptions
        {
            ClusterCategory = "preprod",
            TokenResolver = (agentId, tenantId) => Task.FromResult(cache.GetObservabilityToken(agentId, tenantId)) // fast cached lookup
        };
    });

    builder.AddA365Tracing(config => config
            .WithSemanticKernel());
}

#endregion


builder.Services.AddApplicationInsightsTelemetry(options =>
{
    Console.WriteLine("Setting Application Insights connection string...");
    options.ConnectionString = builder.Configuration["ApplicationInsights:ConnectionString"];
    options.EnableAdaptiveSampling = false; // Disable adaptive sampling to capture all traces
});

builder.Logging.AddApplicationInsights();


var app = builder.Build();

var telemetryConfig = app.Services.GetRequiredService<TelemetryConfiguration>();
Console.WriteLine($"AI ConnectionString: {telemetryConfig.ConnectionString}");

var logger = app.Services.GetRequiredService<ILogger<Program>>();
logger.LogWarning("Application starting...");

// ===================================
// These are needed for Agent SDK
// ===================================
app.UseRouting();
// Enable buffering globally - this allows request body to be read multiple times
app.Use(next => context =>
{
    context.Request.EnableBuffering();
    return next(context);
});


app.MapPost("/api/messages", async (HttpRequest request, HttpResponse response, IAgentHttpAdapter adapter, IAgent agent, CancellationToken cancellationToken) =>
{
    // Comment out this line to disable request logging
    // await request.LogRequestAsync();

    request.EnableBuffering();

    using var reader = new StreamReader(request.Body, encoding: Encoding.UTF8, detectEncodingFromByteOrderMarks: false, leaveOpen: true);
    string body = await reader.ReadToEndAsync();

    // Reset stream position so ASP.NET can read it again
    request.Body.Position = 0;

    await adapter.ProcessAsync(request, response, agent, cancellationToken);
});

app.MapGet("/", () => "Hello World from HelloWorldA365Agent!");

app.MapGet("/liveness", () => "Hello World from HelloWorldA365Agent!");

app.MapGet("/readiness", () => "Hello World from HelloWorldA365Agent!");


if (!app.Environment.IsDevelopment())
{
    app.UseHsts();
}

app.Use(next => context =>
{
    context.Request.EnableBuffering();
    return next(context);
});

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// Map controllers
app.MapControllers();

app.Run();
