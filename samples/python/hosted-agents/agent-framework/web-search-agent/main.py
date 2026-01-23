import os
from agent_framework import ChatAgent, HostedWebSearchTool
from agent_framework_azure_ai import AzureAIAgentClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import DefaultAzureCredential

def create_agent() -> ChatAgent:
    """Create and return a ChatAgent with Bing Grounding search tool."""
    assert "AZURE_AI_PROJECT_ENDPOINT" in os.environ, (
        "AZURE_AI_PROJECT_ENDPOINT environment variable must be set."
    )
    assert "AZURE_AI_MODEL_DEPLOYMENT_NAME" in os.environ, (
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable must be set."
    )
    assert "BING_GROUNDING_CONNECTION_ID" in os.environ, (
        "BING_GROUNDING_CONNECTION_ID environment variable must be set to use HostedWebSearchTool."
    )
    
    chat_client = AzureAIAgentClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        async_credential=DefaultAzureCredential(),
    )

    bing_search_tool = HostedWebSearchTool(
        name="Bing Grounding Search",
        description="Search the web for current information using Bing",
        connection_id=os.environ["BING_GROUNDING_CONNECTION_ID"],
    )

    agent = ChatAgent(
        chat_client=chat_client,
        name="BingSearchAgent",
        instructions=(
            "You are a helpful assistant that can search the web for current information. "
            "Use the Bing search tool to find up-to-date information and provide accurate, "
            "well-sourced answers. Always cite your sources when possible."
        ),
        tools=bing_search_tool,
    )
    return agent

if __name__ == "__main__":
    from_agent_framework(lambda _: create_agent()).run()
