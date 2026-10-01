// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample demonstrates how to generate a voice agent from a natural-language goal:
// the authoring service expands a use case and goal into a full, editable voice agent
// definition, which this sample then inspects and deletes.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using System.ClientModel;

// Set FOUNDRY_PROJECT_ENDPOINT in .env to a project with voice agents enabled.
string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string agentName = $"sample-generated-voice-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;

Console.WriteLine("Generating a voice agent from a goal...");
GenerateVoiceAgentRequest generateRequest = new(agentName)
{
    UseCase = "Travel information",
    Goal = "Help callers find information about public transport. Do not make bookings.",
};

ClientResult<ProjectsAgentRecord> generateResult = await agentsClient.GenerateAgentAsync(generateRequest);
ProjectsAgentRecord agent = generateResult;
Console.WriteLine($"[REST] GENERATE agent -> {(int)generateResult.GetRawResponse().Status}");
Console.WriteLine($"Generated agent: {agent.Name}");

try
{
    if (agent.GetLatestVersion().Definition is VoiceAgentDefinition generatedDefinition)
    {
        Console.WriteLine($"Generated instructions: {generatedDefinition.Instructions}");
        Console.WriteLine($"Generated model type: {generatedDefinition.ModelType}");
    }
}
finally
{
    Console.WriteLine("Deleting the generated sample agent...");
    ClientResult deleteResult = await agentsClient.DeleteAgentAsync(agentName);
    Console.WriteLine($"[REST] DELETE agent -> {(int)deleteResult.GetRawResponse().Status}");
}
