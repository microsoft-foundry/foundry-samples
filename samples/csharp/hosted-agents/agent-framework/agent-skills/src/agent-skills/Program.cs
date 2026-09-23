// Copyright (c) Microsoft. All rights reserved.

/*
 * Agent Skills - Agent Framework Responses agent for C#
 *
 * Hosted agent that loads its behavioral guidelines from Foundry Skills at startup.
 * Skills are authored as SKILL.md files, uploaded to Foundry via the Skills REST API,
 * and downloaded by the agent on boot so guideline updates ship without code changes.
 *
 * The agent uses AgentSkillsProvider from the Agent Framework, which implements the
 * progressive-disclosure pattern from the Agent Skills specification
 * (https://agentskills.io/):
 *   1. Advertise - skill names and descriptions are injected into the system prompt.
 *   2. Load      - the model calls load_skill to retrieve the full SKILL.md body
 *                  on demand.
 *
 * IMPORTANT: In production, skill provisioning (uploading SKILL.md files to Foundry)
 * is an external concern - it is NOT the hosted agent's responsibility. The
 * provisioning helper below is included for sample convenience only, so the sample is
 * self-contained and runnable without a separate setup step. A real deployment
 * pipeline would provision skills separately (for example via a CI/CD step, a CLI
 * script, or a management portal). Enable it with PROVISION_SAMPLE_SKILLS=true.
 *
 * Required environment variables:
 *   FOUNDRY_PROJECT_ENDPOINT       - Foundry project endpoint (auto-injected in hosted
 *                                    containers, set by `azd ai agent run` locally).
 *   AZURE_AI_MODEL_DEPLOYMENT_NAME - Model deployment name (declared in
 *                                    agent.manifest.yaml).
 *   SKILL_NAMES                    - Comma-separated list of Foundry skill names to
 *                                    download at startup (for example
 *                                    "support-style,escalation-policy"). If unset or
 *                                    empty the agent still starts and responds, just
 *                                    without any skills wired in.
 *
 * Optional:
 *   PROVISION_SAMPLE_SKILLS        - Set to "true" on a first run to upload this
 *                                    sample's SKILL.md files to Foundry. Not for
 *                                    production use.
 */

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.AI.AgentServer.Core;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development).
Env.NoClobber().TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT environment variable is not set."));

string deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set.");

// SKILL_NAMES is optional. CI environments that don't pass sample-specific manifest
// parameters will leave it unset (or as the literal "{{SKILL_NAMES}}" placeholder).
// In that case the agent still starts up and responds, just without any skills wired
// in - the container must reach /readiness so the platform doesn't kill it with HTTP 424.
string[] requestedSkills = ParseSkillNames(ResolvedEnv("SKILL_NAMES"));
if (requestedSkills.Length == 0)
{
    Console.WriteLine("[agent-skills] SKILL_NAMES is empty; no skills will be loaded into the agent.");
}

// Validate skill names to prevent path traversal when constructing the download directory.
foreach (string name in requestedSkills)
{
    if (name.Contains('.') || name.Contains('/') || name.Contains('\\') || Path.IsPathRooted(name))
    {
        throw new InvalidOperationException(
            $"Invalid skill name '{name}': skill names must not contain path separators or dots.");
    }
}

var isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
{
    // Managed identity is available in Foundry containers, but probing the IMDS endpoint locally can
    // consume the entire skill-bootstrap timeout before the credential reaches the Azure CLI login.
    ExcludeManagedIdentityCredential = !isHosted,
});
var projectClient = new AIProjectClient(projectEndpoint, credential);

AgentSkillsProvider? skillsProvider = null;
if (requestedSkills.Length > 0)
{
    // Hard ceiling on the skill-bootstrap network round-trips so a slow or hung Foundry
    // Skills API call can't keep /readiness from returning 200 past the hosted-agent
    // runtime's session-readiness timeout.
    // Hosted skill-package downloads can take longer than local calls during a cold session. Keep
    // the ceiling below the platform readiness limit while allowing normal in-region startup jitter.
    using var bootstrapCts = new CancellationTokenSource(TimeSpan.FromSeconds(110));

    // Skills CRUD currently requires the Foundry-Features: Skills=V1Preview opt-in header.
    // The Azure.AI.Projects SDK does not auto-inject this on the Skills sub-client, so we
    // register a pipeline policy on a dedicated AgentAdministrationClient that we use for
    // every call into ProjectAgentSkills (provisioning, GetSkill, DownloadSkill, ...).
    var adminOptions = new AgentAdministrationClientOptions();
    adminOptions.AddPolicy(new FoundryFeaturesPolicy("Skills=V1Preview"), PipelinePosition.PerCall);
    var adminClient = new AgentAdministrationClient(projectEndpoint, credential, adminOptions);
    ProjectAgentSkills skillsClient = adminClient.GetAgentSkills();

    // Provision sample skills (sample convenience only, NOT a production pattern).
    // In production, skills are provisioned externally (for example via CI/CD or a management script).
    // This helper ensures the sample's SKILL.md files exist in Foundry so the sample is runnable
    // out of the box without a separate setup step. Set PROVISION_SAMPLE_SKILLS=true to enable.
    string sourceSkillsDir = Path.Combine(AppContext.BaseDirectory, "skills");
    bool provisionEnabled = string.Equals(
        Environment.GetEnvironmentVariable("PROVISION_SAMPLE_SKILLS"), "true", StringComparison.OrdinalIgnoreCase);
    if (provisionEnabled && Directory.Exists(sourceSkillsDir))
    {
        await EnsureSkillsProvisionedAsync(skillsClient, sourceSkillsDir, requestedSkills, bootstrapCts.Token);
    }

    // Hosted application files may be read-only. Keep downloaded skills in the writable
    // per-session home while reading packaged source skills from the application directory.
    string downloadedSkillsRoot = isHosted
        ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)
        : AppContext.BaseDirectory;
    string downloadedSkillsDir = Path.Combine(downloadedSkillsRoot, "downloaded_skills");
    await DownloadSkillsAsync(skillsClient, requestedSkills, downloadedSkillsDir, bootstrapCts.Token);

    // AgentSkillsProvider implements progressive disclosure: skill names and descriptions
    // are advertised in the system prompt (around 100 tokens per skill), and the full
    // SKILL.md body is loaded on demand when the model calls the load_skill tool.
    skillsProvider = new AgentSkillsProvider(downloadedSkillsDir);
}

