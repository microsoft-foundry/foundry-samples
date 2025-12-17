using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;

string projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AIProjectClient projectClient = new(new Uri(projectEndpoint), new AzureCliCredential());

AgentDefinition agentDefinition = new PromptAgentDefinition(modelDeploymentName)
{
    Instructions = "You are a helpful assistant that answers general questions",
};

AgentVersion newAgentVersion = projectClient.Agents.CreateAgentVersion(
    agentName,
    options: new(agentDefinition));

List<AgentVersion> agentVersions = projectClient.Agents.GetAgentVersions(agentName);
foreach (AgentVersion agentVersion in agentVersions)
{
    Console.WriteLine($"Agent: {agentVersion.Id}, Name: {agentVersion.Name}, Version: {agentVersion.Version}");
}

