import asyncio
import os
from agent_framework import ChatAgent, HostedMCPTool
from agent_framework_azure_ai import AzureAIAgentClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import DefaultAzureCredential

async def handle_approvals_with_thread(query: str, agent: "AgentProtocol", thread: "AgentThread"):
    """Here we let the thread deal with the previous responses, and we just rerun with the approval."""
    from agent_framework import ChatMessage

    result = await agent.run(query, thread=thread, store=True)
    while len(result.user_input_requests) > 0:
        new_input: list[Any] = []
        for user_input_needed in result.user_input_requests:
            print(
                f"User Input Request for function from {agent.name}: {user_input_needed.function_call.name}"
                f" with arguments: {user_input_needed.function_call.arguments}"
            )
            # user_approval = input("Approve function call? (y/n): ")
            new_input.append(
                ChatMessage(
                    role="user",
                    contents=[user_input_needed.create_response(True)],
                )
            )
        result = await agent.run(new_input, thread=thread, store=True)
    return result


def get_agent() -> ChatAgent:
    """Create and return a ChatAgent with Bing Grounding search tool."""
    assert "AZURE_AI_PROJECT_ENDPOINT" in os.environ, (
        "AZURE_AI_PROJECT_ENDPOINT environment variable must be set."
    )
    assert "AZURE_AI_MODEL_DEPLOYMENT_NAME" in os.environ, (
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable must be set."
    )

    chat_client = AzureAIAgentClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        async_credential=DefaultAzureCredential(),
    )

    # Create ChatAgent with the Bing search tool
    agent = chat_client.create_agent(
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        ),
    )
    return agent

async def test_agent():
    agent = get_agent()
    thread = agent.get_new_thread()
    response = await handle_approvals_with_thread("How do I create an Azure Function in Python?", agent, thread)
    print("Agent response:", response.text)

if __name__ == "__main__":
    # asyncio.run(test_agent())
    from_agent_framework(get_agent()).run()
