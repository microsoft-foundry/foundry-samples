from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

# Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint"
FOUNDRY_AGENT_NAME = "your_agent_name"

# Create project client to call Foundry API
project = AIProjectClient(
    endpoint=FOUNDRY_PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)

# Create an agent with a model and instructions
agent = project.agents.create_version(
    agent_name=FOUNDRY_AGENT_NAME,
    definition=PromptAgentDefinition(
        model="gpt-5-mini",  # supports all Foundry direct models
        instructions="You are a helpful assistant that answers general questions",
    ),
)
print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")