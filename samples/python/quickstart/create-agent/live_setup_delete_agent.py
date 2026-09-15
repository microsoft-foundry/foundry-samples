# Live-validation-only helper: deletes the agent created by quickstart-create-agent.py
# so repeated live-validation runs don't accumulate agents. Not part of the
# documented quickstart narrative.
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint"
FOUNDRY_AGENT_NAME = "your-agent-name"

project = AIProjectClient(
    endpoint=FOUNDRY_PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
project.agents.delete(FOUNDRY_AGENT_NAME)
print(f"Agent deleted (name: {FOUNDRY_AGENT_NAME})")
