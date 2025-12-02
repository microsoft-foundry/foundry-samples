import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

load_dotenv()

project_client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

agent = project_client.agents.create_version(
    agent_name=os.environ["AZURE_AI_FOUNDRY_AGENT_NAME"],
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"],
        instructions="You are a helpful assistant that answers general questions",
    ),
)
print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")