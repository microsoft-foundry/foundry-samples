from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint"
FOUNDRY_AGENT_NAME = "your_agent_name"

# Create project and openai clients to call Foundry API
project = AIProjectClient(
    endpoint=FOUNDRY_PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
# Get an OpenAI client pre-bound to the specified agent
openai = project.get_openai_client(agent_name=FOUNDRY_AGENT_NAME)

# Create a conversation for multi-turn chat
conversation = openai.conversations.create()

# Chat with the agent to answer questions
response = openai.responses.create(
    conversation=conversation.id,
    input="What is the size of France in square miles?",
)
print(response.output_text)

# Ask a follow-up question in the same conversation
response = openai.responses.create(
    conversation=conversation.id,
    input="And what is the capital city?",
)
print(response.output_text)
