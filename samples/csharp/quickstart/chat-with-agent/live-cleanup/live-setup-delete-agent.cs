// Live-validation-only helper: deletes the agent created by quickstart-chat-with-agent.cs
// so repeated live-validation runs don't accumulate agent versions. Not part of the
// documented quickstart narrative.
using Azure.Identity;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
var foundryProjectEndpoint = "your_project_endpoint";
var foundryAgentName = "your-agent-name";

// Create project client to call Foundry API
AIProjectClient projectClient = new(
    endpoint: new Uri(foundryProjectEndpoint),
    tokenProvider: new DefaultAzureCredential());

projectClient.AgentAdministrationClient.DeleteAgent(foundryAgentName);
Console.WriteLine($"Agent deleted (name: {foundryAgentName})");
