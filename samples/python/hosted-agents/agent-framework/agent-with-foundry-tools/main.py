import os
from dotenv import load_dotenv
from agent_framework.azure import AzureOpenAIChatClient

from azure.ai.agentserver.agentframework import from_agent_framework, FoundryToolsChatMiddleware
from azure.identity import DefaultAzureCredential

# Load environment variables from .env file for local development
# load_dotenv()

def main():
    required_env_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
        "AZURE_AI_PROJECT_ENDPOINT",
        "AZURE_AI_PROJECT_TOOL_CONNECTION_ID",
    ]
    for env_var in required_env_vars:
        assert env_var in os.environ and os.environ[env_var], (
            f"{env_var} environment variable must be set."
        )

    tool_connection_id = os.environ["AZURE_AI_PROJECT_TOOL_CONNECTION_ID"]

    agent = AzureOpenAIChatClient(
        credential=DefaultAzureCredential(),
        middleware=FoundryToolsChatMiddleware(
            tools=[{"type": "web_search_preview"}, {"type": "mcp", "project_connection_id": tool_connection_id}]
            )).create_agent(
                name="FoundryToolAgent",
                instructions="You are a helpful assistant with access to various tools.",
        )

    from_agent_framework(agent=agent).run()

if __name__ == "__main__":
    main()
