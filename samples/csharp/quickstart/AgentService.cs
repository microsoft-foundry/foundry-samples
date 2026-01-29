// This sample combines each step of creating and running agents and conversations into a single example.
// In practice, you would typically separate these steps into different applications.
//
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using OpenAI.Responses;

#pragma warning disable OPENAI001

string RAW_PROJECT_ENDPOINT = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
?? throw new InvalidOperationException("Missing environment variable 'PROJECT_ENDPOINT'");
string MODEL_DEPLOYMENT = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
?? throw new InvalidOperationException("Missing environment variable 'MODEL_DEPLOYMENT_NAME'");
string AGENT_NAME = Environment.GetEnvironmentVariable("AGENT_NAME")
?? throw new InvalidOperationException("Missing environment variable 'AGENT_NAME'");

AIProjectClient projectClient = new AIProjectClient(new Uri(RAW_PROJECT_ENDPOINT), new DefaultAzureCredential());

//
// Create an agent version for a new prompt agent
//

AgentDefinition agentDefinition = new PromptAgentDefinition(MODEL_DEPLOYMENT)
{
    Instructions = "You are a foo bar agent. In EVERY response you give, ALWAYS include both `foo` and `bar` strings somewhere in the response.",
};
AgentVersion newAgentVersion = await projectClient.Agents.CreateAgentVersionAsync(AGENT_NAME, options: new(agentDefinition));

//
// Create a conversation to maintain state between calls
//

ProjectConversationCreationOptions conversationOptions = new()
{
    Items = { ResponseItem.CreateSystemMessageItem("Your preferred genre of story today is: horror.") },
    Metadata = { ["foo"] = "bar" },
};
ProjectConversation conversation = await projectClient.OpenAI.Conversations.CreateProjectConversationAsync(conversationOptions);

//
// Add items to an existing conversation to supplement the interaction state
//
string EXISTING_CONVERSATION_ID = conversation.Id;

_ = await projectClient.OpenAI.Conversations.CreateProjectConversationItemsAsync(
    EXISTING_CONVERSATION_ID,
    [ResponseItem.CreateSystemMessageItem("Story theme to use: department of licensing.")]);

//
// Use the agent and conversation in a response
//

ProjectResponsesClient responseClient = projectClient.OpenAI.GetProjectResponsesClientForAgent(newAgentVersion, EXISTING_CONVERSATION_ID);
List<ResponseItem> items = [ResponseItem.CreateUserMessageItem(inputTextContent: "Tell me a one-line story.")] ;
ResponseResult response = await responseClient.CreateResponseAsync(items);

Console.WriteLine(response.GetOutputText());
