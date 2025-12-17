using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using OpenAI.Responses;

#pragma warning disable OPENAI001

string projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AIProjectClient projectClient = new(new Uri(projectEndpoint), new AzureCliCredential());

// Optional Step: Create a conversation to use with the agent
ProjectConversation conversation = projectClient.OpenAI.Conversations.CreateProjectConversation();

ProjectResponsesClient responsesClient = projectClient.OpenAI.GetProjectResponsesClientForAgent(
    defaultAgent: agentName,
    defaultConversationId: conversation.Id);

// Chat with the agent to answer questions
ResponseResult response = responsesClient.CreateResponse("What is the size of France in square miles?");
Console.WriteLine(response.GetOutputText());

// Optional Step: Ask a follow-up question in the same conversation
response = responsesClient.CreateResponse("And what is the capital city?");
Console.WriteLine(response.GetOutputText());