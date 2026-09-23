// Copyright (c) Microsoft. All rights reserved.

/*
 * Harness Data Processing — Agent Framework harness agent for C#
 *
 * Hosted agent that uses AsHarnessAgent with the FileAccessProvider to read, analyze, and
 * process a folder of CSV data files. File access is opt-in via HarnessAgentOptions.FileAccessStore,
 * pointed at the sample's working/ folder. Tool approval is required for file operations, with a
 * read-only auto-approval rule so reads run without prompting while writes/deletes still require approval.
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

// When hosted in a Foundry container the app directory is read-only, so the file-access working
// folder must be a writable location. Use the container's home directory ($HOME), which Foundry
// maps per hosted session and persists across turns and idle periods, so each session gets an
// isolated file store that survives the whole conversation. Seed the sample data (working/, e.g.
// sales.csv) only when it is missing, so a user's edits and generated outputs are never clobbered.
// Locally the app directory is writable and used as-is.
var isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
var seedWorkingDir = Path.Combine(AppContext.BaseDirectory, "working");
string workingDir;
if (isHosted)
{
    // The app directory (and initial working directory) is read-only when hosted. Switch the current
    // directory to the writable session home so the harness's default cwd-relative writes (session
    // store, checkpoints) succeed, and seed the file-access working folder there.
    var writableRoot = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    Directory.SetCurrentDirectory(writableRoot);

    workingDir = Path.Combine(writableRoot, "working");
    foreach (var file in Directory.GetFiles(seedWorkingDir, "*", SearchOption.AllDirectories))
    {
        var dest = Path.Combine(workingDir, Path.GetRelativePath(seedWorkingDir, file));
        if (File.Exists(dest))
        {
            continue;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        File.Copy(file, dest);
    }
}
else
{
    workingDir = seedWorkingDir;
}

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

var instructions =
    """
    You are a data analyst assistant. You have access to a folder of data files via the file_access_* tools.

    ## Getting started
    - Start by listing available files with file_access_ls to see what data is available.
    - Read the files to understand their structure and contents.

    ## Working with data
    - When asked to analyze data, read the relevant files first, then perform the analysis.
    - Show your analysis clearly with tables, summaries, and key insights.
    - When calculations are needed, work through them step by step and show your reasoning.

    ## Writing output
    - When asked to produce output files (e.g., reports, summaries, filtered data), use file_access_write to write them.
    - Use appropriate file formats: CSV for tabular data, Markdown for reports.
    - Confirm what you wrote and where.

    ## Important
    - Never modify or delete the original input data files unless explicitly asked to do so.
    - If asked about data you haven't read yet, read it first before answering.
    - Always explain your reasoning and thought process as you work through tasks.
    - Always explain what you learned and what you are going to do next between tool calls, so the user can follow along with your thought process.
    """;

// Build the model client before the harness. Harness persists chat history after every service call
// so approval continuations retain the exact function-call chain across turns.
IChatClient chatClient = new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName)
    .AsIChatClient();

// Create the agent using AsHarnessAgent. FileAccessStore points the FileAccessProvider at the
// sample's working/ folder (copied to the output directory) so it works regardless of cwd.
// Tool approval is required for file operations; a read-only auto-approval rule skips prompts
// for reads while writes/deletes still require explicit approval. Unused providers are disabled.
AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    MaxContextWindowTokens = MaxContextWindowTokens,
    MaxOutputTokens = MaxOutputTokens,
    Name = "DataAnalyst",
    Description = "A data analyst assistant that reads, analyzes, and processes data files.",
    FileAccessStore = new FileSystemAgentFileStore(workingDir),
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        // The HarnessAgent's FileAccessProvider requires approval for all file access operations.
        // This read-only auto-approval rule skips prompts for reads; writes/deletes still require approval.
        AutoApprovalRules = [FileAccessProvider.ReadOnlyToolsAutoApprovalRule]
    },
    DisableTodoProvider = true,
    DisableAgentModeProvider = true,
    DisableFileMemory = true,
    DisableWebSearch = true,
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,                       // Bind the Foundry deployment to the request, matching the pattern used by all hosted samples.
        Instructions = instructions,
        MaxOutputTokens = MaxOutputTokens,
    },
});

// Host the harness agent behind the Foundry Responses protocol so it can be run by
// `azd ai agent run` and inspected via F5 in the Agent Inspector. AgentHost.CreateBuilder
// wires up automatic port, health, and telemetry configuration.
var builder = AgentHost.CreateBuilder(args);
// Harness keeps history in AgentSession.StateBag. Its per-service-call wrapper sets a local-history
// ConversationId, which the 1.22 host mistakes for service-stored output and rejects by default.
// This opt-in bypasses that check, but leaves the model client's storage setting unchanged, so it
// may create a second stored record. Approval-response binding remains enabled.
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
