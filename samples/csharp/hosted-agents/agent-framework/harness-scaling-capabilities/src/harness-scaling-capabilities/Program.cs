// Copyright (c) Microsoft. All rights reserved.

// "Scaling its capabilities" — Post 3 of the "Build your own claw and agent harness with Microsoft
// Agent Framework" series, hosted through the Foundry Responses protocol.
// See: https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-the-claw-or-harness-capabilities/.
//
// Ported from the Claw_Step03_ScalingCapabilities console sample in the Microsoft Agent Framework.
// The original runs the personal-finance harness agent in an interactive console (HarnessConsole);
// this project keeps the same instructions, tools, skills, background agent, confined shell, CodeAct
// provider, and approval policy while replacing the console host with the native Foundry Responses
// host (AgentHost.CreateBuilder + AddFoundryResponses + MapFoundryResponses).
//
// It preserves Post 2's personal finance assistant plus Post 3's four "scaling" capabilities:
//   1. Skills            — discoverable SKILL.md files under skills/ (valuation, risk-scoring), plus
//                          optional Foundry Toolbox MCP skills (FOUNDRY_TOOLBOX_MCP_SERVER_URL).
//   2. Shell             — a sandboxed shell confined to the trade-confirmation vault.
//   3. CodeAct           — a sandboxed Python interpreter on Hyperlight (needs hardware virtualization).
//   4. Background agents — a per-ticker research sub-agent fanned out concurrently.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.Identity;
using ClawSample;
using DotNetEnv;
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;

// Load environment variables from a .env file if present (for local development).
Env.NoClobber().TraversePath().Load();

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set.");

// When hosted in a Foundry container the app directory is read-only, so file writes (file access,
// the shell's reorganization, and file memory) must target a writable location. Locally the app
// directory is writable and used as-is.
var isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));

// The two folders the claw works in: the working folder (portfolio.csv, reports) and the
// trade-confirmation "vault" inside it that the shell will reorganize. Skills are read-only, so
// they stay in the (read-only) app directory even when hosted.
var seedWorkingDir = Path.Combine(AppContext.BaseDirectory, "working");
var skillsDir = Path.Combine(AppContext.BaseDirectory, "skills");

string workingDir;
if (isHosted)
{
    // Use the container's home directory ($HOME), which Foundry maps per hosted session and persists
    // across turns and idle periods, so the working data (and the confirmations the shell reorganizes)
    // is isolated per session and survives the whole conversation. Seed the sample data only when it
    // is missing, so the user's reports and reorganized confirmations are never clobbered on restart.
    workingDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "working");
    CopyDirectory(seedWorkingDir, workingDir);
}
else
{
    workingDir = seedWorkingDir;
}
var vaultDir = Path.Combine(workingDir, "confirmations");

