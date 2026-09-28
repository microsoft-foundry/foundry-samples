using Azure.Identity;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.AI.Extensions.OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
var foundryProjectEndpoint = "your_project_endpoint";
var foundryAgentName = "your-agent-name";

// Create project client to call Foundry API
AIProjectClient projectClient = new(
    endpoint: new Uri(foundryProjectEndpoint),
    tokenProvider: new DefaultAzureCredential());

// Create the agent (or a new version, if it already exists)
ProjectsAgentDefinition agentDefinition = new DeclarativeAgentDefinition("gpt-5-mini") // supports all Foundry direct models
{
    Instructions = "You are a helpful assistant that answers general questions",
};
projectClient.AgentAdministrationClient.CreateAgentVersion(
    foundryAgentName,
    options: new(agentDefinition));

// Create a conversation for multi-turn chat
ProjectConversation conversation = projectClient.ProjectOpenAIClient.GetProjectConversationsClient().CreateProjectConversation();

// Chat with the agent to answer questions
ProjectResponsesClient responsesClient = projectClient.ProjectOpenAIClient.GetProjectResponsesClientForAgent(
    defaultAgent: foundryAgentName,
    defaultConversationId: conversation.Id);
ResponseResult response = responsesClient.CreateResponse("What is the size of France in square miles?");
Console.WriteLine(response.GetOutputText());

// Ask a follow-up question in the same conversation
response = responsesClient.CreateResponse("And what is the capital city?");
Console.WriteLine(response.GetOutputText());