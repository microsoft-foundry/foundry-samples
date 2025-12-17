using Azure.AI.Projects;
using Azure.Identity;

string PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT_NAME = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AgentClient agentClient = new(new Uri(PROJECT_ENDPOINT), new AzureCliCredential());

AgentDefinition agentDefinition = new PromptAgentDefinition(MODEL_DEPLOYMENT_NAME)
{
    Instructions = "You are a helpful assistant that answers general questions",
};

AgentVersion newAgentVersion = agentClient.CreateAgentVersion(
    AGENT_NAME,
    options: new(agentDefinition));

var agentVersions = agentClient.GetAgentVersions(AGENT_NAME);
foreach (AgentVersion oneAgentVersion in agentVersions)
{
    Console.WriteLine($"Agent: {oneAgentVersion.Id}, Name: {oneAgentVersion.Name}, Version: {oneAgentVersion.Version}");
}

