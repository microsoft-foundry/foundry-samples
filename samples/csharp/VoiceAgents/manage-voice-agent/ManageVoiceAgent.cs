// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample walks through the voice agent management lifecycle: create, read, update by
// creating a new version, list, version history, enable/disable, and delete. See
// generate-voice-agent for generating a voice agent definition from a natural-language goal
// instead of authoring one directly, and configure-voice-agent for a closer look at a single
// version's fields.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using System.ClientModel;

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string modelName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL")
    ?? throw new InvalidOperationException("Set FOUNDRY_VOICE_AGENT_MODEL before running this sample.");
string agentName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME")?.Trim()
    ?? $"voice-manage-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;

Console.WriteLine("Creating a voice agent...");
VoiceAgentDefinition firstDefinition = new()
{
    ModelType = VoiceModelType.SelfDeployed,
    Model = modelName,
    Instructions = "Help callers find public transport information. Keep answers short.",
    Store = false,
};
firstDefinition.OutputModalities.Add(VoiceOutputModality.Audio);

ClientResult<ProjectsAgentVersion> createResult =
    await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(firstDefinition));
ProjectsAgentVersion firstVersion = createResult;
Console.WriteLine($"[REST] CREATE version {firstVersion.Version} -> {(int)createResult.GetRawResponse().Status}");
Console.WriteLine($"Created \"{agentName}\", version: {firstVersion.Version}");

try
{
    Console.WriteLine("\nReading the agent back...");
    ClientResult<ProjectsAgentRecord> getResult = await agentsClient.GetAgentAsync(agentName);
    ProjectsAgentRecord agent = getResult;
    Console.WriteLine($"[REST] GET agent -> {(int)getResult.GetRawResponse().Status}");
    if (agent.GetLatestVersion().Definition is VoiceAgentDefinition currentDefinition)
    {
        Console.WriteLine($"Instructions: {currentDefinition.Instructions}");
    }

    Console.WriteLine("\nCreating a second version with updated instructions...");
    VoiceAgentDefinition secondDefinition = new()
    {
        ModelType = VoiceModelType.SelfDeployed,
        Model = modelName,
        Instructions = "Help callers find public transport information. Always mention delays.",
        Store = false,
    };
    secondDefinition.OutputModalities.Add(VoiceOutputModality.Audio);
    ClientResult<ProjectsAgentVersion> secondResult =
        await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(secondDefinition));
    ProjectsAgentVersion secondVersion = secondResult;
    Console.WriteLine($"[REST] CREATE version {secondVersion.Version} -> {(int)secondResult.GetRawResponse().Status}");

    Console.WriteLine("\nCreating a third version with a greeting...");
    VoiceAgentDefinition thirdDefinition = new()
    {
        ModelType = VoiceModelType.SelfDeployed,
        Model = modelName,
        Instructions = "Help callers find public transport information. Always mention delays.",
        Greeting = new VoiceAgentTemplateGreetingConfig("Hi there! Where are you headed today?"),
        Store = false,
    };
    thirdDefinition.OutputModalities.Add(VoiceOutputModality.Audio);
    ClientResult<ProjectsAgentVersion> thirdResult =
        await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(thirdDefinition));
    ProjectsAgentVersion thirdVersion = thirdResult;
    Console.WriteLine($"[REST] CREATE version {thirdVersion.Version} -> {(int)thirdResult.GetRawResponse().Status}");

    Console.WriteLine("\nListing every version of this agent...");
    await foreach (ProjectsAgentVersion version in agentsClient.GetAgentVersionsAsync(agentName))
    {
        Console.WriteLine($"  - version {version.Version}");
    }

    Console.WriteLine($"\nFetching version {thirdVersion.Version} directly...");
    ClientResult<ProjectsAgentVersion> fetchedVersionResult =
        await agentsClient.GetAgentVersionAsync(agentName, thirdVersion.Version);
    Console.WriteLine($"[REST] GET version {thirdVersion.Version} -> {(int)fetchedVersionResult.GetRawResponse().Status}");
    if (fetchedVersionResult.Value.Definition is VoiceAgentDefinition fetchedDefinition
        && fetchedDefinition.Greeting is VoiceAgentTemplateGreetingConfig greeting)
    {
        Console.WriteLine($"Greeting on that version: {greeting.Text}");
    }

    Console.WriteLine("\nListing voice agents in this project...");
    int voiceAgentCount = 0;
    bool foundOurs = false;
    await foreach (ProjectsAgentRecord listed in agentsClient.GetAgentsAsync(kind: ProjectsAgentKind.Voice))
    {
        voiceAgentCount++;
        foundOurs |= listed.Name == agentName;
    }
    Console.WriteLine($"Found {voiceAgentCount} voice agent(s); ours is {(foundOurs ? "" : "not ")}among them.");

    Console.WriteLine("\nDisabling the agent...");
    ClientResult disableResult = await agentsClient.DisableAgentAsync(agentName);
    Console.WriteLine($"[REST] DISABLE agent -> {(int)disableResult.GetRawResponse().Status}");
    ProjectsAgentRecord afterDisable = await agentsClient.GetAgentAsync(agentName);
    Console.WriteLine($"State: {afterDisable.State}");

    Console.WriteLine("\nRe-enabling the agent...");
    ClientResult enableResult = await agentsClient.EnableAgentAsync(agentName);
    Console.WriteLine($"[REST] ENABLE agent -> {(int)enableResult.GetRawResponse().Status}");
    ProjectsAgentRecord afterEnable = await agentsClient.GetAgentAsync(agentName);
    Console.WriteLine($"State: {afterEnable.State}");

    Console.WriteLine($"\nDeleting version {firstVersion.Version} (keeping the latest version)...");
    ClientResult deleteVersionResult = await agentsClient.DeleteAgentVersionAsync(agentName, firstVersion.Version);
    Console.WriteLine($"[REST] DELETE version {firstVersion.Version} -> {(int)deleteVersionResult.GetRawResponse().Status}");
}
finally
{
    Console.WriteLine("\nDeleting the agent...");
    ClientResult deleteAgentResult = await agentsClient.DeleteAgentAsync(agentName);
    Console.WriteLine($"[REST] DELETE agent -> {(int)deleteAgentResult.GetRawResponse().Status}");
}