// Seed the destination per file, copying only files that are missing so a user's edits and
// reorganized confirmations are never overwritten if the directory already exists.
static void CopyDirectory(string source, string destination)
{
    foreach (var file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
    {
        var dest = Path.Combine(destination, Path.GetRelativePath(source, file));
        if (File.Exists(dest))
        {
            continue;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        File.Copy(file, dest);
    }
}

// <instructions>
var instructions =
    """
    ## Personal Finance Assistant Instructions

    You are a personal finance and investing assistant. You help the user understand their
    portfolio and watchlist, value individual stocks, gauge portfolio risk, research the market,
    and keep their records tidy.

    ### Working style

    - The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
      before answering questions about their portfolio, and never modify it unless asked.
    - You have skills for valuation and risk-scoring. When a question matches a skill, load it and
      follow its instructions (read its references, run its scripts) rather than guessing.
    - When asked to research several tickers, delegate each one to the background research agent so
      they run concurrently, then summarize the findings together.
    - The user's trade confirmations accumulate in the confirmations folder. When asked to tidy or
      reorganize them, use the run_shell tool: inspect the folder first, then copy (do not move) the
      files into an organized/ subfolder using a year/month layout, renaming each copy to
      YYYY-MM-DD_TICKER_BUY|SELL.txt. Leave the original flat files untouched so the source data stays
      intact. If organized/ already exists from a previous run, clear it first so the result is clean.
      Explain your plan before running commands that change anything.
    - To buy or sell, use the place_trade tool. This takes a real action, so the user will be asked
      to approve it before it runs — explain what you are about to do first.

    ### Important

    You provide information and analysis only — you are not a licensed financial advisor and you
    must not present your output as personalized investment advice. Remind the user to do their own
    research before making decisions.
    """;
// </instructions>

// <create_client>
// Construct an IChatClient backed by a Microsoft Foundry project (see Post 1 for details).
// DefaultAzureCredential resolves managed identity when hosted (FOUNDRY_HOSTING_ENVIRONMENT is set in
// Foundry containers) and the Azure CLI login (`az login`) locally. Locally we exclude the managed
// identity probe so the credential doesn't stall on the IMDS endpoint before falling back to the CLI.
var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
{
    ExcludeManagedIdentityCredential = !isHosted,
});
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    credential,
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

IChatClient chatClient = projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName);
// </create_client>

// <skills>
// Build our own skills provider so we can point it at this sample's skills/ folder and, when
// configured, fold in centrally-managed Foundry skills from a Foundry Toolbox MCP endpoint.
var skillsBuilder = new AgentSkillsProviderBuilder()
    // File-based skills: valuation and risk-scoring. SubprocessScriptRunner runs their Python scripts.
    .UseFileSkills([skillsDir], scriptRunner: new SubprocessScriptRunner().RunAsync);

// Foundry skills (opt-in): discovered live from a Foundry Toolbox MCP endpoint, so they can be
// managed and updated centrally without changing or redeploying this agent.
HttpClient? toolboxHttpClient = null;
ModelContextProtocol.Client.McpClient? toolboxMcpClient = null;
var toolboxUrl = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_MCP_SERVER_URL");
if (!string.IsNullOrWhiteSpace(toolboxUrl))
{
    (toolboxMcpClient, toolboxHttpClient) = await FoundrySkills.ConnectAsync(toolboxUrl, credential);
    skillsBuilder.UseMcpSkills(toolboxMcpClient);
    Console.WriteLine("Foundry skills enabled (Toolbox MCP).");
}
else
{
    Console.WriteLine("Foundry skills disabled. Set FOUNDRY_TOOLBOX_MCP_SERVER_URL to enable them.");
}

AgentSkillsProvider skillsProvider = skillsBuilder.Build();
// </skills>

// <background>
// Background agents: a lean, web-search-only research sub-agent. Passing it to the harness exposes
// the background_agents_* tools so the claw can start several research tasks concurrently and
// collect the results.
AIAgent researchAgent = ResearchAgent.Create(chatClient);
// </background>

// <shell>
// A sandboxed shell, confined to the trade-confirmation vault. ConfineWorkingDirectory re-anchors
// every command to the vault, and the deny-list policy pre-filters obviously destructive commands.
// (Patterns are a UX guardrail, not a security boundary — for hard isolation use DockerShellExecutor.)
await using var shell = new LocalShellExecutor(new LocalShellExecutorOptions
{
    WorkingDirectory = vaultDir,
    ConfineWorkingDirectory = true,
    Policy = new ShellPolicy(denyList:
    [
        @"\brm\s+-rf\b",
        @"\bsudo\b",
        @":\(\)\s*\{",          // fork-bomb shape
        @"\bmkfs\b",
        @">\s*/dev/sd",
    ]),
    Timeout = TimeSpan.FromSeconds(15),
});
// </shell>

