// Copyright (c) Microsoft. All rights reserved.

/*
 * Harness Research — Agent Framework harness agent for C#
 *
 * Hosted agent that uses AsHarnessAgent to plan and execute research tasks. The harness
 * comes pre-configured with TodoProvider, AgentModeProvider (plan/execute), FileMemoryProvider,
 * tool approval, and web search. This sample adds research instructions, a WebBrowsingTool,
 * and a loop evaluator that re-invokes the agent in "execute" mode until every todo completes.
 *
 * Hosted via AgentHost.CreateBuilder() from Azure.AI.AgentServer.Core with AddFoundryResponses
 * from Microsoft.Agents.AI.Foundry.Hosting, exposing the Foundry Responses protocol on port 8088.
 *
 * Required environment variables:
 *   FOUNDRY_PROJECT_ENDPOINT        — Foundry project endpoint (auto-injected in hosted containers)
 *   AZURE_AI_MODEL_DEPLOYMENT_NAME  — Model deployment name (declared in azure.yaml)
 */

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using SampleApp;

// Load .env file if present (for local development).
Env.NoClobber().TraversePath().Load();

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// When hosted in a Foundry container the app directory (and the process's initial working
// directory) is read-only, so anything the harness writes relative to the current directory —
// file memory ("agent-files"), skill discovery, mode/todo state — would fail. Switch the current
// directory to the container's home directory ($HOME), which Foundry maps per hosted session and
// persists across turns and idle periods, so file memory survives the whole conversation and is
// isolated per session. Locally the app directory is writable and left as-is.
var isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
if (isHosted)
{
    Directory.SetCurrentDirectory(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
}
var fileMemoryDir = isHosted
    ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "agent-files")
    : Path.Combine(AppContext.BaseDirectory, "agent-files");

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.Research";

// Create a HarnessAgent with the Harness providers (TodoProvider and AgentModeProvider)
// and research-focused instructions including the mandatory planning workflow.
var instructions =
    """
    ## Research Assistant Instructions

    You are a research assistant. When given a research topic, research it thoroughly using web search and web browsing.
    Use your knowledge to form good search queries and hypotheses, but always verify claims with the tools available to you rather than relying on memory alone.

    ### Research quality

    Consult multiple sources when possible and cross-reference key claims.
    When sources disagree, note the discrepancy and explain which source you consider more reliable and why.
    If a web page fails to load or a search returns irrelevant results, try alternative search queries or sources before moving on.
    Track your sources — you will need them when presenting results.

    ### Presenting results

    When presenting your final findings:
    - Use Markdown formatting for clarity.
    - Use clear sections with headings for each major topic or sub-question.
    - Cite your sources inline (e.g., "According to [source name](URL), ...").
    - End with a brief summary of key takeaways.
    - In addition to returning the results to the user, save the final research report to file memory so it survives compaction and can be referenced later.
    """;

// Build the model client before the harness. Harness persists chat history after every service call
// so its autonomous research loop retains the exact tool-call chain across iterations and turns.
IChatClient chatClient = new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })  // Enable retries to improve resiliency.
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName)
    .AsIChatClient();

// Create the agent using AsHarnessAgent, which pre-configures function invocation,
// per-service-call chat history persistence, in-loop compaction, TodoProvider, AgentModeProvider,
// FileMemoryProvider, ToolApproval, WebSearch, AgentSkillsProvider, and OpenTelemetry.
// Only custom instructions, a WebBrowsingTool, and FileAccess opt-out are needed.
AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    MaxContextWindowTokens = MaxContextWindowTokens,
    MaxOutputTokens = MaxOutputTokens,
    Name = "ResearchAgent",
    Description = "A research assistant that plans and executes research tasks.",
    OpenTelemetrySourceName = TracingSourceName,        // Use our custom source name so spans are captured by the TracerProvider above.
    FileMemoryStore = new FileSystemAgentFileStore(     // Configure the file memory provider to store files in a local folder called "agent-files".
            fileMemoryDir),
    // The built in ModeProvider has two default modes: "plan" and "execute".
    // Adding a loop evaluator so that in "execute" mode, the harness keeps re-invoking itself until every todo item is complete.
    LoopEvaluators =
        [
            new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] }),
        ],
    LoopAgentOptions = new LoopAgentOptions { MaxIterations = 10 }, // Safety cap on the number of autonomous passes per turn.
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,                       // Bind the Foundry deployment to the request, matching the pattern used by all hosted samples.
        Instructions = instructions,
        Tools =
            [
                new WebBrowsingTool(                        // Add a local web browsing tool that converts html to markdown.
                    new WebBrowsingToolOptions { AllowPublicNetworks = true }),
            ],
        MaxOutputTokens = MaxOutputTokens,              // Set a high token limit for long research tasks with many tool calls and long outputs.
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});

// Host the harness agent behind the Foundry Responses protocol so it can be run by
// `azd ai agent run` and inspected via F5 in the Agent Inspector. AgentHost.CreateBuilder
// wires up automatic port, health, and telemetry configuration.
var builder = AgentHost.CreateBuilder(args);
// Harness keeps history in AgentSession.StateBag. Its per-service-call wrapper sets a local-history
// ConversationId, which the 1.22 host mistakes for service-stored output and rejects by default.
// This opt-in bypasses that check, but leaves the model client's storage setting unchanged, so it
// may create a second stored record. Remove it when hosting recognizes the local-history marker.
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.AllowStoredOutputEnabled = true);
// Harness agents carry per-session state, so the hosting layer requires a session isolation key.
// Register a local-dev fallback so requests without the platform's x-agent-user-id header (dotnet
// run / azd ai agent run / Inspector) still resolve a user id instead of failing with a 500.
builder.Services.AddSingleton<HostedSessionIsolationKeyProvider, LocalDevSessionIsolationKeyProvider>();
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();
