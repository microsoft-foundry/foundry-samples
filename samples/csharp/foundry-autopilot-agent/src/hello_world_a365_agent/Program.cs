using Azure.Identity;
using HelloWorldA365.AgentLogic;
using HelloWorldA365.AgentLogic.ResponsesApi;
using HelloWorldA365.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;

using System.Text;

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

// Map the blueprint client id (already provided via FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID)
// onto the ServiceConnection client id the Agent SDK expects.
var blueprintClientId = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID");
if (!string.IsNullOrEmpty(blueprintClientId))
{
    builder.Configuration["Connections:ServiceConnection:Settings:ClientId"] = blueprintClientId;
    Console.WriteLine("ServiceConnection ClientId set from FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID.");
}
else
{
    Console.WriteLine("FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID not set. ServiceConnection ClientId not configured.");
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

builder.Services.AddSingleton<AgentRequestCorrelationMiddleware>();
builder.Services.AddSingleton<Microsoft.Agents.Builder.IMiddleware[]>(serviceProvider =>
[
    serviceProvider.GetRequiredService<AgentRequestCorrelationMiddleware>()
]);
builder.Services.AddSingleton<ResponsesApiAgentLogicServiceFactory>();

// Register auth helper
builder.Services.AddSingleton<AgentTokenHelper>();

// Register OpenAPI for external agents
builder.Services.AddOpenApi();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddLogging();

AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);

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
if (string.IsNullOrWhiteSpace(
        builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"] ??
        builder.Configuration["ApplicationInsights:ConnectionString"]))
{
    logger.LogWarning(
        "Application Insights is not configured. Set APPLICATIONINSIGHTS_CONNECTION_STRING to enable telemetry.");
}

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


app.MapPost("/activity/messages", async (HttpRequest request, HttpResponse response, IAgentHttpAdapter adapter, IAgent agent, CancellationToken cancellationToken) =>
{
    AgentRequestCorrelation.CaptureCurrentRequest(request);

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
