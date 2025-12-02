#:package Azure.AI.Agents@2.*-*
#:package Azure.Identity@1.*
#:property PublishAot=false
#:property NoWarn=OPENAI001

using Azure.AI.Agents;
using Azure.Identity;

string PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT_NAME = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AZURE_AI_FOUNDRY_AGENT_NAME'");

AgentClient agentClient = new(new Uri(PROJECT_ENDPOINT), new AzureCliCredential(),);

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

