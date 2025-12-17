using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;

#pragma warning disable OPENAI001

string PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT_NAME = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AIProjectClient projectClient = new(new Uri(PROJECT_ENDPOINT), new AzureCliCredential());
AgentClient agentClient = projectClient.GetAgentClient();
OpenAIClient openAIClient = agentClient.GetOpenAIClient();
OpenAIResponseClient responseClient = openAIClient.GetOpenAIResponseClient(MODEL_DEPLOYMENT_NAME);
// Optional Step: Create a conversation to use with the agent
ConversationClient conversations = agentClient.GetConversationClient();
AgentConversation conversation = conversations.CreateConversation();

ResponseCreationOptions responseCreationOptions = new();
responseCreationOptions.SetAgentReference(new AgentReference(AGENT_NAME));
responseCreationOptions.SetConversationReference(conversation.Id);
// Chat with the agent to answer questions
OpenAIResponse response = responseClient.CreateResponse(
    [ResponseItem.CreateUserMessageItem("What is the size of France in square miles?")],
    responseCreationOptions);

Console.WriteLine(response.GetOutputText());
// Optional Step: Ask a follow-up question in the same conversation
response = responseClient.CreateResponse(
    [ResponseItem.CreateUserMessageItem("And what is the capital city?")],
    responseCreationOptions);

Console.WriteLine(response.GetOutputText());