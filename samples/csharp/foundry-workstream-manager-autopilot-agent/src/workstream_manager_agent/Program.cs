using Azure.Identity;
using WorkstreamManager.AgentLogic;
using WorkstreamManager.AgentLogic.ResponsesApi;
using WorkstreamManager.Models;
using WorkstreamManager.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;

using System.Text;
using Microsoft.Agents.A365.Observability.Runtime;
using Microsoft.ApplicationInsights.Extensibility;

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

builder.Services.AddSingleton<ResponsesApiAgentLogicServiceFactory>();

// Register auth helper
builder.Services.AddSingleton<AgentTokenHelper>();

// Register work item tracking service
builder.Services.AddSingleton<WorkItemService>();

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
    builder.AddA365Tracing(config => { });
}

#endregion


// Stamp Foundry hosted-agent identifiers (name, version, instance, session) onto all
// telemetry so it is sliceable per agent version and per instance. Safe no-op when no
// Application Insights connection string is configured (monitoring disabled).
builder.Services.AddSingleton<ITelemetryInitializer, WorkstreamManager.Services.FoundryInstanceTelemetryInitializer>();

builder.Services.AddApplicationInsightsTelemetry(options =>
{
    var connectionString =
        builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"] ??
        builder.Configuration["ApplicationInsights:ConnectionString"];

    if (!string.IsNullOrWhiteSpace(connectionString))
    {
        options.ConnectionString = connectionString;
    }

    options.EnableAdaptiveSampling = false; // Disable adaptive sampling to capture all traces
});

builder.Logging.AddApplicationInsights();


var app = builder.Build();

var logger = app.Services.GetRequiredService<ILogger<Program>>();
logger.LogInformation("Application starting...");

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


app.MapPost("/activity/messages", async (HttpRequest request, HttpResponse response, IAgentHttpAdapter adapter, IAgent agent, CancellationToken cancellationToken) =>
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

app.MapGet("/", () => "Hello World from WorkstreamManagerAgent!");

app.MapGet("/liveness", () => "Hello World from WorkstreamManagerAgent!");

app.MapGet("/readiness", () => "Hello World from WorkstreamManagerAgent!");


if (!app.Environment.IsDevelopment())
{
    app.UseHsts();
}

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
