// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample demonstrates how to configure and retrieve a voice agent definition:
// create a self-deployed voice agent with a spoken greeting and conversation storage
// disabled, then read it back and delete it.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using System.ClientModel;

// Set these values in .env. The deployment must support realtime or cascaded voice.
string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL")
    ?? throw new InvalidOperationException("Set FOUNDRY_VOICE_AGENT_MODEL before running this sample.");
string agentName = $"sample-voice-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;

Console.WriteLine("Creating a voice agent version...");
VoiceAgentDefinition definition = new()
{
    ModelType = VoiceModelType.SelfDeployed,
    Model = deploymentName,
    Instructions = "Help callers find public transport information. Keep answers short.",
    Greeting = new VoiceAgentTemplateGreetingConfig("Hello! How can I help with your journey?"),
    Store = false,
};
definition.OutputModalities.Add(VoiceOutputModality.Audio);

ClientResult<ProjectsAgentVersion> createResult =
    await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(definition));
ProjectsAgentVersion agentVersion = createResult;
Console.WriteLine($"[REST] CREATE version -> {(int)createResult.GetRawResponse().Status}");
Console.WriteLine($"Created voice agent: {agentVersion.Name}, version: {agentVersion.Version}");

try
{
    ClientResult<ProjectsAgentVersion> getResult =
        await agentsClient.GetAgentVersionAsync(agentName, agentVersion.Version);
    Console.WriteLine($"[REST] GET version -> {(int)getResult.GetRawResponse().Status}");

    if (getResult.Value.Definition is VoiceAgentDefinition retrievedDefinition)
    {
        if (retrievedDefinition.Greeting is VoiceAgentTemplateGreetingConfig template)
        {
            Console.WriteLine($"Voice greeting: {template.Text}");
        }
        Console.WriteLine($"Conversation storage enabled: {retrievedDefinition.Store}");
    }
    // This sample configures the agent; it does not open a microphone or voice session.
    // See realtime-audio and realtime-text-and-tools for streaming a live session.
}
finally
{
    Console.WriteLine("Deleting the sample agent...");
    ClientResult deleteResult = await agentsClient.DeleteAgentAsync(agentName);
    Console.WriteLine($"[REST] DELETE agent -> {(int)deleteResult.GetRawResponse().Status}");
}
