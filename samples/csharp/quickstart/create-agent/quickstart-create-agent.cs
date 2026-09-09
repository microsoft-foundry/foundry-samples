using Azure.Identity;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.AI.Extensions.OpenAI;

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
var foundryProjectEndpoint = "your_project_endpoint";
var foundryAgentName = "your_agent_name";

// Create project client to call Foundry API
AIProjectClient projectClient = new(
    endpoint: new Uri(foundryProjectEndpoint),
    tokenProvider: new DefaultAzureCredential());

// Create an agent with a model and instructions
ProjectsAgentDefinition agentDefinition = new DeclarativeAgentDefinition("gpt-5-mini") // supports all Foundry direct models
{
    Instructions = "You are a helpful assistant that answers general questions",
};

ProjectsAgentVersion agent = projectClient.AgentAdministrationClient.CreateAgentVersion(
    foundryAgentName,
    options: new(agentDefinition));
Console.WriteLine($"Agent created (id: {agent.Id}, name: {agent.Name}, version: {agent.Version})");
