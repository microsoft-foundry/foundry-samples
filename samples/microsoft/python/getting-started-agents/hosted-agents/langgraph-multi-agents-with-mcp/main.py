import asyncio
import os
import logging

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.graph import (
    END,
    START,
    MessagesState,
    StateGraph,
)
from typing_extensions import Literal
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from azure.ai.agentserver.core.client.tools.aio import AzureAIToolClient
from azure.ai.agentserver.langgraph import ToolClient, from_langgraph

from azure.monitor.opentelemetry import configure_azure_monitor
from langchain.agents import create_agent



from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import MessagesState, END
from langgraph.types import Command


logger = logging.getLogger(__name__)

load_dotenv()

if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor(enable_live_metrics=True, logger_name="__main__")

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")

try:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    llm = init_chat_model(
        f"azure_openai:{deployment_name}",
        azure_ad_token_provider=token_provider,
    )
except Exception:
    logger.exception("Calculator Agent failed to start")
    raise


async def get_tools_from_mcp():
        # Get configuration from environment
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    tool_connection_id = os.getenv("AZURE_AI_PROJECT_TOOL_CONNECTION_ID")

    if not project_endpoint:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT environment variable is required. "
            "Set it to your Azure AI project endpoint, e.g., "
             "https://<your-account>.services.ai.azure.com/api/projects/<your-project>"
        )

    print(f"Using project endpoint: {project_endpoint}, tool connection ID: {tool_connection_id}")
    # Create Azure credentials
    credential = DefaultAzureCredential()
    tool_definitions = [
        {
            "type": "mcp",
            "project_connection_id": tool_connection_id,
        },
    ]
    # Create the AzureAIToolClient
    # This client supports both MCP tools and Azure AI Tools API
    tool_client = AzureAIToolClient(
        endpoint=project_endpoint,
        credential=credential,
        tools=tool_definitions
    )

    # Create the ToolClient
    client = ToolClient(tool_client)

    # List all available tools and convert to LangChain format
    print("Fetching tools from Azure AI Tool Client...")
    tools = await client.list_tools()
    print(f"Found {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    return tools


# Define tools
def make_system_prompt(suffix: str) -> str:
    return (
        "You are a helpful AI assistant, collaborating with other assistants."
        " Use the provided tools to progress towards answering the question."
        " If you are unable to fully answer, that's OK, another assistant with different tools "
        " will help where you left off. Execute what you can to make progress."
        " If you or any of the other assistants have the final answer or deliverable,"
        " prefix your response with FINAL ANSWER so the team knows to stop."
        f"\n{suffix}"
    )


def word_count_tool(text: str) -> int:
    """A tool that counts the number of words in a given text."""
    return len(text.split())


def get_next_node(last_message: BaseMessage, goto: str):
    if "FINAL ANSWER" in last_message.content:
        # Any agent decided the work is done
        return END
    return goto


tools = asyncio.run(get_tools_from_mcp())
# Research agent and node
research_agent = create_agent(
    llm,
    tools=tools, # TODO: use a tool
    system_prompt=make_system_prompt(
        "You can only do research. You are working with a word count agent colleague."
    ),
)


def research_node(
    state: MessagesState,
) -> Command[Literal["word_counter", END]]:
    result = research_agent.invoke(state)
    goto = get_next_node(result["messages"][-1], "word_counter")
    # wrap in a human message, as not all providers allow
    # AI message at the last position of the input messages list
    result["messages"][-1] = HumanMessage(
        content=result["messages"][-1].content, name="researcher"
    )
    return Command(
        update={
            # share internal message history of research agent with other agents
            "messages": result["messages"],
        },
        goto=goto,
    )

# word count agent and node
word_count_agent = create_agent(
    llm,
    [word_count_tool], # TODO: use a tool
    system_prompt=make_system_prompt(
        "You can only count words in a string. You are working with a researcher colleague."
    ),
)


def word_count_node(state: MessagesState) -> Command[Literal["researcher", END]]:
    result = word_count_agent.invoke(state)
    goto = get_next_node(result["messages"][-1], "researcher")
    # wrap in a human message, as not all providers allow
    # AI message at the last position of the input messages list
    result["messages"][-1] = HumanMessage(
        content=result["messages"][-1].content, name="word_counter"
    )
    return Command(
        update={
            # share internal message history of chart agent with other agents
            "messages": result["messages"],
        },
        goto=goto,
    )


# Build workflow
def build_agent() -> "StateGraph":
    workflow = StateGraph(MessagesState)
    workflow.add_node("researcher", research_node)
    workflow.add_node("word_counter", word_count_node)

    workflow.add_edge(START, "researcher")

    # Compile the agent
    return workflow.compile()


# Build workflow and run agent
if __name__ == "__main__":
    try:
        agent = build_agent()
        adapter = from_langgraph(agent)
        adapter.run()
    except Exception:
        logger.exception("Multi-Agent encountered an error while running")
        raise