// <codeact>
// CodeAct: a sandboxed Python interpreter the model can write and run code in to crunch numbers.
// It runs on Hyperlight (a micro-VM, so it needs hardware virtualization). The guest module path is
// resolved automatically from the Hyperlight.HyperlightSandbox.Guest.Python NuGet package.
// Hyperlight requires hardware virtualization on the host; a hosted Foundry container without nested
// virtualization cannot start it. Treat CodeAct as optional: if initialization fails, the agent runs
// without the CodeAct capability (skills, shell, and background research still work). See the
// README's "CodeAct and hosting" note.
HyperlightCodeActProvider? codeAct = null;
try
{
    codeAct = new HyperlightCodeActProvider(HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));
}
catch (Exception ex)
{
    Console.Error.WriteLine($"CodeAct is unavailable (Hyperlight could not start, likely no hardware virtualization): {ex.Message}. Continuing without CodeAct.");
}
// </codeact>

// <create_agent>
// Turn the chat client into a HarnessAgent with Post 2's file access and approvals plus the
// "scaling" capabilities: skills (our own provider), background agents, a confined shell, and
// (when available) CodeAct.
List<AIContextProvider> contextProviders = codeAct is not null
    ? [skillsProvider, codeAct, new ShellEnvironmentProvider(shell)]
    : [skillsProvider, new ShellEnvironmentProvider(shell)];

AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    Name = "harness-scaling-capabilities",
    Description = "A personal-finance harness agent with file skills, a confined shell, CodeAct, and fan-out background research.",
    // File access: portfolio.csv, reports, and the confirmations vault all live under working/.
    FileAccessStore = new FileSystemAgentFileStore(workingDir),
    // File memory must live in a writable location; when hosted, workingDir is the per-session home
    // directory (the app directory is read-only in Foundry containers). Root it under agent-file-memory.
    FileMemoryStore = new FileSystemAgentFileStore(Path.Combine(workingDir, "agent-file-memory")),
    // We supply our own skills provider (file + optional Foundry), so turn off the default one.
    DisableAgentSkillsProvider = true,
    // Fan-out research is delegated to this background agent.
    BackgroundAgents = [researchAgent],
    // Keep file reads and skill discovery automatic. Script execution, trades, and shell commands
    // require explicit approval even under the headless Responses host.
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        AutoApprovalRules =
        [
            FileAccessProvider.ReadOnlyToolsAutoApprovalRule,
            AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule,
        ],
    },
    // Start in "execute" mode for quick lookups and actions.
    AgentModeProviderOptions = new AgentModeProviderOptions { DefaultMode = "execute" },
    // Our skills provider, optional CodeAct provider, and shell environment details.
    AIContextProviders = contextProviders,
    ChatOptions = new ChatOptions
    {
        Instructions = instructions,
        Tools =
        [
            StockTools.CreateGetStockPriceTool(),
            TradingTools.CreatePlaceTradeTool(),
            // Shell execution remains approval-gated even though read-only file and skill tools auto-approve.
            shell.AsAIFunction(requireApproval: true),
        ],
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});
// </create_agent>

// <run>
// Host the harness agent through the Foundry Responses protocol. AgentHost.CreateBuilder() handles
// the HTTP contract, port binding (8088 or PORT), health probes, SSE lifecycle, and telemetry. The
// Responses host owns conversation history and translates/persists the harness approval requests
// (place_trade, run_shell, file writes) into resumable Responses approval items.
var builder = AgentHost.CreateBuilder(args);
// Harness keeps history in AgentSession.StateBag. Its per-service-call wrapper sets a local-history
// ConversationId, which the 1.22 host mistakes for service-stored output and rejects by default.
// This opt-in bypasses that check, but leaves the model client's storage setting unchanged, so it
// may create a second stored record. Approval-response binding remains enabled.
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.AllowStoredOutputEnabled = true);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();

try
{
    app.Run();
}
finally
{
    codeAct?.Dispose();

    if (toolboxMcpClient is not null)
    {
        await toolboxMcpClient.DisposeAsync().ConfigureAwait(false);
    }

    toolboxHttpClient?.Dispose();
}
// </run>