AIAgent agent = projectClient
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "agent-skills",
        Description = "Customer-support agent that loads tone and escalation policy from Foundry Skills.",
        ChatOptions = new ChatOptions
        {
            ModelId = deployment,
            Instructions = "You are a customer-support assistant for Contoso Outdoors.",
        },
        AIContextProviders = skillsProvider is null ? [] : [skillsProvider],
    })
    .AsBuilder()
    .UseToolApproval(new ToolApprovalAgentOptions
    {
        // These sample skills contain instructions only. Auto-approve their read-only discovery and
        // load operations so progressive disclosure stays transparent to the user.
        AutoApprovalRules = [AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule],
    })
    .Build();

var builder = AgentHost.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.RegisterProtocol("responses", endpoints => endpoints.MapFoundryResponses());

var app = builder.Build();
app.Run();

// Downloads each named skill from Foundry into a separate subdirectory under the target directory.
// GetSkillContentAsync downloads the skill package and unzips it into the destination directory.
static async Task DownloadSkillsAsync(
    ProjectAgentSkills skillsClient, string[] skillNames, string targetDir, CancellationToken cancellationToken)
{
    if (Directory.Exists(targetDir))
    {
        Directory.Delete(targetDir, recursive: true);
    }

    Directory.CreateDirectory(targetDir);

    foreach (string name in skillNames)
    {
        Console.WriteLine($"Downloading skill '{name}' from Foundry...");

        string skillDir = Path.Combine(targetDir, name);
        Directory.CreateDirectory(skillDir);

        await skillsClient.GetSkillContentAsync(name, skillDir, cancellationToken);

        if (!File.Exists(Path.Combine(skillDir, "SKILL.md")))
        {
            throw new InvalidOperationException(
                $"Downloaded skill '{name}' did not contain a SKILL.md at the root.");
        }
    }
}

// Ensures each requested skill is provisioned in Foundry. For each skill name, checks
// whether the skill exists and uploads it from the local source directory if it does not.
//
// This is a sample convenience helper - in production, skill provisioning is an external
// concern handled outside the hosted agent.
static async Task EnsureSkillsProvisionedAsync(
    ProjectAgentSkills skillsClient, string sourceDir, string[] skillNames, CancellationToken cancellationToken)
{
    foreach (string name in skillNames)
    {
        string skillPath = Path.Combine(sourceDir, name);
        if (!Directory.Exists(skillPath) || !File.Exists(Path.Combine(skillPath, "SKILL.md")))
        {
            continue; // No local source for this skill - skip provisioning.
        }

        try
        {
            await skillsClient.GetSkillAsync(name, cancellationToken);
            Console.WriteLine($"Skill '{name}' already exists in Foundry.");
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            Console.WriteLine($"Provisioning skill '{name}' from {skillPath}...");
            AgentsSkill imported = (await skillsClient.CreateSkillVersionFromFilesAsync(name, skillPath, cancellationToken)).Value;
            Console.WriteLine($"  Imported skill '{imported.Name}' (id={imported.Id}, version={imported.LatestVersion}).");
        }
    }
}

// Reads an environment variable and treats un-substituted template placeholders
// ("${VAR}" or "{{VAR}}") as empty. Hosted-agent runtimes that template-substitute
// agent.yaml / agent.manifest.yaml may leave the literal placeholder text when the
// referenced parameter is undefined at deploy time (for example CI smoke runs that
// don't set sample-specific manifest parameters). Treating that case as "unset" keeps
// the container able to pass /readiness and respond, just without the optional capability.
static string ResolvedEnv(string name)
{
    string value = Environment.GetEnvironmentVariable(name)?.Trim() ?? string.Empty;
    if ((value.StartsWith("${", StringComparison.Ordinal) && value.EndsWith('}'))
        || (value.StartsWith("{{", StringComparison.Ordinal) && value.EndsWith("}}", StringComparison.Ordinal)))
    {
        return string.Empty;
    }
    return value;
}

static string[] ParseSkillNames(string value) =>
    value.Length == 0
        ? []
        : value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

// Pipeline policy that adds the Foundry-Features opt-in header on every request.
// Required for Skills (and other preview surfaces) until the SDK injects it automatically.
internal sealed class FoundryFeaturesPolicy(string feature) : PipelinePolicy
{
    private const string FeatureHeader = "Foundry-Features";

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        message.Request.Headers.Add(FeatureHeader, feature);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        message.Request.Headers.Add(FeatureHeader, feature);
        return ProcessNextAsync(message, pipeline, currentIndex);
    }
}
